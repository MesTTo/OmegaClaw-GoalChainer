#!/usr/bin/env bash
# Purpose: let Codex drive Omega through the GoalChainer plugin's tools, across cycles, on one
# explicit incident review, and report each result and the agent's answer as they are.
#
# This is Omega's agent loop with a real LLM in the seat, run to completion.
# Each cycle rebuilds the context the loop sends its provider (the policy, the skill rules and
# prompt extensions Omega answers once the plugin loaded, the tools this loop serves, this run's
# request, the running HISTORY, the LAST_SKILL_USE_RESULTS, and the standing incident). Codex
# answers with the single next tool call, under an output schema made of those tools, and Omega
# reads the reply through upstream's own provider path: llmProviderChat validates it against the
# offered tools, llmResponseToSExpr renders it and sread reads it back. The loop serves the
# plugin's skills, run through Omega's registry on pymetta, and pin, query and send, which it
# answers itself. The result feeds the next cycle.
#
# The request is explicit: omega_request.py builds the review of the packaged incident
# domain with the user's words unchanged in reading.text and the run's limits, and
# Codex is told to send exactly that. A goalchainer-request is evaluated only when its
# argument is that request (omega_request.py match: the same JSON value); any other is
# refused unevaluated with the members it changes, which Codex reads next, so a later
# exact request still counts. A send is refused until that request has returned a result,
# and the loop fails when it ends without an answer that follows one. The plugin's other
# skills are evaluated and shown as Omega would, and their results count for nothing.
# A call Omega refused, or a reply it refused whole, is not evaluated either: its ALERT_FAILED
# is what Codex reads next, as Omega's loop feeds one back. Only omega_eval_skill's success
# counts as the request's result, never a skill's alert or a host that could not run the skill.
# A turn is one call: a reply Omega read as several calls is refused whole, none of them
# evaluated, and the refusal is what Codex reads next, so a later single call still counts.
# A provider turn that fails, or a reply the host could not read, ends the loop as that failure.
# GoalChainer's results authorize no action, and this host holds no authorization of
# its own, so the agent's answer is shown and delivered nowhere (omega_send).
#
# The report keeps data as data. The loop's own lines start in the first column and nothing else
# does: the user's words, each result and Codex's shown run are printed three spaces in, their
# control characters escaped (omega_show), so no text the user, the agent or a skill writes stands
# as one of the loop's lines. A tool name the reply supplies is the agent's text too, so the loop's
# own lines name a call only as omega_name escapes it, one token. A plugin skill's answer follows a
# line only the loop prints, "NAME answered:", so a presenter frames exactly the answers Omega's
# skills gave.
#
# Nothing is scripted to a fixed answer: Codex reads the tools and the live results
# and chooses each step. Codex really runs, so this needs network and the logged-in
# Codex path. CODEX_SHOW=1 streams Codex's run; DEMO_DELAY paces the eval output.
# am[implements a-od-drivers-1018@e5f805] am[implements a-op-drivers-tools-1018@a61ed7]
# am[related a-rt-oh-derived-menu-1018@d6bf3d] am[related a-rt-oh-request-review-1018@4f055a]
# am[related c-integrate-recorder-early-send-1018@11a28e] am[implements a-rre-renderer-origin-1018@ee6148]
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_omega_lib.sh
source "$HERE/_omega_lib.sh"

INCIDENT="${1:-Checkout is down. The on-call engineers want to paste the raw production logs, which include customer emails and order IDs, straight into the public incident channel so everyone can debug. Is that ok, and what should we actually post?}"
MAX_CYCLES="${OMEGA_MAX_CYCLES:-9}"

# The tools this loop serves, as Omega offers them: the plugin's skills, run through Omega's
# registry, and pin, query and send, which the loop answers itself. Codex's reply schema admits
# these alone.
PLUGIN_SKILLS="$(omega_registered)" || exit 1
[ -n "$PLUGIN_SKILLS" ] || { echo "the GoalChainer plugin registered no skill in $OMEGACLAW_DIR" >&2; exit 1; }
mapfile -t SERVED <<< "${PLUGIN_SKILLS}"
SERVED+=(pin query send)
TOOLS="$(omega_tools "${SERVED[@]}")" || exit 1
SCHEMA="$(omega_reply_schema "$TOOLS")" || exit 1
RULES="$(omega_rules)" || exit 1
EXTENSIONS="$(omega_extensions)" || exit 1
# This run's explicit review, observed now, as one JSON line.
# am[implements a-od-request-builder-1018@cf0f5a]
REQUEST="$(printf '%s' "$INCIDENT" | python3 -I "$HERE/omega_request.py" build --review-id omegaclaw-codex-loop)" || exit 1

POLICY='You are Omega in a continuous loop. This is a compliance-sensitive incident, so do NOT answer from your own judgment and do NOT rush to send. Ground the answer in the GoalChainer tools, which run the formal reasoning in MeTTa. Make ONE tool call per turn, reading LAST_SKILL_USE_RESULTS to choose the next step, in this order, and never repeat a step already in HISTORY:
1. pin the task to track what you are deciding;
2. goalchainer-request with exactly the REQUEST below as its json_request argument, which reviews the user'"'"'s words against the packaged incident domain;
3. send the user your answer: what the review found, which norms apply and which evidence is still missing, and what still needs a person'"'"'s authorization.
GoalChainer'"'"'s results authorize no action and confirm no effect: never say an action is approved or done.'

bar() { printf '%s\n' "==============================================================="; }

bar
echo "Omega  |  provider: Codex   tools: GoalChainer   loop: agent cycles"
bar
echo "HUMAN-MSG:"
omega_show "$INCIDENT"
echo

HISTORY="(none yet)"
LASTRESULTS="(none yet)"
requested=0
answered=0

for cycle in $(seq 1 "$MAX_CYCLES"); do
  CONTEXT="You ARE the Omega agentic harness (the LLM in its loop). Answer ONLY with tool calls, as your output schema requires: one JSON object whose tool_calls list calls the TOOLS below, every argument a string. Make exactly ONE call this turn: the single next step.

PROMPT: ${POLICY}

SKILLS:
${RULES}
${EXTENSIONS}

TOOLS: ${TOOLS}

REQUEST: ${REQUEST}

HISTORY:
${HISTORY}

LAST_SKILL_USE_RESULTS:
${LASTRESULTS}

HUMAN-MSG: ${INCIDENT}"

  echo "------------------- agent cycle ${cycle} -------------------"
  show_header=0; [ "$cycle" = 1 ] && show_header=1
  # am[implements a-od-provider-failure-1018@69017b]
  RAW="$(codex_turn "$CONTEXT" "$show_header" "$SCHEMA")" || { echo "(the provider's turn failed, status $?; ending)"; break; }
  CALLS="$(omega_calls "$TOOLS" "$RAW")" || { echo "(Omega could not read the agent's reply, status $?; ending)"; break; }
  # The turn's call is the one Omega read, a served tool's call or an alert. Omega's own reading,
  # one line a call, counts the calls, so a reply of several is refused whole: none of them runs.
  # am[implements a-tr-one-call-loop-1018@af4f6b]
  mapfile -t TURN <<< "$CALLS"
  echo
  skill=""
  if [ "${#TURN[@]}" -gt 1 ]; then
    names=()
    for entry in "${TURN[@]}"; do names+=("$(omega_field "$entry" command)"); done
    printf -v listed '%s, ' "${names[@]}"
    cmd=""; shown="(a reply of ${#TURN[@]} calls: ${listed%, })"
    echo "codex calls:  ${#TURN[@]} tools at once ..."
    echo "Omega evaluates none of them:"
    RES="(turn refused, nothing evaluated: this loop takes one tool call a turn, and the reply made ${#TURN[@]}: ${listed%, })"
  else
    entry="${TURN[0]}"
    cmd="$(omega_field "$entry" command)"; arguments="$(omega_field "$entry" arguments)"
    alert="$(omega_field "$entry" alert)"; shown="$(omega_call_text "$entry")"
    # am[implements a-rfb-name-escape-1018@714ba3]
    named="(its reply)"; [ -z "$cmd" ] || named="$(omega_name "$cmd")"
    echo "codex calls:  ${named} ..."
    echo "Omega evaluates it:"
    if [ -n "$alert" ]; then
      RES="$alert"
    else
      arg="$(omega_field "$entry" arguments 0)"
      case "$cmd" in
        pin)   RES="PIN-SUCCESS" ;;
        query) RES="(no relevant long-term memory yet)" ;;
        send)
          if [ "$requested" = 1 ]; then
            RES="$(omega_send "$arg")"; answered=1
          else
            RES="(send refused: goalchainer-request has not returned a result)"
          fi ;;
        goalchainer-request)
          # am[implements a-od-count-only-the-request-1018@f2f5a8]
          if RES="$(printf '%s' "$arg" | python3 -I "$HERE/omega_request.py" match "$REQUEST" 2>&1)"; then
            RES="$(omega_result "$cmd" "$arguments")" && requested=1 && skill="$cmd"
          fi ;;
        *)
          RES="$(omega_result "$cmd" "$arguments")" && skill="$cmd" ;;
      esac
    fi
  fi
  # The skill that answered, named on the loop's own line: omega_result's success is the only
  # result that is a plugin skill's answer, and only that line says so.
  # am[implements a-rre-renderer-origin-1018@ee6148]
  [ -z "$skill" ] || echo "$(omega_name "$skill") answered:"
  omega_show "$RES"
  echo

  HISTORY="${HISTORY}
cycle ${cycle}: ${shown}"
  LASTRESULTS="${cmd:-the reply} returned:
${RES}"
  [ "$answered" = 1 ] && break
done

bar
if [ "$answered" = 1 ]; then
  echo "The agent answered after goalchainer-request's result; nothing was delivered, since no one authorized an action."
  bar
else
  echo "Loop ended without an answer that follows a goalchainer-request result."
  bar
  exit 1
fi
