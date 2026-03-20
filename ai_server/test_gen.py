import requests
import time

URL = "http://127.0.0.1:5055"
HEADERS = {"X-API-Key": "my_super_secret_proxmox_key"}

def test():
    print("Triggering composition...")
    try:
        r = requests.post(f"{URL}/compose_native_midi", 
                          json={"prompt": "A cinematic orchestral piece with no drums", "song_length": 16},
                          headers=HEADERS)
        if r.status_code != 200:
            print(f"Error triggering task: {r.text}")
            return
        
        task_id = r.json()["task_id"]
        print(f"Task ID: {task_id}")
        
        for _ in range(60):
            rs = requests.get(f"{URL}/task_status/{task_id}")
            data = rs.json()
            status = data.get('status')
            print(f"Status: {status} - {data.get('message')}")
            if status in ["success", "error"]:
                print(f"Final Message: {data.get('message')}")
                if data.get("error"): print(f"Error: {data.get('error')}")
                break
            time.sleep(2)
    except Exception as e:
        print(f"Connection error: {e}")

if __name__ == "__main__":
    test()
