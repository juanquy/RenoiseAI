import os
import time
import json
import glob
import subprocess
import shutil
import traceback
import torch
import torchaudio
from mt3_transcriber import load_mt3_model, transcribe_audio_to_notes
import sys
from unittest.mock import MagicMock
sys.modules['xformers'] = MagicMock()
sys.modules['xformers.ops'] = MagicMock()

from audiocraft.models import MusicGen
from audiocraft.data.audio import audio_write

UPLOAD_FOLDER = 'uploads'
GENERATED_FOLDER = 'generated'
TASKS_FOLDER = 'tasks'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(GENERATED_FOLDER, exist_ok=True)
os.makedirs(TASKS_FOLDER, exist_ok=True)

# Lazy loading for MusicGen to save VRAM for YourMT3
musicgen_model = None

def get_musicgen():
    global musicgen_model
    if musicgen_model is None:
        print("AI Suite WORKER: Loading MusicGen Model (this may take a minute)...")
        model_size = 'medium'
        try:
            musicgen_model = MusicGen.get_pretrained(f'facebook/musicgen-{model_size}')
            print("AI Suite WORKER: MusicGen Loaded Successfully.")
        except Exception as e:
            print(f"AI Suite WORKER: Error loading MusicGen: {e}")
    return musicgen_model

def update_task(task_id, data):
    task_file = os.path.join(TASKS_FOLDER, f"{task_id}.json")
    if os.path.exists(task_file):
        with open(task_file, 'r') as f:
            task = json.load(f)
    else:
        task = {}
    
    task.update(data)
    with open(task_file, 'w') as f:
        json.dump(task, f)
    return task

def process_stems_and_notes(filepath, base_job_id, task_id, host_url, original_filename=""):
    job_dir = os.path.join(GENERATED_FOLDER, base_job_id)
    os.makedirs(job_dir, exist_ok=True)
    
    update_task(task_id, {"message": "Splitting audio: Initializing Demucs 6-stem model..."})
    
    try:
        print("Running Demucs on GPU 0...")
        try:
            update_task(task_id, {"message": "Splitting audio: Separating Drums, Bass, Vocals, Piano, Guitar, and Other via GPU 0..."})
            # Run Demucs on GPU 0
            demucs_env = os.environ.copy()
            demucs_env["CUDA_VISIBLE_DEVICES"] = "0"
            subprocess.run(["/home/juanquy/miniconda3/envs/ai_env/bin/demucs", "-n", "htdemucs_6s", "-d", "cuda", "-o", job_dir, filepath], 
                         check=True, env=demucs_env)
        except subprocess.CalledProcessError as e:
            print(f"Demucs GPU 0 failed ({e}), retrying on CPU...")
            update_task(task_id, {"message": "Splitting audio: GPU failed, falling back to CPU separation..."})
            subprocess.run(["/home/juanquy/miniconda3/envs/ai_env/bin/demucs", "-n", "htdemucs_6s", "-d", "cpu", "-o", job_dir, filepath], check=True)
        
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        stems_dir = os.path.join(job_dir, "htdemucs_6s", base_name)
        
        stem_files = {
            "bass": os.path.join(stems_dir, "bass.wav"),
            "other": os.path.join(stems_dir, "other.wav"),
            "drums": os.path.join(stems_dir, "drums.wav"),
            "vocals": os.path.join(stems_dir, "vocals.wav"),
            "piano": os.path.join(stems_dir, "piano.wav"),
            "guitar": os.path.join(stems_dir, "guitar.wav")
        }
        
        print("Running YourMT3+ on stems...")
        notes_output = {}
        for stem_key in ["bass", "other", "piano", "guitar", "drums"]:
            if os.path.exists(stem_files[stem_key]):
                update_task(task_id, {"message": f"Transcribing: Analyzing {stem_key} with YourMT3+ transformer..."})
                try:
                    stem_notes = transcribe_audio_to_notes(stem_files[stem_key])
                    # YourMT3+ returns dict of categories; merge all notes for this stem
                    all_notes_for_stem = []
                    for cat_notes in stem_notes.values():
                        all_notes_for_stem.extend(cat_notes)
                    if all_notes_for_stem:
                        notes_output[stem_key] = all_notes_for_stem
                        print(f"  {stem_key}: {len(all_notes_for_stem)} notes transcribed")
                except Exception as e:
                    print(f"  YourMT3+ failed on {stem_key}: {e}")
                    notes_output[stem_key] = []
        
        update_task(task_id, {"message": "Finalizing: Formatting stems and tracking data..."})
        outputs = {}
        if original_filename:
            outputs["mix"] = f"{host_url}/download/{original_filename}"
            
        for stem_key, src in stem_files.items():
            if not os.path.exists(src):
                continue
                
            if stem_key == "vocals":
                try:
                    import soundfile as sf
                    import numpy as np
                    audio_data, _ = sf.read(src)
                    rms = np.sqrt(np.mean(audio_data**2))
                    if rms < 0.005:
                        print(f"Vocals stem is silent (RMS: {rms:.5f}). Dropping.")
                        continue
                except Exception as e:
                    print(f"Error checking vocal silence: {e}")
            
            dst_name = f"{base_job_id}_{stem_key}.wav"
            dst = os.path.join(GENERATED_FOLDER, dst_name)
            shutil.move(src, dst)
            outputs[stem_key] = f"{host_url}/download/{dst_name}"
        
        if os.path.exists(job_dir):
            shutil.rmtree(job_dir, ignore_errors=True)
        
        update_task(task_id, {
            "status": "success",
            "stems": outputs,
            "notes": notes_output,
            "message": "Processing complete!"
        })
        
    except Exception as e:
        print(f"Error during full transcription: {e}")
        update_task(task_id, {
            "status": "error",
            "error": str(e)
        })

def run_transcribe_full_bg(task):
    process_stems_and_notes(task["filepath"], task["job_id"], task["task_id"], task["host_url"])

def run_transcribe_bg(task):
    task_id = task["task_id"]
    filepath = task["filepath"]
    
    try:
        update_task(task_id, {"message": "Transcribing: Analyzing single stem with YourMT3+..."})
        stem_notes = transcribe_audio_to_notes(filepath)
        
        update_task(task_id, {
            "status": "success",
            "stems": {},
            "notes": stem_notes,
            "message": "Single stem transcription complete!"
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        update_task(task_id, {
            "status": "error",
            "error": str(e)
        })

def run_generate_song_bg(task):
    task_id = task["task_id"]
    try:
        update_task(task_id, {"message": "Loading MusicGen model..."})
        mg_model = get_musicgen()
        update_task(task_id, {"message": "Generating arrangement with MusicGen..."})
        mg_model.set_generation_params(duration=task["duration"])
        wav = mg_model.generate([task["gen_prompt"]]) 
        
        sr = mg_model.sample_rate
        fade_samples = int(4 * sr)
        if wav.shape[-1] > fade_samples:
            fade_out_curve = torch.linspace(1.0, 0.0, fade_samples, device=wav.device)
            wav[..., -fade_samples:] *= fade_out_curve 
        
        update_task(task_id, {"message": "Saving generated audio..."})
        job_id = f"gen_{int(time.time())}"
        filename = f"{job_id}.wav"
        filepath = os.path.join(GENERATED_FOLDER, filename)
        
        audio_write(
            os.path.join(GENERATED_FOLDER, job_id), 
            wav[0].cpu(), 
            mg_model.sample_rate, 
            strategy="loudness", 
            loudness_compressor=True
        )
        
        process_stems_and_notes(filepath, job_id, task_id, task["host_url"], original_filename=filename)
            
    except Exception as e:
        traceback.print_exc()
        update_task(task_id, {
            "status": "error",
            "error": str(e)
        })

print("AI Suite WORKER: Started listening for tasks...")
while True:
    try:
        # Find any pending tasks
        pending_files = glob.glob(os.path.join(TASKS_FOLDER, "*.json"))
        pending_files.sort(key=os.path.getctime) # Oldest first
        
        for f in pending_files:
            try:
                with open(f, 'r') as file:
                    task = json.load(file)
            except Exception:
                continue
                
            if task.get("status") == "pending":
                print(f"Worker picked up task: {task.get('task_id')}")
                update_task(task["task_id"], {"status": "processing"})
                
                t_type = task.get("type")
                if t_type == "transcribe_full":
                    run_transcribe_full_bg(task)
                elif t_type == "transcribe":
                    run_transcribe_bg(task)
                elif t_type == "generate_song":
                    run_generate_song_bg(task)
                
    except Exception as e:
        print(f"Worker main loop error: {e}")
        
    time.sleep(1)
