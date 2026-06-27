#!/usr/bin/env bash
# Generic terminal-cast recorder: run a recorder script under asciinema, render it
# to a GIF with agg, and convert to the mp4 the film embeds.
#   record-cast.sh <recorder-script> <out.mp4> [cols] [rows] [title]
set -euo pipefail

RECORDER="$1"
MP4_PATH="$2"
COLS="${3:-104}"
ROWS="${4:-30}"
TITLE="${5:-OmegaClaw demo}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CAST_DIR="$ROOT_DIR/out/live-casts"
base="$(basename "${MP4_PATH%.mp4}")"
CAST_PATH="$CAST_DIR/$base.cast"
GIF_PATH="$CAST_DIR/$base.gif"

mkdir -p "$CAST_DIR" "$(dirname "$MP4_PATH")"
for tool in asciinema agg ffmpeg; do
  command -v "$tool" >/dev/null 2>&1 || { printf 'Missing recorder tool: %s\n' "$tool" >&2; exit 1; }
done

asciinema rec --overwrite --quiet --cols "$COLS" --rows "$ROWS" \
  --title "$TITLE" --command "$RECORDER" "$CAST_PATH"

# idle-time-limit compresses Codex's think-wait; speed >1 keeps typed parts brisk.
agg --theme github-dark --font-size 21 --line-height 1.22 --speed 1.1 \
  --idle-time-limit 3 --last-frame-duration 4 --cols "$COLS" --rows "$ROWS" \
  "$CAST_PATH" "$GIF_PATH"

ffmpeg -y -hide_banner -loglevel warning -i "$GIF_PATH" -an -movflags +faststart \
  -vf "fps=30,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x06090f,format=yuv420p" \
  "$MP4_PATH"

printf 'Wrote %s (%ss)\n' "$MP4_PATH" \
  "$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$MP4_PATH")"
