"""
amt_wrapper.py — Anticipatory Music Transformer wrapper for Renoise AI Suite

Wraps Stanford's AMT (359M params, trained on 174K MIDI songs) to generate
multi-instrument MIDI and convert it to Renoise pattern editor commands.

API:
    wrapper = AMTWrapper()
    commands = wrapper.generate_song(prompt, song_length=16, bpm=128)
    # commands is a list of Renoise JSON commands (set_bpm, add_track, set_note, etc.)
"""

import os
import time
import re
import math

import torch
import mido

# Lazy imports for anticipation
_model = None
_device = None


# ─── Music Theory Helpers ────────────────────────────────────────────────────

NOTE_NAMES = ["C-","C#","D-","D#","E-","F-","F#","G-","G#","A-","A#","B-"]

def midi_to_renoise(pitch: int) -> str:
    """Convert MIDI pitch (0-127) to Renoise note string like 'C-4'."""
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
    """Extract BPM, style, etc. from a text prompt."""
    p = prompt.lower()

    style = "default"
    for s in STYLE_DEFAULTS:
        if s in p:
            style = s
            break
    info = dict(STYLE_DEFAULTS[style])

    # Override BPM if specified
    bpm_match = re.search(r'(\d{2,3})\s*bpm', p)
    if bpm_match:
        info["bpm"] = int(bpm_match.group(1))

    info["style"] = style
    info["prompt"] = prompt
    return info


# ─── Model Management ────────────────────────────────────────────────────────

def get_model():
    """Load AMT model (cached singleton). Returns (model, device)."""
    global _model, _device

    if _model is not None:
        return _model, _device

    from transformers import AutoModelForCausalLM

    print("AMTWrapper: Loading Anticipatory Music Transformer (359M params)...")
    _model = AutoModelForCausalLM.from_pretrained('stanford-crfm/music-medium-800k')

    # Use MPS if available, fall back to CPU
    if torch.backends.mps.is_available():
        try:
            _device = 'mps'
            _model = _model.to(_device)
            # Quick smoke test on MPS
            test_input = torch.tensor([[0]]).to(_device)
            _model(test_input)
            print(f"AMTWrapper: Model loaded on MPS (Apple Silicon GPU)")
        except Exception as e:
            print(f"AMTWrapper: MPS failed ({e}), falling back to CPU")
            _device = 'cpu'
            _model = _model.to(_device)
    else:
        _device = 'cpu'
        _model = _model.to(_device)
        print("AMTWrapper: Model loaded on CPU")

    return _model, _device


# ─── MIDI → Renoise Conversion ───────────────────────────────────────────────

# GM instrument program → track role mapping
# AMT uses General MIDI instruments (0-127 programs)
TRACK_ROLE_NAMES = {
    # Drums are always on MIDI channel 10 (instrument 128+ in AMT encoding)
    "drums":  "Drums",
    # Piano/Keys (GM 0-7)
    "piano":  "Piano / Keys",
    # Bass (GM 32-39)
    "bass":   "Bass",
    # Strings (GM 40-51)
    "strings": "Strings / Pad",
    # Ensemble (GM 48-55)
    "ensemble": "Ensemble",
    # Brass (GM 56-63)
    "brass":  "Brass",
    # Reed (GM 64-71)
    "reed":   "Reed / Woodwind",
    # Pipe (GM 72-79)
    "pipe":   "Pipe / Flute",
    # Synth Lead (GM 80-87)
    "lead":   "Lead Synth",
    # Synth Pad (GM 88-95)
    "pad":    "Synth Pad",
    # Synth FX (GM 96-103)
    "fx":     "Synth FX",
    # Other
    "other":  "Synth",
}

def gm_program_to_role(program: int) -> str:
    """Map GM program number to a track role name."""
    if program < 8:   return "piano"
    if program < 16:  return "piano"   # Chromatic percussion
    if program < 24:  return "other"   # Organ
    if program < 32:  return "other"   # Guitar
    if program < 40:  return "bass"
    if program < 48:  return "strings"
    if program < 56:  return "ensemble"
    if program < 64:  return "brass"
    if program < 72:  return "reed"
    if program < 80:  return "pipe"
    if program < 88:  return "lead"
    if program < 96:  return "pad"
    if program < 104: return "fx"
    return "other"


def midi_to_renoise_commands(mid: mido.MidiFile, bpm: int, song_length: int,
                              lines_per_pattern: int = 64, lpb: int = 4) -> list:
    """
    Convert a mido MidiFile into a list of Renoise JSON commands.

    The MIDI file from AMT may have many tracks/channels. We consolidate them
    into up to 8 Renoise tracks and distribute notes across patterns based on
    their timing.
    """
    commands = []

    # Global settings
    commands.append({"type": "set_bpm", "bpm": bpm})
    commands.append({"type": "set_lpb", "lpb": lpb})
    commands.append({"type": "init_arrangement", "patterns": song_length})

    # Calculate timing
    ticks_per_beat = mid.ticks_per_beat or 480
    seconds_per_beat = 60.0 / bpm
    lines_per_beat = lpb
    seconds_per_line = seconds_per_beat / lines_per_beat
    total_lines = song_length * lines_per_pattern

    # Collect ALL note events from all tracks with absolute timing
    all_notes = []  # (abs_time_seconds, pitch, velocity, channel, duration_seconds)

    for track in mid.tracks:
        abs_time_ticks = 0
        active_notes = {}  # (channel, pitch) → start_time_ticks

        for msg in track:
            abs_time_ticks += msg.time

            if msg.type == 'note_on' and msg.velocity > 0:
                key = (msg.channel, msg.note)
                active_notes[key] = abs_time_ticks

            elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                key = (msg.channel, msg.note)
                if key in active_notes:
                    start_ticks = active_notes.pop(key)
                    dur_ticks = abs_time_ticks - start_ticks

                    start_seconds = (start_ticks / ticks_per_beat) * seconds_per_beat
                    dur_seconds = (dur_ticks / ticks_per_beat) * seconds_per_beat

                    all_notes.append((
                        start_seconds,
                        msg.note,
                        72,  # Normalize velocity
                        msg.channel,
                        dur_seconds
                    ))

    if not all_notes:
        print("AMTWrapper: WARNING — no notes in MIDI output")
        return commands

    all_notes.sort(key=lambda x: x[0])

    # Group notes by channel → track assignment
    channels_used = sorted(set(n[3] for n in all_notes))
    max_tracks = min(len(channels_used), 8)

    # Map channels to Renoise track indices (0–7)
    channel_to_track = {}
    for i, ch in enumerate(channels_used[:8]):
        channel_to_track[ch] = i

    # Create track names based on content
    channel_info = {}
    for ch in channels_used[:8]:
        ch_notes = [n for n in all_notes if n[3] == ch]
        pitches = [n[1] for n in ch_notes]
        avg_pitch = sum(pitches) / len(pitches) if pitches else 60

        if ch == 9:  # GM drums
            role = "drums"
        elif avg_pitch < 48:
            role = "bass"
        elif avg_pitch < 60:
            role = "pad"
        elif avg_pitch < 72:
            role = "lead"
        else:
            role = "lead"

        channel_info[ch] = {
            "role": role,
            "name": TRACK_ROLE_NAMES.get(role, "Synth"),
            "count": len(ch_notes)
        }

    # Add track commands
    for ch in channels_used[:8]:
        track_idx = channel_to_track[ch]
        info = channel_info[ch]
        commands.append({
            "type": "add_track",
            "track": track_idx,
            "name": info["name"]
        })

    # Convert notes to Renoise set_note commands
    for start_sec, pitch, vel, channel, dur_sec in all_notes:
        if channel not in channel_to_track:
            continue

        track_idx = channel_to_track[channel]

        # Convert time to line position
        abs_line = int(start_sec / seconds_per_line)
        if abs_line >= total_lines:
            continue

        pattern_idx = abs_line // lines_per_pattern
        line_in_pattern = abs_line % lines_per_pattern

        if pattern_idx >= song_length:
            continue

        note_str = midi_to_renoise(pitch)

        commands.append({
            "type": "set_note",
            "track": track_idx,
            "pattern": pattern_idx,
            "line": line_in_pattern,
            "note": note_str,
            "instrument": track_idx,
            "volume": "7F"
        })

        # Add note-off
        dur_lines = max(1, int(dur_sec / seconds_per_line))
        off_line_abs = abs_line + dur_lines
        off_pattern = off_line_abs // lines_per_pattern
        off_line = off_line_abs % lines_per_pattern

        if off_pattern < song_length and off_line < lines_per_pattern:
            commands.append({
                "type": "note_off",
                "track": track_idx,
                "pattern": off_pattern,
                "line": off_line
            })

    return commands


# ─── Main API ────────────────────────────────────────────────────────────────

class AMTWrapper:
    """High-level API for generating Renoise songs with AMT."""

    def __init__(self):
        self.model = None
        self.device = None

    def ensure_model(self):
        """Lazy-load the model."""
        if self.model is None:
            self.model, self.device = get_model()

    def generate_song(self, prompt: str, song_length: int = 16,
                       bpm: int = None, lines_per_pattern: int = 64,
                       lpb: int = 4, update_fn=None) -> list:
        """
        Generate a complete Renoise song from a text prompt.

        Args:
            prompt: User's musical description
            song_length: Number of patterns (variable — not hardcoded!)
            bpm: Override BPM (if None, extracted from prompt)
            lines_per_pattern: Lines per pattern in Renoise (default 64)
            lpb: Lines per beat
            update_fn: Optional callback(msg) for progress updates

        Returns:
            List of Renoise JSON commands
        """
        self.ensure_model()

        # Parse prompt for musical context
        info = parse_prompt(prompt)
        if bpm:
            info["bpm"] = bpm
        actual_bpm = info["bpm"]

        if update_fn:
            update_fn(f"AMT: Composing {song_length}-pattern song at {actual_bpm} BPM...")

        # Calculate how many seconds of music we need
        beats_per_pattern = lines_per_pattern / lpb
        seconds_per_pattern = beats_per_pattern * (60.0 / actual_bpm)
        total_seconds = seconds_per_pattern * song_length

        print(f"AMTWrapper: Generating {total_seconds:.0f}s of music "
              f"({song_length} patterns × {seconds_per_pattern:.1f}s @ {actual_bpm} BPM)")

        # Generate with AMT
        from anticipation.sample import generate
        from anticipation.convert import events_to_midi

        t0 = time.time()
        events = generate(
            self.model,
            start_time=0,
            end_time=total_seconds,
            top_p=0.98
        )
        elapsed = time.time() - t0

        # Convert to MIDI
        mid = events_to_midi(events)

        total_notes = sum(
            len([m for m in track if m.type == 'note_on' and m.velocity > 0])
            for track in mid.tracks
        )

        print(f"AMTWrapper: Generated {total_notes} notes across "
              f"{len(mid.tracks)} tracks in {elapsed:.1f}s")

        if update_fn:
            update_fn(f"AMT: Generated {total_notes} notes in {elapsed:.1f}s, converting to Renoise...")

        # Convert MIDI → Renoise commands
        commands = midi_to_renoise_commands(
            mid, actual_bpm, song_length,
            lines_per_pattern=lines_per_pattern,
            lpb=lpb
        )

        print(f"AMTWrapper: Produced {len(commands)} Renoise commands")
        return commands


# ─── Smoke Test ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    wrapper = AMTWrapper()
    cmds = wrapper.generate_song(
        "Deep House 124 BPM with a warm bassline and atmospheric pads",
        song_length=4,  # Short test
        bpm=124
    )

    note_cmds = [c for c in cmds if c["type"] == "set_note"]
    print(f"\nTotal commands: {len(cmds)}")
    print(f"Note commands: {len(note_cmds)}")

    # Show distribution across patterns
    from collections import defaultdict
    by_pattern = defaultdict(int)
    by_track = defaultdict(int)
    for c in note_cmds:
        by_pattern[c["pattern"]] += 1
        by_track[c["track"]] += 1

    print("\nNotes per pattern:")
    for p in sorted(by_pattern):
        print(f"  P{p:02d}: {by_pattern[p]}")

    print("\nNotes per track:")
    for t in sorted(by_track):
        name = [c for c in cmds if c.get("type") == "add_track" and c.get("track") == t]
        tname = name[0]["name"] if name else f"Track {t}"
        print(f"  T{t} ({tname}): {by_track[t]}")
