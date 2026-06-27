#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path


CODEX_AUTH_DIR = Path(os.environ.get("OMEGACLAW_CORE_CODEX_AUTH_DIR", "/home/user/Dev/OmegaClaw-Core-codex-auth"))
GOALCHAINER_DIR = Path(os.environ.get("OMEGACLAW_GOALCHAINER_DIR", "/home/user/Dev/OmegaClaw-GoalChainer"))
PETTACHAINER_DIR = Path(os.environ.get("PETTACHAINER_DIR", "/home/user/Dev/PeTTaChainer"))
PETTA_VENV_PYTHON = PETTACHAINER_DIR / ".venv/bin/python"
PYTHON_BIN = os.environ.get(
    "GOALCHAINER_SKILL_PYTHON",
    str(PETTA_VENV_PYTHON if PETTA_VENV_PYTHON.exists() else "python3"),
)
TYPE_DELAY = float(os.environ.get("TERMINAL_DEMO_TYPE_DELAY", "0.018"))
LINE_DELAY = float(os.environ.get("TERMINAL_DEMO_LINE_DELAY", "0.18"))
SECTION_PAUSE = float(os.environ.get("TERMINAL_DEMO_SECTION_PAUSE", "1.7"))
MODEL = os.environ.get("TERMINAL_DEMO_CODEX_MODEL")

sys.path.insert(0, str(CODEX_AUTH_DIR))

import codex_chat  # noqa: E402
from codex_chat import CODEX_DEFAULT_MODEL, ask, amsg, umsg  # noqa: E402


USER_REQUEST = """Checkout is down and I have to post an update.

Engineering wants to paste raw logs into the incident room because it might speed up debugging.
Support says those logs may include customer emails, order IDs, and request payloads.
Customers are asking what is happening, and the responders still need enough detail to coordinate.

What should I send now, and what should I avoid sending?"""


CONCISE_STYLE = """Answer like an incident decision assistant.
Use plain language. Do not assume the user knows OmegaClaw, deontic logic, PeTTaChainer, STV, or audit vocabulary.
Do not ask the user to paste tool output. After the first user message, tool results arrive internally.
Use straight ASCII quotes.
Use at most 3 short lines before the final answer.
For the final answer, use at most 6 short lines."""


HYPERBASE_PROPOSITION_RULES = """Internal proposition rules for HyperBase translation:
Before calling a tool or answering, rewrite the situation as clear structured propositions.
Use one concrete subject, one predicate, and one object or complement per sentence.
Avoid pronouns and vague references like it, this, that, and the issue.
Preserve domain terms from the request, such as raw logs, customer emails, order IDs, request payloads, responders, security review, and customer update.
Keep observed facts separate from norms and recommendations.
Keep the final user-facing answer plain unless a tool result explicitly shows HyperBase notation."""


SKILL_CATALOGUE = """OmegaClaw skills loaded from integrations/omegaclaw/goalchainer_skill.metta:
- Build COLORE-backed ontology context and HyperBase-ready structured propositions:
  (goalchainer-ontology-context "request")
- Decide an incident action by chaining individual goals, collective goals, norms, and PeTTa evidence:
  (goalchainer-decision "request")
- Inspect the PeTTaChainer proof packet and verifier output for a GoalChainer decision:
  (goalchainer-proof-audit "request")
- Run GoalChainer verification tests and return collected test names plus pass/fail output:
  (goalchainer-tests "request")
- Send the final answer:
  (send "answer")
"""


PLAN_PROMPT = """The user asked in natural language:

{request}

{style}

Reply in 3 short lines:
1. the likely safe direction,
2. that you will call OmegaClaw skills to verify it,
3. that raw logs are not approved yet."""


SKILL_CALL_PROMPT = """You are in OmegaClaw command mode.

The agent must use the actual GoalChainer skills before answering.
Call one new skill at a time, using the exact s-expression form.
Do not invent tool output. Do not ask the user for tool output.

{catalogue}

Original user request:
{request}

Skills already called: {used_skills}
Last skill result:
{last_result}

Required before send:
- goalchainer-ontology-context
- goalchainer-decision
- goalchainer-proof-audit
- goalchainer-tests

Return only one command.
Write the command once.
If any required skill has not been called, call the most useful missing skill now.
If all required skills have been called, return one (send "...") command with the final answer."""


RESULT_PROMPT = """LAST_SKILL_USE_RESULTS:

{tool_result}

{style}

Explain in 3 short lines what this proved and what you will do next.
Do not call a skill in this response. The next command turn comes after this explanation."""


FINAL_REPAIR_PROMPT = """The previous command was not a valid OmegaClaw skill command.

Return exactly one command in this form:
(goalchainer-ontology-context "request")
or
(goalchainer-decision "request")
or
(goalchainer-proof-audit "request")
or
(goalchainer-tests "request")
or
(send "answer")

No prose outside the command."""


codex_chat.SYSTEM = f"{CONCISE_STYLE}\n\n{HYPERBASE_PROPOSITION_RULES}"


@dataclass(frozen=True)
class SkillCall:
    name: str
    argument: str


CALL_RE = re.compile(r"\(*\s*([A-Za-z0-9_-]+)\s+\"((?:[^\"\\]|\\.)*)\"\s*\)*")
REQUIRED_SKILLS = (
    "goalchainer-ontology-context",
    "goalchainer-decision",
    "goalchainer-proof-audit",
    "goalchainer-tests",
)


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


def print_codex_command(command: str) -> None:
    lines = [line.strip() for line in command.splitlines() if line.strip()]
    for index, line in enumerate(lines[:3]):
        prefix = "codex> " if index == 0 else ""
        print(f"{prefix}{line}", flush=True)
        time.sleep(0.12)
    print()


def ask_codex(history: list[dict], prompt: str, visible: str | None = None, max_lines: int = 3) -> str:
    if visible is not None:
        type_block("user> ", visible)
    else:
        slow_print("agent> passing LAST_SKILL_USE_RESULTS back to Codex", delay=0.08)
    answer = ask(history + [umsg(prompt)], MODEL or CODEX_DEFAULT_MODEL)
    print_codex_answer(answer, max_lines)
    if not answer.strip():
        raise RuntimeError("Codex response was empty")
    return answer


def ask_for_skill_call(history: list[dict], prompt: str) -> tuple[str, SkillCall]:
    slow_print("agent> asking Codex for the next OmegaClaw skill command", delay=0.08)
    raw = ask(history + [umsg(prompt)], MODEL or CODEX_DEFAULT_MODEL)
    call = parse_skill_call(raw)
    if call is not None:
        print_codex_command(format_skill_call(call))
        return raw, call

    repaired = ask(history + [umsg(prompt), amsg(raw), umsg(FINAL_REPAIR_PROMPT)], MODEL or CODEX_DEFAULT_MODEL)
    call = parse_skill_call(repaired)
    if call is None:
        print_codex_command(raw)
        raise RuntimeError(f"Codex did not return a valid skill command: {raw!r}")
    print_codex_command(format_skill_call(call))
    return repaired, call


def parse_skill_call(raw: str) -> SkillCall | None:
    for name, arg in CALL_RE.findall(raw):
        if name in {*REQUIRED_SKILLS, "send"}:
            return SkillCall(name=name, argument=parse_quoted_argument(arg))
    return None


def parse_quoted_argument(arg: str) -> str:
    try:
        return ast.literal_eval(f'"{arg}"')
    except (SyntaxError, ValueError):
        return arg


def format_skill_call(call: SkillCall) -> str:
    return f"({call.name} {json.dumps(call.argument)})"


def print_tool_header(name: str, command: str, cwd: Path) -> None:
    slow_print(f"tool({name})", delay=0.08)
    slow_print(f"$ cd {cwd}", delay=0.08)
    slow_print(f"$ {command}", delay=0.08)


def execute_skill(call: SkillCall) -> tuple[str, dict]:
    request = call.argument or USER_REQUEST
    with tempfile.NamedTemporaryFile("w", delete=False, prefix="goalchainer-request-", suffix=".txt") as handle:
        handle.write(request)
        request_file = Path(handle.name)

    command = [
        PYTHON_BIN,
        "-m",
        "goal_chainer.omegaclaw_skill",
        call.name,
        "--request-file",
        str(request_file),
        "--pretty",
    ]
    display = "PYTHONPATH=src GOALCHAINER_USE_PETTA=1 " + " ".join(command)
    print_tool_header(call.name, display, GOALCHAINER_DIR)
    try:
        result = subprocess.run(
            command,
            cwd=GOALCHAINER_DIR,
            env={
                **os.environ,
                "PYTHONPATH": "src",
                "GOALCHAINER_USE_PETTA": "1",
                "PETTACHAINER_PATH": str(PETTACHAINER_DIR),
                "PETTACHAINER_DIR": str(PETTACHAINER_DIR),
            },
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        request_file.unlink(missing_ok=True)

    payload = json.loads(result.stdout)
    rendered = render_skill_payload(call.name, payload)
    slow_print(rendered)
    print()
    return rendered, payload


def render_skill_payload(name: str, payload: dict) -> str:
    if name == "goalchainer-decision":
        return render_decision_payload(payload)
    if name == "goalchainer-proof-audit":
        return render_audit_payload(payload)
    if name == "goalchainer-ontology-context":
        return render_ontology_payload(payload)
    if name == "goalchainer-tests":
        return render_test_payload(payload)
    return json.dumps(payload, indent=2, sort_keys=True)


def render_decision_payload(payload: dict) -> str:
    lines = [
        "RESULTS: ((COMMAND_RETURN: (goalchainer-decision ...)))",
        f"scenario: {payload['scenario']['title']}",
        f"reasoner: {payload['runtime']['reasoner']}",
    ]
    ontology = payload.get("ontology", {})
    hyperbase = payload.get("hyperbase", {})
    if ontology:
        lines.append(
            f"ontology: COLORE modules={ontology.get('module_count')} axioms={ontology.get('axiom_count')}"
        )
    if hyperbase.get("propositions"):
        lines.append("structured propositions:")
        for proposition in hyperbase["propositions"][:3]:
            lines.append(f"  {proposition['id']}: {proposition['sentence']}")
    if payload["runtime"].get("reasoner_error"):
        lines.append(f"reasoner fallback: {payload['runtime']['reasoner_error']}")
    lines.append("goals:")
    for goal in payload["goals"]:
        required = "required" if goal["required"] else "optional"
        lines.append(f"  {required} {goal['kind']}: {goal['statement']} ({goal['owner']})")
    lines.append("norm check:")
    for norm in payload["norms"]:
        block = "blocks" if norm["blocks_action"] else "allows"
        lines.append(f"  {norm['action_id']}: {norm['status']} priority={norm['priority']} {block}")
    lines.append("ranked choices:")
    for item in payload["decisions"]:
        missing = ", ".join(item["missing_required_goals"]) or "none"
        lines.append(
            f"  {item['status']}: {item['label']} score={item['score']:.3f} "
            f"norm={item['norm_status']} evidence={item['evidence']['source']}"
        )
        lines.append(f"    missing={missing}")
    plan = payload["release_plan"]
    lines.extend(
        [
            "release plan:",
            f"  publish: {plan['publish_external']}",
            f"  restrict: {', '.join(plan['keep_restricted'])}",
            f"  review: {plan['human_review_gate']}",
        ]
    )
    return "\n".join(lines)


def render_ontology_payload(payload: dict) -> str:
    ontology = payload["ontology"]
    hyperbase = payload["hyperbase"]
    lines = [
        "RESULTS: ((COMMAND_RETURN: (goalchainer-ontology-context ...)))",
        f"COLORE source available: {ontology['source_available']}",
        f"COLORE fixture: modules={ontology['module_count']} axioms={ontology['axiom_count']} predicates={ontology['predicate_count']}",
        "ontology projection rules:",
    ]
    for rule in ontology["projection_rules"]:
        available = "available" if rule["available"] else "missing"
        lines.append(f"  {available}: {rule['id']} :: {' + '.join(rule['from'])} -> {rule['to']}")
    lines.append("HyperBase-ready propositions:")
    for proposition in hyperbase["propositions"][:5]:
        lines.append(f"  {proposition['id']}: {proposition['edge']}")
        lines.append(f"    {proposition['sentence']}")
    return "\n".join(lines)


def render_audit_payload(payload: dict) -> str:
    if not payload.get("available"):
        return "RESULTS: ((COMMAND_RETURN: (goalchainer-proof-audit unavailable)))"
    packet = payload["forensic_packet"]
    proof = payload["incident_proof"]
    routing = payload["routing"]
    verifier = payload.get("verifier", {})
    truth_items = proof.get("truth_values") or {}
    truth_preview = ", ".join(f"{key}={value}" for key, value in list(truth_items.items())[:2])
    lines = [
        "RESULTS: ((COMMAND_RETURN: (goalchainer-proof-audit ...)))",
        f"packet checks pass: {packet['verifier_checks_pass']}",
        f"red-team rejections pass: {packet['red_team_rejections_pass']}",
        f"packet root: {str(packet['packet_root_sha256'])[:20]}...",
        f"proof certificate pass: {proof['certificate_passes']}",
        f"truth values: {truth_preview}",
        f"best proof path: {routing['best_path']}",
    ]
    noise = payload.get("noise_stability") or {}
    if noise:
        lines.append(
            f"noise stability: extra_edges={noise.get('extra_edges')} stable={noise.get('stable')}"
        )
    for line in payload.get("audit_verdict", []):
        lines.append(f"audit: {line}")
    if verifier:
        lines.append(f"verifier exit: {verifier.get('exit')}")
        for line in verifier.get("stdout_tail", [])[-3:]:
            lines.append(f"verifier: {line}")
    return "\n".join(lines)


def render_test_payload(payload: dict) -> str:
    lines = [
        "RESULTS: ((COMMAND_RETURN: (goalchainer-tests ...)))",
        f"collect exit: {payload['collect_exit']}",
        f"test exit: {payload['test_exit']}",
        f"pytest: {payload['stdout']}",
        "collected tests:",
    ]
    for test_name in payload["collected_tests"][:8]:
        lines.append(f"  {test_name}")
    remaining = len(payload["collected_tests"]) - 8
    if remaining > 0:
        lines.append(f"  ... {remaining} more")
    return "\n".join(lines)


def skill_prompt(used: list[str], last_result: str) -> str:
    used_text = ", ".join(used) if used else "none"
    missing = [skill for skill in REQUIRED_SKILLS if skill not in used]
    if missing:
        last = last_result or "none yet"
    else:
        last = last_result or "All required tools have returned."
    return SKILL_CALL_PROMPT.format(
        catalogue=SKILL_CATALOGUE,
        request=USER_REQUEST,
        used_skills=used_text,
        last_result=last,
    )


def result_prompt(rendered: str) -> str:
    return RESULT_PROMPT.format(tool_result=rendered, style=CONCISE_STYLE)


def final_fallback_prompt(last_result: str) -> str:
    return SKILL_CALL_PROMPT.format(
        catalogue=SKILL_CATALOGUE,
        request=USER_REQUEST,
        used_skills=", ".join(REQUIRED_SKILLS),
        last_result=last_result,
    )


def main() -> int:
    model = MODEL or CODEX_DEFAULT_MODEL
    print(f"Codex-led OmegaClaw demo - model={model}")
    print(f"OmegaClaw Core with Codex auth: {CODEX_AUTH_DIR}")
    print(f"GoalChainer skill module: {GOALCHAINER_DIR / 'integrations/omegaclaw/goalchainer_skill.metta'}")
    print("The user speaks once. Codex emits OmegaClaw skill commands, and the tools return results.\n")
    time.sleep(SECTION_PAUSE)

    history: list[dict] = []
    used_skills: list[str] = []
    last_result = ""
    full_context: list[str] = []

    first_prompt = PLAN_PROMPT.format(request=USER_REQUEST, style=CONCISE_STYLE)
    first_answer = ask_codex(history, first_prompt, visible=USER_REQUEST, max_lines=3)
    history.extend([umsg(first_prompt), amsg(first_answer)])
    time.sleep(SECTION_PAUSE)

    for _ in range(6):
        command_prompt = skill_prompt(used_skills, last_result)
        raw_command, call = ask_for_skill_call(history, command_prompt)
        history.extend([umsg(command_prompt), amsg(raw_command)])

        if call.name == "send":
            print_codex_answer(call.argument, max_lines=6)
            break

        if call.name in used_skills:
            raise RuntimeError(f"Codex repeated a skill instead of choosing a new one: {call.name}")

        rendered, payload = execute_skill(call)
        used_skills.append(call.name)
        last_result = rendered
        full_context.append(json.dumps(payload, sort_keys=True))

        explanation_prompt = result_prompt(rendered)
        explanation = ask_codex(history, explanation_prompt, max_lines=3)
        history.extend([umsg(explanation_prompt), amsg(explanation)])
        time.sleep(SECTION_PAUSE)

        if all(skill in used_skills for skill in REQUIRED_SKILLS):
            command_prompt = final_fallback_prompt(last_result)
            raw_command, call = ask_for_skill_call(history, command_prompt)
            history.extend([umsg(command_prompt), amsg(raw_command)])
            if call.name != "send":
                final_prompt = textwrap.dedent(
                    f"""
                    The tools have all returned.

                    Internal context:
                    {' '.join(full_context)}

                    {CONCISE_STYLE}

                    Return one final answer in 6 lines.
                    """
                )
                final_answer = ask_codex(history, final_prompt, max_lines=6)
                history.extend([umsg(final_prompt), amsg(final_answer)])
            else:
                print_codex_answer(call.argument, max_lines=6)
            break

    slow_print(
        textwrap.dedent(
            """

            Terminal demo complete.
            Codex used OmegaClaw skill commands backed by the GoalChainer bridge.
            Tool results were returned internally as LAST_SKILL_USE_RESULTS.
            """
        ).strip(),
        delay=0.2,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
