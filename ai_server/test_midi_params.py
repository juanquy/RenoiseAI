import torch
from midi_composer import MIDIComposer
composer = MIDIComposer()
prompt = "Melodic Progressive House with uplifting pads and a steady drive. PIECE_START <note-on_0_"

inputs = composer.tokenizer(prompt, return_tensors="pt").to(composer.device)
with torch.inference_mode():
    outputs = composer.model.generate(
        **inputs, 
        max_new_tokens=100,
        do_sample=True,
        temperature=0.6,
        top_p=0.95
    )

decoded = composer.tokenizer.decode(outputs[0], skip_special_tokens=False)
print("RAW OUTPUT:")
print(repr(decoded))
print("---")
cmds = composer.tokens_to_renoise_json(decoded)
print(f"Generated {len(cmds)} commands.")
