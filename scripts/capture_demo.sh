#!/usr/bin/env bash
set -euo pipefail

DURATION=${1:-30}
OUT_DIR=${2:-$HOME/fyp_ws/logs/demo_capture}
DISPLAY=${DISPLAY:-:0}

mkdir -p "$OUT_DIR"

if command -v ffmpeg >/dev/null 2>&1; then
  echo "Recording $DURATION seconds to $OUT_DIR/demo.mp4 (DISPLAY=$DISPLAY)"
  ffmpeg -y -video_size 1280x720 -framerate 30 \
    -f x11grab -i "$DISPLAY" -t "$DURATION" \
    "$OUT_DIR/demo.mp4"
else
  echo "ffmpeg not found. Install with: sudo apt install -y ffmpeg"
fi

if command -v gnome-screenshot >/dev/null 2>&1; then
  echo "Capturing screenshot to $OUT_DIR/rviz.png"
  gnome-screenshot -f "$OUT_DIR/rviz.png"
else
  echo "gnome-screenshot not found. Install with: sudo apt install -y gnome-screenshot"
fi

echo "Capture complete. Files in $OUT_DIR"