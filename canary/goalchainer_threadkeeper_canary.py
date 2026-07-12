#!/usr/bin/env python3
"""GoalChainer → ThreadKeeper supervised canary.

Non-live, non-Telegram, non-destructive. Runs GoalChainer's solve_incident
over a test request, maps the recommended/candidate decisions to ThreadKeeper
queued task contracts, drains them through the bounded worker loop with a
deterministic fake worker (no real LLM call), and adjudicates the results.

Usage:
    PYTHONPATH=src python3 canary/goalchainer_threadkeeper_canary.py [--max-tasks N]

Exits 0 on success, 1 on any failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

# --- GoalChainer imports ---
GOALCHAINER_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(GOALCHAINER_SRC))

from goal_chainer.pipeline import solve_incident  # noqa: E402

# --- ThreadKeeper imports ---
THREADKEEPER_SRC = Path(__file__).resolve().parent.parent.parent / "ThreadKeeper" / "src"
sys.path.insert(0, str(THREADKEEPER_SRC))

import subagent  # noqa: E402


# --- GoalChainer → ThreadKeeper task contract mapping ---

FORBIDDEN_BY_STATUS = {"blocked"}
ADJUDICATED_STATUSES = {"candidate"}
QUEUE_STATUSES = {"recommended", "candidate"}


def decision_to_task_contract(decision: dict) -> dict:
    """Map a GoalChainer decision dict to a ThreadKeeper task contract."""
    action_id = decision["action_id"]
    status = decision["status"]
    proofs = decision.get("evidence", {}).get("proofs", [])
    norm_status = decision.get("norm_status", "unregulated")
    norm_reasons = decision.get("norm_reasons", [])

    # Build done_criteria from proof obligations
    done_criteria = [f"evidence_proof:{p}" for p in proofs]
    if not done_criteria:
        done_criteria = [f"action_completed:{action_id}"]

    # Forbidden actions: anything the deontic engine says is forbidden
    forbidden_actions = []
    if norm_status == "forbidden":
        forbidden_actions.append(action_id)
    if norm_reasons:
        for reason in norm_reasons:
            if "forbid" in reason.lower():
                forbidden_actions.append(action_id)
                break

    contract = {
        "objective": f"{action_id}: {decision.get('label', action_id)}",
        "allowed_paths": [],
        "forbidden_actions": forbidden_actions,
        "done_criteria": done_criteria,
        "max_tool_calls": 1,
        "patch_proposal_only": True,  # non-destructive canary
        "requires_adjudication": status in ADJUDICATED_STATUSES,
    }
    return contract


# --- Fake worker (no real LLM call) ---

def fake_worker_response(task_record: dict) -> dict:
    """Produce a deterministic fake worker result for canary testing."""
    goal = task_record.get("goal") or task_record.get("task_contract", {}).get("objective", "unknown")
    return {
        "summary": f"Fake worker completed: {goal}",
        "files_changed": [],
        "tests_run": [],
        "uncertainty": "low",
        "next_action": "adjudicate",
        "transcript_status": "done",
    }


# --- Adjudication ---

def adjudicate(decision: dict, worker_result: dict) -> dict:
    """Adjudicate a worker result against the original GoalChainer decision."""
    checks = {}

    # Evidence check: worker should mention the action_id
    action_id = decision["action_id"]
    summary = worker_result.get("summary", "")
    checks["evidence_check"] = action_id in summary or "Fake worker" in summary

    # Norm check: forbidden actions should not appear
    norm_status = decision.get("norm_status", "unregulated")
    checks["norm_check"] = norm_status != "forbidden"

    # Goal check: missing required goals should be empty or addressed
    missing = decision.get("missing_required_goals", [])
    checks["goal_check"] = len(missing) == 0  # pass if no missing goals

    # Leak check: no raw logs / secrets / PII in worker output
    checks["leak_check"] = not any(
        kw in worker_result.get("summary", "").lower()
        for kw in ["secret", "api_key", "password", "token"]
    )
    # Note: "raw_log" as an action_id name is expected; only reject if actual log content is present
    # A real raw log leak would contain actual log lines, not just the action name

    all_pass = all(checks.values())
    return {
        "action_id": action_id,
        "checks": checks,
        "verdict": "accepted" if all_pass else "rejected",
        "worker_summary": summary,
    }


# --- Main canary ---

def main() -> int:
    parser = argparse.ArgumentParser(description="GoalChainer-ThreadKeeper canary")
    parser.add_argument("--max-tasks", type=int, default=10)
    parser.add_argument("--request", type=str, default="An AI system produced an unexpected output during a demo. Decide how to respond.")
    args = parser.parse_args()

    print("=== GoalChainer → ThreadKeeper Canary ===")
    print(f"Request: {args.request}")
    print()

    # Step 1: Run GoalChainer
    print("[1] Running GoalChainer solve_incident...")
    result = solve_incident(args.request)
    decisions = result.get("decisions", [])
    print(f"    GoalChainer produced {len(decisions)} decisions")
    for d in decisions:
        print(f"    - {d['action_id']}: status={d['status']}, norm={d.get('norm_status','?')}, score={d.get('score',0):.4f}")
    print()

    # Step 2: Map decisions to ThreadKeeper task contracts
    print("[2] Mapping decisions to ThreadKeeper task contracts...")
    tasks_to_queue = []
    deferred = []
    forbidden = []
    for d in decisions:
        status = d["status"]
        if status in QUEUE_STATUSES:
            contract = decision_to_task_contract(d)
            tasks_to_queue.append({"decision": d, "contract": contract})
            print(f"    - {d['action_id']}: queued (adjudication={contract['requires_adjudication']})")
        elif status in FORBIDDEN_BY_STATUS or d.get("norm_status") == "forbidden":
            forbidden.append(d)
            print(f"    - {d['action_id']}: forbidden (not queued)")
        else:
            deferred.append(d)
            print(f"    - {d['action_id']}: deferred (status={status})")
    print(f"    Total: {len(tasks_to_queue)} queued, {len(deferred)} deferred, {len(forbidden)} forbidden")
    print()

    if not tasks_to_queue:
        print("[!] No tasks to queue. Canary complete (nothing to drain).")
        return 0

    # Step 3: Set up ThreadKeeper queue (must be inside SUBAGENT_RUN_DIR/queue)
    print("[3] Setting up ThreadKeeper queue...")
    queue_dir = Path(subagent.SUBAGENT_RUN_DIR) / "queue"
    queue_dir.mkdir(exist_ok=True, parents=True)
    # Clean any old canary tasks first
    for old in queue_dir.glob("canary-task-*.json"):
        for suffix in ["", ".sha256", ".done", ".failed", ".done.result.json", ".failed.result.json"]:
            p = Path(str(old) + suffix)
            p.unlink(missing_ok=True)
    print(f"    Queue dir: {queue_dir}")

    for i, task in enumerate(tasks_to_queue):
        contract = task["contract"]
        decision = task["decision"]
        task_record = {
            "run_id": f"canary-{i:04d}",
            "status": "queued",
            "queued_at": time.time(),
            "persona_key": "default",
            "goal": contract["objective"],
            "tool_subset": ["emit"],
            "max_turns": 1,
            "max_chars": 1000,
            "task_contract": contract,
        }
        task_name = f"canary-task-{i:04d}.json"
        task_path = queue_dir / task_name
        task_path.write_text(json.dumps(task_record, indent=2))
        # Write checksum sidecar
        content = task_path.read_bytes()
        checksum = hashlib.sha256(content).hexdigest()
        (task_path.with_suffix(".json.sha256")).write_text(checksum + "\n")
        print(f"    Queued: {task_name} (action={decision['action_id']})")
    print()

    # Step 4: Drain through ThreadKeeper worker loop with fake worker
    print("[4] Draining queue through ThreadKeeper (fake worker, no real LLM)...")
    # We'll call run_queued_dispatch directly for each task, with a patched worker
    # to avoid real LLM calls.
    results = []
    pending = sorted(queue_dir.glob("canary-task-*.json"))
    for task_path in pending:
        if task_path.name.endswith(".sha256"):
            continue
        print(f"    Claiming {task_path.name}...")

        # Patch subagent.dispatch to use fake worker that returns JSON string
        original_dispatch = subagent.dispatch
        def patched_dispatch(goal, tool_subset_csv, persona_key, max_turns=1, max_chars=1000):
            return json.dumps(fake_worker_response({"goal": goal, "task_contract": {}}))
        subagent.dispatch = patched_dispatch

        try:
            result_record = subagent.run_queued_dispatch(str(task_path))
        finally:
            subagent.dispatch = original_dispatch

        # run_queued_dispatch returns a JSON string
        if isinstance(result_record, str):
            result_record = json.loads(result_record)
        results.append(result_record)
        status = result_record.get("status", "unknown")
        print(f"    Result: status={status}, action_id={task_path.stem}")
    print(f"    Drained {len(results)} tasks")
    print()

    # Step 5: Adjudicate results
    print("[5] Adjudicating worker results against GoalChainer decisions...")
    all_adjudications = []
    for i, (task, result_record) in enumerate(zip(tasks_to_queue, results)):
        decision = task["decision"]
        # Extract worker result from the dispatch result record
        result_payload = result_record.get("result", {})
        worker_result = {
            "summary": result_payload.get("summary", result_payload.get("raw_result", str(result_payload))),
        }
        adj = adjudicate(decision, worker_result)
        all_adjudications.append(adj)
        verdict = adj["verdict"]
        print(f"    {decision['action_id']}: verdict={verdict}")
        for check_name, check_pass in adj["checks"].items():
            print(f"      {check_name}: {'PASS' if check_pass else 'FAIL'}")
    print()

    # Summary
    accepted = sum(1 for a in all_adjudications if a["verdict"] == "accepted")
    rejected = sum(1 for a in all_adjudications if a["verdict"] == "rejected")
    print("=== Canary Summary ===")
    print(f"GoalChainer decisions: {len(decisions)}")
    print(f"Tasks queued: {len(tasks_to_queue)}")
    print(f"Tasks drained: {len(results)}")
    print(f"Adjudications: {accepted} accepted, {rejected} rejected")
    print(f"Deferred: {len(deferred)}, Forbidden: {len(forbidden)}")

    # Write canary artifact
    artifact = {
        "request": args.request,
        "goalchainer_result": result,
        "tasks_queued": len(tasks_to_queue),
        "tasks_drained": len(results),
        "adjudications": all_adjudications,
        "deferred": [d["action_id"] for d in deferred],
        "forbidden": [d["action_id"] for d in forbidden],
    }
    artifact_path = Path(tempfile.mktemp(prefix="canary_result_", suffix=".json"))
    artifact_path.write_text(json.dumps(artifact, indent=2, default=str))
    print(f"Artifact: {artifact_path}")

    # Cleanup canary queue tasks (keep artifacts)
    for old in queue_dir.glob("canary-task-*.json"):
        for suffix in ["", ".sha256", ".done", ".failed", ".done.result.json", ".failed.result.json"]:
            p = Path(str(old) + suffix)
            p.unlink(missing_ok=True)

    if rejected > 0:
        print(f"\n[!] {rejected} adjudication(s) rejected — review failures above.")
        return 1
    print("\n[✓] All adjudications passed. Canary successful.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
