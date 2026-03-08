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

@app.route('/transcribe_full', methods=['POST'])
@require_api_key
def transcribe_full():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    safe_filename = "upload_full_" + str(int(time.time())) + ".wav"
    filepath = os.path.join(UPLOAD_FOLDER, safe_filename)
    file.save(filepath)
    
    job_id = f"job_full_{int(time.time())}"
    task_id = f"task_full_{int(time.time())}"
    
    task_data = {
        "status": "pending",
        "message": "Queued for upload rendering and full demucs extraction...",
        "stems": {},
        "notes": {},
        "error": "",
        "type": "transcribe_full",
        "filepath": filepath,
        "job_id": job_id,
        "task_id": task_id,
        "host_url": request.host_url.rstrip('/')
    }
    save_new_task(task_id, task_data)
    
    return jsonify({"task_id": task_id, "status": "pending"})

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
        "job_id": job_id,
        "task_id": task_id,
        "host_url": request.host_url.rstrip('/')
    }
    save_new_task(task_id, task_data)
    
    return jsonify({"task_id": task_id, "status": "pending"})

@app.route('/generate_song', methods=['POST'])
@require_api_key
def generate_song():
    data = request.json
    prompt = data.get('prompt', '')
    lyrics = data.get('lyrics', '')
    style = data.get('style', '')
    duration = int(data.get('duration', 8))
    
    duration = min(duration, 120) 
    
    gen_prompt = prompt
    if style != "":
        gen_prompt = f"{style}, {prompt}"
        
    gen_prompt += ", clear song structure with intro, development, and a defined outro/ending"
    
    task_id = f"task_{int(time.time())}"
    task_data = {
        "status": "pending",
        "message": "Queued for generator...",
        "stems": {},
        "notes": {},
        "error": "",
        "type": "generate_song",
        "gen_prompt": gen_prompt,
        "duration": duration,
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
    app.run(host='0.0.0.0', port=5000, debug=False)
