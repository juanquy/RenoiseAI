
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
For example, use {"type": "init_arrangement", "patterns": 8}, NOT {"patterns": [8]}.

RENOISE API SNIPPETS:
- Track LFO: `renoise.song().tracks[idx]:device(2):parameter(1).value = math.sin(line/16)`
- Pattern Morphing: Use the global `geometric_morph(track, pattern, mode)` helper.
- Automation: `renoise.song().patterns[p].tracks[t]:automation(p):add_point(line, value)`

OUTPUT FORMAT:
Always return a JSON object with a "plan" description and a "commands" list.

EXAMPLE: {
  "plan": "Dark Techno with increasing resonance LFO.",
  "commands": [
    {"type": "set_bpm", "bpm": 135},
    {"type": "execute_lua", "code": "-- Add a filter LFO to track 1\nlocal tr = renoise.song().tracks[1]\n..."}
  ]
}
"""

class AIConductor:
    def __init__(self, model="gemma3:12b"):
        self.model = model
        self.url = "http://localhost:11434/api/generate"

    def orchestrate(self, user_prompt, song_length=16):
        print(f"[Conductor] Planning ({song_length} segments): {user_prompt[:50]}...")
        
        prompt = f"{CONDUCTOR_SYSTEM_PROMPT}\n\n"
        prompt += f"SONG LENGTH: {song_length} patterns.\n"
        prompt += f"STRUCTURE: Organize the piece into logical Electronic Music sections (Intro, Verse, Build, Drop, Outro) across these {song_length} patterns.\n\n"
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
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                response_text = result.get("response", "{}")
                plan = json.loads(response_text)
                if not isinstance(plan, dict):
                    plan = {"plan": "Fallback (Invalid JSON type)", "commands": []}
                return plan
        except Exception as e:
            print(f"[Conductor] Error: {e}")
            return {"plan": "Fallback", "commands": []}
