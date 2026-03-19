from flask import Flask, request, jsonify, send_file
import os
import subprocess
import time
import json
from functools import wraps

app = Flask(__name__)

# Security: Set your secret API key here (or load from environment variable)
# In production, use os.environ.get('RENOISE_AI_TXT_KEY', 'default-secret-key-123')
SECRET_API_KEY = "my_super_secret_proxmox_key"

UPLOAD_FOLDER = 'uploads'
GENERATED_FOLDER = 'generated'
TASKS_FOLDER = 'tasks'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(GENERATED_FOLDER, exist_ok=True)
os.makedirs(TASKS_FOLDER, exist_ok=True)

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        provided_key = request.headers.get('X-API-Key')
        if not provided_key or provided_key != SECRET_API_KEY:
            return jsonify({"error": "Unauthorized. Invalid or missing API Key (X-API-Key header required)."}), 401
        return f(*args, **kwargs)
    return decorated_function

def save_new_task(task_id, task_data):
    filepath = os.path.join(TASKS_FOLDER, f"{task_id}.json")
    with open(filepath, 'w') as f:
        json.dump(task_data, f)

def strip_nulls(obj):
    """Recursively replace None with empty string/dict for Lua JSON compatibility."""
    if isinstance(obj, dict):
        return {k: strip_nulls(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [strip_nulls(item) for item in obj]
    if obj is None:
        return ""
    return obj

@app.route('/task_status/<task_id>', methods=['GET'])
def task_status(task_id):
    # Just read the JSON file produced by worker.py
    filepath = os.path.join(TASKS_FOLDER, f"{task_id}.json")
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            return jsonify(strip_nulls(data))
        except Exception:
            # File might be mid-write by the worker
            return jsonify({"status": "processing", "message": "Reading state...", "stems": {}, "notes": {}, "error": ""})
    return jsonify({"error": "Task not found"}), 404

@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        "status": "running",
        "message": "Renoise AI V2 Backend Ready (Decoupled Worker)",
        "gpu_available": True,
        "model_loaded": True, # Assume worker loads it
        "auth_required": True
    })



@app.route('/transcribe', methods=['POST'])
@require_api_key
def transcribe():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    safe_filename = "upload_stem_" + str(int(time.time())) + ".wav"
    filepath = os.path.join(UPLOAD_FOLDER, safe_filename)
    file.save(filepath)
    
    job_id = f"job_stem_{int(time.time())}"
    task_id = f"task_stem_{int(time.time())}"
    
    task_data = {
        "status": "pending",
        "message": "Queued for direct single stem MIDI extraction...",
        "stems": {},
        "notes": {},
        "error": "",
        "type": "transcribe",
        "filepath": filepath,
        "original_filename": file.filename,
        "job_id": job_id,
        "task_id": task_id,
        "host_url": request.host_url.rstrip('/')
    }
    save_new_task(task_id, task_data)
    
    return jsonify({"task_id": task_id, "status": "pending"})



@app.route('/compose_native_midi', methods=['POST'])
@require_api_key
def compose_native_midi():
    data = request.json
    
    # Extract prompt from Renoise's JSON format (messages array)
    prompt = data.get('prompt', '')
    if not prompt and 'messages' in data:
        for msg in reversed(data['messages']):
            if msg.get('role') == 'user':
                prompt = msg.get('content', '')
                break
    
    # Extract song_length (default to 16)
    song_length = data.get('song_length', 16)
    
    # Extract instruments (optional)
    instruments = data.get('instruments', [])
    
    task_id = f"task_midi_{int(time.time())}"
    task_data = {
        "status": "pending",
        "message": "Queued for Native MIDI Specialized LLM...",
        "stems": {},
        "notes": {},
        "error": "",
        "type": "compose_native_midi",
        "prompt": prompt,
        "song_length": song_length,
        "instruments": instruments,
        "task_id": task_id,
        "host_url": request.host_url.rstrip('/')
    }
    save_new_task(task_id, task_data)
    
    return jsonify({"task_id": task_id, "status": "pending"})

@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    return send_file(os.path.join(GENERATED_FOLDER, filename))
    
if __name__ == '__main__':
    print("Starting lightweight Flask API.")
    app.run(host='0.0.0.0', port=5055, debug=False)
