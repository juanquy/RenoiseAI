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
try:
    from mt3_transcriber import load_mt3_model, transcribe_audio_to_notes
except ImportError:
    load_mt3_model = None
    transcribe_audio_to_notes = None

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

        print("AI Suite WORKER: Loading Specialized Neural MIDI Engine (Llama 3.2-1B)...")
        try:
            midi_composer_model = MIDIComposer()
            if midi_composer_model.text2midi:
                # Signal to app.py that we are truly neural-capable
                with open(os.path.join(TASKS_FOLDER, "models_ready.flag"), "w") as f:
                    f.write(str(time.time()))
            print("AI Suite WORKER: Neural Engine Ready.")
        except Exception as e:
            print(f"AI Suite WORKER: Error loading MIDI engine: {e}")
    return midi_composer_model



def unload_midi_composer():
    """Flush MIDI Composer from VRAM."""
    global midi_composer_model
    if midi_composer_model is not None:
        print("AI Suite WORKER: Flushing MIDI Composer from VRAM...")
        midi_composer_model.unload() # Use the composer's own unload
        del midi_composer_model
        midi_composer_model = None
        gc.collect()
        torch.cuda.empty_cache()

def unload_ollama_models():
    """Force Ollama to release VRAM by stopping active models."""
    try:
        print("AI Suite WORKER: Stopping Ollama models to free VRAM...")
        subprocess.run(["ollama", "stop", "gemma3:12b"], capture_output=True)
        # Also stop the legacy Llama if it was used
        subprocess.run(["ollama", "stop", "llama3.1"], capture_output=True)
    except Exception as e:
        print(f"AI Suite WORKER: Warning: Failed to stop Ollama models: {e}")

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
        update_task(task_id, {"message": "Neural Planning: Injecting Advanced Electronic Blueprint..."})
        
        prompt = task["prompt"]
        song_length = task.get("song_length", 16)
        instruments = task.get("instruments", [])
        
        # ── Theory Engine: Parse prompt → musical intent ─────────────────────
        # Bypass the broken neural model entirely.
        # regex_parse_intent + _legacy_tokens_to_json IS the working pipeline.
        # It generated the real musical content in the user's existing song.
        from midi_composer import regex_parse_intent, MIDIComposer

        s_len = max(song_length, 16)

        update_task(task_id, {"message": "Parsing musical intent from prompt..."})
        intent = regex_parse_intent(prompt)

        # Override BPM if specified in task (user may set it in the plugin)
        if task.get("bpm"):
            intent["bpm"] = int(task["bpm"])

        # Add section name labels for the pattern sequence
        # _legacy_tokens_to_json handles structure via progress fractions
        intent["song_length"] = s_len

        update_task(task_id, {"message": f"Composing {s_len}-pattern structured song ({intent['bpm']} BPM, {intent['scale']} scale)..."})

        # Call the theory engine directly — it generates all patterns with
        # Intro / Verse / Build / Drop / Breakdown / Outro structure built-in
        composer = MIDIComposer()
        commands = composer._legacy_tokens_to_json(intent, song_length=s_len)
        
        # 1. Structure first: BPM, Arrangement, Tracks
        # 2. Performance: Notes, Offs
        # 3. Polish: Lua code, Effects
        
        # Merge and filter
        if plan is None:
            plan = {"plan": "Default Plan (Conductor Error)", "commands": []}
        
        all_raw_commands = commands + plan.get("commands", [])
        
        ordered_commands = []
        # Priority 1: Setup
        for c in all_raw_commands:
            ctype = c.get("type")
            if ctype in ["init_arrangement", "set_bpm", "set_lpb", "add_track"]:
                # Prevent duplicate system commands
                if ctype == "init_arrangement" and any(x["type"] == "init_arrangement" for x in ordered_commands):
                    continue
                if ctype == "set_bpm" and any(x["type"] == "set_bpm" for x in ordered_commands):
                    continue
                if ctype == "set_lpb" and any(x["type"] == "set_lpb" for x in ordered_commands):
                    continue
                if ctype == "add_track":
                    existing_track_indices = [x.get("track") for x in ordered_commands if x["type"] == "add_track"]
                    if c.get("track") in existing_track_indices:
                        continue
                ordered_commands.append(c)
        
        # Priority 2: Notes
        bulk_notes = []
        for c in all_raw_commands:
            if c.get("type") in ["set_note", "note_off"]:
                # N|track|pattern|line|note|instrument|volume
                # O|track|pattern|line
                if c.get("type") == "set_note":
                    note_str = f"N|{c['track']}|{c.get('pattern', 0)}|{c['line']}|{c['note']}|{c.get('instrument', c['track'])}|{c.get('volume', '7F')}"
                else:
                    note_str = f"O|{c['track']}|{c.get('pattern', 0)}|{c['line']}"
                bulk_notes.append(note_str)
        
        if bulk_notes:
            ordered_commands.append({
                "type": "bulk_notes",
                "data": "\n".join(bulk_notes)
            })
        
        # Priority 3: Everything else (Lua, automation)
        for c in all_raw_commands:
            if c.get("type") not in ["init_arrangement", "set_bpm", "set_lpb", "add_track", "set_note", "note_off"]:
                ordered_commands.append(c)

        update_task(task_id, {
            "status": "success",
            "commands": ordered_commands,
            "message": f"Composition Complete! {plan.get('plan', 'Ready.')}"
        })
            
    except Exception as e:
        traceback.print_exc()
        update_task(task_id, {
            "status": "error",
            "error": str(e)
        })

if __name__ == "__main__":
    print(f"AI Suite WORKER: Booting... (CWD: {os.getcwd()})")
    print(f"AI Suite WORKER: Python Path: {sys.path}")
    
    # Pre-load the composer to ensure everything is ready
    get_midi_composer()
    
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
