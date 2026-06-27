#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RECORDING_DIR="$ROOT_DIR/public/recordings"
CAST_DIR="$ROOT_DIR/out/live-casts"

mkdir -p "$RECORDING_DIR" "$CAST_DIR"

for tool in asciinema agg ffmpeg; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    printf 'Missing required recorder tool: %s\n' "$tool" >&2
    exit 1
  fi
done

record_clip() {
  local title="$1"
  local command="$2"
  local cast_path="$3"
  local gif_path="$4"
  local mp4_path="$5"

  asciinema rec \
    --overwrite \
    --quiet \
    --cols 82 \
    --rows 24 \
    --idle-time-limit 1 \
    --title "$title" \
    --command "$command" \
    "$cast_path"

  agg \
    --theme github-dark \
    --font-size 22 \
    --line-height 1.22 \
    --speed 1.18 \
    --idle-time-limit 1 \
    --last-frame-duration 40 \
    --cols 82 \
    --rows 24 \
    "$cast_path" \
    "$gif_path"

  ffmpeg \
    -y \
    -hide_banner \
    -loglevel warning \
    -i "$gif_path" \
    -an \
    -movflags +faststart \
    -vf "fps=30,scale=1280:-2,pad=1280:800:(ow-iw)/2:(oh-ih)/2:color=0x07101d,format=yuv420p" \
    "$mp4_path"
}

record_clip \
  "Live Codex provider self-test" \
  "$ROOT_DIR/scripts/recorders/live-codex-selftest.sh" \
  "$CAST_DIR/codex-auth-selftest.cast" \
  "$CAST_DIR/codex-auth-selftest.gif" \
  "$RECORDING_DIR/codex-auth-selftest.mp4"

record_clip \
  "Live GoalChainer and PeTTaChainer audit run" \
  "$ROOT_DIR/scripts/recorders/live-goalchainer-audit.sh" \
  "$CAST_DIR/goalchainer-demo.cast" \
  "$CAST_DIR/goalchainer-demo.gif" \
  "$RECORDING_DIR/goalchainer-demo.mp4"

printf 'Wrote %s\n' "$RECORDING_DIR/codex-auth-selftest.mp4"
printf 'Wrote %s\n' "$RECORDING_DIR/goalchainer-demo.mp4"
