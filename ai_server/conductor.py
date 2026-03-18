
import json
import urllib.request
import re

CONDUCTOR_SYSTEM_PROMPT = """
You are the "AI Conductor" for Renoise. You generate high-level musical structures and Renoise Lua code.
You orchestrate a specialized MIDI model that handles the notes.

YOUR CAPABILITIES:
1. init_arrangement(patterns): Setup the song timeline.
2. add_track(track, name): Create a track role.
3. execute_lua(code): Run arbitrary Renoise API code for effects, automation, or complex logic.
4. set_bpm(bpm), set_lpb(lpb).

CRITICAL: All numeric parameters (patterns, bpm, lpb, track indices, lines) MUST be integers, NOT arrays or tables. 

DYNAMIC TEMPLATING (STYLE-FIRST): 
- ANALYZE the musical style and create tracks that match it (e.g., for Industrial: 'Distorted Kick', 'Metal Clang'; for Ambient: 'Granular Pad', 'Ether Flow').
- AVOID generic 'Kick/Snare/HH' templates unless they are the perfect fit.
- Use CREATIVE track names that suggest timbre and role.

DRUM KIT & INSTRUMENT MAPPING: 
- If the user has an instrument named "Drums", "Kit", "Samples", or similar, multiple drum tracks (Kick, Snare, Hats) should mapping to that ONE `instrument_index`.
- DRUM RULE: For any drum element (Kick, Snare, Clap, Hats), always instruct the composition phase to use the 4th octave (e.g., C-4). 

OUTPUT FORMAT:
Always return a JSON object with:
- "plan": Overall description.
- "sections": List of { "name": "Intro", "start_pattern": 0, "end_pattern": 3, "description": "Atmospheric intro with focus on sub-bass" }
- "commands": List of structural commands (add_track, set_bpm, set_lpb, execute_lua).

EXAMPLE: {
  "plan": "Dark Industrial Techno track using user's VSTs and Drum Kit",
  "sections": [
    {"name": "Intro", "start_pattern": 0, "end_pattern": 3, "description": "Hammering kick at C-4 using slot 5"},
    {"name": "Build", "start_pattern": 4, "end_pattern": 7, "description": "Add industrial hats at C-4 using same slot 5"}
  ],
  "commands": [
    {"type": "set_bpm", "bpm": 135},
    {"type": "add_track", "track": 0, "name": "Hammer Kick", "instrument_index": 5},
    {"type": "add_track", "track": 1, "name": "Clang Hats", "instrument_index": 5}
  ]
}
"""

class AIConductor:
    def __init__(self, model="gemma3:12b"):
        self.model = model
        self.url = "http://localhost:11434/api/generate"

    def orchestrate(self, user_prompt, song_length=16, instruments=None):
        print(f"[Conductor] Planning ({song_length} segments): {user_prompt[:50]}...")
        
        prompt = f"{CONDUCTOR_SYSTEM_PROMPT}\n\n"
        prompt += f"SONG LENGTH: {song_length} patterns.\n"
        prompt += f"STRUCTURE: Organize the piece into logical Electronic Music sections (Intro, Verse, Build, Drop, Outro) across these {song_length} patterns.\n\n"
        
        if instruments:
            prompt += "AVAILABLE INSTRUMENTS (Renoise Song):\n"
            for inst in instruments:
                prompt += f"- Slot {inst.get('index')}: \"{inst.get('name')}\"\n"
            prompt += "\nTASK: Whenever possible, map your 'roles' to these existing instrument indices using the 'instrument_index' field in each command.\n\n"

        prompt += f"User Request: {user_prompt}"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.4}
        }
        
        try:
            req = urllib.request.Request(
                self.url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode())
                response_text = result.get("response", "{}")
                # Clean up any markdown
                response_text = re.sub(r"```json|```", "", response_text).strip()
                plan = json.loads(response_text)
                if not isinstance(plan, dict):
                    plan = {"plan": "Fallback (Invalid JSON type)", "commands": []}
                return plan
        except Exception as e:
            print(f"[Conductor] Error: {e}")
            return {"plan": "Fallback", "commands": []}
