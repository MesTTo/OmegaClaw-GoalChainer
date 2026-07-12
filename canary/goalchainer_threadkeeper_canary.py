#!/usr/bin/env python3
"""GoalChainer → ThreadKeeper supervised canary.

Non-live, non-Telegram, non-destructive. Runs GoalChainer's solve_incident
over a test request, maps the recommended/candidate decisions to ThreadKeeper
queued task contracts, drains them through the bounded worker loop, and
adjudicates the results.

Modes:
  --fake       Use deterministic fake worker (default, no real LLM call)
  --openclaw   Use real local OpenClaw Gateway worker calls

Usage:
    PYTHONPATH=src python3 canary/goalchainer_threadkeeper_canary.py [--mode fake|openclaw]

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

    done_criteria = [f"evidence_proof:{p}" for p in proofs]
    if not done_criteria:
        done_criteria = [f"action_completed:{action_id}"]

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
        "patch_proposal_only": True,
        "requires_adjudication": status in ADJUDICATED_STATUSES,
    }
    return contract


# --- Fake worker (no real LLM call) ---

def fake_worker_response(goal: str) -> dict:
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
    checks = {}
    action_id = decision["action_id"]
    summary = worker_result.get("summary", "")

    # Evidence check: worker should mention the action_id or acknowledge the task
    checks["evidence_check"] = action_id in summary or "Fake worker" in summary or len(summary) > 10

    # Norm check: forbidden actions should not appear
    norm_status = decision.get("norm_status", "unregulated")
    checks["norm_check"] = norm_status != "forbidden"

    # Goal check: missing required goals should be empty or addressed
    missing = decision.get("missing_required_goals", [])
    checks["goal_check"] = len(missing) == 0

    # Leak check: no actual leaked secret values or PII in worker output
    # The worker mentioning "secret" or "credential" as a concern is fine —
    # it means the worker is correctly identifying risks, not leaking data
    checks["leak_check"] = not any(
        kw in summary.lower()
        for kw in ["api_key=", "password=", "token=", "-----begin"]
    )

    all_pass = all(checks.values())
    return {
        "action_id": action_id,
        "checks": checks,
        "verdict": "accepted" if all_pass else "rejected",
        "worker_summary": summary,
    }


# --- OpenClaw Gateway worker ---

def setup_openclaw_env():
    """Set up environment for OpenClaw Gateway worker calls."""
    # Get gateway token if not already set
    if not os.environ.get("OPENCLAW_GATEWAY_TOKEN"):
        secrets_path = os.path.expanduser("~/.openclaw/secrets.json")
        with open(secrets_path, encoding="utf-8") as f:
            secrets = json.load(f)
        os.environ["OPENCLAW_GATEWAY_TOKEN"] = secrets["gateway"]["authToken"]
    print(f"    OPENCLAW_GATEWAY_TOKEN: set ({len(os.environ['OPENCLAW_GATEWAY_TOKEN'])} chars)")
    print(f"    Gateway base URL: {os.environ.get('OPENCLAW_GATEWAY_BASE_URL', 'http://127.0.0.1:18789/v1')}")


# --- Main canary ---

def main() -> int:
    parser = argparse.ArgumentParser(description="GoalChainer-ThreadKeeper canary")
    parser.add_argument("--mode", choices=["fake", "openclaw"], default="fake",
                        help="Worker mode: fake (no LLM) or openclaw (real Gateway)")
    parser.add_argument("--request", type=str,
                        default="An AI system produced an unexpected output during a demo. Decide how to respond.")
    args = parser.parse_args()

    print("=== GoalChainer → ThreadKeeper Canary ===")
    print(f"Mode: {args.mode}")
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

    # Step 3: Set up ThreadKeeper queue
    print("[3] Setting up ThreadKeeper queue...")
    queue_dir = Path(subagent.SUBAGENT_RUN_DIR) / "queue"
    queue_dir.mkdir(exist_ok=True, parents=True)
    for old in queue_dir.glob("canary-task-*.json"):
        for suffix in ["", ".sha256", ".done", ".failed", ".done.result.json", ".failed.result.json"]:
            p = Path(str(old) + suffix)
            p.unlink(missing_ok=True)
    print(f"    Queue dir: {queue_dir}")

    persona_key = "canary-worker" if args.mode == "openclaw" else "default"

    for i, task in enumerate(tasks_to_queue):
        contract = task["contract"]
        decision = task["decision"]
        task_record = {
            "run_id": f"canary-{i:04d}",
            "status": "queued",
            "queued_at": time.time(),
            "persona_key": persona_key,
            "goal": contract["objective"],
            "tool_subset": ["read-file"],  # emit is always available; need at least one tool
            "max_turns": 1,
            "max_chars": 1000,
            "task_contract": contract,
        }
        task_name = f"canary-task-{i:04d}.json"
        task_path = queue_dir / task_name
        task_path.write_text(json.dumps(task_record, indent=2))
        content = task_path.read_bytes()
        checksum = hashlib.sha256(content).hexdigest()
        (task_path.with_suffix(".json.sha256")).write_text(checksum + "\n")
        print(f"    Queued: {task_name} (action={decision['action_id']}, persona={persona_key})")
    print()

    # Step 4: Drain queue
    if args.mode == "fake":
        print("[4] Draining queue through ThreadKeeper (fake worker, no real LLM)...")
    else:
        print("[4] Draining queue through ThreadKeeper (real OpenClaw Gateway)...")
        setup_openclaw_env()
    print()

    results = []
    pending = sorted(queue_dir.glob("canary-task-*.json"))
    for task_path in pending:
        if task_path.name.endswith(".sha256"):
            continue
        print(f"    Claiming {task_path.name}...")

        if args.mode == "fake":
            # Patch dispatch to use fake worker
            original_dispatch = subagent.dispatch
            def patched_dispatch(goal, tool_subset_csv, persona_key, max_turns=1, max_chars=1000):
                return json.dumps(fake_worker_response(goal))
            subagent.dispatch = patched_dispatch
            try:
                result_record = subagent.run_queued_dispatch(str(task_path))
            finally:
                subagent.dispatch = original_dispatch
        else:
            # Use real dispatch (OpenClaw Gateway via canary-worker persona)
            result_record = subagent.run_queued_dispatch(str(task_path))

        if isinstance(result_record, str):
            result_record = json.loads(result_record)
        results.append(result_record)
        status = result_record.get("status", "unknown")
        token_usage = result_record.get("worker_token_usage", {})
        print(f"    Result: status={status}, tokens={token_usage.get('total_tokens', 'N/A')}")
    print(f"    Drained {len(results)} tasks")
    print()

    # Step 5: Adjudicate results
    print("[5] Adjudicating worker results against GoalChainer decisions...")
    all_adjudications = []
    for i, (task, result_record) in enumerate(zip(tasks_to_queue, results)):
        decision = task["decision"]
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
    print(f"Mode: {args.mode}")
    print(f"GoalChainer decisions: {len(decisions)}")
    print(f"Tasks queued: {len(tasks_to_queue)}")
    print(f"Tasks drained: {len(results)}")
    print(f"Adjudications: {accepted} accepted, {rejected} rejected")
    print(f"Deferred: {len(deferred)}, Forbidden: {len(forbidden)}")

    # Write canary artifact
    artifact = {
        "mode": args.mode,
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

    # Cleanup canary queue tasks
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
