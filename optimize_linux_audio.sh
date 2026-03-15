#!/bin/bash

# optimize_linux_audio.sh
# Automates Pro-Audio optimization for Renoise on Kubuntu/Ubuntu
# Run this script as root: sudo ./optimize_linux_audio.sh

set -e

echo "🚀 Starting Renoise Linux Optimization..."

# 1. Real-Time Permissions
echo "🔧 Setting real-time permissions in /etc/security/limits.d/audio.conf..."
cat <<EOF | sudo tee /etc/security/limits.d/audio.conf
@audio   -  rtprio     95
@audio   -  memlock    unlimited
EOF

# 2. Group Membership
echo "👥 Adding $USER to the audio group..."
sudo usermod -a -G audio $USER

# 3. CPU Performance Mode
echo "⚡ Setting CPU scaling governor to performance..."
# Try to set it immediately
for file in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    if [ -f "$file" ]; then
        echo performance | sudo tee "$file" > /dev/null
    fi
done

# 4. ALSA MIDI Queue Hardening
echo "🎹 Increasing ALSA MIDI sequencer queue size..."
cat <<EOF | sudo tee /etc/modprobe.d/alsa-base.conf
options snd-seq seq_client_queues=128
EOF

# 5. Low-Latency Kernel (Optional but recommended)
echo "🐧 Suggesting low-latency kernel install..."
# We can't use read -p in a non-interactive shell effectively, but we can print the command.
echo "To install the low-latency kernel, run: sudo apt install linux-lowlatency"

echo ""
echo "✅ Optimization complete!"
echo "⚠️ IMPORTANT: You MUST REBOOT for the real-time permissions and MIDI queue changes to take effect."
echo "🎹 After reboot, remember to check 'Enable Realtime Priority' in Renoise Audio Preferences."
