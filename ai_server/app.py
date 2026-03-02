from flask import Flask, request, jsonify, send_file
import os
import threading
import subprocess
import zipfile
import shutil
import time
import torch
import torchaudio
from basic_pitch.inference import predict
from audiocraft.models import MusicGen
from audiocraft.data.audio import audio_write
from functools import wraps

app = Flask(__name__)

# Security: Set your secret API key here (or load from environment variable)
# In production, use os.environ.get('RENOISE_AI_TXT_KEY', 'default-secret-key-123')
SECRET_API_KEY = "my_super_secret_proxmox_key"

UPLOAD_FOLDER = 'uploads'
GENERATED_FOLDER = 'generated'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(GENERATED_FOLDER, exist_ok=True)

# Global specific lock to ensure only one heavy GPU task runs at a time
gpu_lock = threading.Lock()

def require_api_key(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Look for the API key in headers
        provided_key = request.headers.get('X-API-Key')
        if not provided_key or provided_key != SECRET_API_KEY:
            return jsonify({"error": "Unauthorized. Invalid or missing API Key (X-API-Key header required)."}), 401
        return f(*args, **kwargs)
    return decorated_function

# Load Models (Lazy loading or Startup loading?)
# Let's load MusicGen on startup (it takes the longest).
print("AI Suite: Loading MusicGen Model (this may take a minute)...")
model_size = 'small'
musicgen_model = None

try:
    musicgen_model = MusicGen.get_pretrained(f'facebook/musicgen-{model_size}')
    musicgen_model.set_generation_params(duration=10)
    print("AI Suite: MusicGen Loaded.")
except Exception as e:
    print(f"AI Suite: Error loading MusicGen: {e}")

@app.route('/status', methods=['GET'])
def status():
    # Status endpoint doesn't require auth so client can check if server is up
    return jsonify({
        "status": "running",
        "message": "Renoise AI Backend Ready",
        "gpu_available": torch.cuda.is_available(),
        "model_loaded": musicgen_model is not None,
        "auth_required": True
    })

@app.route('/transcribe', methods=['POST'])
@require_api_key
def transcribe():
    """
    Endpoint to transcribe audio to MIDI notes using Basic Pitch.
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)
    
    print(f"Processing transcription for: {filepath}")
    
    # Process
    try:
        with gpu_lock:
            # basic-pitch inference
            # predict returns: model_output, midi_data, note_events
            # note_events is a list of tuples: (start_time, end_time, pitch, amplitude, list of pitch bends)
            _, _, note_events = predict(filepath)
            
        notes_response = []
        for n in note_events:
            start_time = n[0]
            end_time = n[1]
            pitch = int(n[2])
            velocity = int(n[3] * 127)
            
            notes_response.append({
                "start": start_time,
                "duration": end_time - start_time,
                "note": pitch,
                "velocity": velocity
            })
            
        # Cleanup
        if os.path.exists(filepath):
            os.remove(filepath)
            
        return jsonify({"notes": notes_response})
        
    except Exception as e:
        print(f"Error during transcription: {e}")
        return jsonify({"error": str(e)}), 500

def process_stems_and_notes(filepath, base_job_id, original_filename=""):
    job_dir = os.path.join(GENERATED_FOLDER, base_job_id)
    os.makedirs(job_dir, exist_ok=True)
    
    try:
        # 1. Run Demucs
        print("Running Demucs...")
        try:
            subprocess.run(["demucs", "-n", "htdemucs", "-o", job_dir, filepath], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Demucs GPU failed ({e}), retrying on CPU...")
            subprocess.run(["demucs", "-n", "htdemucs", "-d", "cpu", "-o", job_dir, filepath], check=True)
        
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        stems_dir = os.path.join(job_dir, "htdemucs", base_name)
        
        bass_path = os.path.join(stems_dir, "bass.wav")
        other_path = os.path.join(stems_dir, "other.wav")
        drums_path = os.path.join(stems_dir, "drums.wav")
        vocals_path = os.path.join(stems_dir, "vocals.wav")
        
        # 2. Run Basic Pitch
        print("Running Basic Pitch on stems...")
        def get_notes(p):
            import math
            if not os.path.exists(p): return []
            _, _, note_events = predict(p)
            notes_res = []
            for n in note_events:
                start_val = float(n[0])
                dur_val = float(n[1] - n[0])
                if math.isnan(start_val) or math.isinf(start_val): start_val = 0.0
                if math.isnan(dur_val) or math.isinf(dur_val): dur_val = 0.1
                
                notes_res.append({
                    "start": start_val,
                    "duration": dur_val,
                    "note": int(n[2]),
                    "velocity": int(n[3] * 127)
                })
            return notes_res
            
        bass_notes = get_notes(bass_path)
        melody_notes = get_notes(other_path)
        
        # 3. Create URLs
        outputs = {}
        host_url = request.host_url.rstrip('/')
        if original_filename:
            outputs["mix"] = f"{host_url}/download/{original_filename}"
            
        for stem in ["bass.wav", "other.wav", "drums.wav", "vocals.wav"]:
            src = os.path.join(stems_dir, stem)
            dst_name = f"{base_job_id}_{stem}"
            dst = os.path.join(GENERATED_FOLDER, dst_name)
            if os.path.exists(src):
                shutil.move(src, dst)
                outputs[stem.replace(".wav", "")] = f"{host_url}/download/{dst_name}"
        
        # Cleanup
        # We need to keep the original filepath (mix) and the moved stems for downloading.
        # Only cleanup the demucs intermediate job directory.
        if os.path.exists(job_dir):
            shutil.rmtree(job_dir, ignore_errors=True)
        
        return {
            "status": "success",
            "stems": outputs,
            "notes": {
                "bass": bass_notes,
                "melody": melody_notes
            }
        }
    except subprocess.CalledProcessError as e:
        print(f"Demucs Error: {e}")
        return {"error": "Demucs processing failed."}
    except Exception as e:
        print(f"Error during full transcription: {e}")
        return {"error": str(e)}

@app.route('/transcribe_full', methods=['POST'])
@require_api_key
def transcribe_full():
    """
    Endpoint to separate audio into stems (Demucs) and transcribe bass/melody.
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    safe_filename = "upload_" + str(int(time.time())) + ".wav"
    filepath = os.path.join(UPLOAD_FOLDER, safe_filename)
    file.save(filepath)
    
    job_id = f"job_{int(time.time())}"
    print(f"Processing Full Transcription for: {filepath}")
    
    with gpu_lock:
        result = process_stems_and_notes(filepath, job_id)
        
    if "error" in result:
        return jsonify(result), 500
    return jsonify(result)

@app.route('/generate_song', methods=['POST'])
@require_api_key
def generate_song():
    """
    Endpoint to generate a song/sample from text using MusicGen.
    """
    if musicgen_model is None:
        return jsonify({"error": "MusicGen model not loaded on server."}), 500

    data = request.json
    prompt = data.get('prompt', '')
    lyrics = data.get('lyrics', '')
    style = data.get('style', '')
    instrumental = data.get('instrumental', True)
    duration = int(data.get('duration', 8))
    
    # Validation
    duration = min(duration, 30) # Cap at 30s for safety
    
    print(f"Generating song: Style='{style}' Prompt='{prompt}' Lyrics='{lyrics}'")
    
    # Construct MusicGen prompt
    gen_prompt = prompt
    if style != "":
        gen_prompt = f"{style}, {prompt}"
        
    try:
        with gpu_lock:
            musicgen_model.set_generation_params(duration=duration)
            wav = musicgen_model.generate([gen_prompt]) 
            
            # Save generated WAV
            job_id = f"gen_{int(time.time())}"
            filename = f"{job_id}.wav"
            filepath = os.path.join(GENERATED_FOLDER, filename)
            
            audio_write(
                os.path.join(GENERATED_FOLDER, job_id), 
                wav[0].cpu(), 
                musicgen_model.sample_rate, 
                strategy="loudness", 
                loudness_compressor=True
            )
            
            # Process the generated WAV through Demucs and BasicPitch
            result = process_stems_and_notes(filepath, job_id, original_filename=filename)
            
        if "error" in result:
            return jsonify(result), 500
        return jsonify(result)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    return send_file(os.path.join(GENERATED_FOLDER, filename))
    
import time

if __name__ == '__main__':
    # Threaded=True is default for Flask, allowing concurrent requests 
    # (though we lock the GPU critical section)
    # Host needs to be 0.0.0.0 if we want external access (via Proxmox/Tunnel)
    app.run(host='0.0.0.0', port=5000, debug=False) 
