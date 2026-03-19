# Renoise AI Suite 🤖🎹

The **Renoise AI Suite** is a next-generation integration that bridges the precision of the Renoise Tracker with the power of local Deep Learning models. Designed for high-performance electronic music production, this suite runs complex AI tasks (Demucs separation, Transformer-based transcription, LLM composition) entirely on your local workstation. **Version 3.0 is highly optimized for Mac Studio (Apple Silicon / MPS), leveraging up to 36GB VRAM and a 16-core Neural Engine.**

## 🚀 Key Features

### 1. **Multi-Track Song Replicator (Audio-to-MIDI)**

- **Intelligent Stem Splitting**: Uses the `htdemucs_6s` model to separate any audio file into 6 high-quality stems: Drums, Bass, Vocals, Piano, Guitar, and Other.
- **Transformer MIDI Transcription**: Instead of simple pitch detection, it uses the **YourMT3+ Transformer** model to analyze the nuance and polyphony of each stem, converting them into clean Renoise MIDI tracks.
- **Vocal Preservation**: Automatically identifies vocal tracks and loads them as high-quality Audio Stems into Renoise instruments with `autoseek` enabled.

### 2. **AI Composer & Neural MIDI Architect**

- **Neural MIDI Engine (Text2midi)**: A state-of-the-art MIDI transformer model (AAAI 2025) integrated into the backend. It generates full, multi-track arrangements that are internally structured (Intro, Drop, Outro) across up to 1024 tokens of raw MIDI data.
- **Role-to-Track Filtering**: The neural output is intercepted and mathematically filtered to your active Renoise tracks. A "Hammer Kick" prompt will automatically seek out your drum slot!
- **MPS Hardware Acceleration**: Operates natively on Apple Silicon using the Metal Performance Shaders backend, bypassing legacy CUDA requirements.

### 3. **High-Performance UI & Engine**

- **Non-Blocking Polling**: Heavy AI tasks happen in the background. A persistent status dialog keeps you informed of the GPU's progress (e.g., *"Separating Drums..."*, *"Analyzing Lead..."*).
- **Chunked MIDI Writing**: Handles massive 10,000+ note transcriptions without ever freezing the Renoise interface, thanks to a frame-by-frame chunked note worker.
- **Native HTTP Pipeline**: Uses the high-performance Renoise native networking engine with a robust `curl` fallback for maximum stability on Linux workstations.

---

## ⌨️ Hardware Integration: Push 1 for Renoise

A world-class hardware companion for your tracker workflow. The **Push 1 Module** turns your Ableton hardware into a native Renoise interface with a "Full Device Broadcast" protocol designed for Linux stability.

- **Native Isomorphic Play**: 8x8 grid mapped to custom scales (Major, Minor, Locrian, etc.).
- **Dynamic UI Navigation**: Direct mapping of Push buttons to Renoise Edit, Mix, Sampler, Plugin, and MIDI tabs.
- **Step Sequencer Engine**: A dedicated 8v8 step sequencer for drum patterns.
- **High-Visibility LED Protocol**: Custom monochrome Amber mapping ensures labels are readable in the dark via a 100% "Always-On" dim backlight.
- **4-Line SysEx LCD**: Aligned labels for encoders (BPM, Scroll, Track, Volume, LPB).
- **Zero-Latency Response**: Direct MIDI-to-API mapping for an instrument-like feel.

---

## 🛠️ How to Deploy (Mac Studio Edition)

This setup is fully optimized for **Apple Silicon (macOS) with MPS support**.

### Step 1: Clone and Prepare Environment

```bash
# Clone the repository
git clone https://github.com/juanquy/Renoise-AI-Plugin.git
cd Renoise-AI-Plugin

# The `venv_mac` environment inside `ai_server/` includes PyTorch (MPS) and Huggingface libraries.
```

### Step 2: System Administration (run.sh)

We have replaced complex command-line executions with a unified server administration script.

```bash
chmod +x run.sh

# Start the AI Server Database (API) and Neural Engine (Text2midi worker)
./run.sh start

# Check running status
./run.sh status

# Monitor GPU generations
./run.sh logs

# Shut down the AI safely
./run.sh stop
```

### Step 3: Install the Renoise Plugin (.xrnx)

1. Locate the `com.antigravity.aisuite.xrnx` folder in this repo.
2. Drag it into Renoise via the plugin browser, or set a symlink directly into your Renoise `Tools` directory for live development.
3. **Configuration:**
   - Open Renoise.
   - Go to **Tools > AI Suite > Preferences**.
   - Ensure the **Host URL** points to `http://127.0.0.1:5000` (this targets the Flask API `app.py`).

---

## ⚡ System Requirements & Memory Optimization

Running state-of-the-art AI models locally is resource-intensive. If your system has less than 32GB of physical RAM, the Linux kernel may terminate Renoise to save system stability during peak AI processing.

### **Important: Increase Swap Space**

To prevent crashes during "Stem Splitting" or "Full Transcription," it is highly recommended to have at least **8GB of Swap memory**.
If you encounter a "Low Memory" error or Renoise closes suddenly, run these commands in a terminal to expand your swap file:

```bash
# 1. Turn off the existing small swap
sudo swapoff /swapfile

# 2. Allocate a new 8GB swap file
sudo dd if=/dev/zero of=/swapfile bs=1M count=8192

# 3. Set secure permissions
sudo chmod 600 /swapfile

# 4. Format and activate
sudo mkswap /swapfile
sudo swapon /swapfile

# 5. Verify the change (should show 8.0G in Swap)
free -h
```

---

## 🔬 Electronic Music Optimization

The suite includes an **Electronic Music Saver** logic specifically designed for techno, house, and synth-heavy genres:

- **AI Verification:** Every vocal stem is cross-checked by two different AI models (Demucs + YourMT3+).
- **Synth Confidence:** If the AI detects that a "vocal" is actually a synthesizer, it automatically deletes the audio file and converts the melody into a clean **MIDI: Lead Synth** track.
- **Accurate Templates:** This prevents "ghost" audio tracks from cluttering your project when working on pure instrumental music.

---

## 🎹 Usage Guide

### **Full Song Transcription (Blank Slate)**

1. Go to **Tools > AI Integration > Import & Split Audio**.
2. Select your song (`.wav`, `.mp3`, `.flac`).
3. **Wait for the GPU**: The status window will show the Demucs separation and YourMT3+ analysis.
4. **Watch it grow**: Once the server finishes, your current project will be cleared, and the pattern editor will fill up with individual tracks for Bass, Drums, Melody, and a Vocal audio stem.

### **Single-Stem Tracker Import (Append Mode)**

If you already have high-quality separated stems (e.g., from Suno AI or professional master stems), you can bypass Demucs for a massive boost in MIDI transcription accuracy. YourMT3+ performs radically better on clean, pre-separated audio without algorithm bleed!

1. Go to **Tools > AI Integration > Audio to MIDI Tracker...**
2. Select your isolated stem file.
3. The AI Server will execute pure MIDI extraction via YourMT3+ and **append** the new instrument and notes safely to the far right of your current Renoise arrangement, leaving your existing project intact!

### **AI Assistant/Composer**

1. Right-click in the Pattern Editor > **AI Integration > Compose with AI**.
2. Type a prompt like: *"Create a dark industrial techno loop at 135BPM with a heavy syncopated sub-bass."*
3. The AI will respond with JSON commands and automatically begin building your project.

---

## 🎹 Push 1 Hardware: "How to"

A comprehensive guide to every button, mode, and optimization for the Push 1 hardware can now be found in:

👉 **[HOW_TO_USE_PUSH1.md](file:///home/juanquy/dev/Renoise%20AI%20Plugin/HOW_TO_USE_PUSH1.md)**

---

## 📂 Project Structure

- `com.antigravity.aisuite.xrnx/`: The Renoise Tool source code.
- `push-plugin.xrnx/`: The Push 1 Hardware Integration source code.
- `ai_server/`: The Python backend (Flask API + Background Worker).
- `docs/`: Technical documentation and API references.
- `Push1_for_Renoise.xrnx`: Ready-to-install Push 1 package.
- `RenoiseAI_V2_Fixed.xrnx`: Ready-to-install AI Suite package.

---

*Created for the visionary electronic music producer. All AI processing remains local and private.*
