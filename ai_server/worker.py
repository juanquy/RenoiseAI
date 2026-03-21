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
        
        # ── Electronic Music Blueprint v2: Melody First ───────────────────────
        #
        # REAL electronic music track balance:
        #   - 5 melodic/harmonic tracks (Bass, Lead, Chord, Arp, Sub)
        #   - 3 rhythm tracks (Kick, Hats, Snare)
        #
        # Track indices (0-based):
        T_KICK  = 0   # Kick Drum          — the pulse
        T_BASS  = 1   # Melodic Bass       — harmonic anchor, plays NOTES, not just a thud
        T_SUB   = 2   # Sub / 808          — low-frequency body
        T_LEAD  = 3   # Lead Synth         — main melodic hook, always present in verse/drop
        T_CHORD = 4   # Chord Pad / Stab   — harmonic color (chords, stabs, pads)
        T_ARP   = 5   # Arp / Pluck        — rhythmic melodic layer, texture
        T_HAT   = 6   # Hi-Hats / Rhythm   — groove and movement
        T_SNARE = 7   # Snare / Clap       — backbeat

        # ── Per-section active track rules ───────────────────────────────────
        # RULE: Melody tracks are ALWAYS the CENTER of the mix.
        # Drums support the melody — not the other way around.
        SECTION_ACTIVE_TRACKS = {
            # Intro: bass + subtle melody hint + rhythm skeleton
            "intro":       [T_KICK, T_BASS, T_CHORD, T_HAT],

            # Verse: full harmonic bed + lead melody introduced
            "verse":       [T_KICK, T_BASS, T_SUB, T_LEAD, T_CHORD, T_HAT, T_SNARE],

            # Build: melody escalates, arp adds motion, tension before drop
            "build":       [T_KICK, T_BASS, T_LEAD, T_ARP, T_HAT, T_SNARE],

            # Drop: EVERYTHING — the payoff moment
            "drop":        [T_KICK, T_BASS, T_SUB, T_LEAD, T_CHORD, T_ARP, T_HAT, T_SNARE],

            # Breakdown: NO drums, just pure melody and atmosphere
            # This is the emotional core — pads, lead, bass harmonics
            "breakdown":   [T_BASS, T_LEAD, T_CHORD, T_ARP],

            # Outro: mirror intro — remove lead, keep bass + rhythm
            "outro":       [T_KICK, T_BASS, T_CHORD, T_HAT],
        }

        s_len = max(song_length, 16)

        def build_sections(n):
            q = max(1, n // 8)
            sections = [
                {"name": "Intro A",     "type": "intro",     "start": 0,          "end": min(q-1,        n-1), "desc": "Bass and chords filter in, kick skeleton"},
                {"name": "Intro B",     "type": "intro",     "start": q,          "end": min(q*2-1,      n-1), "desc": "Melody hints appear, groove builds"},
                {"name": "Verse 1",     "type": "verse",     "start": q*2,        "end": min(q*3-1,      n-1), "desc": "Lead melody introduced, full harmonic groove"},
                {"name": "Verse 2",     "type": "verse",     "start": q*3,        "end": min(q*3,        n-1), "desc": "Groove deepens, arp texture added"},
                {"name": "Build 1",     "type": "build",     "start": q*3+1,      "end": min(q*4-1,      n-1), "desc": "Melody climbs, energy rises toward drop"},
                {"name": "Drop 1A",     "type": "drop",      "start": q*4,        "end": min(q*4+q//2-1, n-1), "desc": "Main hook at full energy — all layers hit"},
                {"name": "Drop 1B",     "type": "drop",      "start": q*4+q//2,   "end": min(q*5-1,      n-1), "desc": "Hook repeats, groove locked in"},
                {"name": "Drop 1C",     "type": "drop",      "start": q*5,        "end": min(q*5,        n-1), "desc": "Final bar of drop with variation"},
                {"name": "Breakdown",   "type": "breakdown", "start": q*5+1,      "end": min(q*6,        n-1), "desc": "No drums — pure melody, pads, atmosphere"},
                {"name": "Build 2",     "type": "build",     "start": q*6+1,      "end": min(q*7-1,      n-1), "desc": "Kick returns over melody, climax builds"},
                {"name": "Drop 2A",     "type": "drop",      "start": q*7,        "end": min(q*7+q//2-1, n-1), "desc": "Maximum energy — all elements, melodic peak"},
                {"name": "Drop 2B",     "type": "drop",      "start": q*7+q//2,   "end": min(n-q-1,      n-1), "desc": "Groove variation, lead takes melodic detour"},
                {"name": "Outro A",     "type": "outro",     "start": max(0,n-q), "end": min(max(0,n-q//2-1), n-1), "desc": "Lead fades, bass and chords remain"},
                {"name": "Outro B",     "type": "outro",     "start": max(0,n-q//2), "end": n-1,                    "desc": "Kick and bass, rhythm fades for DJ mix-out"},
            ]
            valid = []
            for s in sections:
                s["start"] = min(max(int(s["start"]), 0), n-1)
                s["end"]   = min(max(int(s["end"]),   s["start"]), n-1)
                valid.append(s)
            return valid

        plan = {
            "plan": f"Electronic Extended Mix (Melody-First) — {prompt}",
            "sections": build_sections(s_len),
            "commands": [
                {"type": "init_arrangement", "patterns": s_len},
                {"type": "add_track", "track": 0, "name": "Kick Drum"},
                {"type": "add_track", "track": 1, "name": "Bass Synth"},
                {"type": "add_track", "track": 2, "name": "Sub / 808"},
                {"type": "add_track", "track": 3, "name": "Lead Synth"},
                {"type": "add_track", "track": 4, "name": "Chord Pad"},
                {"type": "add_track", "track": 5, "name": "Arp / Pluck"},
                {"type": "add_track", "track": 6, "name": "Hi-Hats"},
                {"type": "add_track", "track": 7, "name": "Snare / Clap"},
            ]
        }

        # Step 2: Neural MIDI Generation per Section per Track
        final_midi_commands = []
        if plan and "sections" in plan and "commands" in plan:
            sections = plan.get("sections", [])
            tracks_to_fill = [c for c in plan["commands"] if c.get("type") == "add_track"]

            composer = get_midi_composer()
            composer.clear_cache()

            drum_keywords = ["kick", "snare", "hat", "clap", "perc", "drum", "rim", "crash", "ride"]

            for section in sections:
                sec_name = section.get("name", "Section")
                sec_type = section.get("type", "drop").lower()
                start_p  = int(section.get("start", 0))
                end_p    = int(section.get("end", 0))
                sec_desc = section.get("desc", "")

                # Which tracks are allowed to generate notes in this section?
                active_tracks = SECTION_ACTIVE_TRACKS.get(sec_type, list(range(8)))

                update_task(task_id, {"message": f"Neural Dreaming: [{sec_name}] Patterns {start_p}-{end_p}..."})

                for t_info in tracks_to_fill:
                    track_name = t_info.get("name", "Synth")
                    track_idx  = t_info.get("track", 0)

                    # ── KEY CHANGE: skip tracks not active in this section ──
                    if track_idx not in active_tracks:
                        continue

                    forced_inst = track_idx
                    is_drum = any(k in track_name.lower() for k in drum_keywords)

                    role_context = (
                        f"Section: {sec_name} ({sec_type}). Track: {track_name}. "
                        f"Goal: {sec_desc}. Instrument Slot: {forced_inst}. Song: {prompt}"
                    )

                    raw_output = composer.generate_midi_sequence(
                        role_prompt=role_context,
                        instruments=instruments,
                        plan_context=plan.get("plan", prompt),
                        forced_instrument=forced_inst
                    )

                    base_commands = composer.tokens_to_renoise_json(
                        raw_output,
                        song_length=1,
                        target_track=track_idx,
                        forced_instrument=forced_inst,
                        is_drum=is_drum
                    )

                    for p_idx in range(start_p, end_p + 1):
                        for b_cmd in base_commands:
                            if b_cmd.get("type") in ["set_note", "note_off"]:
                                new_cmd = b_cmd.copy()
                                new_cmd["pattern"] = p_idx
                                final_midi_commands.append(new_cmd)
        
        commands = final_midi_commands
        
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
