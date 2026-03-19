import json
import os
import sys

# Add current dir to path
sys.path.append(os.path.dirname(__file__))

from midi_composer import MIDIComposer

def test():
    print("--- Starting End-to-End Neural Pipeline Test ---")
    composer = MIDIComposer()
    
    plan = "A dark industrial techno track with a heavy kick and metallic percussion."
    role = "Section: Intro. Track: Hammer Kick. Goal: 4-on-the-floor heavy kick."
    
    # Text2midi might take a while on first run
    print("Calling generate_midi_sequence (This will trigger Text2midi)...")
    result_json = composer.generate_midi_sequence(role_prompt=role, plan_context=plan)
    
    events = json.loads(result_json)
    print(f"Test Result: Received {len(events)} MIDI events for the 'Hammer Kick' role.")
    
    if len(events) > 0:
        print("SUCCESS: Neural Engine produced structured MIDI and filtered it!")
        print(f"Sample Event: {events[0]}")
    else:
        print("WARNING: No events matched. Check the filtering heuristic or Text2midi output.")

if __name__ == "__main__":
    test()
