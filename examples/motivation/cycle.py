"""Purpose: run Companion and Research observations, host attempts and reviews through the public
request APIs, saving each request and response for inspection. All observations are synthetic;
the example executes no action and never turns a predicted change into an observed one."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from goal_chainer.motivation import run_motivation_request
from goal_chainer.requests import run_request
from goal_chainer.runtime.budget import RunBudget

# These are host-supplied inputs, not expected decisions or a simulation of an action's effects.
# am[implements a-v2-examples-1019@2d047f]
SCENARIOS = {
    "companion": {"need": "activation", "before": 0.9, "after": 0.5, "action": "guide_breath"},
    "research": {"need": "evidence_coverage", "before": 0.2, "after": 0.85, "action": "gather_evidence"},
}


# The domain never receives an expected answer: each decision is the native policy's result.
# Time: eight public requests, each under a separate caller allowance; storage grows by three events.
# am[implements a-v2-examples-1019@2d047f]
def run_cycle(name: str, directory: Path, *, inference_budget: int, timeout_seconds: float) -> list[dict]:
    scenario = SCENARIOS[name]
    domain = {"path": str(Path(__file__).with_name(f"{name}.metta"))}
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    selection = {"store": str(directory / f"{name}.sqlite3"), "stream": name}
    responses: list[dict] = []

    # am[implements a-v2-examples-1019@2d047f]
    def send(label: str, payload: dict) -> dict:
        request = {"domain": domain, **payload}
        (directory / f"{label}.request.json").write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
        api = run_request if request["operation"] == "review" else run_motivation_request
        answer = api(request, budget=RunBudget(inference_budget=inference_budget, timeout_seconds=timeout_seconds))
        (directory / f"{label}.result.json").write_text(
            json.dumps(answer, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        responses.append(answer)
        return answer

    # am[implements a-v2-examples-1019@2d047f]
    def review(label: str, at: str, *, recorded: bool) -> dict:
        return send(label, {"operation": "review", **({"motivation": selection} if recorded else {}),
                           "context": {"review_id": label, "subject": name, "trigger": "host-check-in",
                                       "as_of": at, "authority": "advisory", "readings": [
                                           {"signal": "review_open", "state": "detected", "estimator": "deterministic",
                                            "source": "host:demo", "observed_at": at}]}})

    review("01-unobserved", "2026-10-20T09:00:00+00:00", recorded=False)
    observation = {"need": scenario["need"], "level": scenario["before"], "scale": [0, 1],
                   "estimator": "human-asserted", "source": "host:synthetic-demo",
                   "observed_at": "2026-10-20T09:00:10+00:00"}
    send("02-observe", {"operation": "observe", "motivation": selection, "observations": [observation]})
    proposed = review("03-before", "2026-10-20T09:00:15+00:00", recorded=True)

    # A separate host statement, named in SCENARIOS, not an automatic application of the proposal.
    attempt = {"attempt": f"{name}-host-1", "action": scenario["action"],
               "applied_at": "2026-10-20T09:00:20+00:00", "review_fingerprint": proposed["review"]["fingerprint"]}
    send("04-attempt", {"operation": "attempt", "motivation": selection, "attempts": [attempt]})
    outcome = {**observation, "level": scenario["after"], "observed_at": "2026-10-20T09:00:30+00:00",
               "produced_by": attempt["attempt"]}
    send("05-outcome", {"operation": "observe", "motivation": selection, "observations": [outcome]})
    send("06-status", {"operation": "status", "motivation": selection, "as_of": "2026-10-20T09:00:40+00:00"})
    review("07-after", "2026-10-20T09:00:40+00:00", recorded=True)
    review("08-repeat", "2026-10-20T09:00:40+00:00", recorded=True)
    return responses


# am[implements a-v2-examples-1019@2d047f]
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=SCENARIOS)
    parser.add_argument("--directory", type=Path, required=True, help="private directory for the stream and JSON records")
    parser.add_argument("--inference-budget", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=float, required=True)
    args = parser.parse_args()
    answers = run_cycle(args.scenario, args.directory, inference_budget=args.inference_budget,
                        timeout_seconds=args.timeout_seconds)
    for answer in answers:
        print(json.dumps(answer, allow_nan=False))


if __name__ == "__main__":
    main()
