"""Purpose: verify SNARS's obligation routes and its interval condition: every structural route kept
with its leaves' conditions and its hypothesis-labelled scenario, a premise discharged only by
evidence that meets the condition, a route established only when its scenario holds as well as its
leaves, the cut exclusive for every threshold and every computed opinion, the attention witness
classified in the batch that found it, nothing written by a search or by one a budget stopped, the
caller's budget threaded unchanged."""

import random
from functools import cache

import pytest
from request_support import budget as request_budget
from snars_differential import tree

from goal_chainer.runtime.budget import InferenceBudgetExceeded, RunBudget
from goal_chainer.snars_engine import run_snars_batch
from goal_chainer.snars_models import Evidence, SubjectiveOpinion
from goal_chainer.errors import InvalidInputError
from goal_chainer.sexpr.codec import SexprCodec
from goal_chainer.snars_program import SnarsBatch
from goal_chainer.snars_protocol import parse_obligations
from goal_chainer.snars_reasoner import SnarsSession, track
from reading_support import incident_reader


# A binary statement as authors write it, and the canonical tree SNARS reports for it.
# am[verifies a-rt-ob-tests-1017@27e310]
def _statement(subject: str, obj: str) -> str:
    return f'(sn p so "is" ((arg s (sn c "{subject}")) (arg o (sn c "{obj}"))))'


# am[verifies a-rt-ob-tests-1017@27e310]
def _canonical(subject: str, obj: str) -> str:
    return (f'(sh (tag P d so ()) "is" (args ((arg s (sh-atom (tag C c NoRoles ()) "{subject}")) '
            f'(arg o (sh-atom (tag C c NoRoles ()) "{obj}")))))')


# The goal has two routes through conditional edges: one from an antecedent the case decides, one
# from a statement believed with no evidence, which is supported and says nothing. The chain case
# reaches the goal from the antecedent through a middle statement instead.
GOAL, ANTECEDENT, VACUOUS = _statement("gamma", "delta"), _statement("alpha", "beta"), _statement("chi", "psi")
MIDDLE = _statement("mu", "nu")


# A conditional edge believed at (8, 0) from one statement's binding to another's.
# am[verifies a-rt-ob-tests-1017@27e310]
def _edge(premise: str, conclusion: str) -> str:
    return (f'(believe! (sh (tag P d so ()) "==>" (args ((arg s (sn-ref {premise})) (arg o (sn-ref {conclusion}))))) '
            '((evidence 8.0 0.0) (source "conditional") (trust 1.0) (domain conditional)))')


# How each case gives the antecedent: interned only, or believed from an observation with
# evidence that meets the 0.6 condition, falls short of it, or contradicts it.
ANTECEDENTS = {
    "interned": f'(sn intern-ref! {ANTECEDENT} "obligations-test")',
    "sufficient": f'(believe! {ANTECEDENT} ((evidence 8.0 0.0) (source "observation") (trust 1.0)))',
    "insufficient": f'(believe! {ANTECEDENT} ((evidence 1.0 0.0) (source "observation") (trust 1.0)))',
    "contrary": f'(believe! {ANTECEDENT} ((evidence 0.0 8.0) (source "observation") (trust 1.0)))',
}
LEAF = {"interned": "Open", "sufficient": "Holds", "insufficient": "Undecided", "contrary": "Fails"}


# The goal's routes record over the bindings given, which bind statements $a and $c and edges $e1
# and $e2, and whether the store's fingerprint was the same on each side of the search.
# am[verifies a-rt-ob-core-1017@26b526] am[verifies a-rt-ob-tests-1017@27e310]
def _case_program(bindings: str) -> str:
    return (f'(let* (($g (sn intern-ref! {GOAL} "obligations-test")) {bindings} ($before (gc state-fingerprint)) '
            f'($record (gc obligations-record {GOAL} 8.0 0.0 0.5 12 0.6)) ($after (gc state-fingerprint))) '
            '(obligations-case $g $a $c $e1 $e2 (== $before $after) $record))')


# am[verifies a-rt-ob-core-1017@26b526] am[verifies a-rt-ob-tests-1017@27e310]
def _routes_program(antecedent: str) -> str:
    return _case_program(f'($a {ANTECEDENTS[antecedent]}) '
                         f'($c (believe! {VACUOUS} ((evidence 0.0 0.0) (source "vacuous") (trust 1.0)))) '
                         f'($e1 {_edge("$a", "$g")}) ($e2 {_edge("$c", "$g")})')


# The goal two conditional steps from the antecedent believed at (8, 0): the edges run from it to
# the middle statement, which is only interned, and from there to the goal.
# am[verifies a-rt-ob-established-1017@31d188]
def _chain_program() -> str:
    return _case_program(f'($a {ANTECEDENTS["sufficient"]}) ($c (sn intern-ref! {MIDDLE} "obligations-test")) '
                         f'($e1 {_edge("$a", "$c")}) ($e2 {_edge("$c", "$g")})')


# Hand-picked opinions and thresholds, each with the status the cut must give: the symmetric cuts'
# overlap below one half, the floating opinions the simplex tolerance accepts, one with b > 1 - d
# and one where 1 - d falls under a threshold b + u clears, a vacuous opinion whose base rate alone
# clears the threshold, and both interval ends.
EDGES = [
    ((0.45, 0.45, 0.10, 0.5), 0.4, "Holds"),
    ((0.45, 0.45, 0.10, 0.5), 0.5, "Undecided"),
    ((0.45, 0.45, 0.10, 0.5), 0.6, "Fails"),
    ((0.5000000000001, 0.5, 0.0, 0.5), 0.50000000000005, "Holds"),
    ((0.4, 0.5000000000001, 0.1, 0.5), 0.49999999999995, "Undecided"),
    ((0.0, 0.0, 1.0, 0.9), 0.6, "Undecided"),
    ((0.6, 0.0, 0.4, 0.5), 0.6, "Undecided"),
    ((0.2, 0.4, 0.4, 0.5), 0.6, "Undecided"),
    ((0.1, 0.7, 0.2, 0.5), 0.3, "Undecided"),
    ((0.1, 0.7, 0.2, 0.5), 0.35, "Fails"),
    ((1.0, 0.0, 0.0, 0.5), 1.0, "Undecided"),
    ((0.0, 1.0, 0.0, 0.5), 0.0, "Undecided"),
]


# Seeded opinions and thresholds spread over the simplex, its edges and the interval ends. Each
# value is a multiple of 2^-20, so its 20-place decimal is exact on both engines and b + u adds
# without rounding; 0.1 + 0.2 at 0.3 above is the case where rounding decides.
# am[verifies a-rt-ob-condition-1017@dc8180]
def _generated(count: int) -> list[tuple[tuple[float, float, float, float], float]]:
    rng = random.Random(1017)
    unit = 2 ** 20
    cases = []
    for _ in range(count):
        b = rng.choice([0, unit, rng.randrange(unit + 1)])
        u = rng.randrange(unit - b + 1)
        a = rng.randrange(unit + 1)
        theta = rng.choice([0, unit, unit // 2, b, b + u, rng.randrange(unit + 1)])
        cases.append(((b / unit, (unit - b - u) / unit, u / unit, a / unit), theta / unit))
    return cases


GENERATED = _generated(120)


# Each number as a decimal both engines read exactly: no exponent, enough places for 2^-20 steps
# and for the hand-picked cases' 13 places.
# am[verifies a-rt-ob-condition-1017@dc8180]
def _number(value: float) -> str:
    text = repr(value)
    return text if "e" not in text else f"{value:.20f}"


# am[verifies a-rt-ob-condition-1017@dc8180]
def _condition_program(cases) -> str:
    calls = " ".join(f"(sn condition (Opinion {_number(b)} {_number(d)} {_number(u)} {_number(a)}) {_number(theta)})"
                     for (b, d, u, a), theta in cases)
    return f"(condition-cases {calls})"


# The same cases read as (Not S): the cut of each opinion's complement.
# am[verifies a-rt-ob-negation-track-1017@a1a80d]
def _complement_program(cases) -> str:
    calls = " ".join(f"(sn condition (sn complement (Opinion {_number(b)} {_number(d)} {_number(u)} {_number(a)})) "
                     f"{_number(theta)})" for (b, d, u, a), theta in cases)
    return f"(condition-cases {calls})"


PROGRAMS = {
    **{f"routes: {name}": _routes_program(name) for name in ANTECEDENTS},
    "routes: chain": _chain_program(),
    "cut: edges": _condition_program([case[:2] for case in EDGES]),
    "cut: generated": _condition_program(GENERATED),
    "cut: complement": _complement_program(GENERATED),
    # Outcome evidence fused without a receipt: the statement stays unsupported, so its view,
    # however strong, decides nothing.
    "support: outcome only": (f'(let* (($x (sn intern-ref! {ANTECEDENT} "obligations-test")) '
                              '($fused (sn outcome! $x 8.0 0.0 0.5 "observation" 1.0))) '
                              '(condition-cases (sn supported? $x) (sn condition-of $x pos 0.6) (sn condition (sn view $x) 0.6)))'),
}


# The batch's one result line, from the in-process engine once per test process.
# am[verifies a-rt-ob-tests-1017@27e310]
def _result(lines) -> str:
    found = [line for line in lines if line.startswith(("(obligations-case", "(condition-cases"))]
    assert len(found) == 1, lines
    return found[0]


# am[verifies a-rt-ob-tests-1017@27e310]
@cache
def _in_process(name: str) -> str:
    batch = SnarsBatch((), frozenset(), PROGRAMS[name])
    return _result(run_snars_batch(batch, budget=RunBudget(inference_budget=None, timeout_seconds=900)).output_lines)


# A routes case's ids ($g $a $c $e1 $e2), whether the store was unchanged across the search, and its
# parsed routes.
# am[verifies a-rt-ob-tests-1017@27e310]
def _routes(name: str):
    codec = SexprCodec()
    case = codec.parse(_in_process(name))
    ids = tuple(codec.emit(item) for item in case[1:6])
    record = case[7]
    assert codec.emit(record[0]) == "goalchainer-snars-v1" and codec.emit(record[1]) == "obligations"
    return ids, codec.emit(case[6]), parse_obligations(record[3], codec)


# Each route as (its leaves' statuses by statement id or open statement, its scenario).
# am[verifies a-rt-ob-tests-1017@27e310]
def _shapes(found, names) -> set:
    label = {sid: name for name, sid in names.items()}
    shapes = set()
    for route in found.routes:
        leaves = frozenset((label.get(leaf.statement_id, leaf.statement), leaf.status) for leaf in route.leaves)
        scenario = tuple(round(value, 9) for value in (route.scenario.belief, route.scenario.disbelief,
                                                       route.scenario.uncertainty))
        shapes.add((leaves, scenario))
    return shapes


# Every structural route is kept: the goal observed directly, each edge with its premise open, and
# each edge with its held premise, its condition read from that premise's own evidence. The
# scenario is the goal's opinion with every open premise at the stated hypothesis, (8, 0) here.
# am[verifies a-rt-ob-core-1017@26b526] am[verifies a-rt-ob-tests-1017@27e310]
# am[rests-on c-integrate-hypothetical-route-not-bound-1017@bbaece]
def test_every_route_is_kept_with_its_open_premises_and_labelled_scenario():
    (goal, antecedent, vacuous, edge, vacuous_edge), same, found = _routes("routes: interned")
    names = {"edge": edge, "vacuous edge": vacuous_edge, "vacuous": vacuous}
    open_goal, open_antecedent, open_vacuous = (_canonical(*pair) for pair in
                                                (("gamma", "delta"), ("alpha", "beta"), ("chi", "psi")))

    assert same == "True"
    assert found.threshold == 0.6
    assert found.hypothesis == SubjectiveOpinion(0.8, 0.0, 0.2, 0.5)
    assert _shapes(found, names) == {
        (frozenset({(open_goal, "Open")}), (0.8, 0.0, 0.2)),
        (frozenset({("edge", "Holds"), (open_antecedent, "Open")}), (0.64, 0.0, 0.36)),
        (frozenset({("vacuous edge", "Holds"), (open_vacuous, "Open")}), (0.64, 0.0, 0.36)),
        (frozenset({("vacuous edge", "Holds"), ("vacuous", "Undecided")}), (0.0, 0.0, 1.0)),
    }
    assert sorted(route.scenario_status for route in found.routes) == ["Holds", "Holds", "Holds", "Undecided"]
    assert all(route.unmet for route in found.routes)


# An observation discharges the antecedent only when its evidence makes it meet the condition:
# one unit leaves it Undecided and contrary evidence makes it Fail, and both keep the route unmet.
# Discharged, the one step gives the goal 0.64, which Holds, so the route is established.
# am[verifies a-rt-ob-core-1017@26b526] am[verifies a-rt-ob-tests-1017@27e310]
# am[verifies a-rt-ob-established-1017@31d188] am[rests-on c-integrate-runtime-obligations-ruling-1017@6a2fe6]
@pytest.mark.parametrize("name", ["sufficient", "insufficient", "contrary"])
def test_only_evidence_meeting_the_condition_discharges_a_premise(name):
    (_, antecedent, _, edge, _), same, found = _routes(f"routes: {name}")
    held = [route for route in found.routes
            if {leaf.statement_id for leaf in route.leaves} == {edge, antecedent}]

    assert same == "True"
    assert len(held) == 1
    [leaf] = [leaf for leaf in held[0].leaves if leaf.statement_id == antecedent]
    assert leaf.status == LEAF[name]
    assert leaf.discharged is (name == "sufficient")
    assert (held[0].unmet == ()) is (name == "sufficient")
    assert held[0].established is (name == "sufficient")


# Leaves that all hold can leave the goal Undecided, since each deduction step discounts belief:
# two steps from (8, 0) give 0.8 * 0.8 * 0.8 = 0.512, so [0.512, 1] straddles 0.6 where one step's
# 0.64 cleared it. The fully held route has nothing unmet and is still not established.
# am[verifies a-rt-ob-established-1017@31d188] am[verifies a-rt-ob-tests-1017@27e310]
# am[rests-on c-integrate-held-leaves-not-held-goal-1017@43c6c3]
def test_a_route_whose_leaves_all_hold_is_established_only_when_its_scenario_holds():
    (_, antecedent, _, first, second), same, found = _routes("routes: chain")
    names = {"antecedent": antecedent, "first edge": first, "second edge": second}
    open_goal, open_middle, open_antecedent = (_canonical(*pair) for pair in
                                               (("gamma", "delta"), ("mu", "nu"), ("alpha", "beta")))

    assert same == "True"
    assert _shapes(found, names) == {
        (frozenset({(open_goal, "Open")}), (0.8, 0.0, 0.2)),
        (frozenset({("second edge", "Holds"), (open_middle, "Open")}), (0.64, 0.0, 0.36)),
        (frozenset({("second edge", "Holds"), ("first edge", "Holds"), (open_antecedent, "Open")}), (0.512, 0.0, 0.488)),
        (frozenset({("second edge", "Holds"), ("first edge", "Holds"), ("antecedent", "Holds")}), (0.512, 0.0, 0.488)),
    }
    [held] = [route for route in found.routes if not route.unmet]
    assert held.scenario_status == "Undecided"
    assert not any(route.established for route in found.routes)


# The same store gives the same routes, in the same order.
# am[verifies a-rt-ob-core-1017@26b526] am[verifies a-rt-ob-tests-1017@27e310]
def test_a_second_derivation_from_the_same_store_is_equal():
    batch = SnarsBatch((), frozenset(), PROGRAMS["routes: interned"])
    again = _result(run_snars_batch(batch, budget=RunBudget(inference_budget=None, timeout_seconds=900)).output_lines)

    assert again == _in_process("routes: interned")


# The cut gives exactly the status each hand-picked case names, the floating one included, and on
# generated opinions Holds exactly when b clears theta and Fails exactly when b + u falls short,
# never both, whatever the threshold.
# am[verifies a-rt-ob-condition-1017@dc8180] am[verifies a-rt-ob-tests-1017@27e310]
# am[rests-on c-integrate-condition-projection-endpoints-1017@364ddb]
def test_the_cut_gives_one_status_for_every_threshold_and_computed_opinion():
    assert tree(_in_process("cut: edges"))[1:] == [status for _, _, status in EDGES]
    for ((b, _, u, _), theta), status in zip(GENERATED, tree(_in_process("cut: generated"))[1:]):
        assert status in ("Holds", "Fails", "Undecided")
        assert (status == "Holds") is (b > theta)
        assert (status == "Fails") is (not b > theta and b + u < theta)


# (Not S) is cut on the complement's interval [d, d + u]: Holds exactly when d clears theta.
# am[verifies a-rt-ob-negation-track-1017@a1a80d] am[verifies a-rt-ob-tests-1017@27e310]
def test_a_negated_literal_is_cut_on_the_complement_interval():
    for ((_, d, u, _), theta), status in zip(GENERATED, tree(_in_process("cut: complement"))[1:]):
        assert (status == "Holds") is (d > theta)
        assert (status == "Fails") is (not d > theta and d + u < theta)


# Support is premise eligibility: evidence outcome! fuses without a receipt leaves the statement
# unsupported, and its condition Undecided, though its view alone would hold.
# am[verifies a-rt-ob-condition-1017@dc8180] am[verifies a-rt-ob-tests-1017@27e310]
def test_evidence_without_support_decides_no_condition():
    assert tree(_in_process("support: outcome only"))[1:] == ["False", "Undecided", "Holds"]


AB = _statement("a", "b")
BC = _statement("b", "c")
AC = _statement("a", "c")



# The condition classifies the attention search's own witness: a is c is derived only inside the
# search's batch, and the next ordinary ask still finds nothing. An explicit threshold above its
# belief leaves it Undecided; a session whose budget stops the search raises and leaves the store as
# it was.
# am[verifies a-rt-ob-condition-1017@dc8180] am[verifies a-rt-ob-session-1017@f1468f]
# am[verifies a-rt-ob-tests-1017@27e310] am[verifies a-rt-rbs-session-budget-1018@8c3da2]
def test_the_condition_classifies_the_attention_witness_in_its_own_batch(tmp_path):
    database = tmp_path / "beliefs.sqlite3"
    with SnarsSession.persistent(database, budget=request_budget(), include_goalchainer_policy=False,
                                 reader=incident_reader()) as session:
        session.believe(AB, evidence=Evidence(8, 0), source="observation-ab")
        unknown = session.condition(AC)
        assert (unknown.status, unknown.search, unknown.steps) == ("Undecided", "Incomplete", 0)

        session.believe(BC, evidence=Evidence(8, 0), source="observation-bc")
        before = session.state_payload()
        spent = session.budget.spent
        found = session.condition(AC)
        assert (found.status, found.search, found.threshold) == ("Holds", "Witness", 0.6)
        assert found.opinion.belief > 0.6 and session.budget.spent > spent
        assert session.ask(AC).payload == ["answers", []]
        assert session.condition(AC, threshold=0.7).status == "Undecided"
    stopped = RunBudget(inference_budget=1, timeout_seconds=900)
    with SnarsSession.persistent(database, budget=stopped, include_goalchainer_policy=False,
                                 reader=incident_reader()) as session:
        with pytest.raises(InferenceBudgetExceeded):
            session.condition(AC)
    with SnarsSession.persistent(database, budget=request_budget(), include_goalchainer_policy=False,
                                 reader=incident_reader()) as session:
        assert session.state_payload() == before


# A statement believed against holds as (Not S) and fails as S, both from one stored opinion.
# am[verifies a-rt-ob-negation-track-1017@a1a80d] am[verifies a-rt-ob-tests-1017@27e310]
def test_a_negated_condition_reads_the_complement_of_the_stored_opinion():
    with SnarsSession.ephemeral(budget=request_budget(), include_goalchainer_policy=False,
                                reader=incident_reader()) as session:
        session.believe(AC, evidence=Evidence(0, 8), source="observation-ac")
        positive = session.condition(AC)
        negative = session.condition(AC, negated=True)
    assert (positive.status, positive.negated) == ("Fails", False)
    assert (negative.status, negative.negated) == ("Holds", True)
    assert negative.opinion == SubjectiveOpinion(positive.opinion.disbelief, positive.opinion.belief,
                                                 positive.opinion.uncertainty, 1.0 - positive.opinion.base_rate)


# track gives SNARS's opinion of counts at its default rate and the one cut of it; it needs the
# caller's budget and refuses counts that are not evidence.
# am[verifies a-rt-ob-negation-track-1017@a1a80d] am[verifies a-rt-ob-tests-1017@27e310]
def test_track_projects_counts_through_the_same_cut():
    budget = RunBudget(inference_budget=None, timeout_seconds=900)
    found = {counts: track(*counts, budget=budget) for counts in ((8, 0), (1, 0), (0, 8), (0, 0))}

    assert found[(8, 0)].opinion == SubjectiveOpinion(0.8, 0.0, 0.2, 0.5)
    assert [found[counts].status for counts in ((8, 0), (1, 0), (0, 8), (0, 0))] == [
        "Holds", "Undecided", "Fails", "Undecided"]
    assert {found[counts].threshold for counts in found} == {0.6}
    assert track(1, 0, budget=budget, threshold=0.3).status == "Holds"
    assert budget.spent > 0
    with pytest.raises(InvalidInputError):
        track(-1, 0, budget=budget)
    with pytest.raises(TypeError):
        track(1, 0)


# In process through the session: the deduction store has no backward rule for its copula, so the
# goal's one route is direct observation, and its scenario is the hypothesis the caller states.
# Nothing persists, and a session whose budget stops the search raises rather than answering no
# routes.
# am[verifies a-rt-ob-session-1017@f1468f] am[verifies a-rt-ob-tests-1017@27e310]
# am[verifies a-rt-rbs-session-budget-1018@8c3da2]
def test_session_obligations_report_the_callers_hypothesis_and_persist_nothing(tmp_path):
    database = tmp_path / "beliefs.sqlite3"
    with SnarsSession.persistent(database, budget=request_budget(), include_goalchainer_policy=False,
                                 reader=incident_reader()) as session:
        session.believe(AB, evidence=Evidence(8, 0), source="observation-ab")
        before = session.state_payload()
        found = session.obligations(AC, hypothesis=Evidence(2, 0))
        assert found.hypothesis == SubjectiveOpinion(0.5, 0.0, 0.5, 0.5)
        assert [[leaf.status for leaf in route.leaves] for route in found.routes] == [["Open"]]
        assert found.routes[0].scenario == found.hypothesis
        assert session.state_payload() == before
    with SnarsSession.persistent(database, budget=RunBudget(inference_budget=1, timeout_seconds=900),
                                 include_goalchainer_policy=False, reader=incident_reader()) as session:
        with pytest.raises(InferenceBudgetExceeded):
            session.obligations(AC)
    with SnarsSession.persistent(database, budget=request_budget(), include_goalchainer_policy=False,
                                 reader=incident_reader()) as session:
        assert session.state_payload() == before


# The budget the caller opened the session with reaches each batch itself, already charged, and an
# operation takes no budget of its own; an omitted threshold stays distinct from an explicit 0: the
# record reads SNARS's decision threshold for the first.
# am[verifies a-rt-ob-session-1017@f1468f] am[verifies a-rt-ob-tests-1017@27e310]
# am[verifies a-rt-rbs-session-budget-1018@8c3da2]
def test_obligations_and_condition_use_the_callers_budget_and_threshold():
    budget = RunBudget(inference_budget=50, timeout_seconds=900)
    budget.charge(7)
    seen = []

    # am[verifies a-rt-ob-session-1017@f1468f]
    def execute(batch, received):
        seen.append((batch.includes, batch.directive, received is budget, received.remaining()[0]))
        received.charge(3)
        if "condition-record" in batch.directive:
            return ('(goalchainer-snars-v1 condition ok (condition (statement (sh-atom x "x")) (sid s1) (polarity neg) '
                    '(threshold 0.0) (search Incomplete) (steps 0) (status Undecided) '
                    '(opinion (Opinion 0.0 0.0 1.0 0.5))))',)
        return ('(goalchainer-snars-v1 obligations ok (obligations (statement (sh-atom x "x")) '
                '(threshold 0.6) (hypothesis (Opinion 0.8 0.0 0.2 0.5)) (routes ())))',)

    with SnarsSession.ephemeral(budget=budget, execute=execute, include_goalchainer_policy=False,
                                reader=incident_reader()) as session:
        assert session.obligations(AC).routes == ()
        negated = session.condition(AC, threshold=0.0, negated=True)
        assert (negated.status, negated.negated) == ("Undecided", True)
        with pytest.raises(TypeError):
            session.obligations(AC, budget=budget)  # type: ignore[call-arg]
    (obligations_includes, obligations_directive, same, left), (condition_includes, condition_directive, again, rest) = seen
    assert (same, again, left, rest) == (True, True, 43, 40)
    assert obligations_includes == frozenset() and condition_includes == frozenset({"attention"})
    assert "(sn config decision-threshold)" in obligations_directive
    assert "(sn config decision-threshold)" not in condition_directive and " neg 0.0)" in condition_directive
    assert budget.spent == 13
