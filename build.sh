#!/usr/bin/env bash
# exit on error
set -o errexit

# Install CPU-only PyTorch to reduce image size (CRITICAL for Render)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Install rest of dependencies
pip install -r requirements.txt

# Download weights if not present
echo "📦 Checking AI Model weights..."
if [ ! -f "weights/mobile_sam.pt" ]; then
    echo "🌐 Downloading weights during build for zero-wait startup..."
    python download_weights.py
    echo "✅ Download finished."
else
    echo "✨ Weights already present in build cache."
fi

# Print final status
ls -lh weights/
