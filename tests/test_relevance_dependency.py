"""Purpose: check the readset policy's static dependency cones and the readsets it gives every candidate and review."""

from __future__ import annotations

from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from goal_chainer.domains.loader import read_domain
from goal_chainer.domains.model import Pattern, Rule, Signal
from goal_chainer.errors import InvalidInputError
from goal_chainer.runtime.budget import RunBudget
from goal_chainer.relevance import dependency
from goal_chainer.relevance.dependency import dependency_index
from goal_chainer.relevance.errors import RelevanceError

from relevance_support import task_control
from request_support import budget as request_budget

INDEX = dependency_index(task_control(), budget=request_budget())


# am[verifies a-rel-compiler-1016@c69c38] am[rests-on c-rel-cone-sound-1016@092cec]
def test_a_candidacy_cone_holds_exactly_the_preconditions() -> None:
    assert INDEX.candidacy["pause_recoverably"] == {"safe_point_reachable", "state_preservation_route"}
    assert INDEX.candidacy["stop_stale"] == {"stale_parent_goal"}


# am[verifies a-rel-compiler-1016@c69c38] am[rests-on c-rel-cone-sound-1016@092cec]
def test_an_appraisal_cone_includes_defeaters_attackers_and_duty_chains() -> None:
    # rStopNeedsGraphQuality withdraws the stop's permission; rStopObliged reads the active path.
    assert {"low_graph_quality", "active_parent_path", "authority_unavailable"} <= INDEX.appraisal["stop_stale"]
    # rContention's chain obliges escalate when the pause is violated, so the pause's duty and
    # escalate's always-duty read each other's signals.
    assert "judgment_exceeds_evaluator" in INDEX.appraisal["pause_recoverably"]
    assert "safe_point_reachable" in INDEX.appraisal["escalate"]


# am[verifies a-rel-compiler-1016@c69c38]
def test_a_review_readset_drops_what_only_a_non_candidate_appraisal_reads() -> None:
    readsets = INDEX.readsets(["continue_task", "escalate", "pause_recoverably"], budget=request_budget())
    readset = readsets.review

    # Only HANDOFF's contribution reads receiving_owner_accepts, and HANDOFF is no candidate.
    # low_graph_quality stays: it bears on a duty the theory can conclude about STOP_STALE.
    assert set(task_control().signal_ids) - readset == {"receiving_owner_accepts"}
    assert "stale_parent_goal" in readset  # it could make STOP_STALE a candidate
    assert readsets.candidates["pause_recoverably"] == INDEX.candidacy["pause_recoverably"] | INDEX.appraisal["pause_recoverably"]


# am[verifies a-rel-compiler-1016@c69c38] am[rests-on c-rel-cone-sound-1016@092cec]
def test_a_duty_on_an_action_that_is_no_candidate_is_in_every_review_readset() -> None:
    # rEscalateAlways obliges ESCALATE on judgment_exceeds_evaluator whether or not it is a
    # candidate, and an undischarged duty changes the disposition; the engine property test
    # found this when the norms were left out.
    assert "judgment_exceeds_evaluator" in INDEX.readsets([], budget=request_budget()).review


# The task-control domain's cones are cached by now, and a call without a RunBudget is refused all
# the same, as it is in a fresh process where the cones would have to be computed.
# am[verifies a-rel-mig-callers-1018@da2f3e]
def test_a_cached_domain_still_needs_its_callers_budget() -> None:
    assert dependency_index(task_control(), budget=request_budget()) is INDEX

    with pytest.raises(InvalidInputError, match="runs only under its caller's RunBudget"):
        dependency_index(task_control(), budget=None)  # type: ignore[arg-type]


# am[verifies a-rel-compiler-1016@c69c38] am[rests-on c-rel-cone-sound-1016@092cec]
def test_a_signal_concluded_from_another_signal_carries_both() -> None:
    text = """
(gc-domain "chain")
(gc-policy-version chain-v1)
(gc-authority advisory 1 "advise")
(gc-estimator-ceiling measured advisory)
(gc-estimator-ceiling deterministic advisory)
(gc-estimator-ceiling receipt-calibrated advisory)
(gc-estimator-ceiling model-proposed advisory)
(gc-estimator-ceiling human-asserted advisory)
(gc-action act "Act" "do it" (authority advisory))
(gc-goal served owner individual 0.5 "served" (priority-source human:test))
(gc-dimension cost cost "what it costs")
(gc-signal root "observed")
(gc-signal derived "concluded from root")
(normally r1 (signal root) (signal derived))
(normally r2 (signal derived) (candidate act))
"""
    index = dependency_index(read_domain(text, "chain", budget=request_budget()), budget=request_budget())

    assert index.candidacy["act"] == {"root", "derived"}


# --- a differential against an independent statement of the cone rule ---------------------

# The cone rule restated in Python, independently of readset.metta (this is the breadth-first
# search the review used before the policy moved to MeTTa): a query matches a rule head of its
# functor and arity, binding the head's variables consistently; every literal of a matching rule
# is instantiated, its unbound variables made wildcards, and searched in turn.
# am[verifies c-rel-cone-sound-1016@092cec]
def reference_cone(queries, rules, signals) -> frozenset[str]:
    def canonical(pattern):
        return Pattern(pattern.functor, tuple("?" if arg.startswith("?") else arg for arg in pattern.args))

    def match(query, head):
        binding: dict[str, str] = {}
        for wanted, offered in zip(query.args, head.args):
            if offered.startswith("?"):
                if wanted != "?" and binding.setdefault(offered, wanted) != wanted:
                    return None
            elif wanted not in ("?", offered):
                return None
        return binding

    found, seen, queue = set(), set(), [canonical(query) for query in queries]
    while queue:
        pattern = queue.pop(0)
        if pattern in seen:
            continue
        seen.add(pattern)
        if pattern.functor == "signal" and len(pattern.args) == 1:
            found |= set(signals) if pattern.args[0] == "?" else {pattern.args[0]} & set(signals)
        for rule in rules:
            for head in rule.heads:
                if head.functor != pattern.functor or len(head.args) != len(pattern.args):
                    continue
                binding = match(pattern, head)
                if binding is not None:
                    queue.extend(canonical(Pattern(l.functor, tuple(binding.get(a, a) for a in l.args)))
                                 for l in (*rule.body, *rule.heads))
    return frozenset(found)


ARITY = {"signal": 1, "candidate": 1, "do": 1, "required": 1, "linked": 2, "contributes": 3}
TERMS = ["s0", "s1", "s2", "a0", "a1", "g0", "?x", "?y"]


# am[related c-rel-cone-sound-1016@092cec]
@st.composite
def rules_strategy(draw):
    def literal():
        functor = draw(st.sampled_from(sorted(ARITY)))
        return Pattern(functor, tuple(draw(st.sampled_from(TERMS)) for _ in range(ARITY[functor])))

    return tuple(
        Rule(None, "normally", tuple(literal() for _ in range(draw(st.integers(1, 3)))), (literal(),),
             (literal(),) if draw(st.booleans()) else ())
        for _ in range(draw(st.integers(1, 7)))
    )


# am[verifies a-rel-compiler-1016@c69c38] am[verifies a-rel-metta-policy-1016@fdaa20] am[rests-on c-rel-cone-sound-1016@092cec]
@settings(max_examples=60, deadline=None)
@given(rules=rules_strategy())
def test_the_readset_policy_computes_the_same_cones_as_an_independent_search(rules) -> None:
    base = task_control()
    domain = replace(
        base,
        rules=rules,
        signals=tuple(Signal(name, name) for name in ("s0", "s1", "s2")),
        actions=tuple(replace(base.actions[0], id=name) for name in ("a0", "a1")),
    )
    signals = domain.signal_ids
    index = dependency_index(domain, budget=request_budget())

    for action in domain.action_ids:
        assert index.candidacy[action] == reference_cone([Pattern("candidate", (action,))], rules, signals)
        assert index.appraisal[action] == reference_cone(
            [Pattern("do", (action,)), Pattern("contributes", (action, "?", "?")), Pattern("effect", (action, "?", "?", "?"))],
            rules, signals,
        )
    assert index.requirement == reference_cone([Pattern("required", ("?",))], rules, signals)
    assert index.norms == reference_cone([norm for rule in rules for norm in rule.norms], rules, signals)


# A packet's caller may name any domain file, so its cones are review work: charged to the
# request's budget and stopped by either of its bounds, with nothing cached when stopped.
# am[verifies a-rt-run-budget-1016@e046b0] am[verifies c-rel-one-deadline-1016@75de2a]
@pytest.mark.parametrize(
    ("bounds", "code"),
    [({"inference_budget": None, "timeout_seconds": 1e-9}, "review-timeout"),
     ({"inference_budget": 1, "timeout_seconds": 60.0}, "review-budget-exceeded")],
    ids=["deadline", "inferences"],
)
def test_a_cold_domains_cones_stop_at_either_bound_and_cache_nothing(bounds: dict, code: str) -> None:
    text = """
(gc-domain "deadline")
(gc-policy-version deadline-v1)
(gc-authority advisory 1 "advise")
(gc-estimator-ceiling measured advisory)
(gc-estimator-ceiling deterministic advisory)
(gc-estimator-ceiling receipt-calibrated advisory)
(gc-estimator-ceiling model-proposed advisory)
(gc-estimator-ceiling human-asserted advisory)
(gc-action act "Act" "do it" (authority advisory))
(gc-goal served owner individual 0.5 "served" (priority-source human:test))
(gc-dimension cost cost "what it costs")
(gc-signal ready "observed")
(normally r1 (signal ready) (candidate act))
"""
    domain = read_domain(text, f"deadline-{code}", budget=request_budget())

    with pytest.raises(RelevanceError) as raised:
        dependency_index(domain, budget=RunBudget(**bounds))

    assert raised.value.code == code
    assert domain not in dependency._INDEXES
    assert dependency_index(domain, budget=request_budget()).candidacy["act"] == {"ready"}
