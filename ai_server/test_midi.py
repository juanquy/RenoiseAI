from midi_composer import MIDIComposer
composer = MIDIComposer()
prompt = "Melodic Progressive House with uplifting pads and a steady drive."
print(f"Generating for prompt: {prompt}")
out = composer.generate_midi_sequence(prompt, max_new_tokens=50)
print("RAW OUTPUT:")
print(repr(out))
print("---")
cmds = composer.tokens_to_renoise_json(out)
print(f"Generated {len(cmds)} commands.")
