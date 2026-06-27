#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CAST_DIR="$ROOT_DIR/out/live-casts"
RECORDING_DIR="$ROOT_DIR/public/recordings"
MP4_PATH="${1:-$RECORDING_DIR/codebase-repair-demo.mp4}"
CAST_PATH="$CAST_DIR/codebase-repair-demo.cast"
GIF_PATH="$CAST_DIR/codebase-repair-demo.gif"

mkdir -p "$CAST_DIR" "$RECORDING_DIR" "$(dirname "$MP4_PATH")"

for tool in asciinema agg ffmpeg; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    printf 'Missing required recorder tool: %s\n' "$tool" >&2
    exit 1
  fi
done

asciinema rec \
  --overwrite \
  --quiet \
  --cols 120 \
  --rows 34 \
  --title "OmegaClaw codebase repair demo" \
  --command "$ROOT_DIR/scripts/recorders/live-codebase-repair-demo.sh" \
  "$CAST_PATH"

agg \
  --theme github-dark \
  --font-size 22 \
  --line-height 1.18 \
  --speed 0.38 \
  --idle-time-limit 10 \
  --last-frame-duration 10 \
  --cols 120 \
  --rows 34 \
  "$CAST_PATH" \
  "$GIF_PATH"

ffmpeg \
  -y \
  -hide_banner \
  -loglevel warning \
  -i "$GIF_PATH" \
  -an \
  -movflags +faststart \
  -vf "fps=30,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x07101d,format=yuv420p" \
  "$MP4_PATH"

printf 'Wrote %s\n' "$MP4_PATH"
