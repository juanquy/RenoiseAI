#!/bin/bash
# Push 1 — Build Script
# This script packages the development folders into installable .xrnx files.

echo "📦 Packaging Push 1 Tool..."

# Clean old packages (files only)
find . -maxdepth 1 -name "*.xrnx" -type f -delete

# Push 1 Integration
echo "  - Building Push1_for_Renoise.xrnx..."
cd "push-plugin.xrnx" && zip -qr ../Push1_for_Renoise.xrnx ./* && cd ..

echo "✅ Done! Packages are ready in the root directory."
