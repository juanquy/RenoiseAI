import os
import json
import requests
import time
from typing import Dict, Any, List

# The local ReMCP server runs on port 19714
RENOISE_MCP_URL = "http://localhost:19714/mcp"

class RenoiseMCPClient:
    """A lightweight JSON-RPC client to control Renoise via ReMCP."""
    
    def __init__(self, url: str = RENOISE_MCP_URL):
        self.url = url
        self.request_id = 1

    def call_tool(self, tool_name: str, arguments: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Executes a Renoise MCP tool dynamically.
        Matches the Anthropic MCP JSON-RPC standard used by ReMCP.
        """
        if arguments is None:
            arguments = {}
            
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            },
            "id": self.request_id
        }
        self.request_id += 1
        
        try:
            response = requests.post(self.url, json=payload, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            if "error" in data:
                print(f"[TCPError] {tool_name}: {data['error'].get('message', data['error'])}")
                return None
                
            result = data.get("result", {})
            if result.get("isError"):
                content = result.get("content", [{"text": "Unknown error"}])
                print(f"[ReMCP Error] {tool_name}: {content[0].get('text')}")
                return None
                
            return result
            
        except requests.exceptions.RequestException as e:
            print(f"[NetworkError] Could not reach Renoise MCP on {self.url}: {e}")
            return None

class RenoiseCopilotAgent:
    """
    The orchestrator that acts as the 'Human-in-the-Middle'.
    It takes user intentions, queries the LLM, and translates findings into Renoise MCP executions.
    """
    def __init__(self, mcp_client: RenoiseMCPClient):
        self.mcp = mcp_client
        
    def ping_renoise(self):
        """Verifies the tracker is open and listening."""
        print("Checking connection to Renoise...")
        info = self.mcp.call_tool("song_get_info")
        if info:
            print("\nSuccessfully connected to active Renoise Project:")
            # ReMCP returns structured text in a specific object
            content = info.get("content", [])
            if content and len(content) > 0:
                print(content[0].get("text", ""))
            return True
        return False
        
    def execute_agentic_workflow(self, user_prompt: str):
        """
        Queries the local Llama-3.1 model to dynamically generate Renoise automation data.
        """
        print(f"Agent received prompt: '{user_prompt}'")
        print("\n--- [LLM REASONING - Llama 3.1] ---")
        
        system_prompt = """
You are an expert Tracker Musician writing Renoise structural song automation.
The user will ask you to create a specific musical pattern.
You must output a raw, valid JSON array of Renoise MCP command objects.
Every object must have a "tool" (string) and "args" (dictionary).
Allowed tools:
- "pattern_set_note" (args: pattern (int 0-based), track (int 1-based), line (int 1-based), note (string like "C-4", "D#4", or "OFF"))

For example, a basic 4-on-the-floor kick drum (track 1) looks like this:
[
    {"tool": "pattern_set_note", "args": {"pattern": 0, "track": 1, "line": 1, "note": "C-4"}},
    {"tool": "pattern_set_note", "args": {"pattern": 0, "track": 1, "line": 5, "note": "C-4"}},
    {"tool": "pattern_set_note", "args": {"pattern": 0, "track": 1, "line": 9, "note": "C-4"}},
    {"tool": "pattern_set_note", "args": {"pattern": 0, "track": 1, "line": 13, "note": "C-4"}},
    {"tool": "pattern_set_note", "args": {"pattern": 0, "track": 1, "line": 17, "note": "C-4"}}
]

OUTPUT ONLY VALID JSON. Do not include markdown formatting, backticks, or any conversational text.
"""
        
        payload = {
            "model": "llama3.1",
            "prompt": f"{system_prompt}\n\nUser Request: {user_prompt}",
            "stream": False,
            "options": {"temperature": 0.2}
        }
        
        try:
            print("Querying Llama-3.1 on Proxmox Server (192.168.200.121:11434)...")
            start_time = time.time()
            # Increased timeout to 300s since the first model load into VRAM can take a while
            response = requests.post("http://192.168.200.121:11434/api/generate", json=payload, timeout=300)
            response.raise_for_status()
            elapsed = time.time() - start_time
            
            raw_text = response.json().get("response", "").strip()
            print(f"Received response from Llama-3.1 in {elapsed:.1f} seconds.")
            
            # Clean up potential markdown formatting from the LLM
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            elif raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            raw_text = raw_text.strip()
            
            ai_generation = json.loads(raw_text)
            
        except requests.exceptions.Timeout:
            print("[Error] Timeout: Llama-3.1 took too long to respond.")
            return
        except json.JSONDecodeError as e:
            print(f"[Error] Failed to parse JSON from LLM: {e}")
            print(f"Raw output was:\n{raw_text}")
            return
        except Exception as e:
            print(f"[Error] Failed to query LLM: {e}")
            return
            
        print(f"\nExecuting {len(ai_generation)} commands against Renoise API...")
        for cmd in ai_generation:
            print(f"Executing: {cmd['tool']} with {cmd['args']}")
            res = self.mcp.call_tool(cmd["tool"], cmd["args"])
            time.sleep(0.1) # Prevent socket flooding
            
        print("\nAgent finished writing sequence! Initiating playback...")
        self.mcp.call_tool("transport_play")



if __name__ == "__main__":
    client = RenoiseMCPClient()
    agent = RenoiseCopilotAgent(client)
    
    if agent.ping_renoise():
        print("------------------------------------------")
        agent.execute_agentic_workflow("Write a techno kick drum loop")
