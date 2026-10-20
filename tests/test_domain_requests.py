"""Purpose: exercise JSON domain requests through real review, planning and admission under one budget."""

from __future__ import annotations

import copy
import json
from importlib import resources
from pathlib import Path
from types import SimpleNamespace

import pytest

from goal_chainer import requests, semantic_reader
from goal_chainer.cli import main as cli_main
from goal_chainer.domains.loader import packaged_domain
from goal_chainer.domains import loader
from goal_chainer.domains.readings import NO_MATCH
from goal_chainer.errors import GoalChainerError, InvalidInputError
from goal_chainer.planning.procedures import NegatedLiteral, SignalLiteral, literal_term, read_literal
from goal_chainer.planning.projection import (Admitted, Answer, Blocked, Inquiry, NoPlan, Plan, Stale, Started,
                                              Unsolved, Verdict)
from goal_chainer.planning.transport import decode, encode
from goal_chainer.runtime.budget import RunBudget
from goal_chainer.semantic_evaluation import CORPUS_PATH
from jev_support import answering, client
from planning_support import RESTORES, sectionless_task_control_text, task_section_text
from request_support import CLI_LIMITS, budget
from test_planning_bindings import BOUND, SEAT, _library as bound_library

AT = "2026-10-18T06:00:00+00:00"
RELEASED = NegatedLiteral(SignalLiteral("resource_contention"))
PAUSE = {"resource_contention": "detected", "state_preservation_route": "detected",
         "safe_point_reachable": "refuted", "owner_mismatch": "refuted",
         "receiving_owner_accepts": "refuted", "review_open": "detected"}


# am[verifies a-integrate-domain-spine-acceptance-1018@23731c]
def context(states):
    return {
        "review_id": "request-acceptance", "subject": "caller-selected-task", "trigger": "test",
        "as_of": AT, "authority": "advisory",
        "readings": [
            {"signal": signal, "state": state, "source": f"test:{signal}",
             "estimator": "deterministic", "observed_at": AT}
            for signal, state in states.items()
        ],
    }


# Real functions still run; the observation checks that composition never substitutes a budget. The
# domain loaders are observed in the loader, where selected_domain calls them.
# am[verifies a-integrate-domain-spine-acceptance-1018@23731c]
def observe_budgets(monkeypatch):
    seen = []
    for module, name in ((loader, "load_domain"), (loader, "packaged_domain"), (requests, "load_procedures"),
                         (requests, "packaged_procedures"), (requests, "review"), (requests, "plan"),
                         (requests, "admit")):
        original = getattr(module, name)

        # am[verifies a-integrate-domain-spine-acceptance-1018@23731c]
        def observed(*args, _original=original, _name=name, **kwargs):
            seen.append((_name, kwargs["budget"]))
            return _original(*args, **kwargs)

        monkeypatch.setattr(module, name, observed)
    return seen


# Requests reading text through one domain share that domain's one process reader: each request's
# domain_reader answers the same reader, the one default_reader gives the incident declaration, each
# answer reports its reading under that reader's declaration, and the reader keeps no request's
# budget, which each read takes as an argument.
# am[verifies a-integrate-domain-reader-reuse-1018@bffd2b] am[verifies a-ie-sr-text-needs-domain-1018@8f7f0b]
def test_requests_reading_one_domain_share_its_process_reader(monkeypatch):
    readers = []
    shared = requests.domain_reader

    def recording(domain):
        readers.append(shared(domain))
        return readers[-1]

    monkeypatch.setattr(requests, "domain_reader", recording)
    texts = [text["text"] for text in json.loads(CORPUS_PATH.read_text(encoding="utf-8"))["texts"][:2]]
    answers = [
        requests.run_request(
            {"operation": "review", "domain": {"packaged": "incident"}, "context": context({"unverified": "refuted"}),
             "reading": {"text": text, "observed_at": AT, "valid_until": None}},
            budget=budget(),
        )
        for text in texts
    ]

    assert len(readers) == 2 and readers[0] is readers[1] is semantic_reader.default_reader(budget=budget())
    assert [answer["reading"]["declaration"] for answer in answers] == [readers[0].declaration.digest] * 2
    assert not any(isinstance(value, RunBudget) for value in vars(readers[0]).values())


# A supplied domain includes its own topology; this fixture uses the planner's declared test topology.
# am[verifies a-integrate-domain-spine-acceptance-1018@23731c]
@pytest.fixture
def planning_request(tmp_path):
    domain = packaged_domain("task-control", budget=budget())
    domain_path = tmp_path / "caller-domain.metta"
    domain_path.write_text(sectionless_task_control_text() + "\n" + task_section_text(domain.signal_ids),
                           encoding="utf-8")
    library_path = tmp_path / "caller-procedures.metta"
    library_path.write_text(
        (resources.files("goal_chainer.planning") / "library" / "task_control.metta").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    restores = literal_term(read_literal(f"(Statement {RESTORES})", "request fixture", budget=None))
    return {
        "operation": "plan", "domain": {"path": str(domain_path)}, "procedures": str(library_path),
        "context": context(PAUSE), "goal": encode((RELEASED,)),
        "rows": [f'(From {restores} (Observation (Drill "drill" "deterministic" Forever)))'],
    }


# am[verifies a-integrate-domain-spine-acceptance-1018@23731c]
@pytest.mark.parametrize("name,states,policy", [
    ("incident", {"sensitive-data": "detected", "unverified": "refuted"}, "incident-v1"),
    ("task-control", {"review_open": "detected", "stale_parent_goal": "detected",
                      "active_parent_path": "refuted"}, "task-control-v1"),
])
def test_packaged_domains_use_the_same_request_path_and_one_budget(monkeypatch, name, states, policy):
    seen = observe_budgets(monkeypatch)
    allowance = budget()
    allowance.charge(17)
    answer = requests.run_request(
        {"operation": "review", "domain": {"packaged": name}, "context": context(states)},
        budget=allowance,
    )

    assert answer["protocol"] == "goalchainer-request-v1"
    assert answer["review"]["domain"]["policy_version"] == policy
    assert answer["review"]["subject"] == "caller-selected-task"
    assert answer["authorization"] == "unresolved"
    assert answer["applies_effects"] is answer["review"]["applies_effects"] is False
    assert answer["inferences"] == allowance.spent - 17 > 0
    assert answer["review"]["engine"]["budget"]["inferences"] == allowance.inference_budget
    assert {name for name, _ in seen} == {"packaged_domain", "review"}
    assert all(item is allowance for _, item in seen)


# The shipped JSON is a caller's explicit handoff scenario, exercised through the documented CLI.
# Its returned step is transported unchanged for admission at the same evidence snapshot.
# am[verifies a-integrate-public-plan-example-1018@0d33ba]
def test_the_public_planning_example_can_be_submitted_and_its_first_step_admitted(tmp_path, capsys):
    source = Path(__file__).parents[1] / "examples" / "planning" / "task-control.request.json"
    assert cli_main(["request", "--input", str(source), *CLI_LIMITS]) == 0
    answer = json.loads(capsys.readouterr().out)
    planned = decode(answer["planning"], Answer)
    assert isinstance(planned, Plan) and not planned.assumptions
    assert any(step.kind == "act" and step.procedure == "release-by-handoff" for step in planned.steps)
    assert planned.steps[0].kind == "start"

    admission = json.loads(source.read_text(encoding="utf-8"))
    del admission["goal"]
    admission.update(operation="admit", step=answer["planning"]["steps"][0], instance_id=None)
    path = tmp_path / "admission.json"
    path.write_text(json.dumps(admission), encoding="utf-8")
    assert cli_main(["request", "--input", str(path), *CLI_LIMITS]) == 0
    checked = json.loads(capsys.readouterr().out)
    assert isinstance(decode(checked["admission"], Verdict), Admitted)
    for result in (answer, checked):
        assert result["authorization"] == "unresolved" and result["applies_effects"] is False


# am[verifies a-integrate-domain-spine-acceptance-1018@23731c]
@pytest.mark.parametrize("selection", ["file", "packaged"])
def test_selected_domain_and_library_plan_then_admit_against_current_readings(monkeypatch, planning_request, selection):
    if selection == "packaged":
        planning_request["domain"] = {"packaged": "task-control"}
        del planning_request["procedures"]
    seen = observe_budgets(monkeypatch)
    allowance = budget()
    answer = requests.run_request(json.loads(json.dumps(planning_request)), budget=allowance)
    planned = decode(answer["planning"], Answer)
    assert isinstance(planned, Plan) and not planned.assumptions
    assert answer["authorization"] == "unresolved" and answer["applies_effects"] is False
    loaders = {"load_domain", "load_procedures"} if selection == "file" else {"packaged_domain", "packaged_procedures"}
    assert {name for name, _ in seen} == loaders | {"review", "plan"}
    assert all(item is allowance for _, item in seen)

    run = next(step for step in planned.steps if step.procedure == "reach-safe-point" and step.kind == "act")
    admission = {key: copy.deepcopy(value) for key, value in planning_request.items() if key != "goal"}
    admission.update(operation="admit", step=encode(run), instance_id="instance-1",
                     journal=encode((Started("instance-1", "reach-safe-point", "journal-1"),)))
    current = requests.run_request(json.loads(json.dumps(admission)), budget=budget())
    assert isinstance(decode(current["admission"], Verdict), Admitted)
    assert current["authorization"] == "unresolved" and current["applies_effects"] is False

    admission["context"] = context({**PAUSE, "state_preservation_route": "refuted"})
    changed = requests.run_request(admission, budget=budget())
    assert decode(changed["admission"], Verdict) == Blocked((SignalLiteral("state_preservation_route"),))
    assert changed["authorization"] == "unresolved" and changed["applies_effects"] is False


# am[verifies a-integrate-domain-spine-acceptance-1018@23731c]
def test_changed_procedure_rules_make_a_json_plan_step_stale(planning_request):
    answer = requests.run_request(planning_request, budget=budget())
    planned = decode(answer["planning"], Answer)
    assert isinstance(planned, Plan)
    step = next(item for item in planned.steps if item.procedure == "reach-safe-point" and item.kind == "act")
    from pathlib import Path

    path = Path(planning_request["procedures"])
    text = path.read_text(encoding="utf-8")
    before = "(When (Signal state_preservation_route))\n  (Steps (Step run act continue_task (After))))"
    after = before.replace("route))", "route) (Signal review_open))")
    assert text.count(before) == 1
    path.write_text(text.replace(before, after), encoding="utf-8")

    admission = {key: value for key, value in planning_request.items() if key != "goal"}
    admission.update(operation="admit", step=encode(step), instance_id="instance-1",
                     journal=encode((Started("instance-1", "reach-safe-point", "journal-1"),)))
    changed = requests.run_request(admission, budget=budget())
    stale = decode(changed["admission"], Verdict)
    assert isinstance(stale, Stale) and stale.expected == step.witness.digest != stale.found
    assert changed["authorization"] == "unresolved"


# am[verifies a-integrate-domain-spine-acceptance-1018@23731c]
@pytest.mark.parametrize("outcome", ["inquiry", "no-plan"])
def test_inquiry_and_exhausted_search_keep_their_distinct_answers(planning_request, outcome):
    if outcome == "inquiry":
        states = {**PAUSE, "state_preservation_route": "refuted"}
        del states["owner_mismatch"]
    else:
        states = {**PAUSE, "owner_mismatch": "detected"}
        planning_request["goal"] = encode((NegatedLiteral(SignalLiteral("owner_mismatch")),))
    planning_request["context"] = context(states)
    answer = requests.run_request(planning_request, budget=budget())
    result = decode(answer["planning"], Answer)
    assert isinstance(result, Inquiry if outcome == "inquiry" else NoPlan)
    if isinstance(result, Inquiry):
        assert result.investigator == "owner-registry"
        assert isinstance(result.if_true, Plan) and isinstance(result.if_false, NoPlan)
    assert answer["authorization"] == "unresolved" and answer["applies_effects"] is False


# am[verifies a-integrate-domain-spine-acceptance-1018@23731c]
@pytest.mark.parametrize("row", [
    '(From (Signal "resource_contention") (Observation (Drill "fake" "measured" Forever)))',
    '(From (Statement (sn c "fake")) (Observation (Reading "never-read" "measured" Forever)))',
])
def test_json_rows_cannot_replace_readings_or_forge_their_provenance(planning_request, row):
    planning_request["rows"].append(row)
    with pytest.raises(InvalidInputError, match="ExtraRow"):
        requests.run_request(planning_request, budget=budget())


# am[verifies a-integrate-domain-spine-acceptance-1018@23731c]
@pytest.mark.parametrize("change", [
    {"domain": {}}, {"domain": {"packaged": "incident", "path": "elsewhere"}},
    {"operation": "solve"}, {"unknown": True},
])
def test_malformed_requests_are_refused(change):
    payload = {"operation": "review", "domain": {"packaged": "incident"}, "context": context({})}
    payload.update(change)
    with pytest.raises(InvalidInputError):
        requests.run_request(payload, budget=budget())


# am[verifies a-integrate-domain-spine-acceptance-1018@23731c]
def test_a_file_domain_needs_an_explicit_procedure_library(planning_request):
    del planning_request["procedures"]
    with pytest.raises(InvalidInputError, match="must name its procedures file"):
        requests.run_request(planning_request, budget=budget())


# am[verifies a-integrate-domain-spine-acceptance-1018@23731c]
def test_a_budget_failure_never_becomes_a_no_plan_answer(planning_request):
    allowance = RunBudget(inference_budget=1, timeout_seconds=600)
    with pytest.raises(GoalChainerError) as stopped:
        requests.run_request(planning_request, budget=allowance)
    assert stopped.value.code == "inference_budget_exceeded"


# Unreadable caller files are input failures at the public request boundary.
# am[verifies a-integrate-domain-spine-acceptance-1018@23731c]
@pytest.mark.parametrize("field", ["domain", "procedures"])
def test_a_file_that_is_not_utf8_is_a_typed_input_failure(planning_request, field):
    from pathlib import Path

    name = planning_request["domain"]["path"] if field == "domain" else planning_request["procedures"]
    Path(name).write_bytes(b"\xff")
    with pytest.raises(InvalidInputError):
        requests.run_request(planning_request, budget=budget())


# Path expansion and resolution are part of reading caller input, before the file is opened.
# am[verifies a-integrate-domain-spine-acceptance-1018@23731c]
@pytest.mark.parametrize("field", ["domain", "procedures"])
@pytest.mark.parametrize("path", ["bad\x00domain.metta", "~user-that-does-not-exist/domain.metta"],
                         ids=["embedded-nul", "unknown-home"])
def test_a_path_that_cannot_be_normalized_is_a_typed_input_failure(planning_request, field, path):
    if field == "domain":
        planning_request["domain"] = {"path": path}
    else:
        planning_request["procedures"] = path
    with pytest.raises(InvalidInputError, match="domain.metta"):
        requests.run_request(planning_request, budget=budget())


# A witness is caller data, including when its strings cannot be parsed as MeTTa terms.
# am[verifies a-integrate-domain-spine-acceptance-1018@23731c]
@pytest.mark.parametrize("field", ["rule", "node", "image"])
def test_an_unparseable_json_witness_is_a_typed_input_failure(planning_request, field):
    planned = decode(requests.run_request(planning_request, budget=budget())["planning"], Answer)
    assert isinstance(planned, Plan)
    step = encode(planned.steps[0])
    if field == "rule":
        step["witness"]["rule"] = "("
    else:
        assert step["witness"]["images"]
        step["witness"]["images"][0][0 if field == "node" else 1] = "("
    admission = {key: value for key, value in planning_request.items() if key != "goal"}
    admission.update(operation="admit", step=step, instance_id=None)
    with pytest.raises(InvalidInputError):
        requests.run_request(admission, budget=budget())


# One public request through a reading binding, the reader's Jev answers replayed by a stand-in client and
# its ranker stood in for: owner_mismatch read supported, with its binding choosing the seat, places the
# reading on the seat, and the planner takes that entity reading beside the context's readings. Being
# model-proposed, it leaves the seat's literal an assumption that only the alternative plan names. No match,
# or a proposition the text leaves unclear, places nothing, so the goal stays blocked with no alternative.
# Admission takes the same readings: the alternative's start, admitted against the same reading, is
# blocked on the seat's literal, which a model's reading never checks.
# The review reads the context's readings and the proposition's own reading alone, never the entity
# reading, and the response carries the binding's answer.
# am[verifies a-bnd-requests-1019@ec32de] am[verifies a-bnd-scripted-request-1019@5277eb]
@pytest.mark.parametrize(("answer", "chosen", "assumed"), [
    ("yes", "seat", True),
    ("yes", NO_MATCH, False),
    ("unclear", "seat", False),
], ids=("seat", "no-match", "unclear"))
def test_a_request_reading_through_a_binding_plans_on_the_chosen_entity_alone(monkeypatch, tmp_path, answer, chosen,
                                                                              assumed):
    domain_path, library_path = tmp_path / "bound.metta", tmp_path / "bound-procedures.metta"
    domain_path.write_text(BOUND, encoding="utf-8")
    library_path.write_text(bound_library("(On (Signal owner_mismatch) seat)"), encoding="utf-8")

    def answer_for(question, state):
        del state
        if question == "owner_mismatch":
            return {option: (0.9 if option == answer else 0.05) for option in ("yes", "no", "unclear")}
        return {option: (0.8 if option == chosen else 0.1) for option in ("seat", "receiving_seat", NO_MATCH)}

    def replayed(domain):
        jev = semantic_reader.JevClient(semantic_reader.AnswerCache(tmp_path / "answers"), domain.readings.model,
                                        client_factory=client(answering(answer_for)))
        return semantic_reader.SemanticReader(
            declaration=domain.readings, jev=jev, serve=lambda: semantic_reader.ServedRanker("base", tmp_path),
            load=lambda ranker: SimpleNamespace(scores=lambda pairs: tuple(0.5 for _ in pairs)))

    monkeypatch.setattr(requests, "domain_reader", replayed)
    goal = SignalLiteral("receiving_owner_accepts")
    request = {
        "operation": "plan", "domain": {"path": str(domain_path)}, "procedures": str(library_path),
        "context": context({"receiving_owner_accepts": "refuted"}), "goal": encode((goal,)),
        "reading": {"text": "The seat holds a task it does not own.", "observed_at": AT, "valid_until": None},
    }
    answered = requests.run_request(copy.deepcopy(request), budget=budget())

    planned = decode(answered["planning"], Answer)
    assert isinstance(planned, NoPlan) and planned.unsolved == (Unsolved(goal, "blocked", ()),)
    if assumed:
        assert planned.alternative is not None and planned.alternative.assumptions == (SEAT,)
        admission = {key: value for key, value in request.items() if key != "goal"}
        admission.update(operation="admit", step=encode(planned.alternative.steps[0]), instance_id=None)
        admitted = requests.run_request(admission, budget=budget())
        assert decode(admitted["admission"], Verdict) == Blocked((SEAT,))
    else:
        assert planned.alternative is None
    assert [(b["signal"], b["control"], b["answer"]) for b in answered["reading"]["bindings"]] == [
        ("owner_mismatch", "Seat", chosen)]
    reviewed = {reading["signal"]: reading for reading in answered["review"]["readings"]}
    (proposition,) = answered["reading"]["propositions"]
    held = [item for kind in ("support", "contested", "decayed", "unknown") for item in reviewed["owner_mismatch"][kind]]
    assert [item["source"] for item in held] == [f"jev:{answered['reading']['model']}:{proposition['answer_key']}"]

