import os
import sys
import pickle
import torch
import torch.nn as nn
from transformers import T5Tokenizer

# Add the Text2midi_Repo to the path so we can import 'model'
sys.path.append(os.path.join(os.path.dirname(__file__), "Text2midi_Repo"))
from model.transformer_model import Transformer

class Text2MidiWrapper:
    def __init__(self, model_dir=None, device=None):
        if not model_dir:
            model_dir = os.path.join(os.path.dirname(__file__), "models", "text2midi")
        self.model_dir = model_dir
        if device:
            self.device = device
        else:
            if torch.cuda.is_available():
                self.device = 'cuda'
            elif torch.backends.mps.is_available():
                self.device = 'mps'
            else:
                self.device = 'cpu'
        
        print(f"Text2MidiWrapper: Using device {self.device}")
        
        # Paths
        self.model_path = os.path.join(self.model_dir, "pytorch_model.bin")
        self.vocab_path = os.path.join(self.model_dir, "vocab_remi.pkl")
        
        # Load vocab/tokenizer
        with open(self.vocab_path, "rb") as f:
            self.r_tokenizer = pickle.load(f)
        
        vocab_size = len(self.r_tokenizer)
        print(f"Text2MidiWrapper: Vocab size {vocab_size}")
        
        # Initialize model (Mapping correctly to weights: 1024 feedforward, 2048 max_len)
        self.model = Transformer(
            n_vocab=vocab_size, 
            d_model=768, 
            nhead=8, 
            dim_feedforward=1024, 
            num_decoder_layers=18, 
            max_len=2048, 
            use_moe=False, 
            num_experts=8, 
            device=self.device
        )
        
        # Load weights
        print(f"Text2MidiWrapper: Loading weights from {self.model_path}...")
        self.model.load_state_dict(torch.load(self.model_path, map_location=self.device))
        self.model.eval()
        
        # T5 Tokenizer for captions
        self.tokenizer = T5Tokenizer.from_pretrained("google/flan-t5-base")
        print("Text2MidiWrapper: Ready.")

    def generate(self, prompt, max_len=2000, temperature=1.0, output_path="generated/output.mid"):
        print(f"Text2MidiWrapper: Generating for prompt: '{prompt[:50]}...'")
        
        inputs = self.tokenizer(prompt, return_tensors='pt', padding=True, truncation=True)
        # Text2midi expectations for padding/ids
        input_ids = nn.utils.rnn.pad_sequence(inputs.input_ids, batch_first=True, padding_value=0).to(self.device)
        attention_mask = nn.utils.rnn.pad_sequence(inputs.attention_mask, batch_first=True, padding_value=0).to(self.device)
        
        with torch.no_grad():
            output = self.model.generate(input_ids, attention_mask, max_len=max_len, temperature=temperature)
            
        output_list = output[0].tolist()
        generated_midi = self.r_tokenizer.decode(output_list)
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        generated_midi.dump_midi(output_path)
        print(f"Text2MidiWrapper: MIDI dumped to {output_path}")
        return output_path

if __name__ == "__main__":
    # Smoke test
    wrapper = Text2MidiWrapper()
    wrapper.generate("A cinematic orchestral piece in C minor, slow tempo, melancholic.")
