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
                
            return data.get("result")
            
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
        Placeholder for the full Llama-3 Reasoning loop.
        1. Agent analyzes prompt using 17.7GB trained JSONL context
        2. Agent formulates a chain of MCP commands
        3. Agent executes them iteratively
        """
        print(f"Agent received prompt: '{user_prompt}'")
        print("\n--- [SIMULATED LLM REASONING] ---")
        print("1. Planning structure: 130 BPM, 4 Tracks (Kick, Snare, Bass, Synth)")
        print("2. Formulating JSON-RPC sequence payloads...")
        print("----------------------------------\n")
        
        # Example hardcoded executions to prove the API bridge works
        self.mcp.call_tool("transport_set_bpm", {"bpm": 130.0})
        print("> Set Song BPM to 130")
        
        # In a real scenario, the LLM will generate a list of dictionaries like this:
        example_ai_generation = [
            {"tool": "pattern_set_note", "args": {"track": 1, "line": 0, "note": "C-4", "instrument": 1}},
            {"tool": "pattern_set_note", "args": {"track": 1, "line": 4, "note": "C-4", "instrument": 1}},
            {"tool": "pattern_set_note", "args": {"track": 1, "line": 8, "note": "C-4", "instrument": 1}},
            {"tool": "pattern_set_note", "args": {"track": 1, "line": 12, "note": "C-4", "instrument": 1}}
        ]
        
        print("Executing AI payload against Renoise API...")
        for cmd in example_ai_generation:
            self.mcp.call_tool(cmd["tool"], cmd["args"])
            
        print("\nAgent finished writing sequence! Initiating playback...")
        self.mcp.call_tool("transport_play")

if __name__ == "__main__":
    client = RenoiseMCPClient()
    agent = RenoiseCopilotAgent(client)
    
    if agent.ping_renoise():
        print("------------------------------------------")
        agent.execute_agentic_workflow("Write a techno kick drum loop")
