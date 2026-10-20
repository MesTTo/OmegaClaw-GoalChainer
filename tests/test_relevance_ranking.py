"""Purpose: check the MeTTa ranking policy's section 9.3 sequence, dispositions, authority ceilings and invariance properties without a theory run."""

from __future__ import annotations

import itertools
import math
from fractions import Fraction
from importlib import resources

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from goal_chainer.domains.loader import PACKAGED_DOMAIN_DIRECTORY, read_domain, vocabulary
from goal_chainer.runtime.engine import metta_engine
from goal_chainer.relevance.errors import RelevanceError
from goal_chainer.relevance.policy import constant, evaluate, items, symbol, term, text
from goal_chainer.relevance.ranking import policy_input, rank, read_ranking

from relevance_support import candidate, derived, helper_call, reading, task_control
from request_support import budget as request_budget

DOMAIN = task_control()
ACTIONS = DOMAIN.action_ids
GOALS = DOMAIN.goal_ids
DIMENSIONS = DOMAIN.dimension_ids
SAME = {"governance-cost": ("slightly-negative", "deterministic")}
# Every set of lib_deontic modes an action can be proved to have, from none to all three.
MODE_SETS = ["".join(chosen) for size in range(4) for chosen in itertools.combinations("FOP", size)]


# am[related a-rel-ranking-1016@334372]
def ranked(review):
    """The ranking policy's answer for a hand-built review, under the bounds its packet sets."""

    return rank(review, review.packet.budget.run_budget())


# am[verifies a-rel-ranking-1016@334372]
def test_an_obligation_outranks_a_permitted_action_that_scores_better() -> None:
    duty = candidate(DOMAIN, "pause_recoverably", modes="OP", effects=SAME)
    better = candidate(
        DOMAIN, "continue_task", effects=SAME,
        contributions={"project_outcome": "strongly-positive", "decision_relevant_speed": "strongly-positive"},
    )

    ranking = ranked(derived(DOMAIN, [better, duty]))

    assert ranking.disposition == "propose"
    assert ranking.selected.id == "pause_recoverably"
    assert ranking.decided_at == "deterministic lifecycle"


# The status a review shows is the rule the incident decision and the scorer read, whatever the
# modes and the dilemma, and a candidate escalates as a conflict exactly when that rule says so.
# Exhaustive: eight mode sets, each with and without a dilemma.
# am[verifies a-rel-status-answer-1016@c302a1] am[verifies a-rel-status-conflict-1016@abec85]
@pytest.mark.parametrize("dilemma", [False, True])
@pytest.mark.parametrize("modes", MODE_SETS)
def test_a_candidates_status_is_the_shared_rules_and_only_a_conflict_escalates_as_one(modes, dilemma) -> None:
    alone = candidate(DOMAIN, "handoff", modes=modes, dilemma=dilemma, effects=SAME)

    ranking = ranked(derived(DOMAIN, [alone]))

    shared = symbol(helper_call("gc-deontic-status", items(constant(mode) for mode in modes), dilemma))
    assert ranking.standing == {"handoff": shared}
    assert any(reason.startswith("handoff: ") for reason in ranking.escalation_reasons) == (shared == "conflict")


# In Standard Deontic Logic F p is O not-p, which contradicts P p, so the review escalates rather
# than quietly removing the action as forbidden.
# am[verifies a-rel-status-conflict-1016@abec85]
def test_a_candidate_both_forbidden_and_permitted_escalates_as_a_conflict() -> None:
    clash = candidate(DOMAIN, "handoff", modes="FP", effects=SAME)
    pause = candidate(DOMAIN, "pause_recoverably", modes="P", effects=SAME)

    ranking = ranked(derived(DOMAIN, [clash, pause]))

    assert ranking.standing == {"handoff": "conflict", "pause_recoverably": "permitted"}
    assert ranking.disposition == "escalate"
    assert "handoff: the theory proves it both permitted and forbidden" in ranking.escalation_reasons


# A status the shared rule never answers is unreadable, so a policy edit that broke the rule fails
# the review instead of printing a label nothing defines.
# am[verifies a-rel-status-answer-1016@c302a1]
def test_a_ranking_whose_status_is_not_one_the_rule_answers_is_unreadable() -> None:
    review = derived(DOMAIN, [candidate(DOMAIN, "handoff", modes="P", effects=SAME)])
    answer = evaluate("gc-relevance-rank", policy_input(review), budget=request_budget())
    tampered = (*answer[:-1], (constant("Standing"), ((constant("For"), "handoff", constant("dilemma")),)))

    with pytest.raises(RelevanceError) as raised:
        read_ranking(review, tampered)

    assert raised.value.code == "engine-output-invalid"
    assert read_ranking(review, answer).standing == {"handoff": "permitted"}


# am[verifies a-rel-ranking-1016@334372] am[verifies i-rel-unpermitted-admissible-1016@1d4f81]
def test_a_duty_whose_permission_was_withdrawn_escalates_instead_of_being_proposed() -> None:
    # rStopNeedsGraphQuality withdraws STOP_STALE's permission while rStopObliged still obliges
    # it, which the engine answers as O without P.
    stop = candidate(DOMAIN, "stop_stale", modes="O", effects=SAME)
    carry_on = candidate(DOMAIN, "continue_task", effects=SAME, contributions={"project_outcome": "positive"})

    ranking = ranked(derived(DOMAIN, [stop, carry_on]))

    assert ranking.disposition == "escalate"
    assert ranking.selected is None
    assert any("stop_stale is obliged but has no admissible discharge" in r for r in ranking.escalation_reasons)
    assert ranking.steps[0].eliminated[0].reason == "obliged, but the theory withdrew its permission"


# am[verifies a-rel-ranking-1016@334372]
def test_several_obligations_at_once_escalate() -> None:
    first = candidate(DOMAIN, "stop_stale", modes="OP", effects=SAME)
    second = candidate(DOMAIN, "declare_blocked", modes="OP", effects=SAME)

    ranking = ranked(derived(DOMAIN, [first, second]))

    assert ranking.disposition == "escalate"
    assert any("several obligations" in reason for reason in ranking.escalation_reasons)


# am[verifies a-rel-ranking-1016@334372] am[verifies i-rel-unknown-neutral-1016@7e3679]
def test_an_unestimated_dimension_never_decides_domination() -> None:
    # Reading the missing option-value as neutral would let `quiet` dominate `estimated`:
    # equal everywhere else, and neutral beats slightly-negative. Unknown spans the scale.
    estimated = candidate(
        DOMAIN, "continue_task",
        effects={**SAME, "option-value": ("slightly-negative", "model-proposed")},
        contributions={"project_outcome": "positive"},
    )
    quiet = candidate(DOMAIN, "replan", effects=SAME, contributions={"project_outcome": "positive"})

    ranking = ranked(derived(DOMAIN, [estimated, quiet]))

    assert ranking.steps[2].survivors == ("continue_task", "replan")
    assert ranking.disposition == "escalate"
    assert any("option-value" in reason and "not decisive" in reason for reason in ranking.escalation_reasons)


# am[verifies a-rel-ranking-1016@334372] am[verifies i-rel-motive-escalation-1016@901e1f]
def test_a_local_and_hive_split_stays_visible_without_forcing_escalation() -> None:
    local = candidate(DOMAIN, "escalate", effects=SAME, contributions={"epistemic_integrity": "slightly-positive"})
    hive = candidate(DOMAIN, "pause_recoverably", effects=SAME, contributions={"project_outcome": "strongly-positive"})

    ranking = ranked(derived(DOMAIN, [local, hive]))

    assert ranking.motive_tension == ("escalate", "pause_recoverably")
    assert ranking.disposition == "propose"
    assert ranking.selected.id == "pause_recoverably"
    assert ranking.decided_at == "tie-breaking projection"


# am[verifies a-rel-ranking-1016@334372]
def test_aggregation_rules_that_disagree_escalate() -> None:
    broad = candidate(
        DOMAIN, "continue_task", effects=SAME,
        contributions={"project_outcome": "positive", "commitment_fulfilment": "positive"},
    )
    sharp = candidate(DOMAIN, "accelerate", effects=SAME, contributions={"decision_relevant_speed": "strongly-positive"})

    ranking = ranked(derived(DOMAIN, [broad, sharp]))

    assert ranking.disposition == "escalate"
    assert any("aggregation rules disagree" in reason for reason in ranking.escalation_reasons)
    assert set(ranking.contested) == {"continue_task", "accelerate"}


# am[verifies a-rel-ranking-1016@334372]
def test_harming_a_required_goal_removes_the_candidate_and_an_all_removed_review_is_blocked() -> None:
    harmful = candidate(DOMAIN, "descope", effects=SAME, contributions={"commitment_fulfilment": "slightly-negative"})
    forbidden = candidate(DOMAIN, "handoff", modes="F", effects=SAME)

    ranking = ranked(derived(DOMAIN, [harmful, forbidden], required=("commitment_fulfilment",)))

    assert ranking.disposition == "blocked"
    assert {(b.action, b.reason) for b in ranking.blockers} == {
        ("handoff", "forbidden by the theory"),
        ("descope", "pushes the required goal commitment_fulfilment backwards (slightly-negative)"),
    }


# am[verifies a-rel-ranking-1016@334372]
def test_conflicting_evidence_inside_the_readset_escalates_and_outside_it_does_not() -> None:
    pause = candidate(DOMAIN, "pause_recoverably", modes="P", effects=SAME)
    conflicting = (
        reading("safe_point_reachable", "detected", source="telemetry-a"),
        reading("safe_point_reachable", "refuted", source="telemetry-b"),
    )
    outside = (
        reading("receiving_owner_accepts", "detected", source="seat-a"),
        reading("receiving_owner_accepts", "refuted", source="seat-b"),
    )

    inside_ranking = ranked(derived(DOMAIN, [pause], readings=conflicting))
    outside_ranking = ranked(derived(DOMAIN, [pause], readings=outside))

    assert inside_ranking.disposition == "escalate"
    assert any("evidence about safe_point_reachable conflicts" in r for r in inside_ranking.escalation_reasons)
    assert outside_ranking.disposition == "propose"


# The parent's ruling (c-integrate-reading-owner-rule-1018): the preferred polarity is projected,
# and a live overruled contrary still escalates when the signal can affect the review.
# am[verifies a-rel-rr-p-escalation-1018@86a7bb]
def test_an_overruled_contrary_inside_the_readset_escalates_and_outside_it_does_not() -> None:
    pause = candidate(DOMAIN, "pause_recoverably", modes="P", effects=SAME)
    measured = reading("safe_point_reachable", "detected", "measured", source="telemetry")
    overruled = (measured, reading("safe_point_reachable", "refuted", "model-proposed", source="model"))
    outside = (
        measured,
        reading("receiving_owner_accepts", "detected", "measured", source="seat"),
        reading("receiving_owner_accepts", "refuted", "model-proposed", source="model"),
    )

    alone = ranked(derived(DOMAIN, [pause], readings=(measured,)))
    inside = ranked(derived(DOMAIN, [pause], readings=overruled))
    elsewhere = ranked(derived(DOMAIN, [pause], readings=outside))

    assert inside.disposition == "escalate"
    assert (
        "evidence about safe_point_reachable conflicts: telemetry says detected; model says refuted"
        in inside.escalation_reasons
    )
    assert alone.disposition == elsewhere.disposition == "propose"


# Acceptance grants no authority (c6bd00cd): the ceiling reads only the supporting readings'
# classes. In a domain whose ceiling for receipt-calibrated outranks the one for measured, a
# defeated receipt-calibrated contrary would otherwise lift the ceiling a measurement caps.
# am[verifies a-rel-rr-p-escalation-1018@86a7bb] am[rests-on c6bd00cd@8dffaf]
def test_an_overruled_contrary_never_lifts_the_authority_ceiling() -> None:
    packaged = resources.files("goal_chainer").joinpath(*PACKAGED_DOMAIN_DIRECTORY.split("/"))
    text = (packaged / "task_control.metta").read_text(encoding="utf-8")
    assert text.count("(gc-estimator-ceiling measured preauthorized)") == 1
    domain = read_domain(text.replace("(gc-estimator-ceiling measured preauthorized)",
                                      "(gc-estimator-ceiling measured advisory)"), "measured-capped", budget=request_budget())
    pause = candidate(domain, "pause_recoverably", modes="P", effects=SAME)
    measured = reading("safe_point_reachable", "detected", "measured", source="telemetry")
    calibrated = reading("safe_point_reachable", "refuted", "receipt-calibrated", source="history")

    compiled = derived(domain, [pause], readings=(measured, calibrated))
    appraisal = ranked(compiled).appraisals["pause_recoverably"]

    assert compiled.readings["safe_point_reachable"].contested == (calibrated,)
    assert appraisal.licensed_authority_ceiling == "advisory"
    assert [limit.basis for limit in appraisal.authority_limits] == ["reading:safe_point_reachable"]


# am[verifies a-rel-ranking-1016@334372]
def test_estimators_that_disagree_about_a_survivor_escalate() -> None:
    pause = candidate(
        DOMAIN, "pause_recoverably",
        effects={"recoverability": [("strongly-positive", "deterministic"), ("negative", "model-proposed")]},
    )

    ranking = ranked(derived(DOMAIN, [pause]))

    assert ranking.disposition == "escalate"
    assert any("estimators disagree about pause_recoverably recoverability" in r for r in ranking.escalation_reasons)


# am[verifies a-rel-ranking-1016@334372] am[verifies i-rel-authority-1016@ab7bf8]
def test_a_model_proposed_estimate_caps_a_preauthorized_action_at_advisory() -> None:
    pause = candidate(DOMAIN, "pause_recoverably", effects={"option-value": ("strongly-positive", "model-proposed")})
    measured = candidate(DOMAIN, "pause_recoverably", effects={"option-value": ("strongly-positive", "measured")})
    guessed_reading = (reading("safe_point_reachable", "detected", "model-proposed"),)
    unrelated_guess = (reading("receiving_owner_accepts", "detected", "model-proposed"),)

    capped = ranked(derived(DOMAIN, [pause])).appraisals["pause_recoverably"]
    clean = ranked(derived(DOMAIN, [measured], readings=unrelated_guess)).appraisals["pause_recoverably"]
    by_reading = ranked(derived(DOMAIN, [measured], readings=guessed_reading)).appraisals["pause_recoverably"]

    assert (capped.action_authority_ceiling, capped.licensed_authority_ceiling) == ("preauthorized", "advisory")
    assert [limit.basis for limit in capped.authority_limits] == ["effect:option-value"]
    assert clean.licensed_authority_ceiling == "preauthorized"
    assert [limit.basis for limit in by_reading.authority_limits] == ["reading:safe_point_reachable"]


# --- properties --------------------------------------------------------------------------

bands = st.sampled_from(vocabulary().bands)
estimators = st.sampled_from(vocabulary().classes)


# am[related a-rel-ranking-1016@334372]
@st.composite
def candidates_strategy(draw, min_size: int = 0, max_size: int = 5):
    actions = draw(st.lists(st.sampled_from(ACTIONS), unique=True, min_size=min_size, max_size=max_size))
    return [
        candidate(
            DOMAIN,
            action,
            modes=draw(st.sampled_from(["", "P", "O", "OP", "F", "FP", "OF"])),
            dilemma=draw(st.booleans()),
            effects=draw(st.dictionaries(st.sampled_from(DIMENSIONS), st.tuples(bands, estimators), max_size=4)),
            contributions=draw(st.dictionaries(st.sampled_from(GOALS), bands, max_size=3)),
        )
        for action in actions
    ]


# am[verifies a-rel-ranking-1016@334372]
@settings(max_examples=300, deadline=None)
@given(candidates=candidates_strategy(), required=st.lists(st.sampled_from(GOALS), unique=True, max_size=2))
def test_dispositions_are_total_and_a_proposal_is_always_admissible(candidates, required) -> None:
    ranking = ranked(derived(DOMAIN, candidates, required=tuple(required)))

    assert ranking.disposition in {"propose", "escalate", "blocked", "no-candidates"}
    if ranking.disposition == "propose":
        chosen = ranking.selected
        # Section 9.3 stated independently of the policy: admissible means permitted, not
        # forbidden and in no dilemma; a proposal never pushes a required goal below neutral;
        # and when an admissible action is obliged, the proposal is obliged too.
        assert chosen is not None and "F" not in chosen.modes and "P" in chosen.modes and not chosen.dilemma
        bands = {c.goal: c.band for c in chosen.contributions}
        neutral = vocabulary().bands.index("neutral")
        assert not any(goal in bands and vocabulary().bands.index(bands[goal]) < neutral for goal in required)
        obliged = [c for c in candidates if "O" in c.modes and "P" in c.modes and "F" not in c.modes and not c.dilemma]
        assert not obliged or "O" in chosen.modes
    else:
        assert ranking.selected is None
    if ranking.disposition == "escalate":
        assert ranking.escalation_reasons
    if ranking.disposition == "blocked":
        assert ranking.blockers and not ranking.escalation_reasons
    assert (ranking.disposition == "no-candidates") == (not candidates and not ranking.escalation_reasons)


# am[verifies a-rel-ranking-1016@334372]
@settings(max_examples=200, deadline=None)
@given(candidates=candidates_strategy(min_size=1, max_size=4), extra=candidates_strategy(min_size=1, max_size=1))
def test_adding_a_candidate_changes_no_other_candidates_appraisal(candidates, extra) -> None:
    if extra[0].id in {c.id for c in candidates}:
        return
    alone = ranked(derived(DOMAIN, candidates)).appraisals
    joined = ranked(derived(DOMAIN, candidates + extra)).appraisals

    for c in candidates:
        assert joined[c.id] == alone[c.id]


# am[verifies a-rel-ranking-1016@334372] am[verifies i-rel-authority-1016@ab7bf8]
@settings(max_examples=200, deadline=None)
@given(
    action=st.sampled_from(ACTIONS),
    effects=st.dictionaries(st.sampled_from(DIMENSIONS), st.tuples(bands, estimators), max_size=4),
    observed=st.dictionaries(st.sampled_from(DOMAIN.signal_ids), estimators, max_size=6),
)
def test_the_licensed_ceiling_is_the_lowest_ceiling_of_everything_the_proposal_may_rest_on(action, effects, observed) -> None:
    subject = candidate(DOMAIN, action, effects=effects)
    readings = tuple(reading(signal, "detected", estimator) for signal, estimator in observed.items())

    compiled = derived(DOMAIN, [subject], readings=readings)
    appraisal = ranked(compiled).appraisals[action]

    tiers = {tier.id: tier.rank for tier in DOMAIN.authorities}
    rested_on = [estimator for _, estimator in effects.values()] + [
        estimator for signal, estimator in observed.items() if signal in compiled.candidate(action).readset
    ]
    expected = min(
        [tiers[DOMAIN.action(action).authority]] + [tiers[DOMAIN.ceiling_for(e)] for e in rested_on]
    )
    assert tiers[appraisal.licensed_authority_ceiling] == expected
    assert appraisal.action_authority_ceiling == DOMAIN.action(action).authority


# Each declared aggregation rule folds with the combine of the semiring carrier it names: the
# carrier declares that combine, and pymetta's own tagged-program evaluation under the carrier
# gives the rule's value for any finite signed path values, up to the sign of a zero. An action
# with no path, which the carrier leaves without an answer, is worth 0 by the review's
# convention. The examples always run the empty case and the probe's signed cases, where a
# maximum of -0.2 must stay -0.2 and not rise to that convention's 0.
# am[verifies a-rel-aggregation-rules-1017@b47aa6] am[verifies c-rel-rules-are-carriers-finite-1017@48def8]
@settings(max_examples=60, deadline=None)
@given(values=st.lists(st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_subnormal=False), max_size=6))
@example(values=[])
@example(values=[-0.3, 0.5])
@example(values=[-0.2, -0.6])
def test_each_aggregation_rule_folds_like_the_pymetta_carrier_it_names(values) -> None:
    import metta  # noqa: PLC0415 (pymetta loads with the engine)
    from metta import S, V  # noqa: PLC0415

    rules = helper_call("gc-relevance-rules")
    assert rules
    for rule in rules:
        name, carrier = text(rule[1]), symbol(rule[2])
        assert symbol(rule[3]) == getattr(metta, carrier).combine, (name, carrier)
        folded = helper_call("gc-relevance-fold", term("gc-relevance-rule-named", name), items(values))
        with metta_engine(None) as engine, engine.space() as space:
            for index, value in enumerate(values):
                space.add_tagged_fact(value, S.contrib("a", f"g{index}"))
            space.add_tagged_rule(1.0, S.serves(V.x), S.contrib(V.x, V.g))
            answers = [answer.annotation for answer in space.match(S.serves("a"), under=carrier)]
        if values:
            assert len(answers) == 1 and math.isclose(folded, answers[0], rel_tol=1e-12, abs_tol=1e-12), (name, carrier)
        else:
            assert answers == [] and folded == 0.0, (name, carrier)


# sum-over-paths answers what the policy's gc-relevance-sum does and max-over-parents what the
# engine's max-atom does, bit for bit, on any values: signed zeros, NaN and infinities included,
# which goals of priority 0, NaN or infinity give their paths. Paths all worth -0.0 sum to 0.0.
# am[verifies a-rel-fold-start-1017@1dacc6] am[verifies c-rel-max-atom-is-max-list-1017@be494f]
@settings(max_examples=60, deadline=None)
@given(values=st.lists(st.one_of(st.sampled_from([0.0, -0.0, math.inf, -math.inf, math.nan]), st.floats()),
                       min_size=1, max_size=6))
@example(values=[-0.0])
@example(values=[-0.0, 0.0])
@example(values=[0.0, -0.0])
@example(values=[0.5, math.nan])
@example(values=[math.nan, 0.5])
@example(values=[math.inf, -math.inf])
def test_each_aggregation_rule_answers_the_policys_sum_or_the_engines_max_atom_bit_for_bit(values) -> None:
    for name, reference in {"sum-over-paths": "gc-relevance-sum", "max-over-parents": "max-atom"}.items():
        folded = helper_call("gc-relevance-fold", term("gc-relevance-rule-named", name), items(values))
        assert repr(folded) == repr(helper_call(reference, items(values))), (name, values)


# A path's value is now an interval of any finite priority times a reduction, so the projection's
# midpoint is the correctly rounded mean of any finite ends: a point at 1e308, whose ends' sum
# overflowed, a sign-spanning interval of the largest magnitudes, both halving thresholds and their
# neighbours, and a subnormal point included.
# am[verifies a-v2m-drive-paths-1019@65a7d5] am[verifies c-v2m-midpoint-libcxx-1020@5020e4]
@settings(max_examples=80, deadline=None)
@given(ends=st.lists(st.floats(allow_nan=False, allow_infinity=False), min_size=2, max_size=2))
@example(ends=[1e308, 1e308])
@example(ends=[-1e308, 1e308])
@example(ends=[-1.7976931348623157e308, 1.7976931348623157e308])
@example(ends=[1.7976931348623157e308, 1.7976931348623157e308])
@example(ends=[8.988465674311579e307, 8.988465674311579e307])
@example(ends=[math.nextafter(8.988465674311579e307, math.inf)] * 2)
@example(ends=[4.450147717014403e-308, 1.7976931348623157e308])
@example(ends=[math.nextafter(4.450147717014403e-308, 0.0), 1.7976931348623157e308])
@example(ends=[-1.7976931348623157e308, -5e-324])
@example(ends=[5e-324, 5e-324])
@example(ends=[-0.0, -0.0])
def test_the_midpoint_is_the_correctly_rounded_mean_of_any_finite_interval(ends) -> None:
    low, high = sorted(ends)
    midpoint = helper_call("gc-relevance-midpoint", term("Interval", low, high))
    assert math.isfinite(midpoint) and midpoint == float((Fraction(low) + Fraction(high)) / 2), (low, high, midpoint)
