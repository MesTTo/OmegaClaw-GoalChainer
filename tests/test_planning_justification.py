"""Purpose: test the justification kernel, planning/justification.metta, by running it on pymetta
and comparing every answer with an independent finite reference model and, for plain attack
graphs, with the grounded labelling found by enumerating complete labellings."""

from __future__ import annotations

import random
from contextlib import contextmanager
from itertools import product
from typing import get_args

import pytest
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st
from metta import Expression, S, V, Variable, parse

import justification_reference as ref
from goal_chainer.errors import InvalidInputError, ProtocolError
from goal_chainer.runtime.budget import InferenceBudgetExceeded, ReviewTimeout, RunBudget, run_bounded
from goal_chainer.runtime.engine import metta_engine
from goal_chainer.runtime.evaluator import ModuleGroup, plain_value, prepare
from goal_chainer.planning import justification as jk

SETTINGS = settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
AT = 10


# am[implements a-jk-tests-1018@7f8ba3]
def budget() -> RunBudget:
    return RunBudget(inference_budget=None, timeout_seconds=120.0)


# am[implements a-jk-tests-1018@7f8ba3]
def atom(term):
    """A plain term, tuples for expressions, as a pymetta atom."""

    if isinstance(term, tuple):
        return Expression(*(atom(child) for child in term))
    return term


# am[implements a-jk-tests-1018@7f8ba3]
def answer_of(justification: jk.Justification) -> set:
    """The boundary's answer in the reference model's form."""

    return {(S.Label, label.argument, S[label.status], S[label.check]) for label in justification.labels} | {
        (S.Link, link.link, S[link.state]) for link in justification.links
    }


# am[implements a-jk-tests-1018@7f8ba3]
def rows_answer(rows, at=AT) -> jk.Justification:
    return jk.justify([atom(row) for row in rows], at=at, budget=budget())


# am[implements a-jk-tests-1018@7f8ba3]
def labels_by_argument(justification: jk.Justification) -> dict:
    return {label.argument: (label.status, label.check) for label in justification.labels}


# am[implements a-jk-tests-1018@7f8ba3]
def link_states(justification: jk.Justification) -> dict:
    return {link.link: link.state for link in justification.links}


# An observation term, (KIND ID ESTIMATOR VALIDITY).
# am[implements a-jk-tests-1018@7f8ba3]
def reading(name, estimator, validity=S.Forever):
    return (S.Obs, name, estimator, validity)


# The reference to an observation, as a source, a reason or a label's argument.
# am[implements a-jk-tests-1018@7f8ba3]
def obs(name, estimator, validity=S.Forever):
    return (S.Observation, reading(name, estimator, validity))


# The references to a claim, a From row and a stated reason.
# am[implements a-jk-tests-1018@7f8ba3] am[implements a-jk-typed-boundary-1018@dee690]
def claim(literal):
    return (S.Claim, literal)


# am[implements a-jk-tests-1018@7f8ba3] am[implements a-jk-typed-boundary-1018@dee690]
def row(term):
    return (S.Row, term)


# am[implements a-jk-tests-1018@7f8ba3] am[implements a-jk-typed-boundary-1018@dee690]
def stated(term):
    return (S.Stated, term)


# am[implements a-jk-tests-1018@7f8ba3]
def frm(claim, source):
    return (S.From, claim, source)


# am[implements a-jk-tests-1018@7f8ba3]
def neg(claim):
    return (S.Not, claim)


A, B, C, D = ((S.Signal, name) for name in ("a", "b", "c", "d"))
MEASURED, MODEL = "measured", "model-proposed"


# --- the abstract frame against the enumerated grounded labelling and the reference -------------


# Every attack relation on one, two and three arguments, 530 graphs: the kernel's Accepted,
# Refuted and Undecided are the grounded labelling's in, out and undec.
# am[verifies a-jk-semantics-1018@8cb82d]
def test_every_small_attack_graph_gets_the_grounded_labelling() -> None:
    for size in (1, 2, 3):
        arguments = [f"p{i}" for i in range(size)]
        pairs = list(product(arguments, repeat=2))
        for chosen in product((False, True), repeat=len(pairs)):
            attacks = {pair for pair, on in zip(pairs, chosen) if on}
            frame = (
                S.Frame,
                tuple(arguments),
                (),
                tuple((S.Attack, f"{b}>{a}", b, a) for b, a in sorted(attacks)),
                (),
                (),
            )
            got = {label.argument: label.status for label in jk.justify_frame(atom(frame), budget=budget()).labels}
            want = ref.grounded_by_enumeration(arguments, attacks)
            assert got == {a: {"in": "Accepted", "out": "Refuted", "undec": "Undecided"}[want[a]] for a in arguments}, attacks


# A frame is a set of arguments, links, undercuts and establishing tags, so an argument, undercut
# or tag may be listed twice (c-jk-frame-established-repeat-1018); link ids stay distinct.
# am[implements a-jk-tests-1018@7f8ba3] am[implements a-jk-frame-sets-1018@390a56]
@st.composite
def frames(draw):
    arguments = [f"p{i}" for i in range(draw(st.integers(1, 5)))]
    supports, attacks = [], []
    for index, (source, target) in enumerate(product(arguments, repeat=2)):
        kind = draw(st.sampled_from(("none", "none", "attack", "support")))
        if kind == "attack":
            attacks.append((S.Attack, f"l{index}", source, target))
        elif kind == "support":
            supports.append((S.Support, f"l{index}", source, target))
    links = [link[1] for link in supports + attacks]
    undercuts = sorted(
        {(S.Undercut, link, draw(st.sampled_from(arguments))) for link in links if draw(st.booleans()) and draw(st.booleans())}
    )
    established = [a for a in arguments if draw(st.integers(0, 3)) == 0]

    def repeated(items):
        return [*items, draw(st.sampled_from(items))] if items and draw(st.integers(0, 3)) == 0 else items

    return (S.Frame, tuple(repeated(arguments)), tuple(supports), tuple(attacks), tuple(repeated(undercuts)),
            tuple(repeated(established)))


# Random frames with supports, undercuts and establishing tags, cycles through negation included:
# the kernel's labels and link states equal the reference model's, whose rules are AgenticMind's
# (c-jk-reference-equals-am-1018).
# am[verifies a-jk-semantics-1018@8cb82d] am[verifies a-jk-metta-kernel-1018@258f74]
@SETTINGS
@given(frames())
def test_frames_match_the_reference_model(frame) -> None:
    labelling = ref.label(
        ref.Frame(
            frozenset(frame[1]),
            frozenset(link[1:] for link in frame[2]),
            frozenset(link[1:] for link in frame[3]),
            frozenset(cut[1:] for cut in frame[4]),
            frozenset(frame[5]),
        )
    )
    want = {(S.Label, a, S[labelling.status[a]], S[labelling.check[a]]) for a in frame[1]} | {
        (S.Link, link, S[state]) for link, state in labelling.links.items()
    }
    assert answer_of(jk.justify_frame(atom(frame), budget=budget())) == want


# A frame that lists an establishing tag twice is answered once, as the frame listing it once is:
# the tag once doubled every answer that tested membership in the tags (c-jk-frame-established-repeat-1018).
# am[verifies a-jk-frame-sets-1018@390a56] am[verifies i-jk-frame-established-repeat-1018@ae0089]
def test_a_frame_repeating_an_establishing_tag_answers_as_one_listing_it_once() -> None:
    once = (S.Frame, ("a", "b"), ((S.Support, "l", "a", "b"),), (), (), ("a",))
    twice = (S.Frame, ("a", "b"), ((S.Support, "l", "a", "b"),), (), (), ("a", "a"))
    assert answer_of(jk.justify_frame(atom(twice), budget=budget())) == answer_of(jk.justify_frame(atom(once), budget=budget()))


# --- evidence rows ----------------------------------------------------------------------------

LITERALS = [A, B, C]
CLAIMS = LITERALS + [neg(literal) for literal in LITERALS]


# A snapshot whose chained sources are claims of earlier rows and whose withdrawal reasons name
# claims, rows and observations of the snapshot, an observation no row uses and a stated reason, so
# the contract holds; claims may be spelled like an earlier row or observation. With `dangling` a
# claim or row reference may name nothing in the snapshot, which the contract refuses.
# am[implements a-jk-tests-1018@7f8ba3]
@st.composite
def snapshots(draw, dangling=False):
    observations = [
        obs(
            f"o{i}",
            draw(st.sampled_from(ref.ESTIMATORS)),
            draw(st.sampled_from((S.Forever, (S.Until, 5), (S.Until, AT), (S.Until, 50)))),
        )
        for i in range(draw(st.integers(1, 4)))
    ]
    froms: list = []
    for _ in range(draw(st.integers(1, 6))):
        claimed = CLAIMS if dangling else [row[1] for row in froms]
        sources = observations + [claim(c) for c in claimed] if claimed and draw(st.booleans()) else observations
        spellings = froms + [o[1] for o in observations]
        claims = CLAIMS + spellings if draw(st.integers(0, 4)) == 0 else CLAIMS
        froms.append(frm(draw(st.sampled_from(claims)), draw(st.sampled_from(sources))))
    reasons = (
        [stated((S.Moved, "domain")), obs("unused", "deterministic")]
        + [claim(c) for c in (CLAIMS if dangling else sorted({row[1] for row in froms}, key=str))]
        + [row(r) for r in sorted(set(froms), key=str)]
        + ([row(frm(A, obs("ghost", MODEL)))] if dangling else [])
        + observations
    )
    withdrawals = [
        (S.Withdrawn, draw(st.sampled_from(froms)), draw(st.sampled_from(reasons)))
        for _ in range(draw(st.integers(0, 2)))
    ]
    rows = froms + withdrawals
    draw(st.randoms(use_true_random=False)).shuffle(rows)
    return rows


# Random snapshots, chains and contrary readings of every estimator class, withdrawals and expiry
# included: the kernel answers the reference model's labels and row states.
# am[verifies a-jk-contract-literal-rows-1018@5a7264] am[verifies a-jk-metta-kernel-1018@258f74]
@SETTINGS
@given(snapshots())
def test_rows_match_the_reference_model(rows) -> None:
    labels, links = ref.justify(AT, rows)
    assert answer_of(rows_answer(rows)) == labels | links


# Where a claim or row reference names nothing in the snapshot, the kernel and the reference refuse
# alike, naming the same problems; otherwise they answer alike.
# am[verifies a-jk-contract-literal-rows-1018@5a7264]
@SETTINGS
@given(snapshots(dangling=True))
def test_rows_with_any_sources_are_refused_or_answered_as_the_reference_does(rows) -> None:
    try:
        labels, links = ref.justify(AT, rows)
    except ref.Refused as refusal:
        with pytest.raises(jk.JustificationRefused) as refused:
            rows_answer(rows)
        assert {str(problem[1]) for problem in refused.value.problems} == refusal.kinds
    else:
        assert answer_of(rows_answer(rows)) == labels | links


# The answer is one canonical term: row order and repetition change nothing, and asking again
# gives the same term.
# am[verifies a-jk-metta-kernel-1018@258f74]
@SETTINGS
@given(snapshots(), st.randoms(use_true_random=False))
def test_the_answer_is_canonical_whatever_the_row_order(rows, shuffler) -> None:
    shuffled = rows + [shuffler.choice(rows)]
    shuffler.shuffle(shuffled)
    first = rows_answer(rows)
    assert rows_answer(shuffled).term == first.term
    assert rows_answer(rows).term == first.term


# A literal and its contrary are never both accepted, whatever the evidence.
# am[verifies a-jk-contract-literal-rows-1018@5a7264]
@SETTINGS
@given(snapshots())
def test_no_snapshot_accepts_a_literal_and_its_contrary(rows) -> None:
    labels = labels_by_argument(rows_answer(rows))
    for literal in LITERALS:
        assert not (
            labels.get(claim(literal), ("",))[0] == "Accepted" and labels.get(claim(neg(literal)), ("",))[0] == "Accepted"
        )


# --- the cases the brief names --------------------------------------------------------------------


# A support cycle with no founded entry founds nothing: both claims and both rows lose their
# grounds, while nothing withdraws the rows' links.
# am[verifies a-jk-semantics-1018@8cb82d] am[verifies a-jk-rr-row-report-1018@6747d2]
def test_a_support_cycle_cannot_bootstrap_support() -> None:
    rows = [frm(A, claim(B)), frm(B, claim(A))]
    answer = rows_answer(rows)
    unsupported = ("Unsupported", "Unchecked")
    assert labels_by_argument(answer) == {
        claim(A): unsupported, claim(B): unsupported, row(rows[0]): unsupported, row(rows[1]): unsupported
    }
    assert set(link_states(answer).values()) == {"Holds"}


# Defeating an attacker reinstates what it attacked: a -> b -> c leaves c accepted.
# am[verifies a-jk-semantics-1018@8cb82d]
def test_defeating_an_attacker_reinstates_its_target() -> None:
    frame = (S.Frame, ("a", "b", "c"), (), ((S.Attack, "ab", "a", "b"), (S.Attack, "bc", "b", "c")), (), ())
    statuses = {label.argument: label.status for label in jk.justify_frame(atom(frame), budget=budget()).labels}
    assert statuses == {"a": "Accepted", "b": "Refuted", "c": "Accepted"}


# Conflicting model-proposed readings leave both claims undecided; an establishing observation
# for one refutes the other and reinstates the reading it agrees with.
# am[verifies a-jk-contract-literal-rows-1018@5a7264]
def test_establishing_evidence_resolves_a_conflict_and_reinstates() -> None:
    conflict = [frm(A, obs("m1", MODEL)), frm(neg(A), obs("m2", MODEL))]
    assert labels_by_argument(rows_answer(conflict))[claim(A)] == ("Undecided", "Unchecked")
    resolved = labels_by_argument(rows_answer(conflict + [frm(A, obs("e", MEASURED))]))
    assert resolved[claim(A)] == ("Accepted", "Checked")
    assert resolved[claim(neg(A))] == ("Refuted", "Unchecked")


# Two establishing observations that disagree conflict: neither claim is accepted or checked.
# am[verifies a-jk-contract-literal-rows-1018@5a7264]
def test_disagreeing_establishing_observations_conflict() -> None:
    labels = labels_by_argument(rows_answer([frm(A, obs("e1", MEASURED)), frm(neg(A), obs("e2", "human-asserted"))]))
    assert labels[claim(A)] == ("Undecided", "Unchecked")
    assert labels[claim(neg(A))] == ("Undecided", "Unchecked")


# A withdrawal takes the claim's grounds without refuting it: the observation and the row itself
# stand, and only the row's link is withdrawn.
# am[verifies a-jk-contract-literal-rows-1018@5a7264] am[verifies a-jk-rr-row-report-1018@6747d2]
def test_withdrawal_loses_grounds_without_refutation() -> None:
    reading_row = frm(A, obs("m", MODEL))
    answer = rows_answer([reading_row, (S.Withdrawn, reading_row, stated((S.Moved, "domain")))])
    labels = labels_by_argument(answer)
    assert labels[claim(A)] == ("Unsupported", "Unchecked")
    assert labels[obs("m", MODEL)] == ("Accepted", "Unchecked")
    assert labels[row(reading_row)] == ("Accepted", "Unchecked")
    assert link_states(answer)[row(reading_row)] == "Withdrawn"


# Refuting a withdrawal's reason reinstates the withdrawn row, a dynamic link coming back.
# am[verifies a-jk-semantics-1018@8cb82d] am[verifies a-jk-contract-literal-rows-1018@5a7264]
def test_refuting_a_withdrawal_reason_reinstates_the_row() -> None:
    reading_row = frm(A, obs("m", MODEL))
    stale = (S.Stale, "m")
    rows = [reading_row, frm(stale, obs("s", MODEL)), (S.Withdrawn, reading_row, claim(stale))]
    assert labels_by_argument(rows_answer(rows))[claim(A)] == ("Unsupported", "Unchecked")
    answer = rows_answer(rows + [frm(neg(stale), obs("e", MEASURED))])
    assert labels_by_argument(answer)[claim(A)] == ("Accepted", "Unchecked")
    assert link_states(answer)[row(reading_row)] == "Holds"


# A claim with several independent grounds stands until every one is withdrawn.
# am[verifies a-jk-contract-literal-rows-1018@5a7264]
def test_independent_supports_each_suffice() -> None:
    first, second = frm(A, obs("m1", MODEL)), frm(A, obs("m2", MODEL))
    one_left = [first, second, (S.Withdrawn, first, stated((S.Moved, "x")))]
    assert labels_by_argument(rows_answer(one_left))[claim(A)] == ("Accepted", "Unchecked")
    assert labels_by_argument(rows_answer(one_left + [(S.Withdrawn, second, stated((S.Moved, "y")))]))[claim(A)] == (
        "Unsupported",
        "Unchecked",
    )


# An establishing observation past its validity stops checking the claim, which still stands on a
# current model-proposed reading: a stale evidence tag loses its provenance, not the claim.
# am[verifies a-jk-contract-literal-rows-1018@5a7264]
def test_a_stale_establishing_observation_stops_checking() -> None:
    rows = [frm(A, obs("e", MEASURED, (S.Until, 50))), frm(A, obs("m", MODEL))]
    assert labels_by_argument(rows_answer(rows, at=40))[claim(A)] == ("Accepted", "Checked")
    assert labels_by_argument(rows_answer(rows, at=60))[claim(A)] == ("Accepted", "Unchecked")


# An expired reading's claim decays toward unknown, never toward refuted.
# am[verifies a-jk-contract-literal-rows-1018@5a7264]
def test_an_expired_reading_decays_to_unsupported() -> None:
    labels = labels_by_argument(rows_answer([frm(A, obs("m", MODEL, (S.Until, 5)))]))
    assert labels[claim(A)] == ("Unsupported", "Unchecked")


# The parent's counterexample: a reading past its validity loses its claim's ground, and claims a
# caller spells like the kernel's own bookkeeping, the stale reason or a link, change nothing,
# while each is labelled like any claim (c-integrate-jk-expiry-collision-measured-1018).
# am[verifies a-integrate-jk-internal-identity-1018@2a131d] am[verifies a-jk-id-tagged-1018@d1757d]
def test_caller_literals_cannot_reach_the_kernels_bookkeeping() -> None:
    expired = frm(A, obs("old", MEASURED, (S.Until, 5)))
    assert labels_by_argument(rows_answer([expired]))[claim(A)] == ("Unsupported", "Unchecked")
    for spelled in ((S.Expired, AT), (S.Stale, AT), (S.Infers, expired), (S.Premise, expired), (S.Refute, expired), (S.Row, expired)):
        rows = [expired, frm(spelled, obs("p", MODEL)), frm(neg(spelled), obs("n", MEASURED))]
        labels = labels_by_argument(rows_answer(rows))
        assert labels[claim(A)] == ("Unsupported", "Unchecked"), spelled
        assert (labels[claim(spelled)], labels[claim(neg(spelled))]) == (("Refuted", "Unchecked"), ("Accepted", "Checked")), spelled
        assert known(A, rows) == jk.Knowledge(None, None), spelled


# A withdrawal names its reason's category: a (Row ROW) reason withdraws only while that row
# stands, a (Claim CLAIM) one while the claim is accepted, and an (Observation OBS) or (Stated TERM)
# one always, with no row claiming it, as evidence's planner sends for a superseded receipt and a
# reading taken before an application (c-ev-pk-typed-rows-1018).
# am[verifies a-jk-typed-boundary-1018@dee690]
def test_withdrawals_name_their_reasons_category() -> None:
    reading_row = frm(A, obs("m", MODEL))
    named = frm(B, obs("b", MODEL))
    defeated = [reading_row, named, frm(neg(B), obs("nb", MEASURED)), (S.Withdrawn, reading_row, row(named))]
    assert link_states(rows_answer(defeated))[row(reading_row)] == "Holds"
    assert link_states(rows_answer([reading_row, named, (S.Withdrawn, reading_row, row(named))]))[row(reading_row)] == "Withdrawn"
    refuted = [reading_row, named, frm(neg(B), obs("nb", MEASURED)), (S.Withdrawn, reading_row, claim(B))]
    assert link_states(rows_answer(refuted))[row(reading_row)] == "Holds"
    receipt = (S.Observation, (S.Receipt, "r-last", "deterministic", S.Forever))
    answer = rows_answer([reading_row, (S.Withdrawn, reading_row, receipt)])
    assert link_states(answer)[row(reading_row)] == "Withdrawn"
    assert labels_by_argument(answer)[receipt] == ("Accepted", "Checked")
    before = rows_answer([reading_row, (S.Withdrawn, reading_row, stated((S.BeforeApplication, "a1")))])
    assert link_states(before)[row(reading_row)] == "Withdrawn"


# A claim spelled like a row, an observation or a stated reason of the snapshot is a claim beside
# it, and adding it never reinterprets the row, the measured source or the stated reason
# (c-jk-audit-claim-row-merge-1018, c-jk-source-role-by-membership-1018,
# c-jk-reason-role-by-membership-1018).
# am[verifies a-jk-typed-boundary-1018@dee690] am[verifies a-integrate-jk-categorical-boundary-1018@254af6]
def test_claims_spelled_like_other_arguments_stand_beside_them() -> None:
    reading_row = frm(A, obs("m", MEASURED))
    measured = reading("m", MEASURED)
    reason = (S.Moved, "domain")
    for spelled in (reading_row, measured, reason):
        rows = [reading_row, (S.Withdrawn, frm(B, obs("w", MODEL)), stated(reason)), frm(B, obs("w", MODEL)),
                frm(spelled, obs("p", MODEL)), frm(neg(spelled), obs("n", "deterministic"))]
        answer = rows_answer(rows)
        labels = labels_by_argument(answer)
        assert labels[claim(A)] == ("Accepted", "Checked"), spelled
        assert labels[row(reading_row)] == ("Accepted", "Checked"), spelled
        assert labels[obs("m", MEASURED)] == ("Accepted", "Checked"), spelled
        assert link_states(answer)[row(frm(B, obs("w", MODEL)))] == "Withdrawn", spelled
        assert (labels[claim(spelled)], labels[claim(neg(spelled))]) == (("Refuted", "Unchecked"), ("Accepted", "Checked")), spelled


# Under the adopted source preference (c-integrate-reading-owner-rule-1018) a current contrary
# reading that lost reads Refuted with its link holding, the live disagreement relevance
# escalates, while an expired or withdrawn contrary reads its link Withdrawn, and the measured
# reading's claim stands in all three.
# am[verifies a-jk-rr-row-report-1018@6747d2]
def test_a_current_contrary_that_lost_is_told_from_an_expired_or_withdrawn_one() -> None:
    measured = frm(A, obs("e", MEASURED))
    current = frm(neg(A), obs("m", MODEL))
    expired = frm(neg(A), obs("m", MODEL, (S.Until, 5)))
    snapshots = {
        "current": [measured, current],
        "expired": [measured, expired],
        "withdrawn": [measured, current, (S.Withdrawn, current, stated((S.Moved, "domain")))],
    }
    answers = {name: rows_answer(rows) for name, rows in snapshots.items()}
    for answer in answers.values():
        labels, links = labels_by_argument(answer), link_states(answer)
        assert labels[claim(A)] == ("Accepted", "Checked")
        assert (labels[row(measured)], links[row(measured)]) == (("Accepted", "Checked"), "Holds")
    current_answer = answers["current"]
    assert (labels_by_argument(current_answer)[row(current)], link_states(current_answer)[row(current)]) == (
        ("Refuted", "Unchecked"),
        "Holds",
    )
    assert link_states(answers["expired"])[row(expired)] == "Withdrawn"
    assert link_states(answers["withdrawn"])[row(current)] == "Withdrawn"


# Contrary readings of one tier stay conflicted: both claims and both rows undecided, both rows
# current, with no reading preferred. A row's check is its own provenance, so a measured row is
# checked while its claim is not.
# am[verifies a-jk-rr-row-report-1018@6747d2] am[verifies a-jk-contract-literal-rows-1018@5a7264]
def test_same_tier_contraries_leave_both_rows_current_and_undecided() -> None:
    for estimator in (MODEL, MEASURED):
        rows = [frm(A, obs("p", estimator)), frm(neg(A), obs("q", estimator))]
        answer = rows_answer(rows)
        labels, links = labels_by_argument(answer), link_states(answer)
        assert [labels[claim(A)], labels[claim(neg(A))]] == [("Undecided", "Unchecked")] * 2
        row_check = "Checked" if estimator == MEASURED else "Unchecked"
        assert [labels[row(rows[0])], labels[row(rows[1])]] == [("Undecided", row_check)] * 2
        assert [links[row(rows[0])], links[row(rows[1])]] == ["Holds", "Holds"]


# A claim is accepted exactly when one of its rows grounds it, the row's own Label Accepted and its
# Link holding: the test evidence's plan report and relevance's projection both read.
# am[verifies a-jk-rr-row-report-1018@6747d2]
@SETTINGS
@given(snapshots())
def test_a_claim_is_accepted_exactly_when_one_of_its_rows_grounds_it(rows) -> None:
    answer = rows_answer(rows)
    labels, links = labels_by_argument(answer), link_states(answer)
    froms = [row for row in rows if row[0] == S.From]
    for literal in {r[1] for r in froms}:
        grounded = any(labels[row(r)][0] == "Accepted" and links[row(r)] == "Holds" for r in froms if r[1] == literal)
        assert (labels[claim(literal)][0] == "Accepted") == grounded, literal


# An undercut that protects its own reason, and two undercuts protecting each other, are cycles
# through negation: AgenticMind's stable models answer two models there, and the kernel leaves them
# undecided rather than choosing one (c-jk-dynamic-link-models-1018).
# am[verifies a-jk-semantics-1018@8cb82d]
def test_self_and_mutually_protecting_undercuts_stay_undecided() -> None:
    selfish = (S.Frame, ("a", "u"), (), ((S.Attack, "k", "a", "u"),), ((S.Undercut, "k", "u"),), ())
    answer = jk.justify_frame(atom(selfish), budget=budget())
    assert labels_by_argument(answer)["u"] == ("Undecided", "Unchecked")
    assert link_states(answer)["k"] == "Undecided"
    mutual = (
        S.Frame,
        ("a", "b", "u", "v"),
        (),
        ((S.Attack, "au", "a", "u"), (S.Attack, "bv", "b", "v")),
        ((S.Undercut, "bv", "u"), (S.Undercut, "au", "v")),
        (),
    )
    statuses = {label.argument: label.status for label in jk.justify_frame(atom(mutual), budget=budget()).labels}
    assert statuses == {"a": "Accepted", "b": "Accepted", "u": "Undecided", "v": "Undecided"}


# A conflict over a chained claim stays with the inference: the supporting claim is untouched.
# am[verifies a-jk-contract-literal-rows-1018@5a7264]
def test_a_conflict_over_a_chain_leaves_the_supporting_claim_alone() -> None:
    labels = labels_by_argument(rows_answer([frm(D, obs("m1", MODEL)), frm(C, claim(D)), frm(neg(C), obs("m2", MODEL))]))
    assert labels[claim(D)] == ("Accepted", "Unchecked")
    assert labels[claim(C)] == ("Undecided", "Unchecked")


# Contested grounds and lost grounds differ: undecided support leaves the claim Undecided, while
# grounds that are gone leave it Unsupported (c-jk-contested-not-lost-1018).
# am[verifies a-jk-semantics-1018@8cb82d]
def test_contested_grounds_are_not_lost_grounds() -> None:
    contested = (
        S.Frame,
        ("x", "y", "c"),
        ((S.Support, "xc", "x", "c"),),
        ((S.Attack, "xy", "x", "y"), (S.Attack, "yx", "y", "x")),
        (),
        (),
    )
    assert labels_by_argument(jk.justify_frame(atom(contested), budget=budget()))["c"] == ("Undecided", "Unchecked")
    lost = (S.Frame, ("x", "z", "c"), ((S.Support, "xc", "x", "c"),), ((S.Attack, "zx", "z", "x"),), (), ())
    assert labels_by_argument(jk.justify_frame(atom(lost), budget=budget()))["c"] == ("Unsupported", "Unchecked")


# --- knowledge ----------------------------------------------------------------------------------


# am[implements a-jk-tests-1018@7f8ba3]
def known(literal, rows) -> jk.Knowledge:
    return jk.knowledge(atom(literal), rows_answer(rows), budget=budget())


# Known False comes only from the contrary literal's own Accepted label, with its check: an
# unchecked contrary is unchecked, a withdrawn sole support is Unknown even when the withdrawal's
# reason is established, and only establishing evidence for (Not L) is checked
# (c-jk-known-false-only-contrary-1018, the parent's regressions of 01:56).
# am[verifies a-jk-knowledge-witness-1018@861c8d]
def test_known_false_comes_only_from_an_accepted_contrary() -> None:
    assert known(A, [frm(neg(A), obs("m", MODEL))]) == jk.Knowledge(False, "Unchecked")
    reading_row = frm(A, obs("m", MODEL))
    stale = (S.Stale, "m")
    undercut = [reading_row, frm(stale, obs("e", MEASURED)), (S.Withdrawn, reading_row, claim(stale))]
    assert known(A, undercut) == jk.Knowledge(None, None)
    assert known(A, [reading_row, frm(neg(A), obs("e", MEASURED))]) == jk.Knowledge(False, "Checked")


# Silence is Unknown, a conflict is Unknown, and a checked reading is Known True and Checked.
# am[verifies a-jk-knowledge-witness-1018@861c8d]
def test_knowledge_of_silence_conflict_and_checked_reading() -> None:
    assert known(B, [frm(A, obs("m", MODEL))]) == jk.Knowledge(None, None)
    assert known(A, [frm(A, obs("m1", MODEL)), frm(neg(A), obs("m2", MODEL))]) == jk.Knowledge(None, None)
    assert known(A, [frm(A, obs("e", "deterministic"))]) == jk.Knowledge(True, "Checked")
    assert known(neg(A), [frm(A, obs("e", "deterministic"))]) == jk.Knowledge(False, "Checked")


# Knowledge reads only (Claim L) labels: a stated reason, an observation or a row spelled L is
# Unknown, whatever its own label (c-jk-audit-knowledge-category-1018).
# am[verifies a-jk-typed-boundary-1018@dee690]
def test_knowledge_reads_only_claims() -> None:
    reading_row = frm(A, obs("m", MODEL))
    rows = [reading_row, (S.Withdrawn, reading_row, stated((S.Moved, "x")))]
    for term in ((S.Moved, "x"), reading("m", MODEL), reading_row):
        assert known(term, rows) == jk.Knowledge(None, None), term


# Knowledge answers what the reference's rule does for every term of a snapshot: its claims and
# their contraries, and the terms of its stated reasons, observations and rows.
# am[verifies a-jk-typed-boundary-1018@dee690] am[verifies a-jk-knowledge-witness-1018@861c8d]
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(snapshots())
def test_knowledge_matches_the_reference(rows) -> None:
    labels, links = ref.justify(AT, rows)
    answer = rows_answer(rows)
    for term in sorted({label[1][1] for label in labels} | set(LITERALS) | {neg(literal) for literal in LITERALS}, key=str):
        got = jk.knowledge(atom(term), answer, budget=budget())
        assert (got.value, got.check) == ref.knowledge(term, labels), term


# Spellings to rename literals into: the kernel's own bookkeeping, its answer's shape, and terms the
# generated snapshots use in other roles, an observation, a stated reason and a row.
POOL = [
    (S.Expired, AT), (S.Expired, 5), (S.Stale, AT), (S.Claim, (S.Signal, "x")), (S.Row, (S.Signal, "x")),
    (S.Observation, (S.Signal, "x")), (S.Stated, (S.Signal, "x")), (S.Infers, (S.Signal, "x")), (S.Premise, (S.Signal, "x")),
    (S.Rebut, (S.Signal, "x"), (S.Signal, "y")), (S.Refute, (S.Signal, "x")), (S.Record, (S.Signal, "x")),
    (S.Undercut, (S.Signal, "x"), (S.Signal, "y")), (S.Label, (S.Signal, "x"), S.Accepted, S.Checked),
    (S.Link, (S.Signal, "x"), S.Holds), (S.Known, (S.Signal, "x")), S.Unknown,
    reading("o0", "measured"), (S.Moved, "domain"), frm((S.Signal, "x"), obs("o0", "measured")),
]


# A term with every literal in `names` replaced by its new spelling.
# am[implements a-jk-tests-1018@7f8ba3]
def renamed(term, names: dict):
    if term in names:
        return names[term]
    return tuple(renamed(child, names) for child in term) if isinstance(term, tuple) else term


# Every literal a snapshot's answer depends on, each claim with its contrary, and the literals the
# property asks knowledge about.
# am[implements a-jk-tests-1018@7f8ba3]
def literal_terms(rows) -> set:
    froms = [row for row in rows if row[0] == S.From] + [row[1] for row in rows if row[0] == S.Withdrawn]
    claims = {row[1] for row in froms} | set(CLAIMS)
    return claims | {ref.contrary(term) for term in claims}


# A respelling of LITERALS from the pool, in the pool's order, that is injective on `terms` and
# commutes with contrary, which is the property's premise: a spelling that would merge two literals,
# such as an observation's term that a claim of the snapshot already has, is skipped.
# Time: at most l * p * 3t renamings, l = len(LITERALS), p = len(pool), t = len(terms).
# am[implements a-jk-tests-1018@7f8ba3]
def injective_names(terms: set, pool) -> dict:
    names: dict = {}
    for literal in LITERALS:
        for spelling in pool:
            trial = {**names, literal: spelling}
            if spelling not in names.values() and len({renamed(term, trial) for term in terms}) == len(terms) and all(
                renamed(ref.contrary(term), trial) == ref.contrary(renamed(term, trial)) for term in terms
            ):
                names = trial
                break
    assert len(names) == len(LITERALS), names
    return names


# The two cases mestowsl found at ba93fe7: the pool offers C the spelling (Obs o0 measured Forever),
# which a claim of the snapshot already has, so taking it would merge two literals.
# am[implements a-jk-tests-1018@7f8ba3]
MERGING_POOL = [POOL[0], POOL[1], POOL[17], *POOL[3:17], POOL[2], *POOL[18:]]
MERGES_CONTRARY = [frm(reading("o0", MEASURED), obs("o0", MEASURED)), frm(neg(C), obs("o0", MEASURED)), frm(A, obs("o0", MEASURED))]
MERGES_QUERY = [frm(reading("o0", MEASURED), obs("o0", MEASURED)), frm(A, obs("o0", MEASURED)), frm(A, obs("o0", MEASURED))]


# Respelling a snapshot's literals, injectively, as the kernel's own bookkeeping, its answer's shape
# or a term another argument of the snapshot uses respells the answer and changes nothing else, in
# the kernel and in the reference alike, knowledge included: a literal's role is never its spelling.
# A spelling one of the snapshot's literals already has would merge two literals, which is no
# respelling, so injective_names skips it.
# am[verifies a-jk-id-invariance-tests-1018@c46c89] am[verifies a-jk-id-tagged-1018@d1757d]
# am[verifies a-integrate-jk-categorical-boundary-1018@254af6]
@SETTINGS
@given(snapshots(), st.permutations(POOL))
@example(rows=MERGES_CONTRARY, pool=MERGING_POOL)
@example(rows=MERGES_QUERY, pool=MERGING_POOL)
def test_answers_do_not_depend_on_how_literals_are_spelled(rows, pool) -> None:
    names = injective_names(literal_terms(rows), pool)
    spelled = [renamed(row, names) for row in rows]
    labels, links = ref.justify(AT, rows)
    want = {renamed(entry, names) for entry in labels | links}
    spelled_labels, spelled_links = ref.justify(AT, spelled)
    assert spelled_labels | spelled_links == want
    original, respelled = rows_answer(rows), rows_answer(spelled)
    assert answer_of(respelled) == want
    for literal in LITERALS + [neg(literal) for literal in LITERALS]:
        assert jk.knowledge(atom(renamed(literal, names)), respelled, budget=budget()) == jk.knowledge(
            atom(literal), original, budget=budget()
        ), literal


# --- boundaries -----------------------------------------------------------------------------------


# A claim whose head names a loaded function arrives and leaves as data, never evaluated
# (c-jk-atom-entry-inert-1018): gc-reading-expired is loaded beside the kernel.
# am[verifies a-jk-metta-kernel-1018@258f74]
def test_claim_terms_are_never_evaluated() -> None:
    statement = (S.Statement, (S["gc-reading-expired"], 0, S.Forever))
    labels = labels_by_argument(rows_answer([frm(statement, obs("e", MEASURED))]))
    assert labels[claim(statement)] == ("Accepted", "Checked")


# The reference model's estimator classes, establishing cut and ranks are the shared vocabulary's,
# read from the copy the kernel's own group loaded, so the two cannot drift apart: the same
# classes, the same establishing ones, and the same order of tiers, a row whose source is a claim
# ranking lowest. The vocabulary's entries are untyped, so they are run in the group's space
# directly rather than through evaluate.
# am[verifies a-jk-rr-kernel-shared-1018@0d101b] am[verifies a-rt-rb-migrate-justification-1018@439e90]
def test_the_reference_vocabulary_is_the_shared_modules() -> None:
    prepare(jk.JUSTIFICATION, budget=budget())
    with metta_engine(None) as engine:
        space = engine.space(jk.JUSTIFICATION.space)

        def ask(source, **holes):
            return plain_value(run_bounded(space, source, budget=budget(), **holes)[0][0][0])

        classes = ask("!(gc-estimator-classes)")
        tiers = {c: ask("!(gc-estimator-tier {c})", c=c) for c in classes}
        establishing = {c for c in classes if ask("!(gc-establishes {c})", c=c) is True}
    assert set(classes) == set(ref.ESTIMATORS)
    assert establishing == set(ref.ESTABLISHING)
    rank = {c: 1 if c in ref.ESTABLISHING else 0 for c in classes}
    assert all((tiers[a] >= tiers[b]) == (rank[a] >= rank[b]) for a in classes for b in classes)


# A malformed snapshot is refused whole, naming the problem, before anything is labelled: a source
# or reason without its category, or a reference to nothing in the snapshot, included.
# am[verifies a-jk-contract-literal-rows-1018@5a7264] am[verifies a-jk-typed-boundary-1018@dee690]
@pytest.mark.parametrize(
    ("rows", "kind"),
    [
        ([(S.Nonsense, A)], "MalformedRow"),
        ([frm(A, obs("m", "guessed"))], "MalformedSource"),
        ([frm(A, (S.Observation, (S.Obs, "m", MODEL)))], "MalformedSource"),
        ([frm(A, obs("m", MODEL, (S.Until, "soon")))], "MalformedSource"),
        ([frm(A, reading("m", MODEL))], "MalformedSource"),
        ([frm(A, (S.Signal, "uncategorised"))], "MalformedSource"),
        ([frm(A, row(frm(B, obs("m", MODEL))))], "MalformedSource"),
        ([frm(A, claim((S.Signal, "unclaimed")))], "DanglingClaim"),
        ([frm(neg(neg(A)), obs("m", MODEL))], "DoubleNegation"),
        ([(S.Withdrawn, frm(A, obs("m", MODEL)), stated((S.Moved, "x")))], "DanglingWithdrawal"),
        ([(S.Withdrawn, A, stated((S.Moved, "x")))], "MalformedRow"),
        ([frm((S.Signal, V.x), obs("m", MODEL))], "NonGround"),
        ([frm(A, obs("m", MODEL)), (S.Withdrawn, frm(A, obs("m", MODEL)), (S.Moved, "x"))], "MalformedReason"),
        ([frm(A, obs("m", MODEL)), (S.Withdrawn, frm(A, obs("m", MODEL)), row((S.Signal, "x")))], "MalformedReason"),
        ([frm(A, obs("m", MODEL)), (S.Withdrawn, frm(A, obs("m", MODEL)), claim(B))], "DanglingClaim"),
        ([frm(A, obs("m", MODEL)), (S.Withdrawn, frm(A, obs("m", MODEL)), row(frm(B, obs("m", MODEL))))], "DanglingRow"),
    ],
)
def test_malformed_rows_are_refused(rows, kind) -> None:
    with pytest.raises(jk.JustificationRefused) as refused:
        rows_answer(rows)
    assert refused.value.code == "invalid_input"
    assert {str(problem[1]) for problem in refused.value.problems} == {kind}
    assert refused.value.details["problems"][0].startswith(f"(Problem {kind}")


# A snapshot time that is not a number is refused like a malformed row.
# am[verifies a-jk-contract-literal-rows-1018@5a7264]
@pytest.mark.parametrize("at", ["10", True])
def test_a_malformed_time_is_refused(at) -> None:
    with pytest.raises(jk.JustificationRefused) as refused:
        rows_answer([frm(A, obs("m", MODEL))], at=at)
    assert str(refused.value.problems[0][1]) == "MalformedTime"


# A malformed abstract frame is refused, naming the problem.
# am[verifies a-jk-semantics-1018@8cb82d]
@pytest.mark.parametrize(
    ("frame", "kind"),
    [
        ((S.Frame, ("p",), (), ()), "MalformedFrame"),
        ((S.Frame, ("p",), ((S.Support, "s", "p"),), (), (), ()), "MalformedLink"),
        ((S.Frame, ("p",), ((S.Support, "s", "p", "q"),), (), (), ()), "DanglingLink"),
        ((S.Frame, ("p", "q"), ((S.Support, "k", "p", "q"),), ((S.Attack, "k", "q", "p"),), (), ()), "RepeatedLink"),
        ((S.Frame, ("p",), (), (), ((S.Undercut, "k", "p"),), ()), "DanglingUndercut"),
        ((S.Frame, ("p",), (), (), (), ("q",)), "UndeclaredEstablished"),
        ((S.Frame, (V.p,), (), (), (), ()), "NonGround"),
    ],
)
def test_malformed_frames_are_refused(frame, kind) -> None:
    with pytest.raises(jk.JustificationRefused) as refused:
        jk.justify_frame(atom(frame), budget=budget())
    assert [str(problem[1]) for problem in refused.value.problems] == [kind]


# A frame's arguments are a set: one listed twice is one argument with one label, as a repeated
# row is one row.
# am[verifies a-jk-semantics-1018@8cb82d]
def test_a_repeated_frame_argument_is_labelled_once() -> None:
    frame = (S.Frame, ("p", "q", "p"), (), ((S.Attack, "k", "q", "p"),), (), ())
    labels = jk.justify_frame(atom(frame), budget=budget()).labels
    assert sorted((label.argument, label.status) for label in labels) == [("p", "Refuted"), ("q", "Accepted")]


# An atom's text with each variable named by its order of first occurrence, since every read of a
# space names a stored atom's variables afresh: (= (gc-count $_532 $_533) ...) read again is
# (= (gc-count $_3 $_4) ...).
# Time: linear in the atom's size.
# am[verifies a-rt-rb-migrate-justification-1018@439e90] am[rests-on c-jk-ev-space-reads-rename-variables-1018@97fa75]
def up_to_renaming(term) -> str:
    names: dict[str, str] = {}

    def walk(part) -> str:
        if isinstance(part, Expression):
            return "(" + " ".join(walk(child) for child in part.children) + ")"
        if isinstance(part, Variable):
            return names.setdefault(str(part), f"$v{len(names)}")
        return str(part)

    return walk(term)


# Evaluation is query-local: after a snapshot, a frame and a knowledge query, the kernel's group
# space holds exactly the atoms it held before, up to the names of their variables.
# am[verifies a-jk-metta-kernel-1018@258f74] am[verifies a-rt-rb-migrate-justification-1018@439e90]
def test_evaluation_leaves_the_group_space_unchanged() -> None:
    prepare(jk.JUSTIFICATION, budget=budget())

    def held():
        with metta_engine(None) as engine:
            return sorted(up_to_renaming(atom) for atom in engine.space(jk.JUSTIFICATION.space).atoms())

    before = held()
    answer = rows_answer([frm(A, obs("m1", MODEL)), frm(neg(A), obs("e", MEASURED)), (S.Withdrawn, frm(A, obs("m1", MODEL)), stated((S.Moved, "x")))])
    jk.justify_frame(atom((S.Frame, ("p", "q"), (), ((S.Attack, "k", "q", "p"),), (), ())), budget=budget())
    jk.knowledge(atom(A), answer, budget=budget())
    assert held() == before


# Every call runs under its caller's RunBudget, never unbounded: a call without one is refused
# before the kernel is reached, even once the group is prepared.
# am[verifies a-rt-rb-migrate-justification-1018@439e90] am[verifies a-rt-run-budget-1016@e046b0]
def test_every_call_requires_its_callers_budget() -> None:
    answer = rows_answer([frm(A, obs("m", MODEL))])
    calls = {
        "justify": lambda b: jk.justify([atom(frm(A, obs("m", MODEL)))], at=AT, budget=b),
        "justify_frame": lambda b: jk.justify_frame(atom((S.Frame, ("p",), (), (), (), ())), budget=b),
        "knowledge": lambda b: jk.knowledge(atom(A), answer, budget=b),
    }
    for name, call in calls.items():
        with pytest.raises(InvalidInputError, match="caller's RunBudget"):
            call(None)
        assert call(budget()) is not None, name


# A kernel answering a call more than once is refused, never read: every entry goes through the
# evaluator's one-answer check, here against a stand-in group whose gc-justify answers twice.
# am[verifies a-rt-rb-migrate-justification-1018@439e90] am[verifies a-jk-metta-kernel-1018@258f74]
def test_a_kernel_answering_twice_is_a_protocol_error(tmp_path, monkeypatch) -> None:
    module = tmp_path / "justification_twice.metta"
    module.write_text(
        "(: gc-justify (-> Atom Atom Expression))\n"
        "(= (gc-justify $at $rows) (Justification))\n"
        "(= (gc-justify $at $rows) (Justification (Label (Claim (Signal \"a\")) Accepted Checked)))\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(jk, "JUSTIFICATION", ModuleGroup(f"test-justification-twice-{tmp_path.name}", (module,)))
    with pytest.raises(ProtocolError, match="answered 2 results where one was required"):
        rows_answer([frm(A, obs("m", MODEL))])


# --- answers out of contract, injected ------------------------------------------------------------


# Inside the block every evaluate the wrapper calls answers `answer`, so the wrapper's reading of an
# answer is tested on its own, through the public calls, whatever the kernel itself would answer.
# am[verifies a-integrate-justification-result-refusal-1018@9a83ce]
@contextmanager
def answering(answer):
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(jk, "evaluate", lambda *arguments, **options: answer)
        yield


# The two public calls that read a (Justification ...) answer, each given inputs the injected answer
# ignores.
# am[verifies a-integrate-justification-result-refusal-1018@9a83ce]
READERS = {
    "justify": lambda: jk.justify([atom(frm(A, obs("m", MODEL)))], at=AT, budget=budget()),
    "justify_frame": lambda: jk.justify_frame(atom((S.Frame, (), (), (), (), ())), budget=budget()),
}
# The type of each value after a row's term, as the kernel's header declares its rows:
# (Label ARG STATUS CHECK) and (Link LINK STATE).
DECLARED = {"Label": (jk.Status, jk.Check), "Link": (jk.State,)}
SYMBOL_NAMES = st.from_regex(r"[A-Za-z][A-Za-z0-9-]{0,6}", fullmatch=True)
# Any term a caller may name an argument or a link by: Strings, numbers, symbols and expressions of
# them, the empty expression included.
TERMS = st.recursive(
    st.one_of(st.text(st.characters(blacklist_categories=("Cs",)), max_size=4), st.integers(-3, 3),
              SYMBOL_NAMES.map(lambda name: S[name])),
    lambda parts: st.lists(parts, max_size=3).map(lambda children: Expression(*children)),
    max_leaves=6,
)
# One well-formed row as (KIND, TERM, VALUE ...), each VALUE the name of a value its type declares.
ROWS = st.one_of(*(st.tuples(st.just(kind), TERMS, *(st.sampled_from(get_args(literal)) for literal in literals))
                   for kind, literals in DECLARED.items()))


# The answer (Justification ROW ...) of rows whose values are already atoms or Strings.
# am[verifies a-integrate-justification-result-refusal-1018@9a83ce]
def injected(rows) -> Expression:
    return Expression(S.Justification, *(Expression(S[kind], term, *values) for kind, term, *values in rows))


# Rows from ROWS with each value's name as its symbol.
# am[verifies a-integrate-justification-result-refusal-1018@9a83ce]
def as_symbols(rows) -> list:
    return [(kind, term, *(S[value] for value in values)) for kind, term, *values in rows]


# An answer outside the grammar the kernel's entries declare is a ProtocolError through each public
# call that reads one, never a record built from it or another exception: an answer of another head,
# a row that is no expression or of an unknown or String-spelled kind or another arity, a value its
# Literal does not name or spelled as a String, a valid row beside an invalid one, and a refusal
# naming no well-formed problem. The first five are the parent's probe at cbf9c63.
# am[verifies a-integrate-justification-result-refusal-1018@9a83ce]
@pytest.mark.parametrize("text", [
    "(Justification Broken)",
    "(Justification ())",
    "(Justification (Label (Claim x) Broken Checked))",
    "(Justification (Label (Claim x) Accepted Broken))",
    "(Justification (Link (Row x) Broken))",
    "Broken",
    "5",
    "()",
    "(Answer (Label (Claim x) Accepted Checked))",
    '("Justification" (Label (Claim x) Accepted Checked))',
    "(Justification (Label (Claim x) Accepted))",
    "(Justification (Label (Claim x) Accepted Checked Checked))",
    "(Justification (Link (Row x)))",
    "(Justification (Link (Row x) Holds Holds))",
    '(Justification (Label (Claim x) "Accepted" Checked))',
    '(Justification ("Label" (Claim x) Accepted Checked))',
    "(Justification (Link (Row x) Accepted))",
    "(Justification (Label (Claim x) Holds Checked))",
    "(Justification (Proof (Claim x) Accepted Checked))",
    "(Justification (Label (Claim x) Accepted Checked) Broken)",
    "(Refused)",
    "(Refused Broken)",
    "(Refused (Problem MalformedRow))",
    '(Refused (Problem "MalformedRow" x))',
    "(Refused (Issue MalformedRow x))",
])
@pytest.mark.parametrize("reader", sorted(READERS))
def test_an_answer_outside_the_grammar_is_a_protocol_error(text, reader) -> None:
    with answering(parse(text)), pytest.raises(ProtocolError):
        READERS[reader]()


# A well-formed refusal is still the caller's JustificationRefused, each problem as the kernel gave it.
# am[verifies a-integrate-justification-result-refusal-1018@9a83ce] am[verifies a-jk-metta-kernel-1018@258f74]
@pytest.mark.parametrize("reader", sorted(READERS))
def test_a_well_formed_refusal_stays_justification_refused(reader) -> None:
    text = '(Refused (Problem MalformedRow (Nonsense x)) (Problem DanglingClaim (Claim (Signal "b"))))'
    with answering(parse(text)), pytest.raises(jk.JustificationRefused) as refused:
        READERS[reader]()
    assert [str(problem[1]) for problem in refused.value.problems] == ["MalformedRow", "DanglingClaim"]
    assert refused.value.details["problems"] == ["(Problem MalformedRow (Nonsense x))",
                                                 '(Problem DanglingClaim (Claim (Signal "b")))']


# Every answer in the grammar reads as the records it names, in order, no row at all included: each
# value its type declares, and any term as an argument or a link, which passes through as it stands,
# so a frame's own names and a snapshot's references alike survive; the answer itself is the term.
# am[verifies a-integrate-justification-result-refusal-1018@9a83ce]
@SETTINGS
@given(st.lists(ROWS, max_size=6), st.sampled_from(sorted(READERS)))
@example(rows=[], reader="justify_frame")
def test_every_answer_in_the_grammar_reads_as_its_records(rows, reader) -> None:
    answer = injected(as_symbols(rows))
    with answering(answer):
        read = READERS[reader]()
    assert read.labels == tuple(jk.Label(plain_value(term), *values) for kind, term, *values in rows if kind == "Label")
    assert read.links == tuple(jk.Link(plain_value(term), *values) for kind, term, *values in rows if kind == "Link")
    assert read.term is answer


# Changing any one value of a well-formed answer to a symbol its type does not name, or to the name
# of one of its own values spelled as a String, makes the whole answer a ProtocolError.
# am[verifies a-integrate-justification-result-refusal-1018@9a83ce]
@SETTINGS
@given(st.lists(ROWS, min_size=1, max_size=6), st.sampled_from(sorted(READERS)), st.data())
def test_a_value_its_type_does_not_name_is_a_protocol_error(rows, reader, data) -> None:
    built = as_symbols(rows)
    index = data.draw(st.integers(0, len(built) - 1))
    kind, term, *values = built[index]
    position = data.draw(st.integers(0, len(values) - 1))
    names = get_args(DECLARED[kind][position])
    values[position] = data.draw(st.one_of(SYMBOL_NAMES.filter(lambda name: name not in names).map(lambda name: S[name]),
                                           st.sampled_from(names)))
    built[index] = (kind, term, *values)
    with answering(injected(built)), pytest.raises(ProtocolError):
        READERS[reader]()


# A knowledge answer outside Unknown and (Known BOOL CHECK) is a ProtocolError, never a Knowledge:
# a check its type does not name or spelled as a String, a value that is no bool, another arity or
# head, Unknown as an expression or a String, and a Justification answer. The first is the parent's
# probe at cbf9c63.
# am[verifies a-integrate-justification-result-refusal-1018@9a83ce]
@pytest.mark.parametrize("text", [
    "(Known True Broken)",
    '(Known True "Checked")',
    "(Known 1 Checked)",
    '(Known "True" Checked)',
    "(Known Maybe Checked)",
    "(Known True)",
    "(Known True Checked Checked)",
    "(Knows True Checked)",
    "Known",
    "(Unknown)",
    '"Unknown"',
    "(Justification)",
])
def test_a_knowledge_answer_outside_the_grammar_is_a_protocol_error(text) -> None:
    with answering(parse(text)), pytest.raises(ProtocolError):
        jk.knowledge(atom(A), jk.Justification((), (), parse("(Justification)")), budget=budget())


# Unknown and each (Known BOOL CHECK) the grammar admits read as their Knowledge.
# am[verifies a-integrate-justification-result-refusal-1018@9a83ce] am[verifies a-jk-knowledge-witness-1018@861c8d]
@pytest.mark.parametrize(("text", "want"), [
    ("Unknown", jk.Knowledge(None, None)),
    *((f"(Known {value} {check})", jk.Knowledge(value, check)) for value in (True, False) for check in get_args(jk.Check)),
])
def test_a_knowledge_answer_in_the_grammar_reads_as_its_knowledge(text, want) -> None:
    with answering(parse(text)):
        assert jk.knowledge(atom(A), jk.Justification((), (), parse("(Justification)")), budget=budget()) == want


# A budget too small for the snapshot stops it with the typed bound, and the spend is charged; a
# deadline already passed is a typed timeout.
# am[verifies a-jk-metta-kernel-1018@258f74] am[verifies a-rt-run-budget-1016@e046b0]
def test_budget_exhaustion_is_typed_and_charged() -> None:
    prepare(jk.JUSTIFICATION, budget=budget())
    rng = random.Random(1018)
    rows = [frm(rng.choice(CLAIMS), obs(f"o{i}", rng.choice(ref.ESTIMATORS))) for i in range(12)]
    small = RunBudget(inference_budget=1000, timeout_seconds=120.0)
    with pytest.raises(InferenceBudgetExceeded):
        jk.justify([atom(row) for row in rows], at=AT, budget=small)
    assert small.spent > 0
    with pytest.raises(ReviewTimeout):
        jk.justify([atom(row) for row in rows], at=AT, budget=RunBudget(inference_budget=None, timeout_seconds=1e-9))
    enough = budget()
    rows_answer(rows)
    jk.justify([atom(row) for row in rows], at=AT, budget=enough)
    assert enough.spent > 0


# Preparing the kernel's group answers its identity, the same on every call in a process.
# am[verifies a-jk-placement-1018@a9cf03] am[verifies a-rt-rb-migrate-justification-1018@439e90]
def test_preparing_the_group_answers_a_stable_identity() -> None:
    identity = prepare(jk.JUSTIFICATION, budget=budget())
    assert identity.startswith("sha256:") and len(identity) == len("sha256:") + 64
    assert prepare(jk.JUSTIFICATION, budget=budget()) == identity
