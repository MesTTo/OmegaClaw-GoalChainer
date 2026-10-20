#!/usr/bin/env bash
# Purpose: let Codex drive Omega, which runs the GoalChainer plugin's tools, for one cycle on one
# explicit incident review, and report what Omega answered for each tool call Codex made.
#
# This is upstream Omega's loop with a real LLM in the seat for one cycle. Omega's loop
# (src/loop.metta) sends its provider a system message built by getContext (PROMPT + SKILLS rules +
# prompt extensions + HISTORY + TIME), the user's message and a tool for every registered skill;
# the provider answers with tool calls, which llmProviderChat validates against those tools,
# llmResponseToSExpr renders and sread reads back, and Omega evaluates each call. Here:
#   - the provider is Codex (codex exec), choosing tools on its own, its reply held to the
#     offered tools by an output schema,
#   - the PROMPT, SKILLS rules, prompt extensions and tools are what Omega answers once the
#     GoalChainer plugin loaded: memory/prompt.txt, getSkillRules, the plugin's extension telling
#     the agent how to write a goalchainer-request, and providers.getTools over getSkills,
#   - after the user's message this host adds the run's explicit request, from omega_request.py:
#     the review of the packaged incident domain with the user's words unchanged in reading.text
#     and the run's limits,
#   - Omega reads Codex's reply through its own provider path (omega_calls), and each plugin call
#     is evaluated as Omega's loop evaluates it, by Omega's own registry with the plugin loaded, on
#     pymetta (omega_metta.py); Omega's own skills are shown, not run, and a call Omega refused
#     is shown with its alert, not run;
#   - a goalchainer-request is evaluated only when its argument is the run's request
#     (omega_request.py match: the same JSON value), and any other is refused unevaluated with
#     the members it changes.
#
# Nothing here is scripted to a fixed answer: Codex reads the tools and the request and writes
# the calls; Omega evaluates whatever it called. A run fails unless the run's own request
# returned a result: the plugin's other skills are shown and count for nothing. It also fails when
# the provider's turn failed or the host could not read its reply.
#
# Usage:  codex_drives_omegaclaw.sh ["request text"]
# am[implements a-od-drivers-1018@e5f805] am[implements a-op-drivers-tools-1018@a61ed7]
# am[related a-rt-oh-derived-menu-1018@d6bf3d] am[related a-rt-oh-request-review-1018@4f055a]
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_omega_lib.sh
source "$HERE/_omega_lib.sh"   # codex_turn, omega_prompt, omega_rules, omega_extensions, omega_registered, omega_tools, omega_reply_schema, omega_calls, omega_field, omega_call_text, omega_result, omega_data, omega_show

INCIDENT="${1:-Checkout is down. The on-call engineers want to paste the raw production logs, which include customer emails and order IDs, straight into the public incident channel so everyone can debug. Is that ok, and what should we actually post?}"

bar() { printf '%s\n' "==============================================================="; }

# --- 1) The request Omega sends the provider this cycle ---------------------------
# Its system message, the PROMPT, SKILLS rules and prompt extensions, and its tools come from Omega
# itself, framed as loop.metta's getContext frames them; the user's message follows, and then the
# request, as this host's own addition, observed now and on one line.
PROMPT="$(omega_prompt)"
RULES="$(omega_rules)"
EXTENSIONS="$(omega_extensions)"
PLUGIN_COMMANDS="$(omega_registered)"
TOOLS="$(omega_tools)"
SCHEMA="$(omega_reply_schema "$TOOLS")"
# am[implements a-od-request-builder-1018@cf0f5a]
REQUEST="$(printf '%s' "$INCIDENT" | python3 -I "$HERE/omega_request.py" build --review-id omegaclaw-codex-driver)"
read -r -d '' CONTEXT <<EOF || true
You ARE the Omega agentic harness (the LLM provider in its loop). Below is the EXACT request Omega sent you this cycle: its system message, the user's message and the tools it offered. Answer the way the agent must: ONLY tool calls, as your output schema requires, one JSON object whose tool_calls list calls the offered tools, every argument a string. Up to 5 calls. Pick the tool(s) that actually fit the request. Do not run any shell command and do not write any file.

----- BEGIN SYSTEM MESSAGE -----
PROMPT: ${PROMPT} SKILLS: ${RULES}
${EXTENSIONS}
 SAVE_PERMANENT_FILES_DIR: ${OMEGACLAW_DIR}/memory HISTORY:  TIME: $(date '+%Y-%m-%d %H:%M:%S')
----- END SYSTEM MESSAGE -----

----- BEGIN USER MESSAGE -----
${INCIDENT}
----- END USER MESSAGE -----

TOOLS: ${TOOLS}

This host's request for the user's words: when you call goalchainer-request, its json_request argument is exactly this JSON, the user's words unchanged in reading.text:
REQUEST: ${REQUEST}
EOF

bar
echo "Omega  |  provider: Codex   tools: Omega + GoalChainer"
bar
# The driver's own lines start in the first column and nothing else does: the user's words, the
# agent's calls and each result are data, three spaces in with their control characters escaped
# (omega_data, omega_show), and a plugin skill's answer follows a line only the driver prints, naming
# the skill as omega_name escapes it.
# am[implements a-rre-renderer-origin-1018@ee6148] am[implements a-rfb-name-escape-1018@714ba3]
echo "HUMAN-MSG:"
omega_show "$INCIDENT"
echo
echo ">> sending Omega's request to the provider (codex exec) ..."

# --- 2) Codex acts as the provider and makes the call(s) --------------------------
# The calls are those Omega's own provider path reads in the reply, each with the string arguments
# Omega would evaluate, or the alert Omega answers for a call or reply it refused.
# am[implements a-od-provider-failure-1018@69017b]
OUTPUT="$(codex_turn "$CONTEXT" 1 "$SCHEMA")" || { echo "!! the provider's turn failed, status $?."; exit 1; }
CALLS="$(omega_calls "$TOOLS" "$OUTPUT")" || { echo "!! Omega could not read the agent's reply, status $?."; exit 1; }

echo
echo "codex (the agent) calls:"
while IFS= read -r entry; do
  omega_call_text "$entry" | omega_data
  echo
done <<< "$CALLS"
echo

# --- 3) Omega evaluates each call through its own registry ------------------------
# Only the run's own request counts, and only when its evaluation succeeded.
# am[implements a-od-count-only-the-request-1018@f2f5a8]
echo "Omega evaluates the agent's call(s):"
echo
reviewed=0
while IFS= read -r entry; do
  cmd="$(omega_field "$entry" command)"; alert="$(omega_field "$entry" alert)"; skill=""
  if [ -n "$alert" ]; then
    result="$alert"   # Omega refused the call, or the whole reply, unevaluated
  elif ! printf '%s\n' "$PLUGIN_COMMANDS" | grep -qxF -- "$cmd"; then
    result="(Omega's own ${cmd}; this driver runs only the GoalChainer plugin's skills)"
  elif [ "$cmd" = goalchainer-request ] \
      && ! result="$(omega_field "$entry" arguments 0 | python3 -I "$HERE/omega_request.py" match "$REQUEST" 2>&1)"; then
    :   # the refusal is the result: the request was not evaluated
  elif result="$(omega_result "$cmd" "$(omega_field "$entry" arguments)")"; then
    skill="$cmd"
    if [ "$cmd" = goalchainer-request ]; then reviewed=1; fi
  fi
  [ -z "$skill" ] || echo "$(omega_name "$skill") answered:"
  omega_show "$result"
  echo
done <<< "$CALLS"
bar
if [ "$reviewed" = 0 ]; then
  echo "!! no goalchainer-request with this run's REQUEST returned a result."
  exit 1
fi
