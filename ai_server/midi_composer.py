import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
import mido
import os
import io
import re
import json
from peft import PeftModel
from transformers import BitsAndBytesConfig

class MIDIComposer:
    def __init__(self, model_id="slseanwu/MIDI-LLM_Llama-3.2-1B"):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.lora_weights = "./renoise_midi_model_lora"
        
        print(f"MIDIComposer: Initializing {model_id} on {self.device}...")
        
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        
        # 8-bit Quantization to fit in VRAM along with LoRA
        bnb_config = BitsAndBytesConfig(
            load_in_8bit=True
        )
        
        print(f"MIDIComposer: Loading base model...")
        base_model = AutoModelForCausalLM.from_pretrained(
            model_id, 
            quantization_config=bnb_config,
            device_map="auto"
        )
        
        if os.path.exists(self.lora_weights):
            print(f"MIDIComposer: Applying EXPERT Renoise LoRA weights from {self.lora_weights}...")
            self.model = PeftModel.from_pretrained(base_model, self.lora_weights)
            print("MIDIComposer: Expert Musical Model Ready.")
        else:
            print("MIDIComposer: No LoRA weights found. Using base MIDI model.")
            self.model = base_model
        
        self.model.eval()
        print("MIDIComposer: Initialization complete.")

    def generate_midi_sequence(self, prompt, max_new_tokens=1024):
        """
        Generates musical tokens based on the prompt.
        Special prompt format expected by MIDI-LLM: 
        'PIECE_START NOTE_ON...'
        """
        # We must closely match the exact schema that train_midi.py used.
        system_prompt = "You are a world-class composer. Please compose some music according to the following description: "
        fake_metadata = "A Renoise tracker song titled 'AI Generation' playing at 128 BPM with LPB 4. Features instruments like synthesizers. "
        
        # We force 'PIECE_START NOTE_ON ' so LLaMA has no choice but to start predicting track digits.
        full_prompt = f"{system_prompt}{fake_metadata}Style: {prompt} PIECE_START NOTE_ON "
            
        inputs = self.tokenizer(full_prompt, return_tensors="pt").to(self.device)
        
        with torch.inference_mode():
            outputs = self.model.generate(
                **inputs, 
                max_new_tokens=max_new_tokens,
                do_sample=True,
                temperature=0.2, # Very low temperature explicitly preserves the rigid tracking syntax
                top_p=0.90,
                repetition_penalty=1.0  # CRITICAL: Do not penalize repeated tokens like TIME 120
            )
        
        # skip special tokens to get clean musical events
        decoded = self.tokenizer.decode(outputs[0], skip_special_tokens=False)
        return decoded

    def tokens_to_renoise_json(self, token_string, bpm=135, lpb=4):
        """
        Parses MIDI-LLM tokens into Renoise 'commands' JSON.
        Format: NOTE_ON 0 60 TIME 10 NOTE_OFF 0 60
        
        Renoise Logic: 
        Lines per tick depends on TPL (usually 12) or we just map time to lines.
        MIDI-LLM time tokens are typically cumulative ticks (usually 480 per beat).
        """
        commands = []
        
        # Regex to find tokens like NOTE_ON track pitch or TIME ticks
        event_pattern = re.compile(r'(NOTE_ON|NOTE_OFF|TIME|CONTROL_CHANGE)\s+([-]?\d+)(?:\s+([-]?\d+))?')
        
        current_tick = 0
        TICKS_PER_BEAT = 480 # Standard for most MIDI-LLMs
        lines_per_beat = lpb
        ticks_per_line = TICKS_PER_BEAT / lines_per_beat
        
        active_tracks = set()
        
        # Find all tokens
        matches = event_pattern.findall(token_string)
        
        for event_type, val1, val2 in matches:
            if event_type == "TIME":
                # Some models use deltas, some use cumulative. MIDI-LLM usually uses increments.
                current_tick += int(val1)
            
            elif event_type == "NOTE_ON":
                if not val2:
                    continue  # Safely skip malformed tokens
                
                track_id = int(val1)
                pitch = int(val2)
                
                # Convert MIDI pitch to Renoise String
                note_str = self.midi_to_renoise_note(pitch)
                
                # Convert Tick to Renoise Line
                line_idx = int(current_tick / ticks_per_line)
                
                commands.append({
                    "type": "set_note",
                    "track": track_id,
                    "line": line_idx,
                    "note": note_str,
                    "volume": "7F", # Default
                    "instrument": track_id
                })
                active_tracks.add(track_id)
                
            elif event_type == "note-off":
                track_id = int(val1)
                line_idx = int(current_tick / ticks_per_line)
                
                commands.append({
                    "type": "note_off",
                    "track": track_id,
                    "line": line_idx
                })

        # Ensure tracks exist if they are referenced
        header_commands = []
        for trk_id in sorted(list(active_tracks)):
            header_commands.append({"type": "add_track", "track": trk_id, "name": f"AI Part {trk_id}"})
        
        return header_commands + commands

    def midi_to_renoise_note(self, midi_pitch):
        """Converts MIDI pitch (60) to Renoise format (C-4)"""
        notes = ["C-", "C#", "D-", "D#", "E-", "F-", "F#", "G-", "G#", "A-", "A#", "B-"]
        octave = (midi_pitch // 12) - 0 # Renoise 3.x uses different mapping but 60 is C-4 usually
        # Adjustment for Renoise octave (MIDI 60 = C-4 in most DAWs)
        # Renoise C-4 is 48 actually? No, usually C-4 is 48 in tracker, 60 in MIDI.
        # Let's use the offset:
        octave_final = octave - 1 
        note_name = notes[midi_pitch % 12]
        return f"{note_name}{octave_final}"

if __name__ == "__main__":
    # Test stub
    composer = MIDIComposer()
    mock_res = "<note-on_0_60> <time_120> <note-on_0_64> <time_120> <note-off_0_60> <note-off_0_64>"
    cmds = composer.tokens_to_renoise_json(mock_res)
    print(json.dumps({"commands": cmds}, indent=2))
