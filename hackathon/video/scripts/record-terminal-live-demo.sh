#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CAST_DIR="$ROOT_DIR/out/live-casts"
MP4_PATH="${1:-$ROOT_DIR/out/omegaclaw-terminal-live-demo.mp4}"
CAST_PATH="$CAST_DIR/terminal-live-demo.cast"
GIF_PATH="$CAST_DIR/terminal-live-demo.gif"

mkdir -p "$CAST_DIR" "$(dirname "$MP4_PATH")"

for tool in asciinema agg ffmpeg; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    printf 'Missing required recorder tool: %s\n' "$tool" >&2
    exit 1
  fi
done

asciinema rec \
  --overwrite \
  --quiet \
  --cols 110 \
  --rows 32 \
  --title "OmegaClaw terminal live demo" \
  --command "$ROOT_DIR/scripts/recorders/live-terminal-full-demo.sh" \
  "$CAST_PATH"

agg \
  --theme github-dark \
  --font-size 24 \
  --line-height 1.2 \
  --speed 0.75 \
  --idle-time-limit 12 \
  --last-frame-duration 15 \
  --cols 110 \
  --rows 32 \
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
