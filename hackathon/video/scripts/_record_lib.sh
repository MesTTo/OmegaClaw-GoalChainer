# Purpose: the steps the recording wrappers share: record_tools checks the tools a wrapper runs are
# installed, record_workdir makes the directory a recording is rendered in, record_run records a
# recorder script under asciinema and answers with the recorder's own exit status, and record_publish
# publishes a finished cast, GIF and MP4 as one capture through _record_publish.py, committed by one
# rename of the MP4. A wrapper publishes only after its recorder and its renders succeeded, so a
# failed run or publication exits with the failure's status and leaves the current capture whole.
# am[implements a-rre-wrapper-status-1018@6b705b]

# The directory holding this library and _record_publish.py beside it.
# am[implements a-rfb-publish-module-1018@54117f]
_RECORD_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# record_tools <tool>...  ->  status 0 when every named tool is installed, else 1, naming the first
# that is missing
# am[implements a-rre-wrapper-status-1018@6b705b]
record_tools() {
  local tool
  for tool in "$@"; do
    command -v "$tool" >/dev/null 2>&1 || { printf 'Missing recorder tool: %s\n' "$tool" >&2; return 1; }
  done
}

# record_workdir <dir>  ->  RECORD_WORK set to a new directory inside <dir>, removed when the
# wrapper exits however it exits. Every render is written there, and only record_publish puts one in
# place, each by a rename within the directory it publishes into, so no run leaves a published file
# half-written.
# am[implements a-rre-wrapper-status-1018@6b705b]
record_workdir() {
  mkdir -p "$1" || return 1
  RECORD_WORK="$(mktemp -d "$1/.recording.XXXXXX")" || return 1
  _RECORD_WORKS+=("$RECORD_WORK")
  trap 'rm -rf -- "${_RECORD_WORKS[@]}"' EXIT
}

# record_run <cast> <asciinema option>... -- <recorder>  ->  the recorder's own exit status, its
# session recorded to <cast>. asciinema 2.4.0 runs the command as sh -c and returns 0 whatever the
# command exits with, so the command writes the recorder's status to a file beside <cast>, both paths
# crossing in the environment rather than in the command's text. A recording that ends with no status
# written, as an interrupted one does, fails too.
# am[implements a-rre-wrapper-status-1018@6b705b] am[rests-on c-tbr-asciinema-drops-status-1018@daf97e]
# am[rests-on c-rre-asciinema-runs-sh-1018@c32ecf]
record_run() {
  local cast="$1" options=() status
  shift
  while [ "$#" -gt 0 ] && [ "$1" != -- ]; do options+=("$1"); shift; done
  shift
  # shellcheck disable=SC2016  # sh -c expands the two names from asciinema's copy of the environment
  RECORD_CHILD="$1" RECORD_STATUS="$cast.status" asciinema rec --quiet "${options[@]}" \
    --command '"$RECORD_CHILD"; echo "$?" > "$RECORD_STATUS"' "$cast" || return
  status="$(cat "$cast.status" 2>/dev/null)" || status=""
  case "$status" in
    0) return 0 ;;
    [1-9] | [1-9][0-9] | [12][0-9][0-9])
      printf '%s exited with status %s, so nothing is published\n' "$1" "$status" >&2
      return "$status" ;;
    *)
      printf '%s ended without reporting a status, so nothing is published\n' "$1" >&2
      return 1 ;;
  esac
}

# record_publish <work> <captures> <mp4>  ->  <work>'s session.cast, session.gif and session.mp4
# published as one capture by _record_publish.py: under a lock on the directory <mp4>'s path owns
# beneath <captures>, the one captures root every wrapper passes, the cast and GIF go there under the
# MP4's sha256, one rename of a copy staged in
# <mp4>'s own directory puts the MP4 in place and commits the capture, and only once that directory
# is synced are the other captures the path owns pruned. Its status is the publication's, 0 once the
# new capture is current and synced; on any other the current capture is whole, and a failure or an
# interrupt before the rename leaves it as it was.
# am[implements a-rfb-capture-commit-1018@2741d7] am[implements a-rfb-publish-module-1018@54117f]
# am[implements a-rfb-owned-captures-1018@ac1c98] am[implements a-rfb-commit-observed-1018@1435d8]
record_publish() {
  python3 -I "$_RECORD_LIB_DIR/_record_publish.py" "$@"
}
