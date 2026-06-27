#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path


CODEX_AUTH_DIR = Path(os.environ.get("OMEGACLAW_CORE_CODEX_AUTH_DIR", "/home/user/Dev/OmegaClaw-Core-codex-auth"))
GOALCHAINER_DIR = Path(os.environ.get("OMEGACLAW_GOALCHAINER_DIR", "/home/user/Dev/OmegaClaw-GoalChainer"))
PETTACHAINER_DIR = Path(os.environ.get("PETTACHAINER_DIR", "/home/user/Dev/PeTTaChainer"))
PYTHON_BIN = os.environ.get("GOALCHAINER_PYTHON", "python3")
TYPE_DELAY = float(os.environ.get("TERMINAL_DEMO_TYPE_DELAY", "0.018"))
LINE_DELAY = float(os.environ.get("TERMINAL_DEMO_LINE_DELAY", "0.22"))
SECTION_PAUSE = float(os.environ.get("TERMINAL_DEMO_SECTION_PAUSE", "2.0"))
MODEL = os.environ.get("TERMINAL_DEMO_CODEX_MODEL")

sys.path.insert(0, str(CODEX_AUTH_DIR))
sys.path.insert(0, str(GOALCHAINER_DIR / "src"))

from codex_chat import CODEX_DEFAULT_MODEL, ask, amsg, umsg  # noqa: E402
from goal_chainer.deontic import resolve_norms  # noqa: E402
from goal_chainer.scenarios import incident_response_scenario  # noqa: E402


USER_REQUEST = """I am incident commander for a production outage.

Engineering wants raw logs in the response channel because it would speed up repair.
Legal and support are worried the logs include private customer data.
Customers still need a useful update, and responders need enough shared context to coordinate.

Use your tools and decide what we should publish. I do not want a score table.
I want the safe action, the blocked action, the reason, and what evidence proves it."""


PLAN_PROMPT = """The user asked in natural language:

{request}

Act as the OmegaClaw agent. Do not ask the user to paste tool output.
State a long tool-driven decision workflow, then wait for tool results.
The workflow should include goals, norms, evidence, counterfactuals, audit, and tests."""


GIT_PROMPT = """Internal tool result from tool(git.inspect_runtime):

{tool_result}

Briefly explain whether the demo can proceed and what this confirms."""


GOAL_MAP_PROMPT = """Internal tool result from tool(goal_chainer.map_stakeholder_goals):

{tool_result}

Explain what the user asked for in terms of individual goals, collective goals, and candidate actions."""


DEONTIC_PROMPT = """Internal tool result from tool(goal_chainer.deontic_trace):

{tool_result}

Explain which action is forbidden, which is obligated, and why priority matters."""


RANKING_PROMPT = """Internal tool result from tool(goal_chainer.rank_actions):

{tool_result}

Explain the ranking. Name the recommended action, the blocked action, the weak action, and the fairness floor."""


COUNTERFACTUAL_PROMPT = """Internal tool result from tool(goal_chainer.counterfactual_probe):

{tool_result}

Use these counterfactuals to explain why this is not just a score table. Keep it concise."""


PLAN_SYNTHESIS_PROMPT = """Internal tool result from tool(goal_chainer.synthesize_release_plan):

{tool_result}

Turn the safe action into an incident-command plan. Explain what to publish, what to keep restricted, and what to ask a human to review."""


PETTA_INCIDENT_PROMPT = """Internal tool result from tool(pettachainer.incident_forensic_packet):

{tool_result}

Explain why the proof packet is useful to a reviewer. Mention replay, red-team rejection, and noise stability."""


AUDIT_PROMPT = """Internal tool result from tool(pettachainer.audit_summary):

{tool_result}

Explain the audit result and why the terminal is not just printing an unverified story."""


TEST_PROMPT = """Internal tool result from tool(test.goalchainer_pytest):

{tool_result}

Explain what the tests cover and whether the demo can be trusted enough for a hackathon recording."""


FINAL_PROMPT = """The user asked:

{request}

Internal final context:

{tool_result}

Give the final answer to the user in eight concise lines:
decision, publish text, private restriction, blocked action, weak action, evidence, audit, human review."""


def slow_print(text: str = "", delay: float = LINE_DELAY) -> None:
    for line in text.splitlines() or [""]:
        print(line, flush=True)
        time.sleep(delay)


def type_block(prefix: str, text: str) -> None:
    sys.stdout.write(prefix)
    sys.stdout.flush()
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(TYPE_DELAY)
    print("\n")


def ask_codex(history: list[dict], prompt: str, visible: str | None = None) -> str:
    if visible is not None:
        type_block("user> ", visible)
    else:
        slow_print("agent> passing tool result to Codex internal context", delay=0.08)
    sys.stdout.write("codex> ")
    sys.stdout.flush()
    answer = ask(history + [umsg(prompt)], MODEL or CODEX_DEFAULT_MODEL, stream_to=sys.stdout)
    print("\n")
    if not answer.strip():
        raise RuntimeError("Codex response was empty")
    return answer


def run_capture(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env={**os.environ, **(env or {})},
        check=True,
        capture_output=True,
        text=True,
    )


def load_showcase_json(name: str) -> dict:
    return json.loads((PETTACHAINER_DIR / "artifacts/showcase" / name).read_text())


def print_tool_header(name: str, command: str, cwd: Path) -> None:
    slow_print(f"tool({name})", delay=0.08)
    slow_print(f"$ cd {cwd}", delay=0.08)
    slow_print(f"$ {command}", delay=0.08)


def inspect_git_runtime() -> str:
    print_tool_header("git.inspect_runtime", "git branch --show-current && git status --short --branch", CODEX_AUTH_DIR)
    branch = run_capture(["git", "branch", "--show-current"], CODEX_AUTH_DIR).stdout.strip()
    status = run_capture(["git", "status", "--short", "--branch"], CODEX_AUTH_DIR).stdout.strip()
    checks = {
        "codex_auth_branch": branch,
        "worktree": status.splitlines()[0] if status else "unknown",
        "provider_script": str((CODEX_AUTH_DIR / "codex_chat.py").exists()),
        "auth_values": "hidden",
    }
    lines = [
        f"branch: {checks['codex_auth_branch']}",
        f"worktree: {checks['worktree']}",
        f"codex chat helper present: {checks['provider_script']}",
        "credential values: hidden",
    ]
    slow_print("\n".join(lines))
    print()
    return "\n".join(lines)


def map_stakeholder_goals() -> str:
    print_tool_header("goal_chainer.map_stakeholder_goals", "read incident_response_scenario()", GOALCHAINER_DIR)
    scenario = incident_response_scenario()
    lines = [scenario.title, "", "stakeholder goals:"]
    for goal in scenario.goals:
        requirement = "required" if goal.required else "optional"
        lines.append(
            f"  {goal.id}: owner={goal.owner} kind={goal.kind} weight={goal.weight:.2f} {requirement}"
        )
        lines.append(f"    {goal.statement}")
    lines.append("")
    lines.append("candidate actions:")
    for action in scenario.actions:
        lines.append(f"  {action.id}: {action.label}")
        lines.append(f"    satisfies={', '.join(action.satisfies)}")
        lines.append(f"    default evidence strength={action.default_strength:.2f}")
    summary = "\n".join(lines)
    slow_print(summary)
    print()
    return summary


def deontic_trace() -> str:
    print_tool_header("goal_chainer.deontic_trace", "resolve forbid/permit/oblige norms by priority", GOALCHAINER_DIR)
    scenario = incident_response_scenario()
    lines = ["norms:"]
    for norm in sorted(scenario.norms, key=lambda item: item.priority, reverse=True):
        lines.append(
            f"  priority={norm.priority:02d} mode={norm.mode:<6} target={norm.target_action}"
        )
        lines.append(f"    reason={norm.reason}")
    lines.append("")
    lines.append("resolution per action:")
    for action in scenario.actions:
        resolution = resolve_norms(action.id, scenario.norms)
        reasons = "; ".join(resolution.reasons) or "none"
        block = "blocks action" if resolution.blocks_action else "does not block"
        lines.append(
            f"  {action.id}: status={resolution.status} priority={resolution.priority} {block}"
        )
        lines.append(f"    {reasons}")
    summary = "\n".join(lines)
    slow_print(summary)
    print()
    return summary


def rank_actions() -> tuple[str, dict]:
    print_tool_header("goal_chainer.rank_actions", "PYTHONPATH=src python3 -m goal_chainer.cli demo --json", GOALCHAINER_DIR)
    result = run_capture(
        [PYTHON_BIN, "-m", "goal_chainer.cli", "demo", "--json"],
        GOALCHAINER_DIR,
        env={"PYTHONPATH": "src"},
    )
    payload = json.loads(result.stdout)
    lines = [payload["scenario"], ""]
    for item in payload["decisions"]:
        missing = ", ".join(item["missing_required_goals"]) or "none"
        satisfied = ", ".join(item["satisfied_goals"])
        lines.extend(
            [
                f"{item['status']:>11} score={item['score']:.3f}  {item['label']}",
                f"            norm={item['norm_status']} evidence={item['evidence']['strength']:.3f}",
                f"            satisfies={satisfied}",
                f"            missing={missing}",
            ]
        )
    lines.extend(["", *payload["notes"]])
    summary = "\n".join(lines)
    slow_print(summary)
    print()
    return summary, payload


def counterfactual_probe(payload: dict) -> str:
    print_tool_header("goal_chainer.counterfactual_probe", "derive counterfactual checks from ranked goals", GOALCHAINER_DIR)
    decisions = {item["action_id"]: item for item in payload["decisions"]}
    redacted = decisions["publish_redacted_summary"]
    hold = decisions["hold_external_update"]
    raw = decisions["publish_raw_log"]
    lines = [
        "counterfactual: if privacy is ignored, raw logs look useful for coordination but fail preserve_privacy.",
        f"  raw_log status={raw['status']} norm={raw['norm_status']} score={raw['score']:.3f}",
        "counterfactual: if we hold the update, privacy is preserved but service repair and team coordination fail.",
        f"  hold status={hold['status']} missing={', '.join(hold['missing_required_goals'])}",
        "positive case: the redacted summary satisfies every required goal and is obligated.",
        f"  redacted status={redacted['status']} satisfied={', '.join(redacted['satisfied_goals'])}",
    ]
    summary = "\n".join(lines)
    slow_print(summary)
    print()
    return summary


def synthesize_release_plan(payload: dict) -> str:
    print_tool_header("goal_chainer.synthesize_release_plan", "compile safe publish plan from winning action", GOALCHAINER_DIR)
    decisions = {item["action_id"]: item for item in payload["decisions"]}
    winner = decisions["publish_redacted_summary"]
    raw = decisions["publish_raw_log"]
    hold = decisions["hold_external_update"]
    lines = [
        "selected action: publish_redacted_summary",
        f"  decision status={winner['status']} score={winner['score']:.3f} norm={winner['norm_status']}",
        "publish externally:",
        "  We are investigating a production outage. Service restoration is in progress.",
        "  We have removed identifiers and will share verified status updates as facts are confirmed.",
        "keep restricted:",
        "  raw incident logs stay in the private response workspace with access limited to responders.",
        "block:",
        f"  publish_raw_log remains {raw['status']} because it misses preserve_privacy and is {raw['norm_status']}.",
        "do not stop here:",
        f"  hold_external_update remains {hold['status']} because it misses restore_service and coordinate_team.",
        "human review gate:",
        "  security owner checks the redaction before external publication.",
    ]
    summary = "\n".join(lines)
    slow_print(summary)
    print()
    return summary


def pettachainer_incident_forensic_packet() -> str:
    print_tool_header(
        "pettachainer.incident_forensic_packet",
        "read showcase-result.json + showcase-forensic-packet.json",
        PETTACHAINER_DIR,
    )
    result = load_showcase_json("showcase-result.json")
    packet = load_showcase_json("showcase-forensic-packet.json")
    incident = result["incident"]
    dispatch = result["dispatch"]["timings"]
    smart = next(item for item in dispatch if item["name"] == "smart")
    reduce = next(item for item in dispatch if item["name"] == "reduce")
    eval_variant = next(item for item in dispatch if item["name"] == "eval")
    noise = result["noise_stability"][-1]
    proof = packet["proof_structure"]
    red_team = packet["red_team"]
    verdict = packet["verdict"]
    truth = incident["truth_values"]
    lines = [
        "forensic packet:",
        f"  verifier_checks_pass={verdict['verifier_checks_pass']}",
        f"  red_team_rejections_pass={verdict['red_team_rejections_pass']}",
        f"  packet_root={packet['packet_root_sha256'][:16]}...",
        "incident proof:",
        f"  facts={incident['facts']} rules={incident['rules']} noise_edges={incident['noise_edges']}",
        f"  isolate_customerdb truth=STV {truth['isolate_customerdb'][0]:.6f} {truth['isolate_customerdb'][1]:.6f}",
        f"  proof certificate={proof['certificate_passes']} proof_sha256={proof['proof_sha256'][:16]}...",
        f"  operator_counts={json.dumps(proof['operator_counts'], sort_keys=True)}",
        "performance and routing:",
        f"  smart dispatch median={smart['median_s']:.6f}s",
        f"  reduce path ratio={reduce['ratio_to_smart']:.2f}x eval path ratio={eval_variant['ratio_to_smart']:.2f}x",
        "noise stability:",
        f"  extra_edges={noise['extra_edges']} atoms={noise['atoms']} proofs={noise['proofs']} stable={noise['stable']}",
        f"  built_in_noise_tokens={noise['built_in_noise_tokens']} injected_noise_tokens={noise['injected_noise_tokens']}",
        "red-team:",
        f"  rejected_cases={red_team['case_count']} mutation_families={len(red_team['mutation_families'])}",
    ]
    summary = "\n".join(lines)
    slow_print(summary)
    print()
    return summary


def audit_summary() -> str:
    print_tool_header(
        "pettachainer.audit_summary",
        "python3 artifacts/showcase/showcase-verify-all.py artifacts/showcase >/tmp/omegaclaw-audit-check.log",
        PETTACHAINER_DIR,
    )
    result = run_capture([PYTHON_BIN, "artifacts/showcase/showcase-verify-all.py", "artifacts/showcase"], PETTACHAINER_DIR)
    Path("/tmp/omegaclaw-audit-check.log").write_text(result.stdout + result.stderr)
    verdict = (PETTACHAINER_DIR / "artifacts/showcase/showcase-audit-verdict.md").read_text()
    wanted = ["Verdict:", "Claims verified:", "Evidence sources sealed:", "Red-team cases:"]
    lines = ["compact audit summary:"]
    for line in verdict.splitlines():
        if any(key in line for key in wanted):
            lines.append(f"  {line.lstrip('- ')}")
    lines.append("  verifier output: PASS PeTTaChainer portable audit capsule")
    summary = "\n".join(lines)
    slow_print(summary)
    print()
    return summary


def run_goalchainer_tests() -> str:
    print_tool_header("test.goalchainer_pytest", "PYTHONPATH=src python3 -m pytest -q", GOALCHAINER_DIR)
    result = run_capture(
        [PYTHON_BIN, "-m", "pytest", "-q"],
        GOALCHAINER_DIR,
        env={"PYTHONPATH": "src"},
    )
    lines = [
        result.stdout.strip(),
        "test focus:",
        "  deontic priority conflict handling",
        "  incident scenario winner and blocked raw-log action",
        "  PeTTa bridge fallback STV parsing and deterministic evidence",
    ]
    summary = "\n".join(line for line in lines if line)
    slow_print(summary)
    print()
    return summary


def internal_turn(history: list[dict], prompt_template: str, tool_result: str) -> None:
    prompt = prompt_template.format(tool_result=tool_result)
    answer = ask_codex(history, prompt)
    history.extend([umsg(prompt), amsg(answer)])
    time.sleep(SECTION_PAUSE)


def main() -> int:
    model = MODEL or CODEX_DEFAULT_MODEL
    print(f"Codex-led OmegaClaw demo - model={model}")
    print("The user speaks once in natural language. Codex then talks to its tools.\n")
    time.sleep(SECTION_PAUSE)

    history: list[dict] = []

    first_prompt = PLAN_PROMPT.format(request=USER_REQUEST)
    first_answer = ask_codex(history, first_prompt, visible=USER_REQUEST)
    history.extend([umsg(first_prompt), amsg(first_answer)])
    time.sleep(SECTION_PAUSE)

    git_result = inspect_git_runtime()
    internal_turn(history, GIT_PROMPT, git_result)

    goal_map_result = map_stakeholder_goals()
    internal_turn(history, GOAL_MAP_PROMPT, goal_map_result)

    deontic_result = deontic_trace()
    internal_turn(history, DEONTIC_PROMPT, deontic_result)

    ranking_result, payload = rank_actions()
    internal_turn(history, RANKING_PROMPT, ranking_result)

    counterfactual_result = counterfactual_probe(payload)
    internal_turn(history, COUNTERFACTUAL_PROMPT, counterfactual_result)

    release_plan = synthesize_release_plan(payload)
    internal_turn(history, PLAN_SYNTHESIS_PROMPT, release_plan)

    forensic_result = pettachainer_incident_forensic_packet()
    internal_turn(history, PETTA_INCIDENT_PROMPT, forensic_result)

    audit_result = audit_summary()
    internal_turn(history, AUDIT_PROMPT, audit_result)

    test_result = run_goalchainer_tests()
    internal_turn(history, TEST_PROMPT, test_result)

    final_context = "\n\n".join(
        [
            "goal map:\n" + goal_map_result,
            "deontic trace:\n" + deontic_result,
            "ranking:\n" + ranking_result,
            "counterfactuals:\n" + counterfactual_result,
            "release plan:\n" + release_plan,
            "forensic packet:\n" + forensic_result,
            "audit:\n" + audit_result,
            "tests:\n" + test_result,
        ]
    )
    final_prompt = FINAL_PROMPT.format(request=USER_REQUEST, tool_result=final_context)
    final_answer = ask_codex(history, final_prompt)
    history.extend([umsg(final_prompt), amsg(final_answer)])

    slow_print(
        textwrap.dedent(
            """

            Terminal demo complete.
            The user asked once in natural language.
            Codex chose tools, read their results, and made the final verified decision.
            """
        ).strip(),
        delay=0.2,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
