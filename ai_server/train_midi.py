import os
import glob
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments, Trainer, DataCollatorForLanguageModeling, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from datasets import Dataset
import zipfile
import xml.etree.ElementTree as ET

# Configuration
MODEL_ID = "slseanwu/MIDI-LLM_Llama-3.2-1B"
DATASET_PATH = "/media/juanquy/Dev/dataset/XRNS-DataSet/"
OUTPUT_DIR = "./renoise_midi_model_lora"

def renoise_to_midi_pitch(renoise_note):
    """Converts 'C-4' or 'D#4' to MIDI pitch (e.g., 60)."""
    if not renoise_note or renoise_note == '---' or renoise_note == 'OFF':
        return None
    
    note_map = {
        "C-": 0, "C#": 1, "D-": 2, "D#": 3, "E-": 4, "F-": 5, 
        "F#": 6, "G-": 7, "G#": 8, "A-": 9, "A#": 10, "B-": 11
    }
    try:
        name = renoise_note[:2]
        octave = int(renoise_note[2:])
        # MIDI-LLM standard is usually 60 for C4 (Octave 4).
        return (octave + 1) * 12 + note_map[name]
    except:
        return None

def extract_xrns_to_tokens(xrns_path):
    """Converts a Renoise song into a linear string of MIDI-LLM style tokens, with text prompting!"""
    import os
    # Skip empty/corrupt files
    if not os.path.exists(xrns_path) or os.path.getsize(xrns_path) < 100:
        return ""
        
    tokens = []
    try:
        with zipfile.ZipFile(xrns_path, 'r') as z:
            if 'Song.xml' not in z.namelist():
                return ""
            with z.open('Song.xml') as f:
                root = ET.parse(f).getroot()
                
                # --- Map Metadata to English Prompt ---
                bpm = root.findtext('.//BeatsPerMin', default='120')
                lpb = root.findtext('.//LinesPerBeat', default='4')
                
                # Renoise stores song name under <GlobalSongData> -> <SongName> typically
                # Or sometimes <Name> under root. Let's try both, or fallback to file name.
                name = root.findtext('.//GlobalSongData/SongName')
                if not name:
                    name = root.findtext('.//Name', default='Untitled').strip()
                
                if not name or name == 'Untitled':
                    name = os.path.basename(xrns_path).replace('.xrns', '').replace('_', ' ')
                
                # Get the first 5 instrument names to give it some musical identity
                instruments = root.findall('.//Instrument/Name')
                inst_names = [i.text.strip() for i in instruments if i.text and i.text.strip()]
                inst_str = ", ".join(inst_names[:5]) if inst_names else "synthesizers"
                
                caption = f"A Renoise tracker song titled '{name}' playing at {bpm} BPM with LPB {lpb}. Features instruments like {inst_str}."
                system_prompt = f"You are a world-class composer. Please compose some music according to the following description: {caption} "
                
                tokens.append(system_prompt)
                tokens.append("PIECE_START")
                
                patterns = root.find('.//Patterns')
                if patterns is None: return ""
                
                # We'll process the first 8 patterns for more context
                for pat_idx, pattern in enumerate(patterns.findall('Pattern')[:8]):
                    tracks = pattern.find('Tracks')
                    if tracks is None: continue
                    for trk_idx, track in enumerate(tracks.findall('PatternTrack')):
                        lines = track.find('Lines')
                        if lines is None: continue
                        for line in lines.findall('Line'):
                            # Simple time mapping: 1 line = 120 MIDI ticks
                            time_step = 120 
                            
                            for nc in line.findall('.//NoteColumn'):
                                note = nc.findtext('Note')
                                pitch = renoise_to_midi_pitch(note)
                                if pitch:
                                    tokens.append(f"NOTE_ON {trk_idx} {pitch}")
                                    tokens.append(f"TIME {time_step}")
                                elif note == 'OFF':
                                    tokens.append(f"NOTE_OFF {trk_idx} 60")
                
        # If no notes were matched
        if len(tokens) <= 2:
            return ""
            
        return " ".join(tokens) + " PIECE_END"
    except Exception:
        return ""

def prepare_dataset():
    from tqdm import tqdm
    print(f"Scanning {DATASET_PATH} for XRNS files...")
    files = glob.glob(os.path.join(DATASET_PATH, "**/*.xrns"), recursive=True)
    print(f"Found {len(files)} files. Extracting tokens...")
    
    data = []
    # Using tqdm for a visual progress bar in the terminal
    for i, f in enumerate(tqdm(files, desc="Ingesting Renoise Songs")):
        t = extract_xrns_to_tokens(f)
        if t: 
            data.append({"text": t})
        
        # Periodic status heartbeat
        if i % 50 == 0 and i > 0:
            print(f" [HEARTBEAT] Processed {i}/{len(files)} files. Current memory cleanup...")
    
    print(f"Extraction complete. Total useful sequences: {len(data)}")
    return Dataset.from_list(data)

def train():
    from transformers import AutoConfig
    dataset = prepare_dataset()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    tokenizer.pad_token = tokenizer.eos_token
    
    def tokenize_function(examples):
        return tokenizer(examples["text"], truncation=True, padding="max_length", max_length=512)

    tokenized_datasets = dataset.map(tokenize_function, batched=True, remove_columns=["text"])

    print(f"Loading configuration for {MODEL_ID}...")
    config = AutoConfig.from_pretrained(MODEL_ID)
    
    print(f"Loading model {MODEL_ID} (this may take a few minutes)...")
    bnb_config = BitsAndBytesConfig(
        load_in_8bit=True
    )
    
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, 
        config=config,
        quantization_config=bnb_config, 
        device_map="auto"
    )
    model = prepare_model_for_kbit_training(model)

    config = LoraConfig(
        r=16, 
        lora_alpha=32, 
        target_modules=["q_proj", "v_proj"], 
        lora_dropout=0.05, 
        bias="none", 
        task_type="CAUSAL_LM"
    )
    model = get_peft_model(model, config)

    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        num_train_epochs=3,
        logging_steps=10,
        save_strategy="epoch",
        push_to_hub=False,
        report_to="none"
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_datasets,
        data_collator=DataCollatorForLanguageModeling(tokenizer, mlm=False),
    )

    print("Starting Fine-Tune...")
    trainer.train()
    model.save_pretrained(OUTPUT_DIR)
    print(f"Fine-tune complete. Model saved to {OUTPUT_DIR}")

if __name__ == "__main__":
    train()
