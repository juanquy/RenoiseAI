# Renoise AI Suite

The Renoise AI Suite is a powerful integration that connects Renoise (the Digital Audio Workstation) to state-of-the-art AI models running on a dedicated local server.

This suite consists of a **Renoise Lua Tool (.xrnx)** backend and a **Python API Server** that runs your heavy ML models (like Meta's MusicGen and Spotify's Basic-Pitch) without locking up the tracker!

## Features

1. **AI Transcription (Audio-to-Notes)**
   - Upload any sample directly from the Renoise Pattern Editor to the AI Server.
   - The server processes the audio using Spotify's `basic-pitch` and Meta's `demucs`.
   - The generated notes are automatically drawn into your active pattern and track.
2. **AI Song Generation (MusicGen)**
   - Prompt the AI server directly from Renoise (e.g., "Industrial Cyberpunk Techno, 140BPM").
   - The server uses `audiocraft` to generate a high-quality audio clip.

## Installation

### Part 1: The Python AI Server

Because the AI models require PyTorch, CUDA, and heavy C-extensions, it is highly recommended to run the AI server on a dedicated machine (like a Proxmox container) or within a Docker environment.

**Requirements:**

- Linux (Ubuntu recommended)
- NVIDIA GPU with CUDA drivers
- Python 3.10 (via Miniconda/Miniforge is highly recommended for dependency resolution)

**Setup Instructions:**

1. Clone the repository and navigate to the `ai_server/` directory.
2. Install the required dependencies:

   ```bash
   pip install -r requirements.txt
   ```

   *(Note: Ensure you have FFmpeg dev headers installed, e.g., `apt install pkg-config libavformat-dev libavcodec-dev libavdevice-dev libavutil-dev libavfilter-dev libswscale-dev libswresample-dev`)*
3. Set your API Key in `app.py`.
4. Run the server:

   ```bash
   python app.py
   ```

   *(For persistent bare-metal deployments, setting this up as a `systemd` service is recommended).*

### Part 2: The Renoise Plugin (.xrnx)

1. Open the `com.antigravity.aisuite.xrnx/main.lua` file.
2. Modify the `server_url` to point to the IP address of your Python API server (e.g., `http://192.168.200.121:5000`).
3. Drag the `com.antigravity.aisuite.xrnx` folder (or zip it into a `.xrnx` file) into your Renoise application window to install it.

## Usage Guide

### Audio-to-Notes Transcription

1. Load a sample into your Renoise Instrument selector.
2. Ensure your cursor is active in the **Pattern Editor**.
3. Right-click anywhere in the Pattern Editor and go to **AI Integration > Transcribe Selected Sample**.
4. The plugin will send the audio to the Python server over the LAN, transcribe it, and write the MIDI note equivalents directly into your track!

### Song Generation

1. Right-click in the Pattern Editor and select **AI Integration > Generate Song...**.
2. A dialog will appear. Enter your prompt (e.g., "Heavy 808 kick drum loop with distortion").
3. Click generate. The server will begin processing the audio (this usually takes 20-60 seconds depending on you GPU).
4. The server will return the `.wav` file for you to drop back into your instrument!
