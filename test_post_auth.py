import requests
import json

url = "http://192.168.200.121:5000/generate_song"
headers = {"X-API-Key": "my_super_secret_proxmox_key"}
payload = {"prompt": "Cyberpunk Techno", "style": "Renoise", "lyrics": "", "instrumental": True, "duration": 8}
try:
    r = requests.post(url, json=payload, headers=headers, timeout=120)
    print("STATUS:", r.status_code)
    # Print exactly what the server outputs
    print("RESPONSE LENGTH:", len(r.text))
    # Look for NaN or Infinity in the text
    if "NaN" in r.text or "Infinity" in r.text:
        print("FOUND INVALID JSON (NaN/Infinity)!")
        
    print("Beginning:", r.text[:200])
    
except Exception as e:
    print("ERROR:", e)
