"""Purpose: supply explicit resource allowances and incident text requests for regression fixtures."""

import json

from goal_chainer.runtime.budget import RunBudget


# These are test inputs, not application defaults or performance acceptance thresholds.
# am[verifies a-integrate-request-budget-surface-1018@d6882c]
LIMITS = {"inference_budget": 1_000_000_000, "timeout_seconds": 600}
CLI_LIMITS = ["--inference-budget", str(LIMITS["inference_budget"]),
              "--timeout-seconds", str(LIMITS["timeout_seconds"])]


# am[verifies a-integrate-request-budget-surface-1018@d6882c]
def budget() -> RunBudget:
    return RunBudget(**LIMITS)


# am[verifies a-integrate-request-budget-surface-1018@d6882c]
def wire(text: str) -> str:
    return json.dumps({"request": text, **LIMITS})


# The incident is an explicit test input. Production requests choose their own domain and context.
# am[verifies a-integrate-domain-surface-1018@759698]
def review_request(text: str) -> str:
    instant = "2026-10-16T09:00:00+00:00"
    return json.dumps({
        "operation": "review", "domain": {"packaged": "incident"},
        "context": {"review_id": "incident-example", "subject": "checkout",
                    "trigger": "incident-report", "as_of": instant, "authority": "advisory",
                    "policy_version": "incident-v1", "readings": []},
        "reading": {"text": text, "observed_at": instant, "valid_until": None},
        **LIMITS,
    })
