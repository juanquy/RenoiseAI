# How to use the Ableton Push 1 in Renoise

This guide documents all the hardware mappings and modes implemented for the Ableton Push 1 integration with Renoise.

## 🔌 Getting Started (Linux/ALSA)

- **Connect**: Plug in your Push 1 and ensure it's powered.
- **User Mode**: Press the **[User]** button on the top right. This is required for custom display and LED control.
- **Renoise Connection**: Go to **Tools > Push 1 > Connect**. The script will automatically scan your ALSA ports.

---

## 🧭 Main Navigation (Direct Access)

These buttons provide instant feedback via **Renoise Status Bar Notifications**:

- **[SESSION]**: Triggers **Matrix (Live) Mode**.
    - Notification: `🎹 PUSH 1 >> MATRIX (LIVE) MODE [ON]`
- **[NOTE]**: Triggers **Tracker (Notes) Mode**.
    - Notification: `🎹 PUSH 1 >> TRACKER (NOTES) MODE [ON]`
- **[SCALES]**: Instant jump to **Scale (Keyboard) Mode**.
    - Notification: `🎹 PUSH 1 >> SCALE (KEYBOARD) MODE [ON]`
- **[SHIFT] + [SESSION]**: Triggers **Step Sequencer Mode**.

---

## 🕹️ Live Performance (Matrix Mode)

Designed for pro-performance loop triggering and mixing:

### 🎨 Visuals

- **Amber Stage**: The 8x8 grid is backlit with **Soft Amber** to signal "Live Mode."
- **Colors**:
    - **Bright Green**: Playing loop.
    - **Dim Red**: Muted loop (easy to see in the mix).
    - **Dim Amber**: Data present in slot.
- **Tactile Flash**: Every pad touch flashes **Bright Amber** instantly.

### 🕹️ Tactical Controls (Right-Side Buttons & Knobs)

- **Scene Buttons (Right of Grid)**: Launch entire rows (Scenes) instantly.
- **Encoders 1-8**: Control **Track Volume** for the first 8 tracks.
- **[REPEAT]**: Toggle **Pattern Block Loop** (stay on the loop while you mix).
- **[ACCENT]**: Secondary **Metronome** toggle.
- **[USER]**: **Tap Tempo** for real-time synchronization.
- **[OCTAVE UP/DOWN]**: **Page Scroll** (Jumps the matrix by 8 tracks/rows at a time).

---

## 🖥️ UI Tab Navigation (Focus Management)

Switch Renoise tabs without losing your focus or closing instruments:

- **[TRACK]**: Focuses the **Mixer**.
- **[DEVICE]**: Focuses the **Instrument/Sampler** tab.
- **[CLIP]**: Focuses the **Plugins** tab.
- **[BROWSE]**: Focuses the **MIDI** tab.

---

## 🎚️ Mixing & Logic

- **[MASTER]**: Selects the Master Track instantly.
- **[MUTE] / [SOLO]**: Control the selected track's state.
- **[UNDO]**: Standard undo.
- **[DELETE]**: Deletes current line/note content.

---

## 🛡️ Stability & "Nuclear" Processing

- **Status Notifications**: Every mode switch or tactical toggle provides a brief banner in the status bar.
- **ALSA Protection**: Throttles MIDI data to prevent Linux driver crashes.
- **Hand-tuned Layout**: Buttons like [REPEAT] and [ACCENT] were mapped specifically for techno/live performance.
