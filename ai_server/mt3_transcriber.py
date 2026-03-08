"""
mt3_transcriber.py — Standalone YourMT3+ wrapper for Renoise AI Worker

Loads the YourMT3+ MoE multi-track model and transcribes audio files to MIDI notes.
Returns structured note data compatible with the Renoise AI worker pipeline.
"""
import sys
import os

# Add YourMT3 to Python path
sys.path.insert(0, '/home/juanquy/dev/YourMT3')
sys.path.insert(0, '/home/juanquy/dev/YourMT3/amt/src')

import torch
import torchaudio
import mido
import math
import soundfile as sf

# These imports come from YourMT3's amt/src/
from model.init_train import initialize_trainer, update_config
from utils.task_manager import TaskManager
from config.vocabulary import drum_vocab_presets
from utils.utils import str2bool, Timer, write_model_output_as_midi
from utils.audio import slice_padded_array
from utils.note2event import mix_notes
from utils.event2note import merge_zipped_note_events_and_ties_to_notes
from model.ymt3 import YourMT3

import argparse

_model = None
_device = None

def load_mt3_model(device_str="cuda:0"):
    """Load the YourMT3+ MoE multi-track model onto the specified CPU."""
    global _model, _device
    if _model is not None:
        return _model

    # Use CUDA but we will manage memory aggressively during inference
    _device = torch.device(device_str if torch.cuda.is_available() else "cpu")
    
    # YourMT3+ expects checkpoints relative to its own directory
    original_cwd = os.getcwd()
    os.chdir('/home/juanquy/dev/YourMT3')
    
    # YPTF.MoE+Multi (noPS) — best accuracy model
    checkpoint = "mc13_256_g4_all_v7_mt3f_sqr_rms_moe_wf4_n8k2_silu_rope_rp_b36_nops@last.ckpt"
    precision = '16'
    project = '2024'
    
    args = [checkpoint, '-p', project, '-tk', 'mc13_full_plus_256', '-dec', 'multi-t5',
            '-nl', '26', '-enc', 'perceiver-tf', '-sqr', '1', '-ff', 'moe',
            '-wf', '4', '-nmoe', '8', '-kmoe', '2', '-act', 'silu', '-epe', 'rope',
            '-rp', '1', '-ac', 'spec', '-hop', '300', '-atc', '1', '-pr', precision]

    # Load model checkpoint follows YourMT3's model_helper.py logic
    parser = argparse.ArgumentParser(description="YourMT3")
    parser.add_argument('exp_id', type=str)
    parser.add_argument('-p', '--project', type=str, default='ymt3')
    parser.add_argument('-ac', '--audio-codec', type=str, default=None)
    parser.add_argument('-hop', '--hop-length', type=int, default=None)
    parser.add_argument('-nmel', '--n-mels', type=int, default=None)
    parser.add_argument('-if', '--input-frames', type=int, default=None)
    parser.add_argument('-sqr', '--sca-use-query-residual', type=str2bool, default=None)
    parser.add_argument('-enc', '--encoder-type', type=str, default=None)
    parser.add_argument('-dec', '--decoder-type', type=str, default=None)
    parser.add_argument('-preenc', '--pre-encoder-type', type=str, default='default')
    parser.add_argument('-predec', '--pre-decoder-type', type=str, default='default')
    parser.add_argument('-cout', '--conv-out-channels', type=int, default=None)
    parser.add_argument('-tenc', '--task-cond-encoder', type=str2bool, default=True)
    parser.add_argument('-tdec', '--task-cond-decoder', type=str2bool, default=True)
    parser.add_argument('-df', '--d-feat', type=int, default=None)
    parser.add_argument('-pt', '--pretrained', type=str2bool, default=False)
    parser.add_argument('-b', '--base-name', type=str, default="google/t5-v1_1-small")
    parser.add_argument('-epe', '--encoder-position-encoding-type', type=str, default='default')
    parser.add_argument('-dpe', '--decoder-position-encoding-type', type=str, default='default')
    parser.add_argument('-twe', '--tie-word-embedding', type=str2bool, default=None)
    parser.add_argument('-el', '--event-length', type=int, default=None)
    parser.add_argument('-dl', '--d-latent', type=int, default=None)
    parser.add_argument('-nl', '--num-latents', type=int, default=None)
    parser.add_argument('-dpm', '--perceiver-tf-d-model', type=int, default=None)
    parser.add_argument('-npb', '--num-perceiver-tf-blocks', type=int, default=None)
    parser.add_argument('-npl', '--num-perceiver-tf-local-transformers-per-block', type=int, default=None)
    parser.add_argument('-npt', '--num-perceiver-tf-temporal-transformers-per-block', type=int, default=None)
    parser.add_argument('-atc', '--attention-to-channel', type=str2bool, default=None)
    parser.add_argument('-ln', '--layer-norm-type', type=str, default=None)
    parser.add_argument('-ff', '--ff-layer-type', type=str, default=None)
    parser.add_argument('-wf', '--ff-widening-factor', type=int, default=None)
    parser.add_argument('-nmoe', '--moe-num-experts', type=int, default=None)
    parser.add_argument('-kmoe', '--moe-topk', type=int, default=None)
    parser.add_argument('-act', '--hidden-act', type=str, default=None)
    parser.add_argument('-rt', '--rotary-type', type=str, default=None)
    parser.add_argument('-rk', '--rope-apply-to-keys', type=str2bool, default=None)
    parser.add_argument('-rp', '--rope-partial-pe', type=str2bool, default=None)
    parser.add_argument('-dff', '--decoder-ff-layer-type', type=str, default=None)
    parser.add_argument('-dwf', '--decoder-ff-widening-factor', type=int, default=None)
    parser.add_argument('-tk', '--task', type=str, default='mt3_full_plus')
    parser.add_argument('-epv', '--eval-program-vocab', type=str, default=None)
    parser.add_argument('-edv', '--eval-drum-vocab', type=str, default=None)
    parser.add_argument('-etk', '--eval-subtask-key', type=str, default='default')
    parser.add_argument('-t', '--onset-tolerance', type=float, default=0.05)
    parser.add_argument('-os', '--test-octave-shift', type=str2bool, default=False)
    parser.add_argument('-w', '--write-model-output', type=str2bool, default=True)
    parser.add_argument('-pr', '--precision', type=str, default="bf16-mixed")
    parser.add_argument('-st', '--strategy', type=str, default='auto')
    parser.add_argument('-n', '--num-nodes', type=int, default=1)
    parser.add_argument('-g', '--num-gpus', type=str, default='auto')
    parser.add_argument('-wb', '--wandb-mode', type=str, default="disabled")
    parser.add_argument('-debug', '--debug-mode', type=str2bool, default=False)
    parser.add_argument('-tps', '--test-pitch-shift', type=int, default=None)
    
    parsed_args = parser.parse_args(args)
    
    if torch.__version__ >= "1.13":
        torch.set_float32_matmul_precision("high")
    parsed_args.epochs = None

    _, _, dir_info, shared_cfg = initialize_trainer(parsed_args, stage='test')
    shared_cfg, audio_cfg, model_cfg = update_config(parsed_args, shared_cfg, stage='test')

    tm = TaskManager(task_name=parsed_args.task,
                     max_shift_steps=int(shared_cfg["TOKENIZER"]["max_shift_steps"]),
                     debug_mode=parsed_args.debug_mode)

    model = YourMT3(
        audio_cfg=audio_cfg,
        model_cfg=model_cfg,
        shared_cfg=shared_cfg,
        optimizer=None,
        task_manager=tm,
        eval_subtask_key=parsed_args.eval_subtask_key,
        write_output_dir=dir_info["lightning_dir"] if parsed_args.write_model_output else None
    ).to("cpu")
    
    checkpoint_data = torch.load(dir_info["last_ckpt_path"], map_location="cpu", weights_only=False)
    state_dict = checkpoint_data['state_dict']
    new_state_dict = {k: v for k, v in state_dict.items() if 'pitchshift' not in k}
    model.load_state_dict(new_state_dict, strict=False)
    
    _model = model.eval().to(_device)
    os.chdir(original_cwd)  # Restore CWD for worker.py
    print(f"YourMT3+ loaded on {_device}")
    return _model


def transcribe_audio_to_notes(filepath):
    """
    Transcribe an audio file to structured note data compatible with Renoise AI worker.
    
    Returns: dict mapping instrument_name -> list of {start, duration, note, velocity}
    """
    global _model, _device
    if _model is None:
        load_mt3_model()

    # Use absolute path for the audio file before changing CWD
    filepath = os.path.abspath(filepath)
    
    # YourMT3 needs its directory as CWD for model output
    original_cwd = os.getcwd()
    os.chdir('/home/juanquy/dev/YourMT3')

    try:
        # Load and preprocess audio using soundfile to avoid torchaudio.load torchcodec crash
        audio_np, sr = sf.read(filepath, dtype='float32')
        if len(audio_np.shape) == 1:
            audio_np = audio_np.reshape(-1, 1)
        audio = torch.from_numpy(audio_np).transpose(0, 1) # -> [channels, samples]
        
        audio = torch.mean(audio, dim=0).unsqueeze(0) # -> mono [1, samples]
        
        if sr != _model.audio_cfg['sample_rate']:
            audio = torchaudio.functional.resample(audio, sr, _model.audio_cfg['sample_rate'])
            
        audio_segments = slice_padded_array(audio, _model.audio_cfg['input_frames'], _model.audio_cfg['input_frames'])
        audio_segments = torch.from_numpy(audio_segments.astype('float32')).to(_device).unsqueeze(1)

        # Calculate the number of items and handle slicing the full track
        import math
        n_items = audio_segments.shape[0]
        start_secs_file = [_model.audio_cfg['input_frames'] * i / _model.audio_cfg['sample_rate'] for i in range(n_items)]
        
        # Determine optimal batch sizes to prevent OOM on large songs
        # Aggressively reduce batch size to 1 for 12GB GPUs to prevent freeze
        batch_size = 1
        pred_token_arr = []
        for i in range(0, n_items, batch_size):
            # Aggressive VRAM clearing before each segment
            torch.cuda.empty_cache()
            
            batch_segments = audio_segments[i:i+batch_size].to(_device)
            # Use inference mode to strictly disable gradient buffering
            with torch.inference_mode():
                batch_tokens, _ = _model.inference_file(bsz=batch_size, audio_segments=batch_segments)
            # extend list of predictions
            pred_token_arr.extend(batch_tokens)
            
            # Delete local variables to free memory explicitly
            del batch_segments
            del batch_tokens
            torch.cuda.empty_cache()

        # Post-process: decode tokens to notes per channel
        num_channels = _model.task_manager.num_decoding_channels
        
        pred_notes_in_file = []
        for ch in range(num_channels):
            pred_token_arr_ch = [arr[:, ch, :] for arr in pred_token_arr]
            zipped_note_events_and_tie, _, _ = _model.task_manager.detokenize_list_batches(
                pred_token_arr_ch, start_secs_file, return_events=True)
            pred_notes_ch, _ = merge_zipped_note_events_and_ties_to_notes(zipped_note_events_and_tie)
            pred_notes_in_file.append(pred_notes_ch)
        
        pred_notes = mix_notes(pred_notes_in_file)

        # Write MIDI file for parsing
        track_name = os.path.splitext(os.path.basename(filepath))[0]
        write_model_output_as_midi(pred_notes, './', track_name, _model.midi_output_inverse_vocab)
        midi_path = os.path.join('./model_output/', track_name + '.mid')
        
        if not os.path.exists(midi_path):
            print(f"Warning: MIDI file not created at {midi_path}")
            return {}

        # Parse the MIDI file into per-instrument note dicts
        return parse_midi_to_notes(midi_path)
    finally:
        os.chdir(original_cwd)


def parse_midi_to_notes(midi_path):
    """
    Parse a multi-track MIDI file into per-instrument note data.
    
    Returns: dict mapping instrument_category -> list of {start, duration, note, velocity}
    """
    import math
    mid = mido.MidiFile(midi_path)
    
    # MIDI program -> instrument category mapping for Renoise tracks
    INSTRUMENT_MAP = {
        # Bass instruments (program 32-39)
        range(32, 40): "bass",
        # Piano/Keys (program 0-7)
        range(0, 8): "piano",
        # Guitar (program 24-31)
        range(24, 32): "guitar",
        # Strings/Ensemble (program 40-55)
        range(40, 56): "other",
        # Brass/Wind (program 56-79)
        range(56, 80): "other",
        # Synth Lead/Pad (program 80-103)
        range(80, 104): "other",
        # Drums (channel 9/10)
        "drums": "drums",
    }
    
    def get_category(program, channel):
        if channel == 9:  # MIDI drum channel
            return "drums"
        for prog_range, category in INSTRUMENT_MAP.items():
            if isinstance(prog_range, range) and program in prog_range:
                return category
        return "other"
    
    result = {}
    
    # Track current program per channel (defaults to 0 / Grand Piano)
    channel_programs = {i: 0 for i in range(16)}
    active_notes = {}  # (channel, note) -> (start_time, velocity)
    time_sec = 0.0
    
    # Iterate through all messages chronologically across all tracks.
    # mido's default iterator provides msg.time in seconds!
    for msg in mid:
        time_sec += msg.time
        
        if msg.type == 'program_change':
            channel_programs[msg.channel] = msg.program
        elif msg.type == 'note_on' and msg.velocity > 0:
            key = (msg.channel, msg.note)
            active_notes[key] = (time_sec, msg.velocity)
        elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
            key = (msg.channel, msg.note)
            if key in active_notes:
                start_time, velocity = active_notes.pop(key)
                duration = time_sec - start_time
                
                # Enforce minimum duration for Renoise notes
                if duration < 0.01:
                    duration = 0.05
                
                program = channel_programs.get(msg.channel, 0)
                category = get_category(program, msg.channel)
                
                if category not in result:
                    result[category] = []
                    
                # Sanitize values
                start_val = float(start_time)
                dur_val = float(duration)
                if math.isnan(start_val) or math.isinf(start_val):
                    start_val = 0.0
                if math.isnan(dur_val) or math.isinf(dur_val):
                    dur_val = 0.1
                
                result[category].append({
                    "start": start_val,
                    "duration": dur_val,
                    "note": int(msg.note),
                    "velocity": int(velocity)
                })
    
    return result


if __name__ == "__main__":
    # Test transcription
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        print(f"Transcribing: {filepath}")
        load_mt3_model()
        notes = transcribe_audio_to_notes(filepath)
        for instrument, note_list in notes.items():
            print(f"  {instrument}: {len(note_list)} notes")
    else:
        print("Usage: python mt3_transcriber.py <audio_file>")
