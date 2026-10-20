#!/usr/bin/env bash
# Purpose: record the film's two live terminal clips, the Codex provider self-test and the
# GoalChainer incident review with its recorded provenance, each as one capture: an MP4 in
# public/recordings with its cast and GIF in out/live-casts/<the MP4 path's own directory>/<the MP4's
# digest>/. A clip is published only when its recorder and both renders succeeded; a failed one exits
# with its status, leaving its capture and every later clip's whole.
# am[implements a-rre-wrapper-status-1018@6b705b] am[implements a-rfb-capture-commit-1018@2741d7]
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=_record_lib.sh
source "$ROOT_DIR/scripts/_record_lib.sh"
RECORDING_DIR="$ROOT_DIR/public/recordings"
CAST_DIR="$ROOT_DIR/out/live-casts"

# record_clip <title> <recorder> <name>  ->  public/recordings/<name>.mp4 with its cast and GIF under
# the directory its path owns in out/live-casts, from one recorded run, or the run's failure and
# nothing published
# am[implements a-rre-wrapper-status-1018@6b705b]
record_clip() {
  local title="$1" recorder="$2" name="$3"

  record_workdir "$CAST_DIR"
  record_run "$RECORD_WORK/session.cast" \
    --cols 82 \
    --rows 24 \
    --idle-time-limit 1 \
    --title "$title" \
    -- "$recorder"

  agg \
    --theme github-dark \
    --font-size 22 \
    --line-height 1.22 \
    --speed 1.18 \
    --idle-time-limit 1 \
    --last-frame-duration 40 \
    --cols 82 \
    --rows 24 \
    "$RECORD_WORK/session.cast" \
    "$RECORD_WORK/session.gif"

  ffmpeg \
    -y \
    -hide_banner \
    -loglevel warning \
    -i "$RECORD_WORK/session.gif" \
    -an \
    -movflags +faststart \
    -vf "fps=30,scale=1280:-2,pad=1280:800:(ow-iw)/2:(oh-ih)/2:color=0x07101d,format=yuv420p" \
    "$RECORD_WORK/session.mp4"

  record_publish "$RECORD_WORK" "$CAST_DIR" "$RECORDING_DIR/$name.mp4"
  printf 'Wrote %s\n' "$RECORDING_DIR/$name.mp4"
}

record_tools asciinema agg ffmpeg

record_clip \
  "Live Codex provider self-test" \
  "$ROOT_DIR/scripts/recorders/live-codex-selftest.sh" \
  codex-auth-selftest

# am[implements a-cd-rec-audit-provenance-1018]
record_clip \
  "Live GoalChainer incident review and its recorded provenance" \
  "$ROOT_DIR/scripts/recorders/live-goalchainer-audit.sh" \
  goalchainer-demo
