#!/usr/bin/env bash
# Build a self-contained QualityScaler binary for Linux.
#
#   sudo apt install python3 python3-venv python3-tk ffmpeg
#   python3 -m venv .venv && .venv/bin/pip install -r requirements-linux.txt
#   tools/build-linux.sh
#
# Result: dist/QualityScaler (AI models and FFmpeg are not embedded; the binary
# uses the FFmpeg found on PATH and the .onnx files next to it or in AI-onnx/).

set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-.venv/bin/python}"

if [ ! -x "$PYTHON" ]; then
    echo "Virtualenv interpreter not found: $PYTHON" >&2
    echo "Create it first: python3 -m venv .venv && .venv/bin/pip install -r requirements-linux.txt" >&2
    exit 1
fi

"$PYTHON" -m PyInstaller --noconfirm --clean QualityScaler.spec

echo
echo "Built: dist/QualityScaler"
echo "Run:   ./dist/QualityScaler"
