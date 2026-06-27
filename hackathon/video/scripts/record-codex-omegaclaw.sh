#!/usr/bin/env bash
# Record the real Codex-drives-OmegaClaw session to public/recordings/codex-omegaclaw.mp4.
# asciinema captures the live run, agg renders it to a GIF, ffmpeg makes the mp4 the
# film embeds. Codex really runs here, so this needs network + the logged-in Codex path.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CAST_DIR="$ROOT_DIR/out/live-casts"
RECORDING_DIR="$ROOT_DIR/public/recordings"
MP4_PATH="${1:-$RECORDING_DIR/codex-omegaclaw.mp4}"
CAST_PATH="$CAST_DIR/codex-omegaclaw.cast"
GIF_PATH="$CAST_DIR/codex-omegaclaw.gif"

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
  --cols 104 \
  --rows 30 \
  --title "Codex drives OmegaClaw Core" \
  --command "$ROOT_DIR/scripts/recorders/live-codex-omegaclaw.sh" \
  "$CAST_PATH"

# idle-time-limit compresses Codex's think-wait; speed >1 keeps the typed parts brisk.
agg \
  --theme github-dark \
  --font-size 21 \
  --line-height 1.22 \
  --speed 1.15 \
  --idle-time-limit 3 \
  --last-frame-duration 4 \
  --cols 104 \
  --rows 30 \
  "$CAST_PATH" \
  "$GIF_PATH"

ffmpeg \
  -y \
  -hide_banner \
  -loglevel warning \
  -i "$GIF_PATH" \
  -an \
  -movflags +faststart \
  -vf "fps=30,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x06090f,format=yuv420p" \
  "$MP4_PATH"

printf 'Wrote %s\n' "$MP4_PATH"
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$MP4_PATH"
