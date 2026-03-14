# Renoise AI Suite 🤖🎹

The **Renoise AI Suite** is a next-generation integration that bridges the precision of the Renoise Tracker with the power of local Deep Learning models. Designed for high-performance electronic music production, this suite runs complex AI tasks (Demucs separation, Transformer-based transcription, LLM composition) entirely on your local workstation's GPU.

## 🚀 Key Features

### 1. **Multi-Track Song Replicator (Audio-to-MIDI)**

- **Intelligent Stem Splitting**: Uses the `htdemucs_6s` model to separate any audio file into 6 high-quality stems: Drums, Bass, Vocals, Piano, Guitar, and Other.
- **Transformer MIDI Transcription**: Instead of simple pitch detection, it uses the **YourMT3+ Transformer** model to analyze the nuance and polyphony of each stem, converting them into clean Renoise MIDI tracks.
- **Vocal Preservation**: Automatically identifies vocal tracks and loads them as high-quality Audio Stems into Renoise instruments with `autoseek` enabled.

### 2. **AI Composer & Song Architect**

- **Native MIDI Expert (Llama 3.2-1B)**: A specialized MIDI-LLM fine-tuned on **666 Renoise compositions** from the community. It understands native tracker logic, pattern structures, and complex percussion layering.
- **LLM-Powered Tracking**: Chat with the AI in "Song Architect" mode to describe a vibe or a full arrangement.
- **Native Command Execution**: The AI generates a series of native Renoise commands to build tracks, set BPM/LPB, and compose patterns in real-time.

### 3. **High-Performance UI & Engine**

- **Non-Blocking Polling**: Heavy AI tasks happen in the background. A persistent status dialog keeps you informed of the GPU's progress (e.g., *"Separating Drums..."*, *"Analyzing Lead..."*).
- **Chunked MIDI Writing**: Handles massive 10,000+ note transcriptions without ever freezing the Renoise interface, thanks to a frame-by-frame chunked note worker.
- **Native HTTP Pipeline**: Uses the high-performance Renoise native networking engine with a robust `curl` fallback for maximum stability on Linux workstations.

---

## ⌨️ Hardware Integration: Push 1 for Renoise

A world-class hardware companion for your tracker workflow. The **Push 1 Module** turns your Ableton hardware into a native Renoise interface.

- **Native Isomorphic Play**: 8x8 grid mapped to custom scales (Major, Minor, Locrian, etc.).
- **Step Sequencer Engine**: A dedicated 8v8 step sequencer for drum patterns.
- **4-Line SysEx LCD**: Full hardware display synchronization for BPM, Volume, and Song naming.
- **Zero-Latency Response**: Direct MIDI-to-API mapping for an instrument-like feel.

---

## 🛠️ How to Deploy (Full Installation)

This setup assumes you are using a **Linux workstation** (Ubuntu/Debian recommended) with an **NVIDIA GPU**.

### Step 1: Clone and Prepare Python Environment

We use a decoupled architecture (API + Worker) to ensure the Renoise UI stays responsive while the GPU is under heavy load.

```bash
# Clone the repository
git clone https://github.com/juanquy/Renoise-AI-Plugin.git
cd Renoise-AI-Plugin

# Create a dedicated environment
conda create -n ai_env python=3.10 -y
conda activate ai_env

# Install Core & LLM Dependencies
pip install flask gunicorn numpy scipy torch torchaudio basic-pitch demucs audiocraft soundfile
pip install --upgrade transformers accelerate peft bitsandbytes datasets tqdm hf_transfer mido
```

### Step 2: Install AI Model Dependencies

To enable the high-fidelity MIDI transcription, you must have the YourMT3+ repository linked:

1. Follow the [YourMT3+ Installation Guide](https://github.com/st-onishi/YourMT3/blob/main/docs/installation.md) to download the model checkpoints.
2. Ensure you have the `mc13_256_g4_all_v7_mt3f_sqr_rms_moe_wf4_n8k2_silu_rope_rp_b36_nops@last.ckpt` checkpoint in your `YourMT3/checkpoints/` folder.

### Step 3: Launch the AI Suite Server

The server is split into two parts: the API (frontend) and the Worker (where the Expert models load).

**Terminal 1 (The Frontend API):**
```bash
cd ai_server
/home/juanquy/miniconda3/envs/ai_env/bin/python app.py
```

**Terminal 2 (The Music Brain / Worker):**
```bash
cd ai_server
/home/juanquy/miniconda3/envs/ai_env/bin/python worker.py
```

> [!TIP]
> **Automatic Maintenance:** The system includes a built-in "Janitor" logic. It will automatically purge temporary audio stems and task logs every 60 minutes to keep your hard drive lean.

> [!IMPORTANT]
> **Expert MIDI Fine-Tuning:** The "Native MIDI Expert" requires the LoRA weights generated during training. If you wish to re-train on your own dataset, update `DATASET_PATH` in `train_midi.py` and run the script. The worker will automatically look for `./renoise_midi_model_lora` on startup.

### Step 4: Install the Renoise Plugin (.xrnx)

1. Locate the `com.antigravity.aisuite.xrnx` folder in this repo.
2. **Standard Install:** Zip the folder and rename it to `.xrnx`, then drag into Renoise.
3. **Developer Install:** Create a symbolic link from your Renoise Tools folder to this directory for real-time code updates.
4. **Configuration:**

   - Open Renoise.
   - Go to **Tools > AI Suite > Preferences**.
   - Set the **Host URL** to `http://127.0.0.1:5000`.
   - Set the **Ollama URL** to `http://127.0.0.1:11434`.

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

## 📂 Project Structure

- `com.antigravity.aisuite.xrnx/`: The Renoise Tool source code.
- `push-plugin.xrnx/`: The Push 1 Hardware Integration source code.
- `ai_server/`: The Python backend (Flask API + Background Worker).
- `docs/`: Technical documentation and API references.
- `Push1_for_Renoise.xrnx`: Ready-to-install Push 1 package.
- `RenoiseAI_V2_Fixed.xrnx`: Ready-to-install AI Suite package.

---

*Created for the visionary electronic music producer. All AI processing remains local and private.*
