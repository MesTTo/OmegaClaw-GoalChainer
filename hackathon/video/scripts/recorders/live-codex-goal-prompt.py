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

import codex_chat  # noqa: E402
from codex_chat import CODEX_DEFAULT_MODEL, ask, amsg, umsg  # noqa: E402
from goal_chainer.deontic import resolve_norms  # noqa: E402
from goal_chainer.scenarios import incident_response_scenario  # noqa: E402


USER_REQUEST = """Checkout is down and I have to post an update.

Engineering wants to paste raw logs into the incident room because it might speed up debugging.
Support says those logs may include customer emails, order IDs, and request payloads.
Customers are asking what is happening, and the responders still need enough detail to coordinate.

What should I send now, and what should I avoid sending?"""


CONCISE_STYLE = """Answer like an incident decision assistant.
Use plain language. Do not assume the user knows OmegaClaw, deontic logic, PeTTaChainer, STV, or audit vocabulary.
Do not ask the user to paste tool output. After the first user message, tool results arrive internally.
For every non-final answer, use at most 3 short lines.
For the final answer, use at most 6 short lines."""

codex_chat.SYSTEM = CONCISE_STYLE


PLAN_PROMPT = """The user asked in natural language:

{request}

{style}

Reply in 3 short lines:
1. the likely safe direction,
2. what you will check with tools,
3. that raw logs are not approved yet."""


GIT_PROMPT = """Internal tool result from tool(git.inspect_runtime):

{tool_result}

{style}

Say in 2 short lines whether the run can proceed and whether secrets were exposed."""


GOAL_MAP_PROMPT = """Internal tool result from tool(omegaclaw.translate_plain_request):

{tool_result}

{style}

Translate this into plain terms in 3 short lines: who is protected, who needs help, and the options."""


DEONTIC_PROMPT = """Internal tool result from tool(omegaclaw.check_publish_rules):

{tool_result}

{style}

Explain the rule result in 3 short lines. Avoid formal terminology unless quoting the action name."""


RANKING_PROMPT = """Internal tool result from tool(omegaclaw.rank_safe_actions):

{tool_result}

{style}

Explain the result in 3 short lines: recommended action, blocked action, and why holding is not enough."""


COUNTERFACTUAL_PROMPT = """Internal tool result from tool(omegaclaw.try_alternatives):

{tool_result}

{style}

Explain in 3 short lines why the alternatives fail."""


PLAN_SYNTHESIS_PROMPT = """Internal tool result from tool(omegaclaw.write_incident_reply):

{tool_result}

{style}

Turn this into 3 short incident-command lines: publish, restrict, review."""


PETTA_INCIDENT_PROMPT = """Internal tool result from tool(pettachainer.incident_forensic_packet):

{tool_result}

{style}

Explain in 3 short lines why a reviewer can trust the evidence."""


AUDIT_PROMPT = """Internal tool result from tool(pettachainer.audit_summary):

{tool_result}

{style}

Explain the audit in 3 short lines without jargon."""


TEST_PROMPT = """Internal tool result from tool(test.goalchainer_pytest):

{tool_result}

{style}

Say in 3 short lines what passed and what this proves for the demo."""


FINAL_PROMPT = """The user asked:

{request}

Internal final context:

{tool_result}

{style}

Give the final answer to the user in 6 concise lines:
decision, exact update to send, what to keep private, what is blocked, evidence, human review."""


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


def visible_answer_lines(answer: str, max_lines: int) -> list[str]:
    lines = [line.strip() for line in answer.splitlines() if line.strip()]
    return lines[:max_lines] or ["[empty response]"]


def print_codex_answer(answer: str, max_lines: int) -> None:
    for index, line in enumerate(visible_answer_lines(answer, max_lines)):
        prefix = "codex> " if index == 0 else ""
        print(f"{prefix}{line}", flush=True)
        time.sleep(0.12)
    print()


def ask_codex(history: list[dict], prompt: str, visible: str | None = None, max_lines: int = 3) -> str:
    if visible is not None:
        type_block("user> ", visible)
    else:
        slow_print("agent> passing tool result to Codex internal context", delay=0.08)
    answer = ask(history + [umsg(prompt)], MODEL or CODEX_DEFAULT_MODEL)
    print_codex_answer(answer, max_lines)
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
    print_tool_header("omegaclaw.translate_plain_request", "map the natural-language incident request", GOALCHAINER_DIR)
    scenario = incident_response_scenario()
    lines = [
        "real-world situation: checkout outage with possible customer data in logs",
        "",
        "what must be protected or achieved:",
    ]
    for goal in scenario.goals:
        requirement = "must" if goal.required else "may"
        lines.append(
            f"  {requirement}: {goal.statement} owner={goal.owner} weight={goal.weight:.2f}"
        )
    lines.append("")
    lines.append("choices the agent will compare:")
    for action in scenario.actions:
        lines.append(f"  {action.id}: {action.label} evidence={action.default_strength:.2f}")
    summary = "\n".join(lines)
    slow_print(summary)
    print()
    return summary


def deontic_trace() -> str:
    print_tool_header("omegaclaw.check_publish_rules", "check which choices are allowed", GOALCHAINER_DIR)
    scenario = incident_response_scenario()
    lines = ["publish rules:"]
    for norm in sorted(scenario.norms, key=lambda item: item.priority, reverse=True):
        lines.append(
            f"  priority={norm.priority:02d} {norm.mode:<6} {norm.target_action}"
        )
        lines.append(f"    reason={norm.reason}")
    lines.append("")
    lines.append("allowed-choice check:")
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
    print_tool_header("omegaclaw.rank_safe_actions", "PYTHONPATH=src python3 -m goal_chainer.cli demo --json", GOALCHAINER_DIR)
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
    print_tool_header("omegaclaw.try_alternatives", "test what goes wrong if the agent chooses differently", GOALCHAINER_DIR)
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
    print_tool_header("omegaclaw.write_incident_reply", "compile safe publish plan from winning action", GOALCHAINER_DIR)
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


def internal_turn(history: list[dict], prompt_template: str, tool_result: str, max_lines: int = 3) -> None:
    prompt = prompt_template.format(tool_result=tool_result, style=CONCISE_STYLE)
    answer = ask_codex(history, prompt, max_lines=max_lines)
    history.extend([umsg(prompt), amsg(answer)])
    time.sleep(SECTION_PAUSE)


def main() -> int:
    model = MODEL or CODEX_DEFAULT_MODEL
    print(f"Codex-led OmegaClaw demo - model={model}")
    print("The user speaks once in natural language. Codex then talks to its tools.\n")
    time.sleep(SECTION_PAUSE)

    history: list[dict] = []

    first_prompt = PLAN_PROMPT.format(request=USER_REQUEST, style=CONCISE_STYLE)
    first_answer = ask_codex(history, first_prompt, visible=USER_REQUEST, max_lines=3)
    history.extend([umsg(first_prompt), amsg(first_answer)])
    time.sleep(SECTION_PAUSE)

    git_result = inspect_git_runtime()
    internal_turn(history, GIT_PROMPT, git_result, max_lines=2)

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
    final_prompt = FINAL_PROMPT.format(request=USER_REQUEST, tool_result=final_context, style=CONCISE_STYLE)
    final_answer = ask_codex(history, final_prompt, max_lines=6)
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
