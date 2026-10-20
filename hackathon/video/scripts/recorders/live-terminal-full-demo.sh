#!/usr/bin/env bash
# Purpose: run the live terminal demo: show that the stock Codex provider path is ready, then let
# Codex drive Omega through the GoalChainer plugin's tools on one explicit incident review with the
# real loop driver, Codex's run shown and paced and each skill's result rendered as its JSON, and
# print the completion line only when the loop ended on an answer that follows the review's result.
#
# The driver decides everything the demo shows happening: the explicit request and its exact match,
# the tools Codex is offered, one call a turn, the send held until the review returned, and the
# failure of a run that ends without an answer after it. This wrapper adds the banner, the self-test
# and the rendering, and its status is the loop's.
# am[implements a-tr-terminal-wrapper-1018@a7ad4c] am[rests-on c-tr-old-recorder-contract-1018@f91cda]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${OMEGACLAW_GOALCHAINER_DIR:-$(cd "$SCRIPT_DIR/../../../.." && pwd)}"
LINE_DELAY="${TERMINAL_DEMO_LINE_DELAY:-0.14}"

# The demo's own incident, in the words a responder would use.
INCIDENT="${1:-Checkout is down and I have to post an update.

Engineering wants to paste raw logs into the incident room because it might speed up debugging.
Support says those logs may include customer emails, order IDs, and request payloads.
Customers are asking what is happening, and the responders still need enough detail to coordinate.

What should I send now, and what should I avoid sending?}"

printf '\033[1;33mOmega terminal live demo\033[0m\n'
printf 'This run shows Codex leading a multi-step decision loop through stock Omega and the GoalChainer plugin.\n\n'

bash "$SCRIPT_DIR/live-codex-selftest.sh"
printf '\n\033[1;32mStarting the decision loop.\033[0m\n\n'

CODEX_SHOW=1 DEMO_DELAY="$LINE_DELAY" bash "$REPO_DIR/integrations/omegaclaw/codex_omegaclaw_loop.sh" "$INCIDENT" \
  | TERMINAL_DEMO_LINE_DELAY="$LINE_DELAY" python3 -I -u "$SCRIPT_DIR/goalchainer_render.py"

printf '\nTerminal demo complete.\n'
