"""Purpose: verify readable request results, including motivation, planning and admission, and
typed refusals for malformed fields and numbers outside their producers' contracts."""

from __future__ import annotations

import io
import json
import math
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from request_support import budget

from goal_chainer import requests
from goal_chainer.cli import main as cli_main
from goal_chainer.errors import InvalidInputError
from goal_chainer.planning.procedures import (
    NegatedLiteral,
    SignalLiteral,
    StatementLiteral,
)
from goal_chainer.planning.projection import (
    Admitted,
    Ambiguous,
    Blocked,
    Inquiry,
    NoPlan,
    Plan,
    PlanStep,
    Progress,
    Stale,
    Unsolved,
    Witness,
)
from goal_chainer.planning.transport import encode
from goal_chainer.relevance_cli import format_review
from goal_chainer.request_text import account

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "planning" / "task-control.request.json"
CHECKPOINT = EXAMPLE.with_name("task-control-checkpoint.request.json")
WITNESS = Witness('(Step 0 "p" Start)', "sha256:" + "0" * 64, (("(Ent task)", "task"),))
RELEASED = NegatedLiteral(SignalLiteral("resource_contention"))
# A text reading as the semantic reader's Reading.to_dict writes one.
READING = {"model": "jev-1.13.0", "revision": "r", "domain": "incident", "declaration": "sha256:cc",
           "propositions": [{"id": "sensitive-data", "answer": "true", "direction": "supported",
                             "probability": 0.934}],
           "choices": [{"id": "audience", "answer": "internal", "probability": 0.5}]}


# One real result, so the review part is a record the review computed and format_review words.
# am[verifies a-dd-show-1018@f9e4e9]
@pytest.fixture(scope="module")
def result() -> dict:
    return requests.run_request(json.loads(EXAMPLE.read_text(encoding="utf-8")), budget=budget())


# A second real result, whose review proposes an action with authority limits and a carrying path and
# whose answer is an inquiry, so every part the account reads is present in one result or the other.
# am[verifies a-sb-substitution-test-1018@777319]
@pytest.fixture(scope="module")
def proposed() -> dict:
    return requests.run_request(json.loads(CHECKPOINT.read_text(encoding="utf-8")), budget=budget())


# am[verifies a-dd-show-1018@f9e4e9]
def step(kind, procedure, step_id=None, *, application=0, instance=None, binding=(("(Ent task)", "task"),)):
    return PlanStep(procedure, step_id, kind, application, instance, binding, WITNESS)


# The account's lines after the review's, for the result with `changes` applied.
# am[verifies a-dd-show-1018@f9e4e9]
def after_review(result: dict, **changes) -> list[str]:
    changed = {**result, **changes}
    text, status = account(changed)
    assert status == 0
    review = format_review(changed["review"]).splitlines()
    lines = text.splitlines()
    assert lines[:len(review)] == review
    return lines[len(review):]


# am[verifies a-dd-show-1018@f9e4e9]
def test_the_account_is_the_review_then_the_answer_then_the_request_line(result) -> None:
    lines = after_review(result)
    planned = result["planning"]["steps"]
    assert lines[0].startswith(f"plan: {len(planned)} steps, ")
    assert [line.split(". ", 1)[0].strip() for line in lines[1:1 + len(planned)]] == [
        str(number) for number in range(1, len(planned) + 1)]
    assert lines[-1] == f"request: authorization unresolved, applies effects no, {result['inferences']} inferences"
    assert len(lines) == len(planned) + 2


# am[verifies a-dd-show-1018@f9e4e9]
def test_a_plan_lists_each_step_with_its_application_instance_and_bound_entities(result) -> None:
    hand = (("(Acted A)", "seat"), ("(Acted B)", "receiving_seat"), ("(Acted T)", "task"), ("(Ent task)", "task"))
    answer = Plan((step("start", "release-by-handoff"),
                   step("act", "release-by-handoff", "hand", instance="handoff-1", binding=hand),
                   step("finish", "release-by-handoff", application=1, binding=())), True)
    assert after_review(result, planning=encode(answer))[:4] == [
        "plan: 3 steps, established",
        "  1. start release-by-handoff, application 0, on task",
        "  2. act release-by-handoff hand, application 0, instance handoff-1, on seat, receiving_seat, task",
        "  3. finish release-by-handoff, application 1",
    ]


# am[verifies a-dd-show-1018@f9e4e9]
def test_an_inquiry_names_its_literal_and_investigator_then_each_branch(result) -> None:
    answer = Inquiry(SignalLiteral("owner_mismatch"), "owner-registry", Plan((step("start", "p"),), False),
                     NoPlan((Unsolved(RELEASED, "blocked"),), None))
    assert after_review(result, planning=encode(answer))[:6] == [
        "inquiry: owner-registry can observe (Signal owner_mismatch)",
        "  if it holds:",
        "    plan: 1 step, not yet established",
        "      1. start p, application 0, on task",
        "  if it does not:",
        "    no plan",
    ]


# am[verifies a-dd-show-1018@f9e4e9]
def test_no_plan_names_each_reason_what_it_waits_on_and_its_alternative(result) -> None:
    statement = StatementLiteral('(sn c "store")')
    answer = NoPlan((Unsolved(RELEASED, "unknowable", (SignalLiteral("owner_mismatch"), statement)),
                     Unsolved(SignalLiteral("review_open"), "no-way")),
                    Plan((step("start", "p"),), False, (SignalLiteral("owner_mismatch"),)))
    assert after_review(result, planning=encode(answer))[:6] == [
        "no plan",
        '  (Not (Signal resource_contention)): unknowable, waiting on (Signal owner_mismatch), (Statement (sn c "store"))',
        "  (Signal review_open): no-way",
        "  alternative, never a plan to act on:",
        "    plan: 1 step, not yet established, assuming (Signal owner_mismatch)",
        "      1. start p, application 0, on task",
    ]


# am[verifies a-dd-show-1018@f9e4e9]
@pytest.mark.parametrize("verdict, line", [
    (Admitted('(Occurrence (Step 2 "p" Start))'), 'admission: admitted, occurrence (Occurrence (Step 2 "p" Start))'),
    (Blocked((SignalLiteral("owner_mismatch"), Progress("i1", "run", True), Progress("i1", "go", False))),
     "admission: blocked, waiting on (Signal owner_mismatch), instance i1 step run done, instance i1 step go not done"),
    (Ambiguous(2), ("admission: ambiguous, the matching occurrences fall in 2 successor classes, and the executor "
                    "must not choose")),
    (Stale("sha256:aa", "sha256:bb"), ("admission: stale, the step's rules changed since the plan (sha256:aa planned, "
                                       "sha256:bb now)")),
], ids=["admitted", "blocked", "ambiguous", "stale"])
def test_each_admission_verdict_reads_as_it_was_returned(result, verdict, line) -> None:
    admitted = {key: value for key, value in result.items() if key != "planning"}
    assert after_review(admitted, operation="admit", admission=encode(verdict)) == [
        line, f"request: authorization unresolved, applies effects no, {result['inferences']} inferences"]


# A reading's answers follow the review, each with its direction and probability.
# am[verifies a-dd-show-1018@f9e4e9]
def test_a_text_reading_is_listed_after_the_review(result) -> None:
    assert after_review(result, reading=READING)[:3] == [
        "reading by jev-1.13.0 under incident (sha256:cc)",
        "  sensitive-data: true (supported, probability 0.93)",
        "  audience: internal (probability 0.50)",
    ]


# am[verifies a-dd-show-1018@f9e4e9]
def test_a_typed_error_result_is_shown_with_status_one() -> None:
    error = {"ok": False, "error": {"code": "invalid_input", "message": "domain must select exactly one path or packaged name.",
                                    "details": {}}}
    assert account(error) == ("GoalChainer error [invalid_input]: domain must select exactly one path or packaged name.", 1)


# am[verifies a-dd-show-1018@f9e4e9]
@pytest.mark.parametrize("change", [
    {"protocol": "goalchainer-request-v0"}, {"operation": "solve"}, {"review": None}, {"review": {}},
    {"planning": {"@type": "Plan"}}, {"planning": {"@type": "Unknown"}},
], ids=["protocol", "operation", "review-none", "review-empty", "plan-fields", "plan-type"])
def test_an_input_that_is_no_request_result_is_refused(result, change) -> None:
    with pytest.raises(InvalidInputError):
        account({**result, **change})


# am[verifies a-dd-show-1018@f9e4e9]
@pytest.mark.parametrize("key", ["review", "planning", "authorization", "applies_effects", "inferences"])
def test_a_result_missing_a_part_is_refused_naming_it(result, key) -> None:
    with pytest.raises(InvalidInputError, match=key):
        account({name: value for name, value in result.items() if name != key})


# The shapes the source review of 4fc506f found: an operation that is a list or an object reached the
# operation table's hashed lookup, and a probability that is text reached its :.2f format. A boolean
# probability is refused too, though Python would format it as 1.00.
# am[verifies a-integrate-show-input-boundary-1018@e8b290] am[verifies a-sb-shape-boundary-1018@917de5]
@pytest.mark.parametrize("operation", [[], {}, ["plan"], {"plan": "planning"}, None, 1])
def test_an_operation_that_is_no_operation_name_is_refused(result, operation, tmp_path, capsys) -> None:
    with pytest.raises(InvalidInputError):
        account({**result, "operation": operation})
    saved = tmp_path / "result.json"
    saved.write_text(json.dumps({**result, "operation": operation}), encoding="utf-8")
    assert cli_main(["show", "--input", str(saved)]) == 1
    assert "invalid_input" in capsys.readouterr().err


# am[verifies a-integrate-show-input-boundary-1018@e8b290] am[verifies a-sb-shape-boundary-1018@917de5]
@pytest.mark.parametrize("probability", ["0.93", True, None, [0.93]])
@pytest.mark.parametrize("part", ["propositions", "choices"])
def test_a_reading_probability_that_is_no_number_is_refused(result, part, probability) -> None:
    reading = {**READING, part: [{**READING[part][0], "probability": probability}]}
    with pytest.raises(InvalidInputError):
        account({**result, "reading": reading})


# JSON nested deeper than the parser reaches is unreadable input, as malformed JSON is.
# am[verifies a-sb-reader-recursion-1018@e6fda1]
def test_input_nested_deeper_than_the_parser_reaches_is_refused(tmp_path, capsys) -> None:
    saved = tmp_path / "deep.json"
    saved.write_text("[" * 100_000 + "]" * 100_000, encoding="utf-8")
    assert cli_main(["show", "--input", str(saved)]) == 1
    assert "invalid_input" in capsys.readouterr().err


# A saved integer of more digits than the interpreter reads as text is unreadable JSON too: json.loads
# raises ValueError for it, which is no JSONDecodeError.
# am[verifies a-sn-contract-numbers-1018@c1d969]
def test_a_saved_integer_too_long_to_read_is_refused(result, tmp_path, capsys) -> None:
    saved = tmp_path / "long.json"
    saved.write_text(json.dumps({**result, "inferences": "DIGITS"}).replace('"DIGITS"', "1" * 5000), encoding="utf-8")
    assert cli_main(["show", "--input", str(saved)]) == 1
    assert "invalid_input" in capsys.readouterr().err


# The command reads a saved result from a file or from standard input and prints exactly the account;
# standard input is a byte stream, as a process's is.
# am[verifies a-dd-show-1018@f9e4e9]
def test_goalchainer_show_prints_the_account_of_a_saved_or_piped_result(result, tmp_path, capsys, monkeypatch) -> None:
    saved = tmp_path / "plan.json"
    saved.write_text(json.dumps(result), encoding="utf-8")
    text, _ = account(result)
    assert cli_main(["show", "--input", str(saved)]) == 0
    assert capsys.readouterr().out == text + "\n"
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(result).encode("utf-8")), encoding="utf-8"))
    assert cli_main(["show"]) == 0
    assert capsys.readouterr().out == text + "\n"
    saved.write_text(json.dumps({"ok": False, "error": {"code": "invalid_input", "message": "m", "details": {}}}),
                     encoding="utf-8")
    assert cli_main(["show", "--input", str(saved)]) == 1
    assert capsys.readouterr().out == "GoalChainer error [invalid_input]: m\n"
    saved.write_text("[]", encoding="utf-8")
    assert cli_main(["show", "--input", str(saved)]) == 1
    assert "invalid_input" in capsys.readouterr().err


NAMES = st.from_regex(r"[a-z][a-z0-9_-]{0,8}", fullmatch=True)
STEPS = st.builds(
    step, st.sampled_from(["start", "act", "investigate", "finish", "derive"]), NAMES,
    st.one_of(st.none(), NAMES), application=st.integers(0, 4), instance=st.one_of(st.none(), NAMES),
    binding=st.lists(st.tuples(NAMES.map(lambda name: f"(Ent {name})"), NAMES), max_size=3).map(tuple),
)


# Whatever plan the result holds, its account lists every step once, in plan order, naming its kind,
# procedure and step id, and nothing else.
# am[verifies a-dd-show-1018@f9e4e9]
@settings(max_examples=60, deadline=None, derandomize=True)
@given(st.lists(STEPS, max_size=6))
def test_every_step_of_any_plan_is_listed_once_in_order(steps) -> None:
    review = {"review_id": "r", "subject": "s", "domain": {"policy_version": "v"}, "fingerprint": "f",
              "proposal": None, "disposition": "no proposal", "escalation": None, "blockers": [], "steps": [],
              "missing_information": {"unknown_signals": [], "unestimated_dimensions": []},
              "engine": {"inferences": 1, "budget": {"inferences": 2}}}
    result = {"protocol": "goalchainer-request-v1", "operation": "plan", "review": review,
              "planning": encode(Plan(tuple(steps), False)), "authorization": "unresolved",
              "applies_effects": False, "inferences": 1}
    lines = after_review(result)
    listed = lines[1:-1]
    assert len(listed) == len(steps)
    for number, (line, planned) in enumerate(zip(listed, steps), 1):
        head = f"  {number}. {planned.kind} {planned.procedure}" + (f" {planned.step}" if planned.step else "")
        assert line == head or line.startswith(head + ", application "), (line, planned)


# --- malformed results ------------------------------------------------------------------------------

# One member of each JSON value class a saved result's part could hold instead of its own value.
CLASSES = [None, True, 7, 0.5, "text", [], ["text"], [{}], {}, {"key": "text"}]
# Stands for removing a part, in put.
GONE = object()


# The JSON class of a value, integers and fractions as one class.
# am[verifies a-sb-substitution-test-1018@777319]
def kind(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return type(value).__name__


# Every path into a JSON value, outermost first, the value's own empty path included.
# Time: linear in the value's size.
# am[verifies a-sb-substitution-test-1018@777319]
def paths(value, path=()):
    yield path
    children = value.items() if isinstance(value, dict) else enumerate(value) if isinstance(value, list) else ()
    for key, item in children:
        yield from paths(item, (*path, key))


# am[verifies a-sb-substitution-test-1018@777319]
def at(value, path):
    for key in path:
        value = value[key]
    return value


# `value` with its part at `path` replaced by `new`, or removed when `new` is GONE, copying only the
# containers along the path.
# Time: the sizes of the containers along the path.
# am[verifies a-sb-substitution-test-1018@777319]
def put(value, path, new):
    head, *rest = path
    if rest:
        new = put(value[head], rest, new)
    if isinstance(value, dict):
        return {key: item for key, item in value.items() if key != head} if new is GONE else {**value, head: new}
    changed = list(value)
    if new is GONE:
        del changed[head]
    else:
        changed[head] = new
    return changed


# The account of `value`, or None when it is refused as no request result.
# am[verifies a-sb-substitution-test-1018@777319]
def shown(value):
    try:
        return account(value)
    except InvalidInputError:
        return None


# Real results of every kind the account renders: a plan under an escalating review, an inquiry under a
# review that proposes an action, the plan with a text reading, a blocked and an ambiguous admission and
# a typed error.
# am[verifies a-sb-substitution-test-1018@777319]
# am[verifies a-v2-cli-skill-surface-1020@6f755c]
@pytest.fixture(scope="module")
def samples(result, proposed) -> dict[str, dict]:
    admitted = {key: value for key, value in result.items() if key != "planning"}
    blocked = Blocked((SignalLiteral("owner_mismatch"), Progress("i1", "run", True)))
    motivation = {"stream": "companion", "as_of": "2026-10-20T00:00:00+00:00", "levels": [
        {"need": "rest", "state": "observed", "level": 0.9, "urgency": 0.75},
        {"need": "contact", "state": "unobserved", "level": None, "urgency": None},
    ]}
    carrying = {"goal": "wellbeing", "priority": 1.0, "priority_source": "host",
                "need": "rest", "value": {"low": 0.75, "high": 0.75}}
    motivated = {**proposed, "review": {**proposed["review"], "motivation": motivation, "proposal": {
        **proposed["review"]["proposal"], "carrying_path": carrying, "predicted_need_changes": [
            {"need": "rest", "expected_change": -0.4, "observed_level": 0.9, "level_state": "observed",
             "predicted_level": {"low": 0.5, "high": 0.5}, "reduction": {"low": 0.75, "high": 0.75},
             "status": "predicted"},
            {"need": "contact", "expected_change": None, "observed_level": None, "level_state": "unobserved",
             "predicted_level": {"low": 0.0, "high": 1.0}, "reduction": {"low": -1.0, "high": 1.0},
             "status": "predicted"},
        ],
    }}}
    held = {**result, "operation": "review", "review": {**result["review"], "proposal": None,
            "disposition": "hold", "escalation": None,
            "hold": {"satisfied": ["rest"], "unserved": ["contact"]}}}
    return {
        "plan": result,
        "inquiry": proposed,
        "reading": {**result, "reading": READING},
        "admission": {**admitted, "operation": "admit", "admission": encode(blocked)},
        "ambiguous": {**admitted, "operation": "admit", "admission": encode(Ambiguous(2))},
        "motivated": motivated,
        "held": held,
        "error": {"ok": False, "error": {"code": "invalid_input", "message": "m", "details": {}}},
    }


SAMPLES = ["plan", "inquiry", "reading", "admission", "ambiguous", "motivated", "held", "error"]


# am[verifies a-v2-cli-skill-surface-1020@6f755c]
# am[verifies a-v2-hold-label-1020@4c7833]
def test_motivation_account_keeps_predictions_unknowns_and_hold_causes_distinct(samples) -> None:
    text, status = account(samples["motivated"])
    assert status == 0
    assert "need rest, value [0.75, 0.75]" in text
    assert "predicted need rest: change -0.4, urgency reduction [0.75, 0.75]" in text
    assert "predicted need contact: change unknown, urgency reduction [-1.0, 1.0]" in text
    assert "contact: unobserved, level unknown, urgency unknown" in text
    assert "authorization unresolved" in text and "applies effects: no" in text
    text, status = account(samples["held"])
    assert status == 0
    assert "disposition: hold" in text
    assert "needs in their target bands: rest" in text
    assert "needs outside their target bands: contact" in text


# The account accepts the producer's two path variants and ordered intervals only, and a prediction
# whose observed level is a number exactly when its state is observed.
# am[verifies a-v2-cli-skill-surface-1020@6f755c] am[verifies a-v2r-predicted-level-1020]
@pytest.mark.parametrize("path, value", [
    (("review", "proposal", "carrying_path", "value"), {"low": 1, "high": 0}),
    (("review", "proposal", "carrying_path", "band"), "strong"),
    (("review", "proposal", "predicted_need_changes", 0, "status"), "observed"),
    (("review", "proposal", "predicted_need_changes", 0, "reduction"), {"low": -2, "high": 0}),
    (("review", "proposal", "predicted_need_changes", 0, "predicted_level"), {"low": 0.6, "high": 0.5}),
    (("review", "proposal", "predicted_need_changes", 0, "level_state"), "guessed"),
    (("review", "proposal", "predicted_need_changes", 0, "observed_level"), None),
    (("review", "proposal", "predicted_need_changes", 1, "observed_level"), 0.3),
])
def test_motivation_account_refuses_inconsistent_prediction_fields(samples, path, value) -> None:
    with pytest.raises(InvalidInputError):
        account(put(samples["motivated"], path, value))


# am[verifies a-v2-cli-skill-surface-1020@6f755c]
def test_hold_without_its_causes_is_refused(samples) -> None:
    with pytest.raises(InvalidInputError, match="hold"):
        account(put(samples["held"], ("review", "hold"), GONE))


# Every part of every sample, replaced by each JSON value class or removed, and the whole input replaced:
# the account renders or refuses as InvalidInputError and never fails otherwise. A value of a class other
# than the part's own is refused, or the account is the sample's own because nothing reads that part. Null
# on either side is held only to the first rule, since a part may be nullable, and so is removal, since a
# part may be optional.
# Time: (paths + 1) x (classes + 1) accounts, each linear in the result's size.
# am[verifies a-sb-substitution-test-1018@777319] am[verifies a-integrate-show-input-boundary-1018@e8b290]
# am[verifies a-sb-shape-boundary-1018@917de5]
@pytest.mark.parametrize("name", SAMPLES)
def test_any_json_class_in_place_of_any_part_of_a_result_is_shown_or_refused(samples, name) -> None:
    sample = samples[name]
    expected = account(sample)
    wrong = []
    cases = [((), new) for new in CLASSES] + [
        (path, new) for path in list(paths(sample))[1:] for new in [*CLASSES, GONE]]
    for path, new in cases:
        try:
            got = shown(put(sample, path, new) if path else new)
        except Exception as error:  # noqa: BLE001 (the property: nothing but InvalidInputError escapes)
            wrong.append((path, new, f"{type(error).__name__}: {error}"))
            continue
        if not path:
            if got is not None:
                wrong.append((path, new, got))
            continue
        old = at(sample, path)
        if new is not GONE and None not in (old, new) and kind(new) != kind(old) and got not in (None, expected):
            wrong.append((path, new, got))
    assert not wrong, f"{len(wrong)} of {len(cases)} cases: {wrong[:12]}"


# --- numbers ----------------------------------------------------------------------------------------

# Numeric extremes, each named, since a number past the interpreter's integer text limit cannot be
# written in a test's id or message: small values on either side of every producer's bound, magnitudes
# past the float range and past that limit, the infinities and NaN.
EXTREMES = {"0": 0, "1": 1, "-1": -1, "2": 2, "1.5": 1.5, "10**1000": 10**1000, "-10**1000": -(10**1000),
            "10**5000": 10**5000, "inf": math.inf, "-inf": -math.inf, "nan": math.nan}


# Every number in every sample, replaced by each numeric extreme: the account renders or refuses as
# InvalidInputError and never fails otherwise, since a number's JSON class alone does not make writing
# it total.
# Time: number parts x extremes accounts, each linear in the result's size.
# am[verifies a-sn-numeric-extremes-test-1018@dcb07e] am[verifies a-sn-contract-numbers-1018@c1d969]
@pytest.mark.parametrize("name", SAMPLES)
def test_any_numeric_extreme_in_place_of_any_number_of_a_result_is_shown_or_refused(samples, name) -> None:
    sample = samples[name]
    numbers = [path for path in list(paths(sample))[1:] if kind(at(sample, path)) == "number"]
    wrong = []
    for path in numbers:
        for label, new in EXTREMES.items():
            try:
                shown(put(sample, path, new))
            except Exception as error:  # noqa: BLE001 (the property: nothing but InvalidInputError escapes)
                wrong.append((path, label, f"{type(error).__name__}: {error}"))
    assert not wrong, f"{len(wrong)} of {len(numbers) * len(EXTREMES)} cases: {wrong[:12]}"


# Each number the account words and the values its producer never writes there: a probability outside 0
# to 1 or not finite (ten to the thousandth among them, the source review's probe, which :.2f cannot write
# as a float), a negative count, a budget of no inferences, a negative or non-finite goal priority, an
# application below 0, fewer than two successor classes, and any number not whole where a whole one is
# written or too long to write as text.
NUMBERS = {
    "proposition probability": ("reading", ("reading", "propositions", 0, "probability"),
                                ["-0.01", "1.01", "10**1000", "-10**1000", "inf", "-inf", "nan"]),
    "choice probability": ("reading", ("reading", "choices", 0, "probability"),
                           ["-0.01", "1.01", "10**1000", "-10**1000", "inf", "-inf", "nan"]),
    "goal priority": ("inquiry", ("review", "proposal", "carrying_path", "priority"),
                      ["-0.5", "inf", "-inf", "nan", "10**5000"]),
    "result inferences": ("plan", ("inferences",), ["-1", "1.5", "10**5000"]),
    "engine inferences": ("plan", ("review", "engine", "inferences"), ["-1", "1.5", "10**5000"]),
    "engine budget": ("plan", ("review", "engine", "budget", "inferences"), ["0", "-1", "1.5", "10**5000"]),
    "step application": ("plan", ("planning", "steps", 0, "application"), ["-1", "1.5", "10**5000"]),
    "successor classes": ("ambiguous", ("admission", "classes"), ["1", "0", "2.5", "10**5000"]),
}
OUTSIDE = {**EXTREMES, "-0.01": -0.01, "1.01": 1.01, "-0.5": -0.5, "2.5": 2.5}


# am[verifies a-integrate-show-number-refusal-fix-1018@8ce706] am[verifies a-sn-contract-numbers-1018@c1d969]
@pytest.mark.parametrize("name, path, label", [
    pytest.param(name, path, label, id=f"{number}={label}")
    for number, (name, path, labels) in NUMBERS.items() for label in labels])
def test_a_number_outside_its_producers_contract_is_refused(samples, name, path, label) -> None:
    with pytest.raises(InvalidInputError):
        account(put(samples[name], path, OUTSIDE[label]))


# The same numbers at their producers' bounds are shown, as the producers write them.
# am[verifies a-integrate-show-number-refusal-fix-1018@8ce706] am[verifies a-sn-contract-numbers-1018@c1d969]
@pytest.mark.parametrize("name, path, value, words", [
    ("reading", ("reading", "propositions", 0, "probability"), 0, "(supported, probability 0.00)"),
    ("reading", ("reading", "propositions", 0, "probability"), 1.0, "(supported, probability 1.00)"),
    ("reading", ("reading", "choices", 0, "probability"), 1, "(probability 1.00)"),
    ("inquiry", ("review", "proposal", "carrying_path", "priority"), 0.0, "(priority 0.0 from "),
    ("plan", ("inferences",), 0, "applies effects no, 0 inferences"),
    ("plan", ("review", "engine", "inferences"), 0, "  engine inferences: 0 of "),
    ("plan", ("review", "engine", "budget", "inferences"), 1, " of 1\n"),
    ("plan", ("planning", "steps", 0, "application"), 0, ", application 0, "),
    ("ambiguous", ("admission", "classes"), 2, "fall in 2 successor classes"),
], ids=["probability-0", "probability-1.0", "choice-1", "priority-0.0", "inferences-0", "engine-0", "budget-1",
        "application-0", "classes-2"])
def test_a_number_at_its_producers_bound_is_shown(samples, name, path, value, words) -> None:
    text, status = account(put(samples[name], path, value))
    assert status == 0 and words in text
