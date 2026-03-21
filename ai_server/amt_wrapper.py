"""
amt_wrapper.py — Hybrid AMT + Theory Engine for Renoise AI Suite

Strategy:
  1. AMT (359M params) generates melodic/harmonic content in chunks
  2. Raw AMT event tokens parsed directly (bypasses buggy events_to_midi)
  3. Theory engine provides reliable drum patterns as backbone
  4. Results merged into Renoise pattern editor commands
"""

import os
import time
import re
import math
import random

import torch

# Lazy imports for anticipation
_model = None
_device = None


# ─── Music Theory Helpers ────────────────────────────────────────────────────

NOTE_NAMES = ["C-","C#","D-","D#","E-","F-","F#","G-","G#","A-","A#","B-"]

def midi_to_renoise(pitch: int) -> str:
    pitch = max(0, min(119, pitch))
    return f"{NOTE_NAMES[pitch % 12]}{pitch // 12}"


STYLE_DEFAULTS = {
    "techno":    {"bpm": 140, "scale": "minor"},
    "house":     {"bpm": 128, "scale": "minor"},
    "trance":    {"bpm": 140, "scale": "minor"},
    "dnb":       {"bpm": 174, "scale": "minor"},
    "dubstep":   {"bpm": 140, "scale": "minor"},
    "ambient":   {"bpm": 95,  "scale": "major"},
    "hiphop":    {"bpm": 90,  "scale": "minor"},
    "jazz":      {"bpm": 100, "scale": "dorian"},
    "neurofunk": {"bpm": 174, "scale": "minor"},
    "default":   {"bpm": 128, "scale": "minor"},
}


def parse_prompt(prompt: str) -> dict:
    p = prompt.lower()
    style = "default"
    for s in STYLE_DEFAULTS:
        if s in p:
            style = s
            break
    info = dict(STYLE_DEFAULTS[style])
    bpm_match = re.search(r'(\d{2,3})\s*bpm', p)
    if bpm_match:
        info["bpm"] = int(bpm_match.group(1))
    info["style"] = style
    info["prompt"] = prompt
    return info


# ─── Model Management ────────────────────────────────────────────────────────

def get_model():
    global _model, _device
    if _model is not None:
        return _model, _device

    from transformers import AutoModelForCausalLM
    print("AMTWrapper: Loading Anticipatory Music Transformer (359M params)...")
    _model = AutoModelForCausalLM.from_pretrained('stanford-crfm/music-medium-800k')

    if torch.backends.mps.is_available():
        try:
            _device = 'mps'
            _model = _model.to(_device)
            test_input = torch.tensor([[0]]).to(_device)
            _model(test_input)
            print("AMTWrapper: Model loaded on MPS (Apple Silicon GPU)")
        except Exception as e:
            print(f"AMTWrapper: MPS failed ({e}), falling back to CPU")
            _device = 'cpu'
            _model = _model.to(_device)
    else:
        _device = 'cpu'
        _model = _model.to(_device)
        print("AMTWrapper: Model loaded on CPU")

    return _model, _device


# ─── Theory Engine: Drum Patterns ────────────────────────────────────────────

def gen_kick_pattern(lines, lpb):
    events = []
    step = lpb  # One kick per beat
    for l in range(0, lines, step):
        events.append((l, "C-4"))
        if random.random() > 0.7:
            ghost = l + step // 2
            if ghost < lines:
                events.append((ghost, "C-4"))
    return events

def gen_snare_pattern(lines, lpb):
    events = []
    bar = lpb * 4
    for b in range(0, lines, bar):
        events.append((b + lpb, "D-4"))
        events.append((b + lpb * 3, "D-4"))
    return events

def gen_hihat_pattern(lines, lpb):
    events = []
    step = max(1, lpb // 2)
    for l in range(0, lines, step):
        events.append((l, "F#4"))
    return events


# ─── Section Structure ───────────────────────────────────────────────────────

def get_section_type(pattern_idx, total_patterns):
    progress = pattern_idx / max(1, total_patterns)
    if progress < 0.12:  return "intro"
    if progress < 0.38:  return "verse"
    if progress < 0.50:  return "build"
    if progress < 0.75:  return "drop"
    if progress < 0.87:  return "breakdown"
    return "outro"

DRUMS_SILENT_IN = {
    "intro":     set(),
    "verse":     set(),
    "build":     set(),
    "drop":      set(),
    "breakdown": {"kick", "snare", "hihat"},
    "outro":     {"snare"},
}


# ─── Direct AMT Event Parsing (bypasses buggy events_to_midi) ────────────────

def parse_amt_events_direct(events, bpm, song_length, lines_per_pattern=64, lpb=4):
    """
    Parse raw AMT event tokens directly into Renoise commands.
    
    AMT events are a flat list of triplets: [time, dur, note, time, dur, note, ...]
    Each triplet uses vocabulary offsets from anticipation.vocab.
    
    This bypasses events_to_midi entirely, avoiding the MIDI channel overflow bug.
    """
    from anticipation.config import TIME_RESOLUTION, MAX_PITCH
    from anticipation.vocab import TIME_OFFSET, DUR_OFFSET, NOTE_OFFSET
    from anticipation import ops

    # Clean events (remove padding/controls)
    events = ops.unpad(events)
    
    if len(events) < 3:
        return [], 0

    # Parse triplets
    seconds_per_beat = 60.0 / bpm
    seconds_per_line = seconds_per_beat / lpb
    total_lines = song_length * lines_per_pattern

    # Group notes by instrument for track assignment
    # instrument_notes: {instrument_id: [(time_sec, dur_sec, pitch), ...]}
    instrument_notes = {}
    
    for i in range(0, len(events) - 2, 3):
        raw_time = events[i]
        raw_dur = events[i+1]
        raw_note = events[i+2]
        
        # Decode
        time_ticks = raw_time - TIME_OFFSET
        dur_ticks = raw_dur - DUR_OFFSET
        note_val = raw_note - NOTE_OFFSET
        
        if time_ticks < 0 or dur_ticks < 0 or note_val < 0:
            continue
        
        instrument = note_val // MAX_PITCH
        pitch = note_val % MAX_PITCH
        
        time_sec = time_ticks / TIME_RESOLUTION
        dur_sec = dur_ticks / TIME_RESOLUTION
        
        if instrument not in instrument_notes:
            instrument_notes[instrument] = []
        instrument_notes[instrument].append((time_sec, dur_sec, pitch))

    if not instrument_notes:
        return [], 0

    # Sort instruments by note count (most used first), take top 5
    sorted_instruments = sorted(instrument_notes.keys(), 
                                key=lambda k: len(instrument_notes[k]), 
                                reverse=True)
    
    # Skip instrument 128 (drums — we handle those with theory engine)
    melodic_instruments = [i for i in sorted_instruments if i != 128][:5]
    
    commands = []
    note_count = 0
    
    # Name tracks based on GM instrument + pitch range
    GM_NAMES = {
        range(0, 8): "Piano (AI)", range(8, 16): "Chromatic (AI)",
        range(16, 24): "Organ (AI)", range(24, 32): "Guitar (AI)",
        range(32, 40): "Bass (AI)", range(40, 48): "Strings (AI)",
        range(48, 56): "Ensemble (AI)", range(56, 64): "Brass (AI)",
        range(64, 72): "Reed (AI)", range(72, 80): "Flute (AI)",
        range(80, 88): "Lead (AI)", range(88, 96): "Pad (AI)",
        range(96, 104): "FX (AI)", range(104, 128): "Synth (AI)",
    }
    
    def get_gm_name(instr_id):
        for rng, name in GM_NAMES.items():
            if instr_id in rng:
                return name
        return "Synth (AI)"
    
    for track_offset, instr_id in enumerate(melodic_instruments):
        track_idx = track_offset + 3  # Tracks 3-7 (0-2 are drums)
        
        commands.append({
            "type": "add_track", 
            "track": track_idx, 
            "name": get_gm_name(instr_id)
        })
        
        for time_sec, dur_sec, pitch in instrument_notes[instr_id]:
            abs_line = int(time_sec / seconds_per_line)
            if abs_line >= total_lines:
                continue
            
            pattern_idx = abs_line // lines_per_pattern
            line = abs_line % lines_per_pattern
            
            if pattern_idx >= song_length:
                continue
            
            commands.append({
                "type": "set_note",
                "track": track_idx,
                "pattern": pattern_idx,
                "line": line,
                "note": midi_to_renoise(pitch),
                "instrument": track_idx,
                "volume": "7F"
            })
            note_count += 1
            
            # Note-off
            dur_lines = max(1, int(dur_sec / seconds_per_line))
            off_abs = abs_line + dur_lines
            off_pat = off_abs // lines_per_pattern
            off_line = off_abs % lines_per_pattern
            if off_pat < song_length:
                commands.append({
                    "type": "note_off",
                    "track": track_idx,
                    "pattern": off_pat,
                    "line": off_line
                })

    return commands, note_count


# ─── Main API ────────────────────────────────────────────────────────────────

class AMTWrapper:
    def __init__(self):
        self.model = None
        self.device = None

    def ensure_model(self):
        if self.model is None:
            self.model, self.device = get_model()

    def generate_song(self, prompt, song_length=16, bpm=None,
                       lines_per_pattern=64, lpb=4, update_fn=None):
        """
        Hybrid generation: AMT melody + theory engine drums.
        Generates in short chunks for higher note density.
        """
        self.ensure_model()

        info = parse_prompt(prompt)
        if bpm:
            info["bpm"] = bpm
        actual_bpm = info["bpm"]

        if update_fn:
            update_fn(f"AMT: Composing {song_length}-pattern song at {actual_bpm} BPM...")

        # Calculate timing
        beats_per_pattern = lines_per_pattern / lpb
        seconds_per_pattern = beats_per_pattern * (60.0 / actual_bpm)
        total_seconds = seconds_per_pattern * song_length

        print(f"AMTWrapper: Generating {total_seconds:.0f}s of music "
              f"({song_length} patterns × {seconds_per_pattern:.1f}s @ {actual_bpm} BPM)")

        # ── Step 1: Generate AMT melody in chunks ───────────────────────
        from anticipation.sample import generate

        CHUNK_SIZE = 10  # shorter chunks = denser output
        all_events = []
        t0 = time.time()

        num_chunks = max(1, int(math.ceil(total_seconds / CHUNK_SIZE)))

        if update_fn:
            update_fn(f"AMT: Generating melody in {num_chunks} chunks...")

        for chunk_idx in range(num_chunks):
            chunk_start = chunk_idx * CHUNK_SIZE
            chunk_end = min(chunk_start + CHUNK_SIZE, total_seconds)

            if update_fn and chunk_idx % 3 == 0:
                update_fn(f"AMT: Chunk {chunk_idx+1}/{num_chunks}...")

            try:
                events = generate(
                    self.model,
                    start_time=chunk_start,
                    end_time=chunk_end,
                    top_p=0.95
                )
                all_events.extend(events)
            except Exception as e:
                print(f"AMTWrapper: Chunk {chunk_idx} failed: {e}")
                continue

        elapsed = time.time() - t0
        print(f"AMTWrapper: Generated {len(all_events)} raw event tokens in {elapsed:.1f}s")

        # ── Step 2: Build Renoise commands ──────────────────────────────
        commands = []
        commands.append({"type": "set_bpm", "bpm": actual_bpm})
        commands.append({"type": "set_lpb", "lpb": lpb})
        commands.append({"type": "init_arrangement", "patterns": song_length})

        # Drum tracks (0-2)
        commands.append({"type": "add_track", "track": 0, "name": "Kick"})
        commands.append({"type": "add_track", "track": 1, "name": "Snare"})
        commands.append({"type": "add_track", "track": 2, "name": "Hi-Hat"})

        # ── Step 3: Add drum patterns per section ───────────────────────
        if update_fn:
            update_fn("Adding structured drum patterns...")

        drum_note_count = 0
        for p_idx in range(song_length):
            sec = get_section_type(p_idx, song_length)
            silent = DRUMS_SILENT_IN.get(sec, set())

            if "kick" not in silent:
                for line, note in gen_kick_pattern(lines_per_pattern, lpb):
                    commands.append({
                        "type": "set_note", "track": 0, "pattern": p_idx,
                        "line": line, "note": note, "instrument": 0, "volume": "7F"
                    })
                    drum_note_count += 1

            if "snare" not in silent:
                for line, note in gen_snare_pattern(lines_per_pattern, lpb):
                    commands.append({
                        "type": "set_note", "track": 1, "pattern": p_idx,
                        "line": line, "note": note, "instrument": 1, "volume": "7F"
                    })
                    drum_note_count += 1

            if "hihat" not in silent:
                for line, note in gen_hihat_pattern(lines_per_pattern, lpb):
                    commands.append({
                        "type": "set_note", "track": 2, "pattern": p_idx,
                        "line": line, "note": note, "instrument": 2, "volume": "7F"
                    })
                    drum_note_count += 1

        # ── Step 4: Parse AMT events directly (no events_to_midi) ───────
        if update_fn:
            update_fn("Converting AI melody to Renoise patterns...")

        amt_commands, amt_note_count = parse_amt_events_direct(
            all_events, actual_bpm, song_length,
            lines_per_pattern=lines_per_pattern,
            lpb=lpb
        )
        commands.extend(amt_commands)

        total_notes = drum_note_count + amt_note_count
        print(f"AMTWrapper: {drum_note_count} drum + {amt_note_count} AI melody "
              f"= {total_notes} total notes in {elapsed:.1f}s")

        if update_fn:
            update_fn(f"AMT: Done! {total_notes} notes ({amt_note_count} AI + {drum_note_count} drums)")

        return commands
