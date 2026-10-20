"""Purpose: run every planning example through the public request command, offline, and check that its
answer is what its inputs derive. The shipped request plans a way its library declares, and each step
it returns is admitted unchanged while the evidence holds and blocked once it does not. Each variation's
changed observation, library or goal changes the answer as the library says it must. A consistent
renaming of every name the domain and library declare renames the answers and changes nothing else, so
no step is chosen by spelling. The supplied bench-booking domain answers as Cortez's independent
planning oracle expects. No result authorizes or applies anything."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest
from planning_oracle import Oracle, State, holds_everywhere, lit, matches, start_state
from request_support import CLI_LIMITS, LIMITS, budget

from goal_chainer import requests
from goal_chainer.cli import main as cli_main
from goal_chainer.domains.forms import parsed_forms
from goal_chainer.domains.loader import selected_domain
from goal_chainer.planning.procedures import (
    NegatedLiteral,
    ProcedureLibrary,
    ProcedureLiteral,
    SignalLiteral,
    literal_text,
    load_procedures,
    packaged_procedures,
    read_literal,
)
from goal_chainer.planning.projection import (
    Admitted,
    Answer,
    Blocked,
    Inquiry,
    NoPlan,
    Plan,
    PlanStep,
    Started,
    Verdict,
)
from goal_chainer.planning.transport import decode, encode
from goal_chainer.relevance.packet import PACKET_PROTOCOL, parse_packet
from goal_chainer.relevance.signals import SignalReading
from goal_chainer.request_text import account

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "planning"
BASE = "task-control.request.json"
REQUESTS = sorted(path.name for path in EXAMPLES.glob("*.request.json"))
TASK_CONTROL = [name for name in REQUESTS if name.startswith("task-control")]
BENCH = [name for name in REQUESTS if name.startswith("bench-booking")]
# A request's goal as the request command decodes it.
GOAL = tuple[ProcedureLiteral, ...]


# A request as the guide runs it from the repository root, its file paths made absolute for this process.
# am[verifies a-dd-examples-1018@dfa4b9]
def load(name: str) -> dict:
    request = json.loads((EXAMPLES / name).read_text(encoding="utf-8"))
    if "path" in request["domain"]:
        request["domain"] = {"path": str(ROOT / request["domain"]["path"])}
    if "procedures" in request:
        request["procedures"] = str(ROOT / request["procedures"])
    return request


_RESULTS: dict[str, dict] = {}


# Each example's result, computed once: the request path is a function of the request.
# am[verifies a-dd-examples-1018@dfa4b9]
def result(name: str) -> dict:
    if name not in _RESULTS:
        _RESULTS[name] = requests.run_request(load(name), budget=budget())
    return _RESULTS[name]


# am[verifies a-dd-examples-1018@dfa4b9]
def answer(name: str) -> Answer:
    return decode(result(name)["planning"], Answer)


# The library a request plans with: its procedures file, or its packaged domain's.
# am[verifies a-dd-examples-1018@dfa4b9]
def library(request: dict) -> ProcedureLibrary:
    domain = selected_domain(**requests.domain_selection(request["domain"]), budget=budget())
    if "procedures" in request:
        return load_procedures(request["procedures"], domain, budget=budget())
    return packaged_procedures(domain, budget=budget())


# am[verifies a-dd-examples-1018@dfa4b9]
def readings(request: dict) -> dict[str, tuple[str, str]]:
    return {item["signal"]: (item["state"], item["estimator"]) for item in request["context"]["readings"]}


# The readings plan takes from a request with no model reading: its context's, parsed as the request command
# parses its packet under the limits CLI_LIMITS gives it (requests.run_request). A model reading would add
# readings this parse does not see, so a request holding one is refused here.
# am[verifies a-dd-tests-1018@39b144] am[implements a-jk-pc-outside-binding-1019@59f29c]
def plan_readings(request: dict) -> tuple[SignalReading, ...]:
    assert "reading" not in request, "a model reading gives plan readings its context does not hold"
    budget_fields = {"inferences": LIMITS["inference_budget"], "timeout_seconds": LIMITS["timeout_seconds"]}
    return parse_packet({**request["context"], "protocol": PACKET_PROTOCOL, "budget": budget_fields}).readings


# Every signal whose reading a variation changes from the shipped request's: its new reading, or None
# where the variation has none.
# am[verifies a-dd-examples-1018@dfa4b9]
def changed(name: str) -> dict[str, tuple[str, str] | None]:
    base, varied = readings(load(BASE)), readings(load(name))
    return {signal: varied.get(signal) for signal in base.keys() | varied.keys() if base.get(signal) != varied.get(signal)}


# am[verifies a-dd-examples-1018@dfa4b9]
def steps(plan: Plan) -> Counter:
    return Counter((step.kind, step.procedure, step.step) for step in plan.steps)


# Every step an answer names: a plan's, each inquiry branch's, and a no-plan answer's alternative's.
# am[verifies a-dd-step-free-check-1018@e1dc03]
def named_steps(value: Answer) -> list[PlanStep]:
    if isinstance(value, Plan):
        return list(value.steps)
    if isinstance(value, Inquiry):
        return named_steps(value.if_true) + named_steps(value.if_false)
    return [] if value.alternative is None else list(value.alternative.steps)


# Every object, list and scalar a JSON value holds, itself included.
# am[verifies a-dd-step-free-check-1018@e1dc03]
def parts(value) -> list:
    children = value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
    return [value, *(part for child in children for part in parts(child))]


# A request declares what it wants and what it knows, never a step: no step of its answer appears anywhere
# in it, so every plan below is the planner's. Which fields a plan request may carry is the request
# surface's to say. Run through the command the guide runs, from the repository root.
# am[verifies a-dd-examples-1018@dfa4b9] am[verifies c-user-derived-plans-over-scripted-demo-1017@735286]
# am[verifies a-dd-step-free-check-1018@e1dc03]
@pytest.mark.parametrize("name", REQUESTS)
def test_every_example_plans_through_the_request_command_and_authorizes_and_applies_nothing(
        name, capsys, monkeypatch) -> None:
    request = json.loads((EXAMPLES / name).read_text(encoding="utf-8"))
    monkeypatch.chdir(ROOT)
    assert cli_main(["request", "--input", f"examples/planning/{name}", *CLI_LIMITS]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert request["operation"] == printed["operation"] == "plan"
    assert printed["authorization"] == "unresolved" and printed["applies_effects"] is False
    assert printed["review"]["applies_effects"] is False
    given = parts(request)
    assert not [step for step in named_steps(decode(printed["planning"], Answer)) if encode(step) in given]
    text, status = account(printed)
    assert status == 0 and text.endswith("authorization unresolved, applies effects no, "
                                         f"{printed['inferences']} inferences")


# The shipped request's plan applies a procedure its library declares for the goal, its first step is
# admitted as it was returned, its act is admitted on the instance the host's journal started, and the
# act is blocked, naming the literal, once the evidence refutes a literal its procedure's When reads.
# am[verifies a-dd-examples-1018@dfa4b9] am[verifies a-dd-doc-1018@da16cf]
def test_the_shipped_plan_is_a_declared_way_and_its_returned_steps_are_admitted_while_the_evidence_holds() -> None:
    request = load(BASE)
    planned = answer(BASE)
    ways = library(request)
    goal = decode(request["goal"], GOAL)
    assert isinstance(planned, Plan) and not planned.assumptions and planned.steps[0].kind == "start"
    first = planned.steps[0].procedure
    assert any(first == way.name for literal in goal for way in ways.achieving(literal))

    def admitted(step, instance_id, journal=(), states=None) -> Verdict:
        admission = {key: value for key, value in request.items() if key != "goal"}
        if states:
            admission["context"] = {**request["context"], "readings": [
                {**item, "state": states.get(item["signal"], item["state"])} for item in request["context"]["readings"]]}
        admission.update(operation="admit", step=encode(step), instance_id=instance_id, journal=encode(tuple(journal)))
        return decode(requests.run_request(json.loads(json.dumps(admission)), budget=budget())["admission"], Verdict)

    assert isinstance(admitted(planned.steps[0], None), Admitted)
    act = next(step for step in planned.steps if step.kind == "act")
    started = (Started("handoff-1", act.procedure, "host-journal:1"),)
    assert isinstance(admitted(act, "handoff-1", started), Admitted)
    when = next(way for way in ways.procedures if way.name == act.procedure).when
    refutable = [literal for literal in when if isinstance(literal, SignalLiteral)]
    assert refutable
    for literal in refutable:
        assert admitted(act, "handoff-1", started, {literal.name: "refuted"}) == Blocked((literal,))


# Refuting the observation the shipped plan relied on adds the applications that bring that literal
# about, each a procedure the library declares for it, and keeps every step the shipped plan took.
# am[verifies a-dd-examples-1018@dfa4b9]
def test_a_refused_handoff_adds_a_way_to_the_literal_whose_observation_changed() -> None:
    (signal, now), = changed("task-control-declined.request.json").items()
    assert now[0] == "refuted"
    base, declined = answer(BASE), answer("task-control-declined.request.json")
    assert isinstance(base, Plan) and isinstance(declined, Plan)
    extra = steps(declined) - steps(base)
    assert extra and steps(base) <= steps(declined)
    ways = {way.name for way in library(load(BASE)).achieving(SignalLiteral(signal))}
    assert {procedure for _, procedure, _ in extra} <= ways


# With an observation removed, the planner asks an investigator that can observe it, and the branch
# where it holds as the shipped request observed it is the shipped request's own plan.
# am[verifies a-dd-examples-1018@dfa4b9]
def test_an_unread_literal_is_inquired_and_its_observed_branch_is_the_shipped_plan() -> None:
    (signal, now), = changed("task-control-owner-unknown.request.json").items()
    assert now is None
    asked = answer("task-control-owner-unknown.request.json")
    assert isinstance(asked, Inquiry) and asked.literal == SignalLiteral(signal)
    ways = library(load(BASE))
    assert asked.investigator in {investigator.name for investigator in ways.investigators_of(asked.literal)}
    observed = readings(load(BASE))[signal][0] == "detected"
    assert (asked.if_true if observed else asked.if_false) == answer(BASE)
    unobserved = asked.if_false if observed else asked.if_true
    assert isinstance(unobserved, NoPlan)


# On the pause route the planner asks for the one literal a way to the goal still needs, through an
# investigator that observes it, and the branch where it holds applies that way.
# am[verifies a-dd-examples-1018@dfa4b9]
def test_the_checkpoint_route_inquires_into_what_its_way_to_the_goal_reads() -> None:
    request = load("task-control-checkpoint.request.json")
    asked = answer("task-control-checkpoint.request.json")
    ways = library(request)
    goal = decode(request["goal"], GOAL)
    assert isinstance(asked, Inquiry) and isinstance(asked.if_true, Plan) and isinstance(asked.if_false, NoPlan)
    reading = [way for literal in goal for way in ways.achieving(literal) if asked.literal in way.when]
    assert reading and asked.investigator in {item.name for item in ways.investigators_of(asked.literal)}
    assert {way.name for way in reading} & {step.procedure for step in asked.if_true.steps}


# A host whose library lacks every procedure the shipped plan applied has no plan for the same goal and
# evidence, each goal literal named.
# am[verifies a-dd-examples-1018@dfa4b9]
def test_a_library_without_the_shipped_plans_procedures_has_no_plan() -> None:
    request = load("task-control-pause-only.request.json")
    assert changed("task-control-pause-only.request.json") == {}
    reduced = {way.name for way in library(request).procedures}
    shipped = answer(BASE)
    assert isinstance(shipped, Plan)
    assert reduced < {way.name for way in library(load(BASE)).procedures}
    assert not reduced & {step.procedure for step in shipped.steps}
    none = answer("task-control-pause-only.request.json")
    assert isinstance(none, NoPlan) and {item.literal for item in none.unsolved} == set(decode(request["goal"], GOAL))


# A different goal over the same domain and library is planned through a procedure declared for it.
# am[verifies a-dd-examples-1018@dfa4b9]
def test_a_different_goal_is_planned_through_a_way_declared_for_it() -> None:
    request = load("task-control-safe-point.request.json")
    goal = decode(request["goal"], GOAL)
    assert goal != decode(load(BASE)["goal"], GOAL)
    planned = answer("task-control-safe-point.request.json")
    assert isinstance(planned, Plan) and planned.steps[0].kind == "start"
    first = next(step.procedure for step in planned.steps if step.application == 0)
    assert any(first == way.name for literal in goal for way in library(request).achieving(literal))


# The restore drill's result, a statement row in the procedure library's spelling, answers exactly what the
# checkpoint request's inquiry gave for the branch where that statement holds.
# am[verifies a-dd-drill-row-variation-1018@0861dc]
def test_the_drills_row_answers_the_checkpoint_inquirys_branch_where_the_statement_holds() -> None:
    drilled = load("task-control-checkpoint-drilled.request.json")
    asked = answer("task-control-checkpoint.request.json")
    assert {key: value for key, value in drilled.items() if key != "rows"} == load("task-control-checkpoint.request.json")
    assert isinstance(asked, Inquiry) and drilled["rows"]
    assert answer("task-control-checkpoint-drilled.request.json") == asked.if_true


# On evidence that opens two ways to the goal, the receipts of earlier applied attempts give the procedure
# the journal applied a track record under the library's promotion rule, and the planner switches to that
# procedure, established; the same request without its journal and receipts plans as before.
# am[verifies a-dd-receipt-variation-1018@655fcb]
def test_verified_receipts_switch_the_plan_to_the_way_they_established() -> None:
    proven_request = load("task-control-both-routes-proven.request.json")
    open_routes, proven = answer("task-control-both-routes.request.json"), answer("task-control-both-routes-proven.request.json")
    assert isinstance(open_routes, Plan) and isinstance(proven, Plan)
    assert not open_routes.established and proven.established
    applied = {event["procedure"] for event in proven_request["journal"] if event["@type"] == "Started"}
    assert applied == {step.procedure for step in proven.steps}
    assert applied.isdisjoint(step.procedure for step in open_routes.steps)
    unproven = {key: value for key, value in proven_request.items() if key not in ("journal", "receipts")}
    without = decode(requests.run_request(json.loads(json.dumps(unproven)), budget=budget())["planning"], Answer)
    assert normal(without, {}) == normal(open_routes, {})
    promoted = [atom for _, atom in parsed_forms(Path(proven_request["procedures"]).read_text(encoding="utf-8"), budget=None)]
    packaged_path = ROOT / "src" / "goal_chainer" / "planning" / "library" / "task_control.metta"
    packaged = [atom for _, atom in parsed_forms(packaged_path.read_text(encoding="utf-8"), budget=None)]
    assert [str(atom) for atom in promoted[:-1]] == [str(atom) for atom in packaged]
    assert str(promoted[-1]).startswith("(gc-track-promotion ")


# --- the same answers under other names ------------------------------------------------------------

_DECLARING = {"gc-action", "gc-signal", "gc-goal", "gc-dimension", "gc-brs-control", "gc-brs-entity",
              "gc-procedure", "gc-investigator"}


# The names a domain or library text declares: what each declaring form names, each port, each link's
# edge and each procedure step's id.
# am[verifies a-dd-examples-1018@dfa4b9]
def declared(atoms) -> set[str]:
    from metta import Expression

    names: set[str] = set()

    def walk(atom) -> None:
        if not isinstance(atom, Expression) or not atom.children:
            return
        head = str(atom.children[0])
        if head in _DECLARING and len(atom.children) > 1:
            names.add(str(atom.children[1]))
        if head in ("Ports", "Edge"):
            names.update(str(child) for child in atom.children[1:])
        if head == "Step" and len(atom.children) > 1:
            names.add(str(atom.children[1]))
        for child in atom.children:
            walk(child)

    for atom in atoms:
        walk(atom)
    return names


# The text with every symbol `names` maps renamed, read and written by pymetta, strings untouched.
# am[verifies a-dd-examples-1018@dfa4b9]
def renamed_text(text: str, names: dict[str, str]) -> str:
    from metta import Expression, Symbol

    def rename(atom):
        if isinstance(atom, Expression):
            return Expression(tuple(rename(child) for child in atom.children))
        if isinstance(atom, Symbol) and str(atom) in names:
            return Symbol(names[str(atom)])
        return atom

    return "\n".join(str(rename(atom)) for _, atom in parsed_forms(text, budget=None))


# An answer with every name read back through `back`, the witnesses' rule text and digests left out,
# since they spell the names they compile.
# am[verifies a-dd-examples-1018@dfa4b9]
def normal(value, back: dict[str, str]):
    def literal(item):
        if isinstance(item, NegatedLiteral):
            return NegatedLiteral(literal(item.literal))
        return SignalLiteral(back.get(item.name, item.name)) if isinstance(item, SignalLiteral) else item

    if isinstance(value, Plan):
        return ("plan", value.established, tuple(map(literal, value.assumptions)), tuple(
            (step.kind, back.get(step.procedure, step.procedure), back.get(step.step, step.step), step.application,
             step.instance_id, tuple(back.get(entity, entity) for _, entity in step.binding)) for step in value.steps))
    if isinstance(value, Inquiry):
        return ("inquiry", literal(value.literal), back.get(value.investigator, value.investigator),
                normal(value.if_true, back), normal(value.if_false, back))
    return ("none", tuple((literal(item.literal), item.reason, tuple(map(literal, item.unknowable)))
                          for item in value.unsolved), None if value.alternative is None else normal(value.alternative, back))


# Renaming every signal, action, goal, dimension, control, port, edge, entity, procedure, step and
# investigator the task-control domain and its libraries declare, consistently in the domain, the
# libraries and each request, gives every example the same review disposition and the same answer under
# the new names.
# am[verifies a-dd-examples-1018@dfa4b9] am[verifies c-user-derived-plans-over-scripted-demo-1017@735286]
# am[verifies a-dd-drill-row-variation-1018@0861dc] am[verifies a-dd-receipt-variation-1018@655fcb]
def test_renaming_every_declared_name_renames_the_answers_and_changes_nothing_else(tmp_path) -> None:
    from importlib import resources

    domain_text = (resources.files("goal_chainer.domains") / "data" / "task_control.metta").read_text(encoding="utf-8")
    texts = {"packaged": (resources.files("goal_chainer.planning") / "library" / "task_control.metta").read_text(
        encoding="utf-8")}
    for name in TASK_CONTROL:
        if "procedures" in load(name):
            texts[name] = Path(load(name)["procedures"]).read_text(encoding="utf-8")
    atoms = [atom for text in (domain_text, *texts.values()) for _, atom in parsed_forms(text, budget=None)]
    names = {name: f"n{index:03d}" for index, name in enumerate(sorted(declared(atoms)))}
    back = {new: old for old, new in names.items()}
    domain_path = tmp_path / "renamed.metta"
    domain_path.write_text(renamed_text(domain_text, names), encoding="utf-8")
    libraries = {}
    for key, text in texts.items():
        libraries[key] = tmp_path / f"renamed-{len(libraries)}.metta"
        libraries[key].write_text(renamed_text(text, names), encoding="utf-8")

    def literal(item: dict) -> dict:
        if item["@type"] == "SignalLiteral":
            return {**item, "name": names[item["name"]]}
        return {**item, "literal": literal(item["literal"])} if item["@type"] == "NegatedLiteral" else item

    # A receipt's target is a literal as a procedures file writes it, read and written by that grammar.
    def target(text: str) -> str:
        def rename(value):
            if isinstance(value, NegatedLiteral):
                return NegatedLiteral(rename(value.literal))
            return SignalLiteral(names[value.name]) if isinstance(value, SignalLiteral) else value

        return literal_text(rename(read_literal(text, "receipt target", budget=None)))

    for name in TASK_CONTROL:
        request = load(name)
        request["domain"] = {"path": str(domain_path)}
        request["procedures"] = str(libraries[name if "procedures" in request else "packaged"])
        request["goal"] = [literal(item) for item in request["goal"]]
        request["context"] = {**request["context"], "readings": [
            {**item, "signal": names[item["signal"]]} for item in request["context"]["readings"]]}
        request["journal"] = [{key: names[value] if key in ("procedure", "step") else value for key, value in event.items()}
                              for event in request.get("journal", [])]
        request["receipts"] = {receipt: {**document, "action": names[document["action"]], "observations": [
            {**item, "target": target(item["target"])} for item in document["observations"]]}
            for receipt, document in request.get("receipts", {}).items()}
        renamed = requests.run_request(request, budget=budget())
        assert normal(decode(renamed["planning"], Answer), back) == normal(answer(name), {}), name
        review, original = renamed["review"], result(name)["review"]
        assert review["disposition"] == original["disposition"], name
        proposed = None if review["proposal"] is None else back[review["proposal"]["action"]]
        assert proposed == (None if original["proposal"] is None else original["proposal"]["action"]), name


# --- the independent oracle on a supplied domain -----------------------------------------------------


# The bench-booking domain is in the oracle's sublanguage, one entity and signals only, so its answers
# are checked against Cortez's planning_oracle: the model's expected answer, every plan holding in every
# world the observations leave open, and the model's state embedding each world's along the way. The model
# reads the readings plan is given, and its domain declares no binding, so no entity reading reaches plan
# (c-jk-ob-request-entity-needs-binding-1019).
# am[verifies a-dd-tests-1018@39b144] am[rests-on c-dd-oracle-one-entity-signals-1018@0c3271]
# am[rests-on c-jk-ob-request-entity-needs-binding-1019@29f628]
@pytest.mark.parametrize("name", BENCH)
def test_the_supplied_bench_domain_answers_as_the_independent_oracle_expects(name) -> None:
    request = load(name)
    domain = selected_domain(**requests.domain_selection(request["domain"]), budget=budget())
    oracle = Oracle.of(library(request), domain, [lit(item) for item in decode(request["goal"], GOAL)])
    observed, assumable = start_state(plan_readings(request))
    matches(oracle, answer(name), State(observed), assumable)
    holds_everywhere(oracle, answer(name), State(observed))
