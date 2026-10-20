"""Purpose: test the one deontic status rule: its status order is a lattice whose join is the rule,
the incident example host's blocking cut is the statuses at least forbidden, duplicated order facts
change no answer, a review's dilemma makes conflict, and a clash lib_deontic leaves unproved leaves
the action unregulated."""

from __future__ import annotations

import itertools

import pytest
from metta import Expression, S

from goal_chainer import evidence_policy
from goal_chainer.deontic_engine import DEONTIC_STATUSES, run_deontic_theory
from goal_chainer.examples.incident.execution import SETTLEMENT
from goal_chainer.runtime.engine import metta_engine
from policy_support import policy_call
from request_support import budget


# The status the rule answers for a set of proved modes and whether a dilemma was reported.
# am[verifies a-ev-status-lattice-1017@a862b7]
def _status(modes, dilemma: bool) -> str:
    return str(policy_call("(gc-deontic-status {modes} {dilemma})",
                           modes=Expression(*(S[mode] for mode in sorted(modes))), dilemma=dilemma))


# Standard Deontic Logic: F p is O not-p, so forbidden with any other mode is a conflict, and
# obligated covers permitted (c-ev-two-status-lattices); a dilemma is a clash nothing resolved.
# am[verifies a-ev-status-lattice-1017@a862b7] am[verifies a-ev-in-dilemma-conflict@9cbf4c]
# am[rests-on c-ev-two-status-lattices@fab97a] am[verifies a-ie-c5b-tests-1018]
@pytest.mark.parametrize(
    "modes",
    [frozenset(combo) for size in range(4) for combo in itertools.combinations("FOP", size)],
)
@pytest.mark.parametrize("dilemma", [False, True])
def test_the_status_of_every_combination_of_proved_modes(modes, dilemma):
    expected = (
        "conflict"
        if dilemma or ("F" in modes and modes & {"O", "P"})
        else "forbidden"
        if "F" in modes
        else "obligated"
        if "O" in modes
        else "permitted"
        if "P" in modes
        else "unregulated"
    )
    assert _status(modes, dilemma) == expected


# The status's readers, the relevance review and the incident example host, accept nothing outside
# DEONTIC_STATUSES, so the rule must answer exactly that vocabulary over its whole input space:
# every mode set, with and without a dilemma.
# am[verifies a-ev-status-lattice-1017@a862b7] am[verifies a-ie-c5b-tests-1018]
def test_the_rule_answers_exactly_the_status_vocabulary_the_reader_accepts():
    cases = [
        (frozenset(combo), dilemma)
        for size in range(4)
        for combo in itertools.combinations("FOP", size)
        for dilemma in (False, True)
    ]

    assert {_status(modes, dilemma) for modes, dilemma in cases} == set(DEONTIC_STATUSES)



# am[verifies a-ev-status-lattice-1017@a862b7]
def _statuses():
    return [str(status) for status in policy_call("(gc-statuses)")]


# am[verifies a-ev-status-lattice-1017@a862b7]
def _at_least(floor, status):
    return str(policy_call("(gc-status-at-least {floor} {status})", floor=S[floor], status=S[status])) == "True"


# The declared order is a partial order with a bottom and a top, its join is the least upper bound,
# and the join is associative, commutative and idempotent with the bottom as identity: a join
# semilattice, checked by exhaustion over every status the order declares, which are exactly the
# statuses the reader accepts. The order is N5 and not distributive, so it is no semiring.
# Time: s^2 order and join evaluations, then s^3 table lookups, s = 5 statuses.
# am[verifies a-ev-status-lattice-1017@a862b7] am[rests-on c-ev-status-rule-is-a-lattice-join-1017@c5b4d0]
def test_the_status_order_is_a_lattice_whose_join_is_the_rule():
    statuses = _statuses()
    assert sorted(statuses) == sorted(DEONTIC_STATUSES) and len(statuses) == len(set(statuses))
    leq = {(a, b): _at_least(a, b) for a in statuses for b in statuses}
    join = {
        (a, b): str(policy_call("(gc-status-join {a} {b})", a=S[a], b=S[b]))
        for a in statuses
        for b in statuses
    }
    bottom = str(policy_call("(gc-status-bottom)"))
    top = str(policy_call("(gc-status-top)"))

    for a, b, c in itertools.product(statuses, repeat=3):
        assert leq[a, a]
        assert not (leq[a, b] and leq[b, a]) or a == b
        assert not (leq[a, b] and leq[b, c]) or leq[a, c]
        assert join[join[a, b], c] == join[a, join[b, c]]
    for a, b in itertools.product(statuses, repeat=2):
        upper = [u for u in statuses if leq[a, u] and leq[b, u]]
        assert join[a, b] in upper and all(leq[join[a, b], u] for u in upper)
        assert join[a, b] == join[b, a]
    for a in statuses:
        assert join[a, a] == a and join[bottom, a] == a and join[top, a] == top
        assert leq[bottom, a] and leq[a, top]
    assert (bottom, top) == ("unregulated", "conflict")


# The incident example host's blocking cut, (gc blocking-status?) in its settlement policy, is its
# own pinned policy (c-core-blocking-cut-independent-1017); today it is exactly the statuses at least
# forbidden, checked over every status the order declares.
# am[verifies a-ev-status-lattice-1017@a862b7] am[related c-core-blocking-cut-independent-1017@b1b8b4]
# am[verifies a-ie-s5-incident-host-1018@53176a] am[verifies a-ie-s2a-blocking-cut-home-1018@dd66bf]
def test_the_blocking_cut_is_the_statuses_at_least_forbidden():
    for status in _statuses():
        at_least_forbidden = _at_least("forbidden", status)
        blocks = policy_call("(gc blocking-status? {status})", group=SETTLEMENT, status=S[status])

        assert (str(blocks) == "True") is at_least_forbidden, status


# The rank run reads one answer per call, so the rule folds and never answers alternatives: a
# duplicated cover or mode fact changes no status. A mode no status is settled for answers an Error,
# which no reader accepts as a status.
# am[verifies a-ev-status-lattice-1017@a862b7]
def test_duplicated_order_facts_change_no_answer_and_an_unsettled_mode_is_an_error():
    cases = [
        (" ".join(combo), dilemma)
        for size in range(4)
        for combo in itertools.combinations("FOP", size)
        for dilemma in ("False", "True")
    ]
    program = " ".join(f"!(gc-deontic-status ({modes}) {dilemma})" for modes, dilemma in cases)
    with metta_engine(None) as engine:
        with engine.space() as space:
            space.load(evidence_policy.POLICY_DIRECTORY / "goalchainer_deontic.metta")
            once = [[str(answer) for answer in group] for group in space.run(program)]
            space.add(S["gc-status-cover"](S.unregulated, S.permitted))
            space.add(S["gc-mode-status"](S.O, S.obligated))
            twice = [[str(answer) for answer in group] for group in space.run(program)]
            unsettled = [[str(answer) for answer in group] for group in space.run("!(gc-deontic-status (X) False)")]

    assert all(len(group) == 1 for group in once) and twice == once
    assert unsettled[0][0].startswith("(Error X")

# The deontic modes `run` proved of `action`: its provable, atemporal, argument-free conclusions in
# a deontic mode.
# am[verifies a-ev-in-dilemma-conflict@9cbf4c]
def _proved_modes(run, action: str) -> set[str]:
    return {
        conclusion.literal.mode
        for conclusion in run.conclusions
        if conclusion.is_provable and conclusion.literal.functor == action and conclusion.literal.temporal == "none"
        and not conclusion.literal.args and conclusion.literal.mode != "none"
    }


# lib_deontic proves neither side of an unranked must-versus-forbidden clash and reports it only
# as a dilemma (c-ev-deontic-clash-semantics), so the review's dilemma is what makes the action's
# status conflict, the top.
# am[verifies a-ev-in-dilemma-conflict@9cbf4c] am[rests-on c-ev-deontic-clash-semantics@dc6408]
# am[verifies a-ie-c5b-tests-1018]
def test_an_action_a_review_leaves_in_a_dilemma_is_in_conflict():
    run = run_deontic_theory(
        "(given a)\n(normally r1 a (must send_report))\n(normally r2 a (forbidden send_report))\n",
        budget=budget(),
    )
    dilemmas = [literal.functor for literal in run.dilemmas]

    assert dilemmas == ["send_report"] and _proved_modes(run, "send_report") == set()
    assert _status(_proved_modes(run, "send_report"), "send_report" in dilemmas) == "conflict"


# An unranked may-versus-forbidden clash proves no mode and reports no dilemma
# (c-ev-deontic-clash-semantics), so the action it is about comes out unregulated, the bottom: the
# theory decided nothing about it.
# am[verifies a-ev-status-lattice-1017@a862b7] am[rests-on c-ev-deontic-clash-semantics@dc6408]
# am[verifies a-ie-c5b-tests-1018]
def test_a_clash_lib_deontic_leaves_unproved_leaves_the_action_unregulated():
    run = run_deontic_theory(
        "(given a)\n(normally r1 a (may publish))\n(normally r2 a (forbidden publish))\n",
        budget=budget(),
    )

    assert not run.dilemmas and _proved_modes(run, "publish") == set()
    assert _status(_proved_modes(run, "publish"), False) == "unregulated"
