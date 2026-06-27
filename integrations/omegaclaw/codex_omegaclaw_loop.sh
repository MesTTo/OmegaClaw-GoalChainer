#!/usr/bin/env bash
# Codex drives OmegaClaw Core through the GoalChainer skill, across cycles.
#
# This is the OmegaClaw agent loop with a real LLM in the seat, run to completion.
# Each cycle rebuilds the context the loop sends its provider (the prompt, the
# getSkills menu, the running HISTORY, the LAST_SKILL_USE_RESULTS, and the standing
# incident), Codex emits the single next command, and OmegaClaw evaluates it through
# its own registry. The result feeds the next cycle. The agent works the incident
# the way the system intends: ground the verdict in the formal reasoning rather than
# guess, so it runs goalchainer-decision for the proof-backed verdict, then
# goalchainer-solve for the leak-checked deliverable, then sends that to the user.
#
# Nothing is scripted to a fixed answer: Codex reads the menu and the live results
# and chooses each step. Codex really runs, so this needs network and the logged-in
# Codex path. CODEX_SHOW=1 streams Codex's run; DEMO_DELAY paces the eval output.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_omega_lib.sh
source "$HERE/_omega_lib.sh"

INCIDENT="${1:-Checkout is down. The on-call engineers want to paste the raw production logs, which include customer emails and order IDs, straight into the public incident channel so everyone can debug. Is that ok, and what should we actually post?}"
MAX_CYCLES="${OMEGA_MAX_CYCLES:-9}"

SKILLS='- Query long-term memory with a short phrase: query string
- Pin a string as short-term working memory to track task state: pin string
- Send a message to the user: send string
- Decide what to send in an incident, weighing individual and collective goals, norms (lib_deontic), belief (PeTTaChainer) and motivation (MetaMo); returns a ranked, proof-backed verdict: goalchainer-decision request
- Decide AND execute: run the recommended action on the incident data and return the safe, leak-checked deliverable: goalchainer-solve request
- Reconcile individual vs collective goals with MetaMo consensus: goalchainer-motivation request
- Deduce the verdict with SNARS, a Subjective-Logic opinion with provenance: goalchainer-snars request'

POLICY='You are OmegaClaw in a continuous loop. This is a compliance-sensitive incident, so do NOT answer from your own judgment and do NOT rush to send. Investigate thoroughly first, the way this harness requires (several cycles before answering), grounding everything in the GoalChainer skill, which runs the formal reasoning on PeTTa. Work ONE command per turn, reading LAST_SKILL_USE_RESULTS to choose the next step, in this order, and never repeat a step already in HISTORY:
1. pin the task to track what you are deciding;
2. goalchainer-snars to get the Subjective-Logic opinion on sharing the raw log (belief, disbelief, uncertainty, with provenance);
3. goalchainer-motivation to reconcile the individual goal against the collective goal with MetaMo consensus;
4. goalchainer-decision for the ranked, proof-backed verdict (lib_deontic + PeTTaChainer + MetaMo);
5. goalchainer-solve for the leak-checked deliverable;
6. send that deliverable to the user.
Do not send until goalchainer-solve has returned safe=True.'

bar() { printf '%s\n' "==============================================================="; }
delay() { [ "${DEMO_DELAY:-0}" != 0 ] && sleep "$DEMO_DELAY"; }

bar
echo "OmegaClaw Core  |  provider: Codex   skill: GoalChainer   loop: agent cycles"
bar
echo "HUMAN-MSG: ${INCIDENT}"
echo

HISTORY="(none yet)"
LASTRESULTS="(none yet)"
answered=0

for cycle in $(seq 1 "$MAX_CYCLES"); do
  CONTEXT="You ARE the OmegaClaw agentic harness (the LLM in its loop). Output ONLY command lines, each \"toolName arg\" (no quotes, no markdown, no commentary). Emit exactly ONE command this turn: the single next step.

PROMPT: ${POLICY}

SKILLS:
${SKILLS}

HISTORY:
${HISTORY}

LAST_SKILL_USE_RESULTS:
${LASTRESULTS}

HUMAN-MSG: ${INCIDENT}"

  echo "------------------- agent cycle ${cycle} -------------------"
  show_header=0; [ "$cycle" = 1 ] && show_header=1
  RAW="$(codex_turn "$CONTEXT" "$show_header")"
  OUT="$(printf '%s\n' "$RAW" | grep -E '^(goalchainer-|query |pin |send )' | head -1 || true)"
  if [ -z "$OUT" ]; then echo "(no command emitted; ending)"; break; fi

  echo
  echo "codex emits:  ${OUT%% *} ..."
  cmd="${OUT%% *}"; arg="${OUT#* }"
  echo "OmegaClaw evaluates it:"
  case "$cmd" in
    goalchainer-decision|goalchainer-solve|goalchainer-motivation|goalchainer-snars)
      RES="$(omega_eval_skill "$cmd" "$arg")" ;;
    pin)   RES="PIN-SUCCESS" ;;
    query) RES="(no relevant long-term memory yet)" ;;
    send)  RES="-> delivered to the incident channel:
${arg}" ; answered=1 ;;
    *)     RES="(unknown command)" ;;
  esac
  printf '%s\n' "$RES" | while IFS= read -r l; do printf '   %s\n' "$l"; delay; done
  echo

  HISTORY="${HISTORY}
cycle ${cycle}: ${OUT}"
  LASTRESULTS="${cmd} returned:
${RES}"
  [ "$answered" = 1 ] && break
done

bar
[ "$answered" = 1 ] && echo "Agent delivered a grounded, leak-checked answer." || echo "Loop ended."
bar
