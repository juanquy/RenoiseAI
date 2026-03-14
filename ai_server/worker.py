import os
import time
import json
import glob
import subprocess
import shutil
import traceback
import torch
import torchaudio
import gc
from mt3_transcriber import load_mt3_model, transcribe_audio_to_notes
import sys
from unittest.mock import MagicMock
sys.modules['xformers'] = MagicMock()
sys.modules['xformers.ops'] = MagicMock()


from midi_composer import MIDIComposer

UPLOAD_FOLDER = 'uploads'
GENERATED_FOLDER = 'generated'
TASKS_FOLDER = 'tasks'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(GENERATED_FOLDER, exist_ok=True)
os.makedirs(TASKS_FOLDER, exist_ok=True)

midi_composer_model = None


def get_midi_composer():
    global midi_composer_model
    if midi_composer_model is None:

        print("AI Suite WORKER: Loading Llama 3.2 MIDI Composer (Specialized Musical Specialist)...")
        try:
            midi_composer_model = MIDIComposer()
            print("AI Suite WORKER: MIDI Composer Loaded Successfully.")
        except Exception as e:
            print(f"AI Suite WORKER: Error loading MIDI Composer: {e}")
    return midi_composer_model



def unload_midi_composer():
    """Flush MIDI Composer from VRAM."""
    global midi_composer_model
    if midi_composer_model is not None:
        print("AI Suite WORKER: Flushing MIDI Composer from VRAM...")
        del midi_composer_model
        midi_composer_model = None
        gc.collect()
        torch.cuda.empty_cache()

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
def cleanup_old_files(max_age_seconds=3600):
    """Delete files older than max_age_seconds in standard folders."""
    now = time.time()
    for folder in [UPLOAD_FOLDER, GENERATED_FOLDER, TASKS_FOLDER]:
        for f in glob.glob(os.path.join(folder, "*")):
            # Don't delete directories (like job dirs being processed)
            if os.path.isfile(f):
                if os.path.getmtime(f) < now - max_age_seconds:
                    try:
                        os.remove(f)
                        print(f"Janitor: Purged old file {os.path.basename(f)}")
                    except Exception as e:
                        print(f"Janitor error on {f}: {e}")
            elif os.path.isdir(f):
                # Cleanup old job directories
                if os.path.getmtime(f) < now - max_age_seconds:
                    try:
                        shutil.rmtree(f, ignore_errors=True)
                        print(f"Janitor: Purged old directory {os.path.basename(f)}")
                    except Exception:
                        pass



def run_transcribe_bg(task):
    task_id = task["task_id"]
    filepath = task["filepath"]
    
    # Use the filename (e.g. "2 Bass") as the flat category name for pure imports
    import os
    track_name = task.get("original_filename")
    if not track_name:
        track_name = os.path.basename(filepath)
    track_name = os.path.splitext(track_name)[0]
    
    try:
        update_task(task_id, {"message": f"Transcribing {track_name}: Analyzing single stem..."})
        stem_notes = transcribe_audio_to_notes(filepath, flat_name=track_name)
        
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


def run_compose_native_midi_bg(task):
    task_id = task["task_id"]
    try:
        update_task(task_id, {"message": "Initializing Specialized MIDI LLM..."})
        composer = get_midi_composer()
        
        prompt = task["prompt"]
        update_task(task_id, {"message": f"Composing native sequence for: {prompt[:30]}..."})
        
        # Generate tokens
        raw_sequence = composer.generate_midi_sequence(prompt)
        
        # Parse tokens into Renoise JSON commands
        # We assume default 135 BPM and 4 LPB for now, can be expanded to get from task
        commands = composer.tokens_to_renoise_json(raw_sequence)
        
        update_task(task_id, {
            "status": "success",
            "notes": {}, # Legacy field
            "commands": commands, # The real meat
            "raw_output": raw_sequence,
            "message": "Native MIDI Generation (Llama 3.2-1B) Complete!"
        })
            
    except Exception as e:
        traceback.print_exc()
        update_task(task_id, {
            "status": "error",
            "error": str(e)
        })

print("AI Suite WORKER: Started listening for tasks...")
while True:
    try:
        # Run cleanup every few iterations
        if int(time.time()) % 300 == 0: # Every 5 minutes
            cleanup_old_files()

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
                update_task(task["task_id"], {"status": "processing"})

                if task["type"] == "transcribe":
                    run_transcribe_bg(task)
                elif task["type"] == "compose_native_midi":
                    run_compose_native_midi_bg(task)
                else:
                    print(f"Unknown task type: {task.get('type')}")
                    update_task(task["task_id"], {"status": "error", "error": "Unknown task type"})
                
                # After any task, ensure a scrub
                gc.collect()
                torch.cuda.empty_cache()
                
    except Exception as e:
        print(f"Worker main loop error: {e}")
        
    # Micro-scrub every loop iteration
    if int(time.time()) % 60 == 0:
         gc.collect()
         torch.cuda.empty_cache()

    time.sleep(1)
