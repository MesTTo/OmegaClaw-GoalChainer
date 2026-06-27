#!/usr/bin/env bash
# Codex drives OmegaClaw Core, which runs the GoalChainer skill.
#
# This is the real OmegaClaw loop with a real LLM in the seat. OmegaClaw's loop
# (src/loop.metta) builds the agent context (PROMPT + SKILLS + OUTPUT_FORMAT +
# HUMAN-MSG), sends it to the provider, the provider emits "toolName arg" command
# lines, and OmegaClaw runs (eval $command) on each. Here:
#   - the provider is Codex (codex exec), choosing a skill on its own,
#   - the skill it has to choose from includes GoalChainer (its getSkills lines),
#   - the chosen command is evaluated by OmegaClaw's own registry
#     (library OmegaClaw-Core src/skills) + the GoalChainer skill file.
#
# Nothing here is scripted to a fixed answer: Codex reads the menu and the
# incident and picks the command; OmegaClaw evaluates whatever it picked.
#
# Usage:  codex_drives_omegaclaw.sh ["incident text"]
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_omega_lib.sh
source "$HERE/_omega_lib.sh"   # codex_turn, omega_run_metta
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

INCIDENT="${1:-Checkout is down. The on-call engineers want to paste the raw production logs, which include customer emails and order IDs, straight into the public incident channel so everyone can debug. Is that ok, and what should we actually post?}"

bar() { printf '%s\n' "==============================================================="; }

# --- 1) The agent context OmegaClaw sends the provider this cycle ----------------
# PROMPT is OmegaClaw-Core/memory/prompt.txt; the SKILLS block is getSkills plus
# GoalChainer's getSkills lines (goalchainer-skill-docs); OUTPUT_FORMAT and the
# HUMAN-MSG framing are from loop.metta's getContext.
read -r -d '' CONTEXT <<EOF || true
You ARE the OmegaClaw agentic harness (the LLM provider in its loop). Below is the EXACT context string OmegaClaw sent you this cycle. Respond the way the agent must: output ONLY the command lines, each line "toolName arg" with the arg as plain text (no quotes, no variables, no markdown, no code fences, no commentary). Up to 5 lines. Pick the skill(s) from the SKILLS menu that actually fit the request. Do not run any shell command and do not write any file. Output nothing except the command lines.

----- BEGIN CONTEXT -----
PROMPT: You are a OmegaClaw agentic harness in a continuous loop. Understand and remember the user goals, and choose your own goals in ways that are assistive for the user. Use send commands to communicate questions and progress on goals to the user. Responses must be short, communicate with purpose.

SKILLS:
- Remember a particular string such as skills and memories: remember string
- Query long-term embedding memory for skills and memories with short phrases only: query string
- Pin a certain string as short-term working memory item to keep track of task state: pin string
- Execute shell command without apostrophe in string, it returns the command output to you: shell string
- Read file to string: read-file filename
- Send message to user: send string
- Search the web: search string
- Get technical analysis for a stock ticker using the Technical Analysis Agent: technical-analysis ticker
- Execute MeTTa expression: metta sexpression
- Decide what to send in an incident, weighing individual and collective goals, norms (lib_deontic), belief (PeTTaChainer), and motivation (MetaMo); returns a ranked decision with a proof: goalchainer-decision request
- Decide AND execute: run the recommended action on the incident data and return the safe, leak-checked deliverable: goalchainer-solve request
- Reconcile individual vs collective goals with MetaMo's motivation consensus: goalchainer-motivation request
- Deduce the verdict with SNARS, returning a Subjective-Logic opinion with provenance: goalchainer-snars request

OUTPUT_FORMAT: Up to 5 lines, do not wrap quotes around args, do not use variables:
 toolName1 arg1
 toolName2 arg2

LAST_SKILL_USE_RESULTS:  HISTORY:  TIME: $(date '+%Y-%m-%d %H:%M:%S')
:-:-:-: HUMAN-MSG: ${INCIDENT}
----- END CONTEXT -----
EOF

bar
echo "OmegaClaw Core  |  provider: Codex   skills: OmegaClaw + GoalChainer"
bar
echo "HUMAN-MSG: ${INCIDENT}"
echo
echo ">> sending agent context to the provider (codex exec) ..."

# --- 2) Codex acts as the provider and emits the command(s) ----------------------
# codex_turn runs Codex (CODEX_SHOW=1 streams its real run to the terminal).
CMD_RE='^(goalchainer-|remember |query |pin |send |shell |read-file |search |technical-analysis |metta )'
AGENT_OUT="$(codex_turn "$CONTEXT" 1 | grep -E "$CMD_RE" || true)"

if [ -z "$AGENT_OUT" ]; then
  echo "!! provider emitted no recognizable command. raw output kept for inspection."
  exit 1
fi

echo
echo "codex (the agent) emits:"
printf '%s\n' "$AGENT_OUT" | sed 's/^/   /'
echo

# --- 3) OmegaClaw evaluates each emitted command through its own registry --------
EVAL="$WORK/eval_agent_commands.metta"
{
  echo '!(import! &self (library OmegaClaw-Core src/skills))'
  echo '!(import! &self goalchainer_skill)'
  while IFS= read -r line; do
    cmd="${line%% *}"                       # toolName
    arg="${line#* }"                        # everything after the first space
    case "$cmd" in
      goalchainer-decision|goalchainer-solve|goalchainer-motivation|goalchainer-snars)
        esc="${arg//\\/\\\\}"; esc="${esc//\"/\\\"}"
        echo "!(eval ($cmd \"$esc\"))"
        echo '!("")'
        ;;
    esac
  done <<< "$AGENT_OUT"
} > "$EVAL"

echo "OmegaClaw evaluates the agent's command(s):"
echo
# DEMO_DELAY pauses between output lines so a recording reads like a live session.
omega_run_metta "$EVAL" \
  | while IFS= read -r line; do printf '   %s\n' "$line"; [ "${DEMO_DELAY:-0}" != 0 ] && sleep "$DEMO_DELAY"; done
echo
bar
