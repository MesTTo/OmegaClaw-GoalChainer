#!/usr/bin/env bash
# Purpose: record the live terminal demo, the stock provider self-test and then Codex driving Omega
# through the GoalChainer plugin's tools, to out/omegaclaw-terminal-live-demo.mp4 by way of an
# asciinema cast and a GIF, publishing them as one capture, the cast and GIF in
# out/live-casts/<the MP4 path's own directory>/<the MP4's digest>/, only when the demo and both
# renders succeeded; a failed run or publication exits with its status and leaves the current
# capture whole.
# am[implements a-tr-terminal-wrapper-1018@a7ad4c] am[implements a-rre-wrapper-status-1018@6b705b]
# am[implements a-rfb-capture-commit-1018@2741d7]
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=_record_lib.sh
source "$ROOT_DIR/scripts/_record_lib.sh"
CAST_DIR="$ROOT_DIR/out/live-casts"
MP4_PATH="${1:-$ROOT_DIR/out/omegaclaw-terminal-live-demo.mp4}"

record_tools asciinema agg ffmpeg
record_workdir "$CAST_DIR"
record_run "$RECORD_WORK/session.cast" \
  --cols 110 \
  --rows 32 \
  --title "Omega terminal live demo" \
  -- "$ROOT_DIR/scripts/recorders/live-terminal-full-demo.sh"

agg \
  --theme github-dark \
  --font-size 24 \
  --line-height 1.2 \
  --speed 0.35 \
  --idle-time-limit 12 \
  --last-frame-duration 12 \
  --cols 110 \
  --rows 32 \
  "$RECORD_WORK/session.cast" \
  "$RECORD_WORK/session.gif"

ffmpeg \
  -y \
  -hide_banner \
  -loglevel warning \
  -i "$RECORD_WORK/session.gif" \
  -an \
  -movflags +faststart \
  -vf "fps=30,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x07101d,format=yuv420p" \
  "$RECORD_WORK/session.mp4"

record_publish "$RECORD_WORK" "$CAST_DIR" "$MP4_PATH"
printf 'Wrote %s\n' "$MP4_PATH"
