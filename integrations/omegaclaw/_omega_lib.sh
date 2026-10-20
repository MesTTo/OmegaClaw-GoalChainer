# Purpose: shared helpers for the Codex + Omega drivers, sourced by both: codex_turn runs Codex as
# Omega's provider under a reply schema; omega_prompt, omega_registered, omega_tools, omega_rules,
# omega_extensions, omega_reply_schema, omega_calls and omega_eval_skill give the agent's prompt,
# the plugin's skills, the tools Omega offers an LLM, the skill rules and prompt extensions of
# Omega's context, the schema of Codex's reply, the calls Omega reads in a reply and the loop's
# result for one call, as upstream Omega would; omega_result reports that result, omega_field and
# omega_call_text read a call's parts, omega_send is this host's answer to the agent's send, and
# omega_data, omega_show and omega_name print what a driver did not write, the user's words, Codex's
# run, every result and every tool name a reply supplies, as data.
# omega_metta and the helpers built on it run omega_metta.py, Omega's registry and the installed
# GoalChainer plugin on pymetta, in the interpreter the plugin's install recorded.
# Omega is the pinned external/OmegaClaw-Core unless OMEGACLAW_DIR names another checkout, and the
# interpreter is the recorded one unless GOALCHAINER_PYTHON names another.
# am[implements a-rt-vendored-defaults-1016@182749] am[implements a-rt-oh-pymetta-run-1018@ace6fb]
# am[implements a-op-drivers-tools-1018@a61ed7]

_OMEGA_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_OMEGA_REPO="$(cd "$_OMEGA_HERE/../.." && pwd)"
OMEGACLAW_DIR="${OMEGACLAW_DIR:-$_OMEGA_REPO/external/OmegaClaw-Core}"

# omega_python  ->  the interpreter the installed plugin runs GoalChainer's skills in
# scripts/install_plugin.py records it in the checkout's install receipt; a checkout with no receipt
# has no plugin installed, which scripts/setup-omegaclaw.sh does.
# am[implements a-rt-oh-pymetta-run-1018@ace6fb]
omega_python() {
  if [ -n "${GOALCHAINER_PYTHON:-}" ]; then
    printf '%s\n' "$GOALCHAINER_PYTHON"
    return
  fi
  local receipt="$OMEGACLAW_DIR/.goalchainer-plugin-receipt.json"
  if [ ! -f "$receipt" ]; then
    echo "no GoalChainer plugin is installed in $OMEGACLAW_DIR; run scripts/setup-omegaclaw.sh" >&2
    return 1
  fi
  python3 -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["python"])' "$receipt"
}

# omega_metta <action> [arguments]  ->  omega_metta.py's answer; standard input passes through
# The child boots its own pymetta, which refuses an SWI-Prolog home it did not bring, so the
# SWI_HOME_DIR a pymetta host process set stays out of it, as gcskill keeps it out of the skill
# process; -I keeps PYTHONPATH and PYTHONHOME out.
# am[implements a-rt-oh-pymetta-run-1018@ace6fb] am[rests-on c-rt-pymetta-not-inside-swi-1016@304c96]
omega_metta() {
  local python
  python="$(omega_python)" || return 1
  env -u SWI_HOME_DIR "$python" -I "$_OMEGA_HERE/omega_metta.py" --omega "$OMEGACLAW_DIR" "$@"
}

# omega_prompt  ->  the agent's PROMPT: Omega's getPrompt reads memory/prompt_PROVIDER.txt and falls
# back to memory/prompt.txt (src/memory.metta:18-28 at 1a7624e), the only one a Codex provider has.
# am[implements a-rt-oh-derived-menu-1018@d6bf3d]
omega_prompt() {
  cat "$OMEGACLAW_DIR/memory/prompt.txt"
}

# omega_registered  ->  the skills the plugin's loader registered, one per line
# am[implements a-rt-oh-request-review-1018@4f055a] am[implements a-op-session-self-1018@bd8329]
omega_registered() { omega_metta registered </dev/null; }

# omega_tools [names...]  ->  as one JSON list, the tools Omega offers an LLM for the named skills,
# or for every skill, each as upstream's provider sends it
# am[implements a-op-reply-schema-1018@d51383]
omega_tools() { omega_metta tools "$@" </dev/null; }

# omega_rules  ->  the skill rules Omega's context carries under SKILLS, one per line;
# omega_extensions  ->  the text the plugin adds to the context after them
# am[implements a-rt-oh-derived-menu-1018@d6bf3d] am[implements a-op-drivers-tools-1018@a61ed7]
omega_rules() { omega_metta rules </dev/null; }
# am[implements a-rt-oh-derived-menu-1018@d6bf3d]
omega_extensions() { omega_metta extensions </dev/null; }

# omega_reply_schema <tools>  ->  the JSON schema Codex's reply must satisfy to call those tools
# am[implements a-op-reply-schema-1018@d51383]
omega_reply_schema() { printf '%s' "$1" | omega_metta schema; }

# omega_calls <tools> <reply>  ->  the calls Omega's loop reads in Codex's <reply> against the
# offered <tools>, one JSON object a line, {"id", "command", "arguments", "alert"}: upstream validates
# the reply, renders it and reads it back with sread, so each call's arguments are the strings Omega
# would evaluate, and a call or reply upstream refused carries the loop's alert instead. It fails
# only when the host could not read the reply.
# am[implements a-op-calls-1018@94747e]
omega_calls() { printf '%s' "$2" | omega_metta calls "$1"; }

# omega_field <json-object> <key> [index]  ->  that key's value, or its element at <index>, as text
# when a string, as nothing when null and as JSON otherwise, with no newline added
# am[implements a-rt-oh-request-review-1018@4f055a]
omega_field() {
  printf '%s' "$1" | python3 -I -c '
import json, sys
value = json.load(sys.stdin)[sys.argv[1]]
if len(sys.argv) > 2:
    value = value[int(sys.argv[2])]
sys.stdout.write(value if isinstance(value, str) else "" if value is None else json.dumps(value))' "${@:2}"
}

# omega_call_text <call>  ->  one of omega_calls' calls as a line of text: its command and each
# argument as it is, or "(the reply)" for a reply Omega refused whole
# am[implements a-op-drivers-tools-1018@a61ed7]
omega_call_text() {
  printf '%s' "$1" | python3 -I -c '
import json, sys
call = json.load(sys.stdin)
sys.stdout.write(" ".join([call["command"] or "(the reply)", *call["arguments"]]))'
}

# codex_turn <context> <show_header> <schema>
# Sends the context to Codex (Omega's provider) with <schema> as its reply's output schema and echoes
# the captured stdout: Codex's final message, the JSON of its tool calls. With CODEX_SHOW=1 Codex's
# real run streams to the terminal so a recording shows it working: show_header=1 keeps the
# version/model banner (the first cycle) and 0 shows only the reasoning and the reply (later cycles),
# so the banner is not repeated; otherwise its progress is dropped. What it shows is Codex's text,
# so it streams as data (omega_data), each line flushed as awk selects it, and the turn returns only
# once the last of it is shown, so no driver line lands among it: the filter is opened on a
# descriptor of this shell, whose process the turn waits for once Codex has exited and the
# descriptor is closed, since a process substitution on the pipeline's last command would belong to
# that command's subshell and leave $! here empty.
# am[implements a-op-reply-schema-1018@d51383] am[rests-on c-op-codex-output-schema-strict-1018@139d03]
# am[implements a-rre-renderer-origin-1018@ee6148]
codex_turn() {
  local context="$1" show_header="${2:-1}" schema="$3" shown status shown_fd filter
  if [ "${CODEX_SHOW:-0}" != 1 ]; then
    shown='0'
  elif [ "$show_header" = 1 ]; then
    shown='BEGIN{p=1} /^user$/{p=0} /^hook: SessionStart$/{p=1} p{print; fflush()}'
  else
    shown='BEGIN{p=0} /^hook: SessionStart Completed$/{p=1;next} /^hook: Stop$/{p=0} p{print; fflush()}'
  fi
  exec {shown_fd}> >(awk "$shown" | omega_data >&2)
  filter=$!
  printf '%s' "$context" | codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check \
    --output-schema <(printf '%s' "$schema") - 2>&"$shown_fd"
  status=$?
  exec {shown_fd}>&-
  wait "$filter"
  return "$status"
}

# omega_eval_skill <command> <arguments>  ->  the loop's result for the plugin skill's call, its
# arguments a JSON list crossing on standard input, never as shell words: SUCCESS, RETURN: and the
# answers (status 0), or the loop's ALERT_FAILED for a skill that raised (status 3). Any other status
# is a host that could not run it, explained on standard error.
# am[implements a-rt-oh-request-review-1018@4f055a] am[implements a-op-calls-1018@94747e]
omega_eval_skill() {
  printf '%s' "$2" | omega_metta eval "$1"
}

# omega_result <command> <arguments>  ->  what a driver reports for the call: omega_eval_skill's
# result, or "(COMMAND could not run, status N)" for a host that could not run it, whose standard
# error explains why. Its status is omega_eval_skill's, so only 0 is the skill's success.
# am[implements a-op-drivers-tools-1018@a61ed7] am[implements a-od-count-only-the-request-1018@f2f5a8]
omega_result() {
  local result status
  result="$(omega_eval_skill "$1" "$2")"
  status=$?
  [ "$status" = 0 ] || [ "$status" = 3 ] || result="($1 could not run, status $status)"
  printf '%s\n' "$result"
  return "$status"
}

# omega_send <agent-text>  ->  what this host does when the agent sends: nothing leaves it. A
# GoalChainer review, plan or admission authorizes no action and confirms no effect, and this demo
# host holds no authorization of its own, so the agent's text is shown as asked and not delivered
# (status 1). A model-valid plan alone never becomes host authorization.
# am[implements a-rt-oh-request-review-1018@4f055a]
omega_send() {
  echo "(not delivered: GoalChainer's results authorize nothing, and this host has no authorization of its own to send)"
  echo "the agent asked to send: $1"
  return 1
}

# omega_pace  ->  the pause DEMO_DELAY asks for between output lines, so a recording reads like a
# live session; status 0 either way, so a driver under set -e and pipefail goes on.
# am[implements a-rt-oh-request-review-1018@4f055a]
omega_pace() {
  [ "${DEMO_DELAY:-0}" = 0 ] || sleep "$DEMO_DELAY"
}

# _omega_escape data | _omega_escape name <name>  ->  text a driver did not write, every character
# it does not keep shown as its escape in the forms Python's backslashreplace writes, each with one
# reading: two hex digits below U+0100 (a carriage return as \x0d, a space in a name as \x20, a
# backslash in a name as \x5c), backslash-u and four below U+10000 (U+202E, and the byte 0xff of a
# name as the surrogate U+DCFF its argument decoding gives it, PEP 383), backslash-U and eight past
# it. Data keeps every character but a control, format or surrogate character or a line or paragraph
# separator, and keeps a tab. A name keeps only printable ASCII other than the backslash, which every
# tool name the drivers serve is, as UTS 39 restricts identifiers to an allowed set: a character
# that renders as nothing or as a blank, U+034F, U+FE0F, U+3164 or U+2800 among them, shows as its
# escape, so no name reads as another, and a shown name reads back as its bytes. Data shows an
# undecodable byte as \xNN and keeps its backslashes, since the terminal's renderer reads a result's
# Python text from it.
# data prints each line of standard input three spaces in, as it arrives, only a line feed ending a
# line; name prints <name> as one token for a driver's own line. A driver prints its own lines from the
# first column and nothing else there, so no data, whatever text it carries, reads as one of them, to
# a presenter or a viewer: it can neither start a line in the first column nor end one, move the
# cursor back or up, erase, recolour or reorder what the terminal shows. A tab, which data keeps,
# only steps forward on its own line.
# Time: linear in the text's length.
# am[implements a-rre-renderer-origin-1018@ee6148] am[implements a-rfb-name-escape-1018@714ba3]
# am[rests-on c-rre-gha-stdout-commands-1018@032f9d] am[implements a-rfb-name-injective-1018@0bffc5]
# am[rests-on c-rfb-backslashreplace-forms-1018@696cf7] am[rests-on c-rfb-name-escape-not-injective-1018@1f47b1]
# am[rests-on c-rfb-pep383-1018@08f5e0] am[implements a-rfb-name-ascii-raw-1018@55758d]
# am[rests-on c-rfb-served-names-ascii-1018@18e519] am[rests-on eba9cd1f@576a04]
_omega_escape() {
  python3 -I -u -c '
import sys, unicodedata
mode = sys.argv[1]
sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
kept = {"name": lambda c: "!" <= c <= "~" and c != "\\",
        "data": lambda c: c == "\t" or unicodedata.category(c) not in ("Cc", "Cf", "Cs", "Zl", "Zp")}[mode]
def shown(c):
    if kept(c):
        return c
    code = ord(c)
    return f"\\x{code:02x}" if code < 0x100 else f"\\u{code:04x}" if code < 0x10000 else f"\\U{code:08x}"
if mode == "name":
    sys.stdout.write("".join(map(shown, sys.argv[2])))
else:
    sys.stdin.reconfigure(newline="\n", errors="backslashreplace")
    for line in sys.stdin:
        sys.stdout.write("   " + "".join(map(shown, line.removesuffix("\n"))) + "\n")' "$@"
}

# omega_data  ->  standard input as lines of data (_omega_escape data)
# am[implements a-rre-renderer-origin-1018@ee6148]
omega_data() { _omega_escape data; }

# omega_name <name>  ->  a tool name a reply supplied, escaped for a driver's own line
# (_omega_escape name): a call's name is the agent's text, not the driver's
# am[implements a-rfb-name-escape-1018@714ba3]
omega_name() { _omega_escape name "$1"; }

# omega_show <text>  ->  <text> as data (omega_data), one line at a time at the pace omega_pace sets
# am[implements a-rre-renderer-origin-1018@ee6148]
omega_show() {
  printf '%s\n' "$1" | omega_data | while IFS= read -r line; do printf '%s\n' "$line"; omega_pace; done
}
