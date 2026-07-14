"""Artifact-only GoalChainer → ThreadKeeper adapter validator.

Validates GoalChainer decision dicts before constructing ThreadKeeper task
contracts.  No provider, live queue, Telegram, runtime bridge, memory write,
or authority change is involved.

This module formalises the fail-closed contract described in
``docs/GOAL_TASK_STATE_CONTRACT.md`` v0.2:

  * ``action_id`` must be a non-empty unique string.
  * ``status`` must be one of the known statuses.
  * ``norm_status`` must be one of the known norm statuses.
  * ``score`` must be a finite number in ``[0, 1]``.
  * ``evidence`` must be present with at least one proof pointer.
  * A forbidden norm always blocks queueing, regardless of score or status.
  * Duplicate ``action_id`` within a single decision batch is rejected.
  * Unknown / malformed / ambiguous results fail closed (do not queue).

The validator is intentionally pure: it does not import GoalChainer internals,
ThreadKeeper, or any runtime component.  It operates entirely on plain dicts.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KNOWN_STATUSES: frozenset[str] = frozenset(
    {"recommended", "candidate", "held", "weak", "blocked"}
)

KNOWN_NORM_STATUSES: frozenset[str] = frozenset(
    {"obliged", "permitted", "forbidden", "unregulated"}
)

# Statuses that may produce a candidate queue record.
QUEUE_ELIGIBLE_STATUSES: frozenset[str] = frozenset(
    {"recommended", "candidate"}
)

# Statuses that are never queued.
QUEUE_EXCLUDED_STATUSES: frozenset[str] = frozenset(
    {"held", "weak", "blocked"}
)

# Minimum required decision fields for shape validation.
REQUIRED_DECISION_FIELDS: tuple[str, ...] = (
    "action_id",
    "label",
    "status",
    "score",
    "norm_status",
    "evidence",
)


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DecisionValidation:
    """Outcome of validating a single decision dict."""
    action_id: str
    valid: bool
    queue_eligible: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class BatchValidation:
    """Outcome of validating a batch of decision dicts."""
    valid_count: int
    invalid_count: int
    queue_eligible_count: int
    results: tuple[DecisionValidation, ...] = ()
    batch_errors: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Single-decision validation
# ---------------------------------------------------------------------------

def validate_decision(decision: dict) -> DecisionValidation:
    """Validate one GoalChainer decision dict.

    Returns a ``DecisionValidation`` with ``valid=True`` when the decision
    is well-formed and ``queue_eligible`` set when it may be queued.

    A forbidden norm always makes a decision non-queue-eligible even if
    the rest of the shape is valid.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # --- Type guard: non-dict inputs fail closed ---
    if not isinstance(decision, dict):
        return DecisionValidation(
            action_id="",
            valid=False,
            queue_eligible=False,
            errors=(f"decision is not a dict: {type(decision).__name__}",),
        )

    # --- Field presence ---
    for field_name in REQUIRED_DECISION_FIELDS:
        if field_name not in decision:
            errors.append(f"missing required field: {field_name}")

    action_id = str(decision.get("action_id", ""))
    if not action_id or not action_id.strip():
        errors.append("action_id is empty or whitespace-only")

    # --- Status ---
    status = decision.get("status", "")
    if status not in KNOWN_STATUSES:
        errors.append(f"unknown status: {status!r} (expected one of {sorted(KNOWN_STATUSES)})")

    # --- Norm status ---
    norm_status = decision.get("norm_status", "")
    if norm_status not in KNOWN_NORM_STATUSES:
        errors.append(
            f"unknown norm_status: {norm_status!r} (expected one of {sorted(KNOWN_NORM_STATUSES)})"
        )

    # --- Score ---
    score = decision.get("score")
    if score is None:
        errors.append("score is missing")
    elif not isinstance(score, (int, float)):
        errors.append(f"score is not a number: {type(score).__name__}")
    elif not math.isfinite(score):
        errors.append(f"score is not finite: {score}")
    elif not (0.0 <= score <= 1.0):
        errors.append(f"score outside [0, 1]: {score}")

    # --- Evidence ---
    evidence = decision.get("evidence")
    if evidence is None:
        errors.append("evidence is missing")
    elif not isinstance(evidence, dict):
        errors.append(f"evidence is not a dict: {type(evidence).__name__}")
    else:
        proofs = evidence.get("proofs")
        if proofs is None:
            errors.append("evidence.proofs is missing")
        elif not isinstance(proofs, (list, tuple)):
            errors.append(f"evidence.proofs is not a list: {type(proofs).__name__}")
        elif len(proofs) == 0:
            errors.append("evidence.proofs is empty")

    # --- Norm reasons (optional but checked if present) ---
    norm_reasons = decision.get("norm_reasons", [])
    if norm_reasons and not isinstance(norm_reasons, (list, tuple)):
        errors.append(f"norm_reasons is not a list: {type(norm_reasons).__name__}")

    # --- Queue eligibility ---
    valid = len(errors) == 0
    queue_eligible = False
    if valid:
        if norm_status == "forbidden":
            # Forbidden always blocks queueing, regardless of status or score.
            queue_eligible = False
            warnings.append("forbidden norm_status blocks queueing despite valid shape")
        elif status in QUEUE_EXCLUDED_STATUSES:
            queue_eligible = False
        elif status in QUEUE_ELIGIBLE_STATUSES:
            queue_eligible = True
        else:
            # Should not reach here if status was validated, but be safe.
            queue_eligible = False

    return DecisionValidation(
        action_id=action_id,
        valid=valid,
        queue_eligible=queue_eligible,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


# ---------------------------------------------------------------------------
# Batch validation
# ---------------------------------------------------------------------------

def validate_batch(decisions: Sequence[dict]) -> BatchValidation:
    """Validate a batch of decisions and check for duplicate action IDs."""
    results: list[DecisionValidation] = []
    seen_action_ids: dict[str, int] = {}
    batch_errors: list[str] = []

    for i, decision in enumerate(decisions):
        if not isinstance(decision, dict):
            results.append(DecisionValidation(
                action_id="",
                valid=False,
                queue_eligible=False,
                errors=(f"decision {i} is not a dict: {type(decision).__name__}",),
            ))
            continue
        result = validate_decision(decision)
        results.append(result)

        # Track duplicates
        if result.action_id:
            if result.action_id in seen_action_ids:
                batch_errors.append(
                    f"duplicate action_id: {result.action_id!r} "
                    f"(first at index {seen_action_ids[result.action_id]}, "
                    f"repeat at index {i})"
                )
            else:
                seen_action_ids[result.action_id] = i

    # Invalidate duplicates: mark all but the first occurrence as invalid
    if batch_errors:
        # Re-validate to mark duplicates as invalid in the results
        seen: set[str] = set()
        updated: list[DecisionValidation] = []
        for i, r in enumerate(results):
            if r.action_id in seen_action_ids and r.action_id in seen:
                updated.append(DecisionValidation(
                    action_id=r.action_id,
                    valid=False,
                    queue_eligible=False,
                    errors=r.errors + (f"duplicate action_id: {r.action_id!r}",),
                    warnings=r.warnings,
                ))
            else:
                seen.add(r.action_id)
                updated.append(r)
        results = updated

    valid_count = sum(1 for r in results if r.valid)
    invalid_count = len(results) - valid_count
    queue_eligible_count = sum(1 for r in results if r.queue_eligible)

    return BatchValidation(
        valid_count=valid_count,
        invalid_count=invalid_count,
        queue_eligible_count=queue_eligible_count,
        results=tuple(results),
        batch_errors=tuple(batch_errors),
    )


# ---------------------------------------------------------------------------
# Adapter: validated decision → task contract
# ---------------------------------------------------------------------------

def validated_decision_to_contract(
    decision: dict,
    validation: DecisionValidation | None = None,
) -> dict | None:
    """Map a validated decision to a ThreadKeeper task contract.

    Returns ``None`` if the decision is not queue-eligible.
    Returns a contract dict otherwise.

    This is the artifact-only adapter: it does not claim, queue, or execute.
    """
    if validation is None:
        validation = validate_decision(decision)

    if not validation.valid:
        return None
    if not validation.queue_eligible:
        return None

    action_id = decision["action_id"]
    label = decision.get("label", action_id)
    proofs = decision.get("evidence", {}).get("proofs", [])
    norm_status = decision.get("norm_status", "unregulated")
    norm_reasons = decision.get("norm_reasons", [])

    done_criteria = [f"evidence_proof:{p}" for p in proofs]
    if not done_criteria:
        done_criteria = [f"action_completed:{action_id}"]

    forbidden_actions: list[str] = []
    if norm_status == "forbidden":
        forbidden_actions.append(action_id)
    for reason in norm_reasons:
        if "forbid" in reason.lower():
            forbidden_actions.append(action_id)
            break

    return {
        "objective": f"{action_id}: {label}",
        "allowed_paths": [],
        "forbidden_actions": forbidden_actions,
        "done_criteria": done_criteria,
        "max_tool_calls": 1,
        "patch_proposal_only": True,
        "requires_adjudication": True,
    }
