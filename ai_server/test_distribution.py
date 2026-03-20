import requests
import json
import time

URL = "http://127.0.0.1:5055"
HEADERS = {"X-API-Key": "my_super_secret_proxmox_key"}

def test():
    print("Triggering composition...")
    r = requests.post(f"{URL}/compose_native_midi", 
                      json={"prompt": "A cinematic orchestral piece with clear piano, bass, and minimal drums", "song_length": 16},
                      headers=HEADERS)
    task_id = r.json()["task_id"]
    print(f"Task ID: {task_id}")
    
    for _ in range(60):
        rs = requests.get(f"{URL}/task_status/{task_id}")
        data = rs.json()
        if data.get("status") in ["success", "error"]:
            print(f"Final Status: {data.get('status')}")
            break
        time.sleep(2)
        
    # Analyze
    with open(f"ai_server/tasks/{task_id}.json", "r") as f:
        res = json.load(f)
        
    cmds = res.get("commands", [])
    bulk = [c for c in cmds if c.get("type") == "bulk_notes"]
    if bulk:
        notes = bulk[0].get("data", "").split("\n")
        track_counts = {}
        for n in notes:
            if n.startswith("N|"):
                parts = n.split("|")
                t = parts[1]
                track_counts[t] = track_counts.get(t, 0) + 1
        print("Note Counts per Track:")
        for t, c in sorted(track_counts.items()):
            print(f"Track {t}: {c} notes")
            
if __name__ == "__main__":
    test()
