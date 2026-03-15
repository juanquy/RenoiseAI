#!/bin/bash
# Renoise AI Suite & Push 1 — Build Script
# This script packages the development folders into installable .xrnx files.

echo "📦 Packaging Renoise Tools..."

# Clean old packages (files only)
find . -maxdepth 1 -name "*.xrnx" -type f -delete

# 1. AI Suite
echo "  - Building RenoiseAI_V2_Fixed.xrnx..."
cd "com.antigravity.aisuite.xrnx" && zip -qr ../RenoiseAI_V2_Fixed.xrnx ./* && cd ..

# 2. Push 1 Integration
echo "  - Building Push1_for_Renoise.xrnx..."
cd "push-plugin.xrnx" && zip -qr ../Push1_for_Renoise.xrnx ./* && cd ..

echo "✅ Done! Packages are ready in the root directory."
