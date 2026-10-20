#!/usr/bin/env bash
# Purpose: record a recorder script's terminal session under asciinema, render it to a GIF with agg
# and convert that to the MP4 the film embeds, publishing them as one capture, the MP4 with its cast
# and GIF in out/live-casts/<the MP4 path's own directory>/<the MP4's digest>/, only when the recorder
# and both renders succeeded; a failed run or publication exits with its status and leaves the
# current capture whole.
#   record-cast.sh <recorder-script> <out.mp4> [cols] [rows] [title]
# am[implements a-rre-wrapper-status-1018@6b705b] am[implements a-rfb-capture-commit-1018@2741d7]
set -euo pipefail

RECORDER="$1"
MP4_PATH="$2"
COLS="${3:-104}"
ROWS="${4:-30}"
TITLE="${5:-OmegaClaw demo}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=_record_lib.sh
source "$ROOT_DIR/scripts/_record_lib.sh"
CAST_DIR="$ROOT_DIR/out/live-casts"
record_tools asciinema agg ffmpeg ffprobe
record_workdir "$CAST_DIR"
record_run "$RECORD_WORK/session.cast" --cols "$COLS" --rows "$ROWS" --title "$TITLE" -- "$RECORDER"

# idle-time-limit compresses Codex's think-wait; speed >1 keeps typed parts brisk.
agg --theme github-dark --font-size 21 --line-height 1.22 --speed 1.1 \
  --idle-time-limit 3 --last-frame-duration 4 --cols "$COLS" --rows "$ROWS" \
  "$RECORD_WORK/session.cast" "$RECORD_WORK/session.gif"

ffmpeg -y -hide_banner -loglevel warning -i "$RECORD_WORK/session.gif" -an -movflags +faststart \
  -vf "fps=30,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x06090f,format=yuv420p" \
  "$RECORD_WORK/session.mp4"

record_publish "$RECORD_WORK" "$CAST_DIR" "$MP4_PATH"
printf 'Wrote %s (%ss)\n' "$MP4_PATH" \
  "$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$MP4_PATH")"
