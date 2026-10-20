"""Purpose: render what the hackathon recorders print from GoalChainer's answers: a skill command's
frame line with exactly the JSON the skill process returned, a typed refusal included, a review
result's recorded provenance, and, run as a filter over the Omega loop driver's report, each answer
the loop names as a plugin skill's shown that way; kept apart from the recorders so
tests/test_hackathon_recorder.py can load it without Codex."""

from __future__ import annotations

import ast
import json
import os
import re
import sys
import time
from collections.abc import Iterable, Iterator


# The JSON is the text the skill process prints under --pretty, so the terminal shows the answer the
# skill gave, an Inquiry, NoPlan, Stale or Ambiguous outcome or a refusal included, and no line beside
# it says anything the answer does not; Codex reads the same answer in the loop's result. `command`
# is the call as the recorder shows it, for example "(goalchainer-request ...)".
# Time and space: linear in the size of the result.
# am[implements a-cd-rec-render-1018@3743ce] am[rests-on c-cd-rec-omegaclaw-error-is-result-1018@dfbc05]
def render_skill_payload(command: str, payload: dict) -> str:
    return f"RESULTS: ((COMMAND_RETURN: {command}))\n{json.dumps(payload, indent=2, sort_keys=True)}"


# The review's fields that say where it came from: its fingerprint, the labels the fingerprint
# leaves out (the review id and reference time), and the inputs it identifies: the subject, the
# authority rung, the domain and review policy with their digests, the engine identity with its
# budget and spend, and the readset, each signal's effective reading with the observations
# behind it (relevance/review.py).
# am[implements a-cd-rec-audit-provenance-1018@a15419] am[rests-on c-cd-rec-review-records-provenance-1018@0877cb]
PROVENANCE = ("fingerprint", "review_id", "as_of", "subject", "review_authority", "domain",
              "review_policy", "engine", "readset")


# The provenance a request result records, each value the result's own; a result without a
# review, a refusal included, has none and raises KeyError. The frame names the review id as
# JSON, so it stays one line whatever the id holds.
# Time and space: linear in the size of the selected fields.
# am[implements a-cd-rec-audit-provenance-1018@a15419] am[rests-on c-cd-rec-review-records-provenance-1018@0877cb]
def render_provenance(result: dict) -> str:
    review = result["review"]
    selected = {field: review[field] for field in PROVENANCE}
    return f"PROVENANCE: {json.dumps(review['review_id'])}\n{json.dumps(selected, indent=2, sort_keys=True)}"


# The loop driver names a plugin skill's answer on a line of its own, "NAME answered:", in the first
# column, where no line of data can start: the drivers print every line of data three spaces in
# (omega_data in integrations/omegaclaw/_omega_lib.sh). The answer is the line right after it, the
# loop's success, SUCCESS, RETURN: and the Python text of the normalized answers
# (src/loop.metta:123-124 at Omega 1a7624e).
# am[implements a-rre-renderer-origin-1018@ee6148]
ANSWERED = re.compile(r"^(\S+) answered:$")
SUCCESS = re.compile(r"^(\s*)SUCCESS, RETURN: (.*)$")


# A plugin skill answers with the JSON its process printed, so a success's answers are a list of
# JSON objects; anything else, a refusal or an alert included, is no skill payload.
# am[implements a-tr-terminal-wrapper-1018@a7ad4c] am[rests-on c-op-loop-result-string-1018@421a49]
def _payloads(answers: str) -> list[dict] | None:
    try:
        listed = ast.literal_eval(answers)
        payloads = [json.loads(answer) for answer in listed]
    except (ValueError, SyntaxError, TypeError):
        return None
    return payloads if payloads and all(isinstance(payload, dict) for payload in payloads) else None


# The terminal's view of the report: the line right after each "NAME answered:" line, when it is a
# success whose answers are skill payloads, is shown as render_skill_payload shows each, under NAME
# and at the line's indent, every rendered line marked so a caller can pace it. Every other line
# passes as the driver printed it, any data that reads like a success, a frame or the loop's own
# lines included, since the origin of an answer is the loop's line and never the text below it.
# Time: linear in the report's length.
# am[implements a-tr-terminal-wrapper-1018@a7ad4c] am[implements a-cd-rec-render-1018@3743ce]
# am[implements a-rre-renderer-origin-1018@ee6148]
def present(lines: Iterable[str]) -> Iterator[tuple[str, bool]]:
    """(line, rendered) for each line the terminal shows, newline included."""

    answered = None
    for line in lines:
        text = line.rstrip("\n")
        command, answered = answered, None
        success = SUCCESS.match(text) if command else None
        payloads = _payloads(success.group(2)) if success else None
        if payloads is not None:
            for payload in payloads:
                for rendered in render_skill_payload(f"({command} ...)", payload).splitlines():
                    yield f"{success.group(1)}{rendered}\n", True
            continue
        origin = ANSWERED.match(text)
        answered = origin.group(1) if origin else None
        yield line, False


# Run as `driver | python3 -I -u goalchainer_render.py`, it shows each line as it arrives, pausing
# TERMINAL_DEMO_LINE_DELAY seconds after each rendered line so a recording can be read.
# am[implements a-tr-terminal-wrapper-1018@a7ad4c]
def main() -> int:
    pace = float(os.environ.get("TERMINAL_DEMO_LINE_DELAY", "0"))
    for line, rendered in present(sys.stdin):
        sys.stdout.write(line)
        sys.stdout.flush()
        if rendered:
            time.sleep(pace)
    return 0


if __name__ == "__main__":
    sys.exit(main())
