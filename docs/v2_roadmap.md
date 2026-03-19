# Renoise AI Project - Phase 2 Roadmap: The Agentic Copilot

## Goal

To evolve from a simple Audio-Domain generation model (V1) into a **Native Interactive Agentic System**.

With the discovery of the massive **17.7 GiB `XRNS-DataSet`**, Phase 2 will focus on training a local AI to understand the structural DNA of Renoise music. The ultimate goal is to build an AI Copilot that can perfectly operate Renoise, generate structural sequence XML, mix stems, and synthesize vocals—keeping the "Human in the Middle".

---

## 1. System Architecture: The Agentic Copilot

Version 2 will shift from "generating a WAV file" to actively designing the song structure using the local API and the XRNS dataset.

* **The Local AI Server (Proxmox):**
  * Hosts the Voice Synthesis engine (for lyrics).
  * Hosts the locally fine-tuned LLM capable of outputting Renoise-flavored XML and MCP JSON commands.
  * Continues to host the MusicGen/Demucs stack for sample synthesis.
* **The Agent Workflow:**
  1. **User prompts:** *"Create a 3-minute cyberpunk track with a driving bassline and synthesize these lyrics: 'Neon rain falling'."*
  2. **Vocal Synthesis:** The server generates an Acapella vocal track.
  3. **XRNS Generation / MCP:** Using its structural knowledge from the 17GB dataset, the fine-tuned LLM leverages the Renoise MCP server to add instruments, create sequences, dial in DSP effects, and structure the 3-minute song block by block.
  4. **Human in the Middle:** The human producer reviews the generated tracks within the Renoise UI, fine-tunes the mix, and iterates via chat.

## 2. Exploiting the 17.7GB XRNS Dataset

This dataset is the key to teaching an LLM "how to track."

* **Data Extraction Pipeline:** We will build a Python parser to mass-extract `Song.xml` files from the 17.7GB of zipped `.xrns` archives.
* **Tokenization Strategy:**
  * The raw XML is too verbose. We will compress the tracker data into an intermediate JSON or Domain-Specific Language (DSL) that represents "Musical Intent" (e.g., *Track 1 Delay 50%, Pattern 0 Line 12 Note C-4*).
* **Fine-tuning the Local LLM:** We will train a local model (like Llama-3 8B or Mistral) on this compressed language so it intuitively understands Renoise parameters, instrument envelopes, and DSP routing.

## 3. Implementing Local Voice/Lyric Synthesis

To complete the end-to-end music production pipeline:

* **Text-to-Speech / Singing Voice Synthesis (SVS):** Integrate an open-source model like **Bark**, **Suno/AI**, or **DiffSinger** onto the Proxmox server.
* **Workflow integration:** The LLM agent will script the lyrics, feed them to the singing synthesis model, download the resulting audio to Renoise, and map the vocal sample into a dedicated track perfectly synced to the BPM.

## 4. Next Steps for Implementation

1. **Dataset Ingestion:** Write the Python scripts to unzip, parse, and clean the 17.7GB XRNS dataset.
2. **Model Selection:** Test local LLMs for their ability to generate structured JSON/XML matching the dataset.
3. **Vocal Implementation:** Install and test an open-source Singing Voice model on the Proxmox server alongside MusicGen.
4. **Agent Logic:** Upgrade the Renoise MCP Server and the `app.py` script to handle complex, multi-step agentic workflows.
