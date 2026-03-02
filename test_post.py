import requests
import json

url = "http://192.168.200.121:5000/generate_song"
payload = {"prompt": "Cyberpunk Techno", "style": "Renoise", "lyrics": "", "instrumental": True, "duration": 8}
try:
    r = requests.post(url, json=payload, timeout=120)
    print("STATUS:", r.status_code)
    print("RESPONSE:", r.text[:200])
except Exception as e:
    print("ERROR:", e)
