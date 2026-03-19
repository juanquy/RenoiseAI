import os
from huggingface_hub import hf_hub_download
from transformers import T5Tokenizer

def download():
    repo_id = "amaai-lab/text2midi"
    
    print(f"Downloading Text2midi weights from {repo_id}...")
    # Download the model.bin file
    hf_hub_download(repo_id=repo_id, filename="pytorch_model.bin", local_dir="ai_server/models/text2midi")
    
    # Download the vocab_remi.pkl file
    hf_hub_download(repo_id=repo_id, filename="vocab_remi.pkl", local_dir="ai_server/models/text2midi")
    
    print("Pre-fetching T5 Tokenizer...")
    T5Tokenizer.from_pretrained("google/flan-t5-base", cache_dir="ai_server/models/huggingface_cache")
    
    print("All weights downloaded successfully.")

if __name__ == "__main__":
    download()
