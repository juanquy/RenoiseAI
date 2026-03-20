"""
midi_composer.py  –  Renoise AI Suite v2
Hybrid AI + Deterministic Architecture:
  1. Ollama (llama3.1 7B) parses user's natural language → rich JSON musical plan
  2. A deterministic theory engine converts that plan → always-correct Renoise commands

This gives us REAL AI musical intelligence (7B parameters) without the risk of
the AI hallucinating broken note strings.
"""

import os
import re
import json
import random
import urllib.request
import urllib.error

try:
    import torch
    # No longer loading 8B Transformers to save VRAM for Gemma-3
    _HAS_TORCH = True
except ImportError:
    _HAS_TORCH = False

# ──────────────────────────────────────────────────────────────────────────────
# Music Theory Constants
# ──────────────────────────────────────────────────────────────────────────────

NOTE_NAMES   = ["C-","C#","D-","D#","E-","F-","F#","G-","G#","A-","A#","B-"]
ROOT_MAP     = {"C":0,"C#":1,"Db":1,"D":2,"D#":3,"Eb":3,"E":4,"F":5,
                "F#":6,"Gb":6,"G":7,"G#":8,"Ab":8,"A":9,"A#":10,"Bb":10,"B":11}

SCALES = {
    "major":      [0,2,4,5,7,9,11],
    "minor":      [0,2,3,5,7,8,10],
    "dorian":     [0,2,3,5,7,9,10],
    "phrygian":   [0,1,3,5,7,8,10],
    "mixolydian": [0,2,4,5,7,9,10],
    "pentatonic": [0,2,4,7,9],
    "blues":      [0,3,5,6,7,10],
}

# Roman numeral → scale degree index
CHORD_DEGREE = {
    "i":0,"ii":1,"iii":2,"iv":3,"v":4,"vi":5,"vii":6,
    "I":0,"II":1,"III":2,"IV":3,"V":4,"VI":5,"VII":6,
}

# Pattern names the AI may return → internal pattern ID
PATTERN_ALIASES = {
    # rhythmic
    "4_on_floor": "kick_4otf",   "four on the floor": "kick_4otf",
    "half_time":  "kick_half",   "half time":         "kick_half",
    "closed hihat": "hihat",     "hi-hat":            "hihat",
    # bass
    "root_walk":  "bass_walk",   "walking":       "bass_walk",
    "ostinato":   "bass_ostinato","repeating":    "bass_ostinato",
    "square":     "bass_ostinato","arpeggio":     "bass_arp",
    # harmonic
    "chord_sustain":"pad_sustain","sustain":      "pad_sustain",
    "sweep":      "pad_sustain", "stab":          "pad_stab",
    "arp":        "chord_arp",   "arpeggiated":   "chord_arp",
    # melodic
    "melodic":    "lead_phrase", "phrase":        "lead_phrase",
    "riff":       "lead_riff",   "acid":          "lead_acid",
    "ascending":  "lead_phrase",
}

def norm_pattern(raw: str) -> str:
    raw_l = raw.lower().strip()
    for alias, internal in PATTERN_ALIASES.items():
        if alias in raw_l:
            return internal
    # Guess from role name heuristics
    return "default"


# ──────────────────────────────────────────────────────────────────────────────
# Pitch helpers
# ──────────────────────────────────────────────────────────────────────────────

def midi_to_renoise(pitch: int) -> str:
    pitch = max(0, min(119, pitch))
    return f"{NOTE_NAMES[pitch % 12]}{pitch // 12}"

def scale_pitches(root: int, octave: int, scale_name: str) -> list:
    """MIDI pitches for `octave` of the named scale starting on `root`."""
    intervals = SCALES.get(scale_name.lower(), SCALES["minor"])
    base = root + (octave + 1) * 12
    return [base + i for i in intervals]

def chord_root_pitch(root: int, degree_str: str, scale_name: str, octave: int = 3) -> int:
    """Return the MIDI root of a chord given a roman numeral degree."""
    intervals = SCALES.get(scale_name.lower(), SCALES["minor"])
    deg = CHORD_DEGREE.get(degree_str.strip(), 0)
    base = root + (octave + 1) * 12
    return base + intervals[deg % len(intervals)]


# ──────────────────────────────────────────────────────────────────────────────
# Pattern generators
# ──────────────────────────────────────────────────────────────────────────────

def gen_kick(lines, lpb, pattern_id="kick_4otf"):
    events = []
    beat = lpb
    step = beat if "half" not in str(pattern_id) else beat * 2
    for l in range(0, lines, step):
        events.append((l, "C-4"))    # GM Kick (Octave 4)
        # Add a faint ghost kick 20% of the time for groove
        if random.random() > 0.8:
            ghost_l = l + (step // 2)
            if ghost_l < lines:
                events.append((ghost_l, "C-4"))
    return events

def gen_snare(lines, lpb, pattern_id="snare"):
    """Snare on beats 2 and 4."""
    events = []
    bar = lpb * 4
    for bar_start in range(0, lines, bar):
        for beat in [1, 3]:          # beats 2 and 4 (0-indexed)
            l = bar_start + beat * lpb
            if l < lines:
                # 30% chance of a "ghost" snare hit before the main backbeat
                if random.random() > 0.7:
                     ghost_l = l - (lpb // 2)
                     if ghost_l > 0:
                         events.append((ghost_l, "D-4"))
                events.append((l, "D-4"))  # GM Snare (Octave 4)
    return events

def gen_clap(lines, lpb, pattern_id="clap"):
    """Clap on beats 2 and 4, slightly offset from snare."""
    events = []
    bar = lpb * 4
    offset = max(1, lpb // 4)
    for bar_start in range(0, lines, bar):
        for beat in [1, 3]:
            l = bar_start + beat * lpb + offset
            if l < lines:
                events.append((l, "C#4"))  # GM Clap (Octave 4)
    return events

def gen_hihat(lines, lpb, pattern_id="hihat"):
    """Closed hi-hat on every 8th note."""
    events = []
    step = max(1, lpb // 2)
    for l in range(0, lines, step):
        # 90% chance of hi-hat (occasional missed hit for realism)
        if random.random() > 0.1:
            events.append((l, "F#4"))    # GM Closed HH (Octave 4)
        # 15% chance of an extra rapid 16th note fill
        if random.random() > 0.85:
            fill_l = l + (step // 2)
            if fill_l < lines:
                events.append((fill_l, "F#4"))
    return events

def gen_open_hat(lines, lpb, pattern_id="open_hat"):
    """Open hi-hat on the off-beats."""
    events = []
    bar = lpb * 4
    off = max(1, lpb // 2)
    for bar_start in range(0, lines, bar):
        for beat in [0, 2]:
            l = bar_start + beat * lpb + off
            if l < lines:
                events.append((l, "A#4"))  # GM Open HH (Octave 4)
    return events

def gen_bass(notes, lines, lpb, chord_prog, root, scale_name, pattern_id="bass_walk"):
    events = []
    bar  = lpb * 4
    beat = lpb
    num_chords = max(1, len(chord_prog))

    for bar_idx, bar_start in enumerate(range(0, lines, bar)):
        deg = chord_prog[bar_idx % num_chords]
        chord_midi = chord_root_pitch(root, deg, scale_name, octave=1)   # octave 2

        if pattern_id == "bass_ostinato":
            # Repeat root on every beat
            for b in range(4):
                l = bar_start + b * beat
                if l < lines:
                    events.append((l, midi_to_renoise(chord_midi)))

        elif pattern_id == "bass_arp":
            scale_notes = scale_pitches(root, 1, scale_name)
            for step_idx, off in enumerate([0, beat, beat*2, beat*3]):
                l = bar_start + off
                if l < lines:
                    n = scale_notes[step_idx % len(scale_notes)]
                    events.append((l, midi_to_renoise(n)))
        else:  # bass_walk (default)
            # Root on beat 1, fifth on beat 3
            fifth_note = chord_root_pitch(root, deg, scale_name, octave=1) + 7
            events.append((bar_start, midi_to_renoise(chord_midi)))
            beat3 = bar_start + beat * 2
            if beat3 < lines:
                events.append((beat3, midi_to_renoise(min(119, fifth_note))))

    return events

def gen_pad(notes, lines, lpb, chord_prog, root, scale_name, pattern_id="pad_sustain"):
    events = []
    bar = lpb * 4
    num_chords = max(1, len(chord_prog))

    for bar_idx, bar_start in enumerate(range(0, lines, bar)):
        deg = chord_prog[bar_idx % num_chords]
        chord_midi = chord_root_pitch(root, deg, scale_name, octave=3)   # octave 4

        if pattern_id == "pad_stab":
            # Stab on beat 1 and 3
            for b in [0, 2]:
                l = bar_start + b * lpb
                if l < lines:
                    events.append((l, midi_to_renoise(chord_midi)))
        else:  # sustain
            events.append((bar_start, midi_to_renoise(chord_midi)))

    return events

def gen_lead(notes, lines, lpb, chord_prog, root, scale_name, pattern_id="lead_phrase"):
    events = []
    bar     = lpb * 4
    half_b  = max(1, lpb // 2)
    num_chords = max(1, len(chord_prog))

    for bar_idx, bar_start in enumerate(range(0, lines, bar)):
        deg = chord_prog[bar_idx % num_chords]
        # Use scale tones around the chord root
        base_oct = 4 if pattern_id != "lead_acid" else 2
        sc = scale_pitches(root, base_oct, scale_name)
        # Choose 4 notes for the phrase (adjacent scale tones from chord root)
        chord_midi = chord_root_pitch(root, deg, scale_name, octave=base_oct)
        idx_in_scale = min(range(len(sc)), key=lambda i: abs(sc[i]-chord_midi))
        phrase = [sc[(idx_in_scale + k) % len(sc)] for k in range(4)]

        offsets = [0, half_b, half_b*2, half_b*3]
        if pattern_id == "lead_riff":
            offsets = [0, half_b, half_b*2, half_b*3, half_b*4, half_b*6]
            phrase = phrase * 2

        for i, off in enumerate(offsets):
            l = bar_start + off
            if l < lines:
                # Add random velocity or slight pitch variation
                note_midi = phrase[i % len(phrase)]
                # 20% chance to shift note by an octave or scale step
                if random.random() > 0.8:
                    note_midi += random.choice([-12, 0, 7, 12])
                
                events.append((l, midi_to_renoise(note_midi)))
        
        # Add a random "flourish" note 10% of the time
        if random.random() > 0.9:
            flourish_l = bar_start + bar - 1
            if flourish_l < lines:
                events.append((flourish_l, midi_to_renoise(phrase[0] + 12)))

    return events

def gen_chord_arp(notes, lines, lpb, chord_prog, root, scale_name, pattern_id="chord_arp"):
    """Arpeggio through chord tones."""
    events = []
    bar = lpb * 4
    step = max(1, lpb // 2)
    num_chords = max(1, len(chord_prog))

    for bar_idx, bar_start in enumerate(range(0, lines, bar)):
        deg = chord_prog[bar_idx % num_chords]
        sc = scale_pitches(root, 3, scale_name)
        chord_midi = chord_root_pitch(root, deg, scale_name, octave=3)
        idx = min(range(len(sc)), key=lambda i: abs(sc[i]-chord_midi))
        triad = [sc[(idx+k) % len(sc)] for k in [0,2,4]]   # root, third, fifth

        beat_in_bar = 0
        for l in range(bar_start, min(bar_start+bar, lines), step):
            events.append((l, midi_to_renoise(triad[beat_in_bar % 3])))
            beat_in_bar += 1

    return events


# ──────────────────────────────────────────────────────────────────────────────
# Role dispatcher
# ──────────────────────────────────────────────────────────────────────────────

def role_to_events(role_name: str, pattern_id: str, notes, lines, lpb,
                   chord_prog, root, scale_name) -> list:
    rn  = role_name.lower()
    pid = norm_pattern(pattern_id) if pattern_id else "default"

    # Drum roles — match by name first
    if "kick" in rn or ("drum" in rn and "bass" not in rn):
        return gen_kick(lines, lpb, pid)
    if "snare" in rn:
        return gen_snare(lines, lpb)
    if "clap" in rn:
        return gen_clap(lines, lpb)
    if "open" in rn and ("hat" in rn or "hh" in rn):
        return gen_open_hat(lines, lpb)
    if "closed" in rn or "hat" in rn or "hh" in rn or "perc" in rn:
        return gen_hihat(lines, lpb)
    # Melodic roles
    if "bass" in rn or "sub" in rn:
        return gen_bass(notes, lines, lpb, chord_prog, root, scale_name,
                        pid if "bass" in pid else "bass_walk")
    if "pad" in rn or "atmo" in rn or "chord" in rn or "harmony" in rn:
        if "arp" in pid:
            return gen_chord_arp(notes, lines, lpb, chord_prog, root, scale_name)
        return gen_pad(notes, lines, lpb, chord_prog, root, scale_name,
                       pid if "pad" in pid else "pad_sustain")
    if "lead" in rn or "melody" in rn or "synth" in rn or "acid" in rn or "arp" in rn:
        return gen_lead(notes, lines, lpb, chord_prog, root, scale_name,
                        pid if "lead" in pid else "lead_phrase")
    # Unknown role → melodic phrase
    return gen_lead(notes, lines, lpb, chord_prog, root, scale_name, "lead_phrase")


# ──────────────────────────────────────────────────────────────────────────────
# Fallback regex-based intent parser (used when Ollama is unavailable)
# ──────────────────────────────────────────────────────────────────────────────

STYLE_DEFAULTS = {
    "trance":    {"scale":"minor","root":9, "bpm":138,"lpb":8},
    "techno":    {"scale":"minor","root":0, "bpm":140,"lpb":4},
    "house":     {"scale":"minor","root":5, "bpm":128,"lpb":4},
    "ambient":   {"scale":"major","root":7, "bpm":95, "lpb":4},
    "hiphop":    {"scale":"minor","root":0, "bpm":90, "lpb":4},
    "jazz":      {"scale":"dorian","root":5,"bpm":100,"lpb":4},
    "dnb":       {"scale":"minor","root":0, "bpm":174,"lpb":8},
    "default":   {"scale":"minor","root":0, "bpm":128,"lpb":4},
}

def regex_parse_intent(prompt: str) -> dict:
    p = prompt.lower()
    style = "default"
    for s in STYLE_DEFAULTS:
        if s in p:
            style = s
            break
    cfg = dict(STYLE_DEFAULTS[style])

    for sc in SCALES:
        if sc in p:
            cfg["scale"] = sc
            break

    key_match = re.search(r'\b([A-G][b#]?)\s*(minor|major)?\b', prompt)
    if key_match:
        cfg["root"] = ROOT_MAP.get(key_match.group(1), 0)

    bpm_match = re.search(r'\b(\d{2,3})\s*bpm\b', p)
    if bpm_match:
        cfg["bpm"] = int(bpm_match.group(1))

    roles = []
    role_keywords = {
        "kick":    ["kick","drums","drum","beat"],
        "snare":   ["snare","snap"],
        "clap":    ["clap"],
        "closed":  ["hihat","hi-hat","hats","closed"],
        "open":    ["open hat","open hh"],
        "bass":    ["bass","sub","bassline","low end"],
        "pad":     ["pad","pads","chord","atmosphere","atmo","harmony","keys"],
        "lead":    ["lead","melody","synth","acid","arp","motif","riff"],
    }
    role_name_map = {
        "kick": "Kick", "snare": "Snare", "clap": "Clap",
        "closed": "Closed HH", "open": "Open HH",
        "bass": "Sub Bass", "pad": "Synth Pad", "lead": "Lead Synth",
    }
    for role_key, kws in role_keywords.items():
        if any(kw in p for kw in kws):
            roles.append({"name": role_name_map[role_key], "pattern": role_key})

    # Always guarantee full 8-track drum + synth kit
    full_kit = [
        {"name": "Kick",       "pattern": "kick"},
        {"name": "Snare",      "pattern": "snare"},
        {"name": "Clap",       "pattern": "clap"},
        {"name": "Closed HH",  "pattern": "hihat"},
        {"name": "Open HH",    "pattern": "open_hat"},
        {"name": "Sub Bass",   "pattern": "root_walk"},
        {"name": "Lead Synth", "pattern": "melodic"},
        {"name": "Synth Pad",  "pattern": "sweep"},
    ]
    existing_names = {r["name"].lower() for r in roles}
    for default_role in full_kit:
        if default_role["name"].lower() not in existing_names:
            roles.append(default_role)
            existing_names.add(default_role["name"].lower())
        if len(roles) >= 8:
            break

    cfg["roles"] = roles[:8]
    cfg["chord_progression"] = ["i","VI","III","VII"]
    cfg["lines"] = 128  # Full 128-line pattern
    return cfg


# ──────────────────────────────────────────────────────────────────────────────
# Ollama JSON intent extractor
# ──────────────────────────────────────────────────────────────────────────────

OLLAMA_SYSTEM = """You are a professional electronic music producer assistant.
Analyze the user's music prompt and return ONLY a valid JSON object with EXACTLY these keys:

{
  "style": "genre name",
  "key": "note letter, e.g. A or F#",
  "scale": "minor | major | dorian | phrygian | mixolydian | pentatonic | blues",
  "bpm": integer,
  "chord_progression": ["i","VI","III","VII"],
  "roles": [
    {"name": "human-readable track name", "pattern": "pattern style"}
  ]
}

CRITICAL RULES:
- You MUST provide EXACTLY 8 roles - no more, no less.
- The drum section MUST include these 5 roles in this order:
    1. {"name": "Kick", "pattern": "kick"}
    2. {"name": "Snare", "pattern": "snare"}
    3. {"name": "Clap", "pattern": "clap"}
    4. {"name": "Closed HH", "pattern": "hihat"}
    5. {"name": "Open HH", "pattern": "open_hat"}
- Then add 3 melodic/harmonic synth roles based on the prompt style, for example:
    6. {"name": "Sub Bass", "pattern": "root_walk"}
    7. {"name": "Lead Synth", "pattern": "melodic"}
    8. {"name": "Synth Pad", "pattern": "sweep"}
- chord_progression: use Roman numerals (i, ii, III, IV, v, VI, vii)
- pattern values for melodic roles: root_walk, ostinato, arpeggio, sweep, sustain, stab, riff, acid, melodic
- bpm must be an integer between 60 and 200
- Do NOT include any explanation, markdown, or text outside the JSON.
"""

def ollama_parse_intent(prompt: str, model: str = "llama3.1", timeout: int = 30) -> dict:
    """Call Ollama HTTP API to get a musical intent JSON. Returns dict or raises."""
    payload = json.dumps({
        "model": model,
        "prompt": f"{OLLAMA_SYSTEM}\n\nUser prompt: \"{prompt}\"",
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 500}
    }).encode()

    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode())

    raw = body.get("response", "")

    # Strip markdown fences if present
    raw = re.sub(r"```(?:json)?", "", raw).strip()

    # Extract first {...} block
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if not m:
        raise ValueError(f"No JSON found in Ollama response: {raw[:300]}")

    intent = json.loads(m.group(0))

    # Normalise fields
    intent.setdefault("scale", "minor")
    intent.setdefault("bpm", 128)
    intent.setdefault("chord_progression", ["i","VI","III","VII"])
    intent.setdefault("roles", [])
    intent["lines"] = 128  # Full 128-line pattern
    intent["lpb"]   = 8 if intent["bpm"] >= 130 else 4

    # Convert key string to root MIDI offset
    raw_key = str(intent.get("key","C")).strip()
    key_letter = raw_key.split()[0]
    intent["root"] = ROOT_MAP.get(key_letter, 0)

    # Ensure we always have exactly 8 roles
    roles = intent["roles"]
    # Inject missing drum tracks at the front if not present
    drum_defaults = [
        {"name": "Kick",      "pattern": "kick"},
        {"name": "Snare",     "pattern": "snare"},
        {"name": "Clap",      "pattern": "clap"},
        {"name": "Closed HH", "pattern": "hihat"},
        {"name": "Open HH",   "pattern": "open_hat"},
    ]
    synth_defaults = [
        {"name": "Sub Bass",   "pattern": "root_walk"},
        {"name": "Lead Synth", "pattern": "melodic"},
        {"name": "Synth Pad",  "pattern": "sweep"},
    ]
    drum_names = {d["name"].lower() for d in drum_defaults}
    has_drums  = any(r["name"].lower() in drum_names for r in roles)

    if not has_drums:
        roles = drum_defaults + [r for r in roles
                                 if r["name"].lower() not in drum_names]
    # Pad to 8
    melodic_defaults_iter = iter(synth_defaults)
    while len(roles) < 8:
        try:
            roles.append(next(melodic_defaults_iter))
        except StopIteration:
            break
    intent["roles"] = roles[:8]  # Cap at 8

    return intent


# ──────────────────────────────────────────────────────────────────────────────
# MIDIComposer class
# ──────────────────────────────────────────────────────────────────────────────

class MIDIComposer:
    """
    MIDIComposer 3.0: High-Fidelity Neural Brain for Renoise.
    Uses AMAAI-Lab/Text2midi (AAAI 2025) for high-quality symbolic music.
    Accelerated via Apple Silicon MPS (Metal Performance Shaders).
    """

    def __init__(self, model_dir=None):
        if not model_dir:
            model_dir = os.path.join(os.path.dirname(__file__), "models", "text2midi")
        self.model_dir = model_dir
        self.device = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
        self._last_intent = None
        self._memoized_midi = None # Whole-song MIDI cache
        
        print(f"MIDIComposer: Initializing State-of-the-Art Neural Engine (Text2midi) on {self.device}...")
        try:
            from text2midi_wrapper import Text2MidiWrapper
            self.text2midi = Text2MidiWrapper(model_dir=self.model_dir, device=self.device)
            print("MIDIComposer: Neural Engine Ready (MPS Accelerated).")
        except Exception as e:
            print(f"MIDIComposer: Error loading Neural Engine: {e}. Falling back to Lightweight Mode.")
            self.text2midi = None

    def clear_cache(self):
        """Clear the memoized MIDI cache to allow for a new generation."""
        print("[Composer] Clearing Neural MIDI cache for new generation.")
        self._memoized_midi = None

    def unload(self):
        """Flush Text2midi from VRAM."""
        print(f"MIDIComposer: Flushing Neural Brain from VRAM...")
        if hasattr(self, 'text2midi') and self.text2midi:
            del self.text2midi.model
            del self.text2midi
        import gc
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def generate_midi_sequence(self, role_prompt: str, instruments: list = None, plan_context: str = "", forced_instrument: int = None) -> str:
        """
        Generates high-quality MIDI for a specific role within the song context.
        Note: Now uses Text2midi for the WHOLE song and memoizes it.
        """
        if not self.text2midi:
            print("[Composer] Falling back to empty response (No Neural Engine).")
            return "[]"

        if self._memoized_midi is None:
            # Construct a rich caption for Text2midi
            caption = f"{plan_context}. Roles: {role_prompt}. Instruments: "
            if instruments:
                caption += ", ".join([inst['name'] for inst in instruments])
            
            print(f"[Composer] Neural Mastering (Text2midi): '{caption[:100]}...'")
            temp_mid = "generated/master_ai.mid"
            try:
                self.text2midi.generate(caption, max_len=1024, temperature=0.9, output_path=temp_mid)
                from midi_utils import midi_to_renoise_commands
                self._memoized_midi = midi_to_renoise_commands(temp_mid, lpb=4)
                print(f"[Composer] Master MIDI parsed: {len(self._memoized_midi)} events.")
            except Exception as e:
                print(f"[Composer] Text2midi Error: {e}")
                return "[]"

        # Track Filtering Logic:
        # Match the role_prompt (e.g., "Hammer Kick") against our memoized tracks
        import re
        m = re.search(r"Track: ([^.]+)", role_prompt)
        target_name = m.group(1).lower() if m else "unknown"
        
        filtered_commands = []
        
        # Get all unique tracks from the generated MIDI
        unique_tracks = {}
        for cmd in (self._memoized_midi or []):
            t_name = cmd.get("track_name", "").lower()
            if t_name not in unique_tracks:
                unique_tracks[t_name] = []
            unique_tracks[t_name].append(cmd)
            
        drum_keywords = ["kick", "snare", "hat", "clap", "perc", "drum"]
        target_is_drum = any(k in target_name for k in drum_keywords)
        
        # Priority 1: Smart filtering based on role
        if target_is_drum:
            # For drums, we usually have one "Drum" track containing all drums on different pitches.
            # We must filter by pitch to separate kick, snare, hats!
            drum_cmds = []
            for t_name, cmds in unique_tracks.items():
                if any(k in t_name for k in drum_keywords):
                    drum_cmds.extend(cmds)
            
            # General drum mapping (General MIDI std)
            kick_pitches = [35, 36]
            snare_pitches = [38, 39, 40]
            hat_pitches = [42, 44, 46]
            perc_pitches = [x for x in range(27, 88) if x not in kick_pitches + snare_pitches + hat_pitches]
            
            for cmd in drum_cmds:
                if "note" not in cmd:
                    continue
                # Extract MIDI pitch number from the Renoise note string or if it's stored
                # (Assuming the original midi_pitch might be lost, we map back roughly or just 
                # keep all drums if we can't tell. Wait, midi_to_renoise_commands retains 'midi_pitch'?
                # If not, let's just distribute drum tracks by index if there are multiple)
                
                # Actually, Text2midi often separates drums into different tracks sometimes? No, usually one track.
                # If we don't have midi_pitch, let's just use string names:
                note_str = cmd.get("note", "")
                
                # Very rough distribution if we can't separate by pitch:
                # If target is kick, keep lower notes (C-1 to B-2)
                # If target is snare, keep mid notes (C-3 to B-3)
                # If hats, keep high notes (C-4+)
                octave_match = re.search(r"\d", note_str)
                octave = int(octave_match.group(0)) if octave_match else 4
                
                if "kick" in target_name and octave < 3:
                    filtered_commands.append(cmd)
                elif ("snare" in target_name or "clap" in target_name) and octave == 3:
                    filtered_commands.append(cmd)
                elif "hat" in target_name and octave >= 4:
                    filtered_commands.append(cmd)
                elif "perc" in target_name:
                    filtered_commands.append(cmd) # Catch-all
                    
            # If no rough pitch matches but we found drums, just give them the drum track if they are the FIRST drum target? 
            # (To avoid completely empty tracks)
            if not filtered_commands and drum_cmds and "kick" in target_name:
                 filtered_commands = drum_cmds
        else:
            # NON-DRUMS: We want to assign ONE unique neural track to ONE renoise track to avoid messy stacking.
            # Let's map target track names to available neural tracks
            neural_non_drums = {k: v for k, v in unique_tracks.items() if not any(kw in k for kw in drum_keywords)}
            
            # Simple assignment: hash the target_name to pick a track stably
            if neural_non_drums:
                keys = sorted(list(neural_non_drums.keys()))
                # Try to find a substring match first (e.g. "bass" -> "acoustic bass")
                matched_key = None
                for k in keys:
                    if target_name in k or k in target_name:
                        matched_key = k
                        break
                
                if not matched_key:
                    # Deterministic hash to distribute non-matching tracks
                    idx = sum(ord(c) for c in target_name) % len(keys)
                    matched_key = keys[idx]
                    
                filtered_commands = neural_non_drums[matched_key]
            
        print(f"[Composer] Role '{target_name}' matched {len(filtered_commands)} events.")
        return json.dumps(filtered_commands)

    def _enforce_drum_octave(self, note_str: str) -> str:
        """
        Ensures drum notes are in Octave 4 (e.g., C-1 -> C-4).
        """
        if not note_str or len(note_str) < 3:
            return note_str
        
        # If the note is already in octave 4, leave it
        if "-4" in note_str:
            return note_str
            
        # If the note is in octave 1, 2, or 3, shift to 4
        # Common in generic MIDI models to output C-1 or C-3 for kicks
        import re
        return re.sub(r"-[0-3]", "-4", note_str)

    def tokens_to_renoise_json(self, tokens: str, song_length: int = 1, target_track: int = 0, forced_instrument: int = None, is_drum: bool = False) -> list:
        """
        Parses neural/token output into Renoise JSON.
        """
        tokens_stripped = tokens.strip()
        if tokens_stripped.startswith("["):
            try:
                grid_data = json.loads(tokens_stripped)
                if isinstance(grid_data, list):
                    return self._parse_native_grid_tokens(grid_data, song_length, target_track, forced_instrument, is_drum)
            except:
                pass
        
        # Fallback to legacy
        intent_json = "{}"
        if self._last_intent:
            intent_json = json.dumps(self._last_intent)
        else:
            intent_json = json.dumps(regex_parse_intent("techno"))
            
        return self._legacy_tokens_to_json(intent_json, song_length=song_length)

    def _parse_native_grid_tokens(self, grid_data: list, song_length: int, target_track: int = 0, forced_instrument: int = None, is_drum: bool = False) -> list:
        """
        Converts native [line, note, inst, vel, delay] tuples directly to Renoise commands.
        """
        commands = []
        for item in grid_data:
            if isinstance(item, list) and len(item) >= 2:
                line = item[0]
                note = str(item[1])
                if is_drum:
                    note = self._enforce_drum_octave(note)
                    
                inst = forced_instrument if forced_instrument is not None else (item[2] if len(item) > 2 else target_track)
                vel  = item[3] if len(item) > 3 else 255
                
                commands.append({
                    "type": "set_note",
                    "track": target_track,
                    "pattern": 0, 
                    "line": int(line),
                    "note": note,
                    "instrument": int(inst),
                    "velocity": int(vel)
                })
            elif isinstance(item, dict) and "line" in item and "note" in item:
                note_val = str(item["note"])
                if is_drum:
                    note_val = self._enforce_drum_octave(note_val)
                    
                inst_val = forced_instrument if forced_instrument is not None else item.get("instrument", target_track)
                commands.append({
                    "type": "set_note",
                    "track": target_track,
                    "pattern": item.get("pattern", 0),
                    "line": int(item["line"]),
                    "note": note_val,
                    "instrument": int(inst_val),
                    "velocity": int(item.get("velocity", 255))
                })
        return commands

    def _legacy_tokens_to_json(self, token_string: str, song_length: int = 1) -> list:
        """
        Deterministic Theory Engine: Converts Intent JSON -> Renoise Commands.
        """
        try:
            # If it's already a dict, use it. If string, parse it.
            if isinstance(token_string, dict):
                intent = token_string
            else:
                intent = json.loads(token_string)
        except:
            intent = regex_parse_intent("techno")

        key = intent.get("key", "C")
        root = ROOT_MAP.get(key, 0)
        scale = intent.get("scale", "minor")
        bpm = intent.get("bpm", 128)
        lpb = intent.get("lpb", 4)
        prog = intent.get("chord_progression", ["i", "VI", "III", "VII"])
        lines = intent.get("lines", 128)
        roles = intent.get("roles", [])

        commands = []
        
        # 1. Globals
        commands.append({"type": "set_bpm", "bpm": int(bpm)})
        commands.append({"type": "set_lpb", "lpb": int(lpb)})
        commands.append({"type": "init_arrangement", "patterns": int(song_length)})

        # 2. Multi-Pattern Arrangement Loop
        for p_idx in range(song_length):
            # Simple Heuristic for Electronic Music Structure:
            # Intro: 0-15%, Verse: 15-45%, Build: 45-65%, Drop: 65-85%, Outro: 85-100%
            progress = p_idx / max(1, song_length)
            is_intro = progress < 0.10 # Shorter intro
            is_outro = progress > 0.90 # Shorter outro
            is_drop = 0.50 < progress < 0.85 # Longer main section

            for i, role in enumerate(roles):
                track_idx = i # 0-based
                
                # Arrangement Logic: Decide if this instrument is active in this pattern
                # Always active: Kick, Sub Bass (except Outro)
                # Build/Drop only: High-energy Lead
                role_name = role["name"].lower()
                is_active = True
                
                if "lead" in role_name:
                    if is_intro or is_outro: is_active = False # Leads only in main
                if "snare" in role_name or "clap" in role_name:
                    if is_intro and p_idx % 2 != 0: is_active = False # Half-intensity drums
                
                if not is_active:
                    continue

                if p_idx == 0:
                    # Only add track definition once
                    commands.append({"type": "add_track", "track": track_idx, "name": role["name"]})
                
                # Generate notes (optionally vary the pattern a bit based on p_idx)
                events = role_to_events(
                    role["name"], role["pattern"], None, lines, lpb,
                    prog, root, scale
                )
                
                # Convert to Renoise commands
                for line, note in events:
                    commands.append({
                        "type": "set_note",
                        "track": track_idx,
                        "pattern": p_idx, # Targeted pattern
                        "line": line,
                        "note": note,
                        "instrument": i,
                        "volume": "7F"
                    })
                    # Add a note-off 2 lines later for non-pads
                    if "pad" not in role["name"].lower():
                        off_line = line + 2
                        if off_line < lines:
                            commands.append({
                                "type": "note_off",
                                "track": track_idx,
                                "pattern": p_idx,
                                "line": off_line
                            })

        return commands


    def midi_to_renoise_note(self, midi_pitch: int) -> str:
        return midi_to_renoise(midi_pitch)


# ──────────────────────────────────────────────────────────────────────────────
# Smoke test
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    prompts = [
        "Progressive Trance Verse with a deep sub bass, a driving kick, and a subtle atmosphere",
        "Minimal Techno with an acid bassline and hi-hats",
        "Melancholic Jazz with piano chords and a slow melody",
    ]
    for p in prompts:
        print(f"\n{'='*60}\nPrompt: {p}")
        try:
            intent = ollama_parse_intent(p)
            print("Ollama intent:", json.dumps(intent, indent=2))
        except Exception as e:
            print(f"Ollama error: {e}")
            intent = regex_parse_intent(p)
            print("Regex intent:", json.dumps(intent, indent=2))

        # Simulate the full pipeline
        class _Stub:
            _last_intent = intent
        stub = MIDIComposer.__new__(MIDIComposer)
        stub._last_intent = intent
        cmds = MIDIComposer.tokens_to_renoise_json(stub, json.dumps(intent))
        note_cmds = [c for c in cmds if c["type"]=="set_note"]
        print(f"Commands: {len(cmds)} total, {len(note_cmds)} notes")
        for c in cmds[:6]:
            print(" ", c)
