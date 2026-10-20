"""Purpose: compile a domain and a review packet into a DerivedReview within the review's one budget.

This is the review-packet compiler of the paper's section 11.3. It decides nothing: whether an
action is a candidate, what it is permitted or obliged to be, what it does for each goal and
what it costs all come from the domain's own theory. One `dl-run-deontic` derives all of it
together:

    (pd (lit pos F none do (ACTION)))                        deontic status
    (pd (lit pos none none candidate (ACTION)))              preconditions hold
    (pd (lit pos none none required (GOAL)))                 goals this review must serve
    (pd (lit pos none none contributes (ACTION GOAL BAND)))  per-goal-path contribution
    (pd (lit pos none none effect (ACTION DIM BAND EST)))    typed predicted effects

and the same run reports the deontic dilemmas, duties whose opposite also applies, which
otherwise leave no conclusion at all (`c-rel-dilemma-blocks-both-1016`).

Three stages share the review's RunBudget, each given only what the earlier ones left: the
evidence policy's effective readings, the theory run, and the readset policy's readsets.
"""

from __future__ import annotations

from ..deontic_engine import (
    DEONTIC_MODES,
    OBLIGED,
    DeonticOutputError,
    DeonticRun,
    run_deontic_theory,
)
from ..domains.model import Domain
from ..runtime.budget import BudgetExhausted, RunBudget
from ..errors import DependencyUnavailableError, GoalChainerError
from .dependency import dependency_index
from .derived import Candidate, Contribution, DerivedReview, EngineRecord
from .errors import RelevanceError
from .packet import ReviewPacket
from .policy import stopped
from ..domains.loader import vocabulary
from .quantity import Quantity, band_position, build_profile
from .signals import EffectiveReading, effective_readings, theory_facts

# am[implements a-rel-compiler-1016@c69c38] am[addresses i-rel-unreachable-1016@f105ff]
# am[implements a-rt-run-budget-1016@e046b0]
def compile_review(domain: Domain, packet: ReviewPacket, budget: RunBudget) -> DerivedReview:
    """Run the domain's theory once against the packet's readings and read off the review, every
    stage charged to `budget`."""

    packet.check_against(domain)
    readings = effective_readings(packet.readings, domain.signal_ids, packet.as_of, budget=budget)
    theory = theory_text(domain, readings)
    try:
        run = run_deontic_theory(theory, budget=budget)
    except BudgetExhausted as error:
        raise stopped(error) from error
    except DeonticOutputError as error:
        raise RelevanceError("engine-output-invalid", str(error)) from error
    except DependencyUnavailableError as error:
        raise RelevanceError("runtime-unavailable", str(error), details=dict(error.details)) from error
    except GoalChainerError as error:
        raise RelevanceError("engine-failed", str(error), details={"code": error.code}) from error
    return read_review(domain, packet, readings, theory, run, budget)


# am[implements a-rel-compiler-1016@c69c38]
def theory_text(domain: Domain, readings: dict[str, EffectiveReading]) -> str:
    """The exact theory a review runs: the packet's facts, then the domain theory verbatim.

    Only declared signal names and the domain's own policy version reach this text, so no
    packet field can inject a rule.
    """

    header = f"; relevance review under policy {domain.policy_version}\n"
    return f"{header}{theory_facts(readings)}\n\n{domain.theory}"


# Time: c log c for the c conclusions, to group and sort them; the rest is linear.
# am[implements a-rel-compiler-1016@c69c38] am[addresses i-rel-dilemma-silent-1016@8b9179]
# am[implements a-rel-mig-callers-1018@da2f3e]
# am[implements a-integrate-deontic-support-trees-1019@508ecf]
def read_review(
    domain: Domain,
    packet: ReviewPacket,
    readings: dict[str, EffectiveReading],
    theory: str,
    run: DeonticRun,
    budget: RunBudget,
) -> DerivedReview:
    """Read a DerivedReview off one engine run, rejecting any conclusion the domain cannot own;
    the readset policy's call is charged to `budget`."""

    provable = [conclusion.literal for conclusion in run.conclusions if conclusion.is_provable]

    candidate_ids = {
        literal.args[0] for literal in provable if literal.functor == "candidate" and len(literal.args) == 1
    }
    _require_declared(candidate_ids, domain.action_ids, "candidates", "actions")

    modes: dict[str, set[str]] = {}
    for literal in provable:
        if literal.functor == "do" and len(literal.args) == 1 and literal.mode in DEONTIC_MODES:
            modes.setdefault(literal.args[0], set()).add(literal.mode)
    _require_declared(set(modes), domain.action_ids, "deontic conclusions about", "actions")

    dilemma_actions: set[str] = set()
    other_dilemmas: list[str] = []
    for literal in run.dilemmas:
        if literal.functor == "do" and len(literal.args) == 1:
            dilemma_actions.add(literal.args[0])
        else:
            other_dilemmas.append(f"({literal.functor} {' '.join(literal.args)})")

    required = {literal.args[0] for literal in provable if literal.functor == "required" and len(literal.args) == 1}
    _require_declared(required, domain.goal_ids, "required", "goals")

    effects: dict[str, list[Quantity]] = {}
    contributions: dict[str, set[Contribution]] = {}
    for literal in provable:
        if literal.functor == "effect" and len(literal.args) == 4:
            action, dimension, band, estimator = literal.args
            if action in candidate_ids:
                _require_declared({dimension}, domain.dimension_ids, "effects on", "dimensions")
                effects.setdefault(action, []).append(Quantity(dimension, band, estimator))
        elif literal.functor == "contributes" and len(literal.args) == 3:
            action, goal, band = literal.args
            if action in candidate_ids:
                _require_declared({goal}, domain.goal_ids, "contributions to", "goals")
                if band not in vocabulary().bands:
                    raise RelevanceError(
                        "theory-defect", f"the theory derived a contribution band {band} for {action}"
                    )
                contributions.setdefault(action, set()).add(Contribution(goal, band))

    # Ordered by the domain's declaration, so a review never depends on the engine's
    # conclusion order.
    ordered = [action_id for action_id in domain.action_ids if action_id in candidate_ids]
    readsets = dependency_index(domain, budget=budget).readsets(ordered, budget=budget)
    candidates = tuple(
        Candidate(
            action=domain.action(action_id),
            modes=frozenset(modes.get(action_id, ())),
            dilemma=action_id in dilemma_actions,
            profile=build_profile(action_id, effects.get(action_id, [])),
            contributions=tuple(
                sorted(contributions.get(action_id, ()), key=lambda c: (c.goal, band_position(c.band)))
            ),
            readset=readsets.candidates[action_id],
        )
        for action_id in ordered
    )
    for candidate in candidates:
        defects = [conflict for conflict in candidate.profile.conflicts if conflict.is_theory_defect]
        if defects:
            raise RelevanceError(
                "theory-defect",
                f"{domain.source}: one estimator class derives contradictory levels: "
                + "; ".join(conflict.describe() for conflict in defects),
            )
        for contribution_goal in {c.goal for c in candidate.contributions}:
            if len([c for c in candidate.contributions if c.goal == contribution_goal]) > 1:
                raise RelevanceError(
                    "theory-defect",
                    f"{domain.source}: {candidate.id} derives several contributions to {contribution_goal}",
                )

    return DerivedReview(
        domain=domain,
        packet=packet,
        readings=readings,
        candidates=candidates,
        obligations=tuple(
            action_id for action_id in domain.action_ids if OBLIGED in modes.get(action_id, ())
        ),
        required_goals=tuple(goal for goal in domain.goal_ids if goal in required),
        other_dilemmas=tuple(sorted(set(other_dilemmas))),
        readset=readsets.review,
        engine=EngineRecord(
            runtime=run.engine.runtime,
            runtime_digest=run.engine.runtime_digest,
            plugin_digest=run.engine.plugin_digest,
            swipl_version=run.engine.swipl_version,
        ),
        theory=theory,
        deontic_support=run.support,
    )


# am[implements a-rel-compiler-1016@c69c38]
def _require_declared(names: set[str], declared: tuple[str, ...], what: str, kind: str) -> None:
    unknown = sorted(names - set(declared))
    if unknown:
        raise RelevanceError(
            "theory-defect",
            f"the theory derived {what} things the domain does not declare as {kind}: "
            f"{', '.join(unknown)}",
        )
