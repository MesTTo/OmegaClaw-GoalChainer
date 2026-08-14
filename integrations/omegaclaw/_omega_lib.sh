# Shared helpers for the Codex + OmegaClaw drivers. Source this; it defines
# codex_turn (run Codex as the provider) and omega_run_metta (evaluate commands
# through OmegaClaw's own registry). Both the single-shot driver and the
# multi-cycle loop use these, so there is one source of truth.

_OMEGA_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_OMEGA_REPO="$(cd "$_OMEGA_HERE/../.." && pwd)"
PETTA="${PETTA:-/home/user/Dev/PeTTa}"
SWIPL="${SWIPL:-swipl}"
OMEGACLAW_DIR="${OMEGACLAW_DIR:-$_OMEGA_REPO/external/OmegaClaw-Core}"

# omega_metta_prelude  ->  the import lines every generated eval file starts with
# PeTTa resolves a two-argument (library OmegaClaw-Core X) import against a
# registered library_path, and git-import! is what asserts one; on an existing
# directory it registers without cloning. Then OmegaClaw's own skill registry is
# loaded, and GoalChainer's commands come from the installed plugin.
omega_metta_prelude() {
  echo '!(import! &self (library lib_import))'
  echo "!(git-import! \"https://github.com/asi-alliance/OmegaClaw-Core.git\" \"\" \"$(dirname "$OMEGACLAW_DIR")\")"
  echo '!(import! &self (library OmegaClaw-Core ./src/skills))'
  echo '!(import! &self (library OmegaClaw-Core ./plugins/goalchainer/goalchainer))'
}

# codex_turn <context> [show_header]
# Sends the context to Codex (the OmegaClaw provider) and echoes the captured
# stdout: the command line(s) the agent emits. With CODEX_SHOW=1, Codex's real run
# streams to the terminal so a recording shows it working. show_header=1 keeps the
# version/model banner (the first cycle); 0 shows only the reasoning and the command
# (later cycles), so the banner is not repeated.
codex_turn() {
  local context="$1" show_header="${2:-1}"
  local flags=(--dangerously-bypass-approvals-and-sandbox --skip-git-repo-check -)
  if [ "${CODEX_SHOW:-0}" = 1 ]; then
    if [ "$show_header" = 1 ]; then
      printf '%s' "$context" | codex exec "${flags[@]}" \
        2> >(awk 'BEGIN{p=1} /^user$/{p=0} /^hook: SessionStart$/{p=1} p' >&2)
    else
      printf '%s' "$context" | codex exec "${flags[@]}" \
        2> >(awk 'BEGIN{p=0} /^hook: SessionStart Completed$/{p=1;next} /^hook: Stop$/{p=0} p' >&2)
    fi
  else
    printf '%s' "$context" | codex exec "${flags[@]}" 2>/dev/null
  fi
}

# omega_run_metta <metta-file>
# Runs a metta file through PeTTa with the GoalChainer skill on the path, strips
# PeTTa's string quoting and the bare import 'true's, and indents the result.
omega_run_metta() {
  ( cd "$_OMEGA_HERE" && PYTHONPATH="$_OMEGA_REPO/src:$PETTA/python" "$SWIPL" --stack_limit=8g -q \
      -s "$PETTA/src/main.pl" -- "$1" silent 2>/dev/null \
      | sed -E 's/^\("(.*)"\)$/\1/; s/^"(.*)"$/\1/' \
      | grep -vE '^(true|)$' )
}

# omega_eval_skill <command> <arg>  ->  the GoalChainer skill's result
# Builds the eval file (load OmegaClaw's registry + the skill, eval the command)
# and runs it. The command is whatever the agent emitted, evaluated exactly as
# OmegaClaw's loop would.
omega_eval_skill() {
  local cmd="$1" arg="$2" esc f
  esc="${arg//\\/\\\\}"; esc="${esc//\"/\\\"}"
  f="$(mktemp)"
  {
    omega_metta_prelude
    echo "!(eval ($cmd \"$esc\"))"
  } > "$f"
  omega_run_metta "$f"
  rm -f "$f"
}
