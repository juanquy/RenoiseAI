"""
amt_wrapper.py — Hybrid AMT + Theory Engine for Renoise AI Suite

Strategy:
  1. AMT (359M params) generates melodic/harmonic MIDI in 10-second segments
  2. Theory engine provides reliable drum patterns as backbone
  3. Results are merged into Renoise pattern editor commands

This gives us AI-quality melodies WITH reliable rhythm.
"""

import os
import time
import re
import math
import random

import torch
import mido

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
    """4-on-the-floor kick pattern."""
    events = []
    step = lpb  # One kick per beat
    for l in range(0, lines, step):
        events.append((l, "C-4"))
        # Ghost kick 30% of the time for groove
        if random.random() > 0.7:
            ghost = l + step // 2
            if ghost < lines:
                events.append((ghost, "C-4"))
    return events

def gen_snare_pattern(lines, lpb):
    """Snare on beats 2 and 4."""
    events = []
    bar = lpb * 4
    for b in range(0, lines, bar):
        events.append((b + lpb, "D-4"))      # Beat 2
        events.append((b + lpb * 3, "D-4"))  # Beat 4
    return events

def gen_hihat_pattern(lines, lpb):
    """Closed hi-hat on every 8th note."""
    events = []
    step = max(1, lpb // 2)
    for l in range(0, lines, step):
        events.append((l, "F#4"))
    return events


# ─── Section-aware structure ─────────────────────────────────────────────────

def get_section_type(pattern_idx, total_patterns):
    """Determine what section a pattern belongs to."""
    progress = pattern_idx / max(1, total_patterns)
    if progress < 0.12:  return "intro"
    if progress < 0.38:  return "verse"
    if progress < 0.50:  return "build"
    if progress < 0.75:  return "drop"
    if progress < 0.87:  return "breakdown"
    return "outro"

# Which drum tracks are SILENT in each section
DRUMS_SILENT_IN = {
    "intro":     set(),           # Kick present in intro
    "verse":     set(),           # Full drums
    "build":     set(),           # Full drums
    "drop":      set(),           # Full drums
    "breakdown": {"kick", "snare", "hihat"},  # NO drums in breakdown
    "outro":     {"snare"},       # Strip back snare in outro
}


# ─── MIDI → Renoise Conversion ───────────────────────────────────────────────

def midi_to_renoise_commands(mid, bpm, song_length, lines_per_pattern=64, lpb=4):
    """Convert AMT MIDI output to Renoise commands for melodic tracks."""
    commands = []

    ticks_per_beat = mid.ticks_per_beat or 480
    seconds_per_beat = 60.0 / bpm
    seconds_per_line = seconds_per_beat / lpb
    total_lines = song_length * lines_per_pattern

    # Collect all note events
    all_notes = []
    for track in mid.tracks:
        abs_time_ticks = 0
        active_notes = {}

        for msg in track:
            abs_time_ticks += msg.time
            if msg.type == 'note_on' and msg.velocity > 0:
                active_notes[(msg.channel, msg.note)] = abs_time_ticks
            elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                key = (msg.channel, msg.note)
                if key in active_notes:
                    start_ticks = active_notes.pop(key)
                    dur_ticks = abs_time_ticks - start_ticks
                    start_sec = (start_ticks / ticks_per_beat) * seconds_per_beat
                    dur_sec = (dur_ticks / ticks_per_beat) * seconds_per_beat
                    all_notes.append((start_sec, msg.note, msg.channel, dur_sec))

    if not all_notes:
        return commands, 0

    all_notes.sort(key=lambda x: x[0])

    # Group by channel, map to tracks (skip channel 9 = drums, AMT handles melody)
    channels = sorted(set(n[2] for n in all_notes if n[2] != 9))
    channel_to_track = {}
    # Reserve tracks 0-2 for drums (kick, snare, hihat), AMT gets tracks 3-7
    for i, ch in enumerate(channels[:5]):
        channel_to_track[ch] = i + 3  # Offsets 3-7

    # Name tracks by pitch range
    for ch in channels[:5]:
        track_idx = channel_to_track[ch]
        ch_notes = [n for n in all_notes if n[2] == ch]
        pitches = [n[1] for n in ch_notes]
        avg = sum(pitches) / len(pitches) if pitches else 60

        if avg < 48:
            name = "Bass (AI)"
        elif avg < 60:
            name = "Pad (AI)"
        elif avg < 72:
            name = "Lead (AI)"
        else:
            name = "Melody (AI)"

        commands.append({"type": "add_track", "track": track_idx, "name": name})

    # Convert notes
    note_count = 0
    for start_sec, pitch, channel, dur_sec in all_notes:
        if channel not in channel_to_track:
            continue

        track_idx = channel_to_track[channel]
        abs_line = int(start_sec / seconds_per_line)
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

        Generates in 10-second chunks for higher note density,
        then adds reliable drum patterns from the theory engine.
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
        from anticipation.convert import events_to_midi

        CHUNK_SIZE = 15  # seconds per chunk — shorter = denser output
        all_events = []
        t0 = time.time()

        num_chunks = max(1, int(math.ceil(total_seconds / CHUNK_SIZE)))

        if update_fn:
            update_fn(f"AMT: Generating melody in {num_chunks} chunks...")

        for chunk_idx in range(num_chunks):
            chunk_start = chunk_idx * CHUNK_SIZE
            chunk_end = min(chunk_start + CHUNK_SIZE, total_seconds)

            if update_fn and chunk_idx % 3 == 0:
                update_fn(f"AMT: Chunk {chunk_idx+1}/{num_chunks} ({chunk_start:.0f}-{chunk_end:.0f}s)...")

            try:
                events = generate(
                    self.model,
                    start_time=chunk_start,
                    end_time=chunk_end,
                    top_p=0.95  # Lower = more notes (less selective)
                )
                all_events.extend(events)
            except Exception as e:
                print(f"AMTWrapper: Chunk {chunk_idx} failed: {e}")
                continue

        elapsed = time.time() - t0

        # Convert all events to MIDI
        if all_events:
            mid = events_to_midi(all_events)
        else:
            mid = mido.MidiFile()
            mid.add_track()
            print("AMTWrapper: WARNING — no events generated, using empty MIDI")

        # ── Step 2: Convert AMT MIDI → Renoise commands ─────────────────
        commands = []
        commands.append({"type": "set_bpm", "bpm": actual_bpm})
        commands.append({"type": "set_lpb", "lpb": lpb})
        commands.append({"type": "init_arrangement", "patterns": song_length})

        # Drums first (tracks 0-2)
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

            # Kick (track 0)
            if "kick" not in silent:
                for line, note in gen_kick_pattern(lines_per_pattern, lpb):
                    commands.append({
                        "type": "set_note", "track": 0, "pattern": p_idx,
                        "line": line, "note": note, "instrument": 0, "volume": "7F"
                    })
                    drum_note_count += 1

            # Snare (track 1)
            if "snare" not in silent:
                for line, note in gen_snare_pattern(lines_per_pattern, lpb):
                    commands.append({
                        "type": "set_note", "track": 1, "pattern": p_idx,
                        "line": line, "note": note, "instrument": 1, "volume": "7F"
                    })
                    drum_note_count += 1

            # Hi-hat (track 2)
            if "hihat" not in silent:
                for line, note in gen_hihat_pattern(lines_per_pattern, lpb):
                    commands.append({
                        "type": "set_note", "track": 2, "pattern": p_idx,
                        "line": line, "note": note, "instrument": 2, "volume": "7F"
                    })
                    drum_note_count += 1

        # ── Step 4: Add AMT melodic content (tracks 3-7) ────────────────
        if update_fn:
            update_fn("Converting AI melody to Renoise patterns...")

        amt_commands, amt_note_count = midi_to_renoise_commands(
            mid, actual_bpm, song_length,
            lines_per_pattern=lines_per_pattern,
            lpb=lpb
        )
        commands.extend(amt_commands)

        total_notes = drum_note_count + amt_note_count
        print(f"AMTWrapper: {drum_note_count} drum notes + {amt_note_count} AI melody notes "
              f"= {total_notes} total in {elapsed:.1f}s")

        if update_fn:
            update_fn(f"AMT: Done! {total_notes} notes ({amt_note_count} AI melody + {drum_note_count} drums)")

        return commands
