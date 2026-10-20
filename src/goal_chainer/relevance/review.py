"""Purpose: run a whole relevance review and render it as the versioned, deterministic review record.

    review(domain, packet, *, budget, motivation=None) -> ReviewResult    under the caller's one RunBudget
    ReviewResult.to_dict()                         the goalchainer-relevance-review-v2 record

The record never applies an effect (`applies_effects` is always false) and never grants
authority: `authorization` is always `unresolved`, because who may apply a proposal, and at
what rung, is the host's policy. A proposal's predicted effects and contributions all carry
`status: predicted`; only an observation can move them, through the receipt assessment.

The fingerprint identifies the decision inputs: the domain digest, the review policy's digest,
the engine identity, the review's authority rung, the subject under review, and every declared
signal's effective reading with the identity of the observations behind it, and for a domain that
declares needs the motivation snapshot's identity: its stream, every need's level and each
candidate's expected change of each need, each with the observations behind it. It leaves out what
only labels, bounds or measures the review: the review id, the trigger, the reference time as
such, the budget, the inferences spent, and reading notes. Two reviews with one fingerprint
reached the same disposition about the same subject from the same evidence under the same
policy, so a receipt naming a fingerprint names exactly one of them.

A domain that declares needs is reviewed against its motivation snapshot at the packet's as_of,
which the caller computes from its stream (goal_chainer.motivation) before the theory runs; a
caller that names none is reviewed against an empty history, every need unobserved. Version 2 of
the record adds the snapshot, each candidate's need paths, aggregates as intervals and the hold
disposition; a version-1 record is refused by the freshness check and the receipt assessment as an
invalid-record naming its protocol, so a host reviews again (c-v2m-v1-refused-1019).

The review runs under its caller's RunBudget, the one budget a request spends across its
stages, so its deadline is the caller's and covers all of it: whatever preparation the process
still needs, the domain's dependency cones, the effective readings, the theory run, the readsets
and the ranking. The packet's budget declares the most the review may cost, so a caller budget
with more left than that is refused; the relevance CLI builds the one budget from the packet's
bounds. Every stage but the preparation is charged to the caller's inference budget, and
`engine.inferences` reports what the review itself spent. The preparation, loading lib_deontic
and compiling the review policy, is fixed work no input changes, so no review is charged for it,
and a host can do it at startup with `prepare_service(budget)`, under a budget of its own whose
deadline bounds the startup, such as RunBudget(inference_budget=None, timeout_seconds=120).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..deontic_engine import DeonticEngine, prepare_deontic_engine
from ..domains.model import Domain
from ..runtime.budget import BudgetExhausted, RunBudget, caller_budget
from ..errors import DependencyUnavailableError, GoalChainerError
from .canonical import fingerprint_of
from .compiler import compile_review
from .dependency import dependency_index
from .derived import ENGINE_IDENTITY_FIELDS, Candidate, DerivedReview
from .errors import RelevanceError
from .motivation import MotivationSnapshot, motivation_snapshot
from .packet import ReviewPacket
from .policy import POLICY_MODULES, prepare, stopped
from .ranking import Ranking, rank

REVIEW_PROTOCOL = "goalchainer-relevance-review-v2"


# am[implements a-rel-review-contract-1016@d0bea9] am[addresses i-rel-unreachable-1016@f105ff]
# am[implements a-rt-run-budget-1016@e046b0] am[implements a-integrate-domain-review-budget-1018@a84bf4]
# am[implements a-v2m-snapshot-identity-1019@118a4b]
def review(domain: Domain, packet: ReviewPacket, *, budget: RunBudget,
           motivation: MotivationSnapshot | None = None) -> "ReviewResult":
    """Compile the packet against the domain, rank the candidates, and return the record, all
    under the caller's budget, which must have no more left than the packet declares. A domain
    with needs ranks by `motivation`, its snapshot at the packet's as_of, or by an empty stream's
    when none is given; a snapshot for any other domain or instant, or for a domain without
    needs, is an invalid-motivation error."""

    try:
        budget = packet.budget.admit(budget, "a relevance review")
    except BudgetExhausted as error:
        raise stopped(error) from error
    spent_before = budget.spent
    policy_digest = prepare_service(budget)
    motivation = _motivation(domain, packet, motivation, budget)
    # The cones come before the theory run, so a domain whose cones the budget cannot cover
    # fails before any theory is run.
    dependency_index(domain, budget=budget)
    derived = compile_review(domain, packet, budget)
    ranking = rank(derived, budget, motivation)
    return ReviewResult(derived=derived, ranking=ranking, policy_digest=policy_digest,
                        inferences=budget.spent - spent_before, motivation=motivation)


# The snapshot the review ranks by: the caller's, checked to be this domain's at this instant, or
# an empty stream's for a domain with needs whose caller named none; None for a domain without
# needs. Computing it is the modulation before appraisal, so it comes before the theory run.
# am[implements a-v2m-snapshot-identity-1019@118a4b]
def _motivation(domain: Domain, packet: ReviewPacket, snapshot: MotivationSnapshot | None,
                budget: RunBudget) -> MotivationSnapshot | None:
    if not domain.needs:
        if snapshot is not None:
            raise RelevanceError("invalid-motivation", f"{domain.source} declares no needs, so a review of it takes no motivation snapshot")
        return None
    if snapshot is None:
        try:
            return motivation_snapshot(domain, None, stream=None, as_of=packet.as_of, budget=budget)
        except BudgetExhausted as error:
            raise stopped(error) from error
    if snapshot.domain_digest != domain.digest or snapshot.as_of != packet.as_of:
        raise RelevanceError(
            "invalid-motivation",
            "the motivation snapshot was computed for another domain or instant than the review's",
            details={"snapshot": {"domain_digest": snapshot.domain_digest, "as_of": snapshot.as_of.isoformat()},
                     "review": {"domain_digest": domain.digest, "as_of": packet.as_of.isoformat()}},
        )
    return snapshot


# Loading lib_deontic and compiling the review policy are fixed per-process work that no input
# changes, so their inferences are charged to no review; a host can run this at startup. Inside a
# request both run inside the request's deadline, which stops them, and an overrun is a
# review-timeout with no review returned. A call without a RunBudget is refused before either
# load, so neither can run unbounded.
# am[implements a-rel-review-contract-1016@d0bea9] am[implements a-rel-metta-policy-1016@fdaa20]
# am[implements a-rel-request-deadline-1016@b72f03] am[rests-on c-rel-one-deadline-1016@75de2a]
# am[implements a-rel-digest-from-loads-1016@b6583d] am[implements a-rel-mig-callers-1018@da2f3e]
def prepare_service(budget: RunBudget) -> str:
    """Load the deontic engine and the review policy into the process's engine, once each, and
    answer the policy's identity, both inside `budget`'s deadline and charged none of its
    inferences. Raises InvalidInputError when `budget` is not a RunBudget."""

    budget = caller_budget(budget, "preparing the relevance service")
    _prepared_engine(budget)
    return prepare(budget)


# The engine identity a freshness check compares with a review record's, in the fields the record
# keeps of it. lib_deontic is loaded under the caller's budget if this process has not loaded it
# yet, so a check inside a request runs within the request's deadline; after the first load this
# reads what was loaded without taking the engine.
# am[implements a-ie-host-freshness-1018@ff618a]
def engine_identity(*, budget: RunBudget) -> dict[str, str]:
    """The current engine identity, in the fields a review record keeps of it."""

    budget = caller_budget(budget, "reading the relevance engine identity")
    current = _prepared_engine(budget)
    return {name: getattr(current, name) for name in ENGINE_IDENTITY_FIELDS}


# lib_deontic loaded under `budget`, with its failures typed as every relevance operation types
# them: a missing runtime is runtime-unavailable, a stop is the budget's own code and any other
# engine failure is engine-failed.
# am[implements a-rel-review-contract-1016@d0bea9] am[implements a-ie-host-freshness-1018@ff618a]
def _prepared_engine(budget: RunBudget) -> DeonticEngine:
    try:
        return prepare_deontic_engine(budget=budget)
    except DependencyUnavailableError as error:
        raise RelevanceError("runtime-unavailable", str(error), details=dict(error.details)) from error
    except BudgetExhausted as error:
        raise stopped(error) from error
    except GoalChainerError as error:
        raise RelevanceError("engine-failed", str(error), details={"code": error.code}) from error


# am[implements a-rel-review-contract-1016@d0bea9] am[rests-on c-integrate-agenticmind-effects-1016@7fdbf0]
@dataclass(frozen=True)
class ReviewResult:
    derived: DerivedReview
    ranking: Ranking
    policy_digest: str
    inferences: int
    motivation: MotivationSnapshot | None = None

    @property
    def fingerprint(self) -> str:
        derived = self.derived
        inputs = {
            "protocol": REVIEW_PROTOCOL,
            "subject": derived.packet.subject,
            "domain_digest": derived.domain.digest,
            "review_policy_digest": self.policy_digest,
            "engine": derived.engine.identity(),
            "review_authority": derived.packet.authority,
            "readings": {name: reading.snapshot() for name, reading in derived.readings.items()},
        }
        if self.motivation is not None:
            inputs["motivation"] = self.motivation_identity
        return fingerprint_of(inputs)

    # What the decision rests on of the motivation snapshot: the stream, every need's level and
    # each candidate's expected changes, with the observations behind each, which the freshness
    # check compares.
    # am[implements a-v2m-snapshot-identity-1019@118a4b] am[rests-on c-v2-motivation-freshness-obligation-1019@ad4628]
    @property
    def motivation_identity(self) -> dict[str, object] | None:
        if self.motivation is None:
            return None
        return self.motivation.identity(candidate.id for candidate in self.derived.candidates)

    # The record names the domain it was decided against, with the signals no rule reads, so a
    # reading of one, which changes nothing, is visible beside the review it did not move.
    # am[implements a-rel-nd-unread-signals-1018@f57790]
    # am[implements a-integrate-deontic-support-trees-1019@508ecf]
    def to_dict(self) -> dict[str, object]:
        derived, ranking = self.derived, self.ranking
        packet, domain = derived.packet, derived.domain
        return {
            "protocol": REVIEW_PROTOCOL,
            "applies_effects": False,
            "review_id": packet.review_id,
            "subject": packet.subject,
            "trigger": packet.trigger,
            "as_of": packet.as_of.isoformat(),
            "review_authority": packet.authority,
            "domain": {
                "title": domain.title,
                "source": domain.source,
                "policy_version": domain.policy_version,
                "digest": domain.digest,
                "unread_signals": list(domain.unread_signals),
            },
            "review_policy": {"digest": self.policy_digest, "modules": list(POLICY_MODULES)},
            "engine": {
                **derived.engine.identity(),
                "inferences": self.inferences,
                "budget": {
                    "inferences": packet.budget.inferences,
                    "timeout_seconds": packet.budget.timeout_seconds,
                },
            },
            "fingerprint": self.fingerprint,
            "disposition": ranking.disposition,
            "proposal": self._proposal(),
            "escalation": (
                {"reasons": list(ranking.escalation_reasons), "contested": list(ranking.contested)}
                if ranking.disposition == "escalate"
                else None
            ),
            "hold": None if ranking.hold is None else ranking.hold.to_dict(),
            "blockers": [item.to_dict() for item in ranking.blockers],
            "obligations": list(derived.obligations),
            "dilemmas": [c.id for c in derived.candidates if c.dilemma] + list(derived.other_dilemmas),
            "deontic_support": [support.to_dict() for support in derived.deontic_support],
            "required_goals": list(derived.required_goals),
            "unserved_required_goals": list(ranking.unserved_required),
            "motive_tension": (
                None
                if ranking.motive_tension is None
                else {"local_prefers": ranking.motive_tension[0], "hive_prefers": ranking.motive_tension[1]}
            ),
            "steps": [step.to_dict() for step in ranking.steps],
            "candidates": [self._candidate(candidate) for candidate in derived.candidates],
            "missing_information": self._missing(),
            "readings": [reading.to_dict() for _, reading in sorted(derived.readings.items())],
            "readset": {
                "signals": sorted(derived.readset),
                "snapshot": {name: derived.readings[name].snapshot() for name in sorted(derived.readset)},
            },
            "display_order": [{"action": action, "projection": value} for action, value in ranking.display_order],
            "motivation": self._motivation(),
        }

    # The snapshot the review ranked by, as a review records it, one size however long its stream
    # is, with the identity the fingerprint and the freshness check read and the history it was
    # read from, through which a status read recovers its samples; None for a domain without needs.
    # am[implements a-v2m-snapshot-identity-1019@118a4b] am[implements a-v2r-record-digest-1020]
    def _motivation(self) -> dict[str, object] | None:
        if self.motivation is None:
            return None
        return {**self.motivation.to_review_dict(), "snapshot": self.motivation_identity}

    # am[implements a-rel-status-answer-1016@c302a1]
    def _proposal(self) -> dict[str, object] | None:
        selected = self.ranking.selected
        if selected is None:
            return None
        appraisal = self.ranking.appraisals[selected.id]
        carrying = appraisal.carrying
        return {
            "action": selected.id,
            "label": selected.action.label,
            "description": selected.action.description,
            "deontic": self.ranking.standing[selected.id],
            "decided_at": self.ranking.decided_at,
            "action_authority_ceiling": appraisal.action_authority_ceiling,
            "licensed_authority_ceiling": appraisal.licensed_authority_ceiling,
            "authority_limits": [limit.to_dict() for limit in appraisal.authority_limits],
            "authorization": "unresolved",
            "carrying_path": None if carrying is None else carrying.to_dict(),
            "predicted_effects": [
                {**quantity.to_dict(), "status": "predicted"} for quantity in selected.profile.quantities
            ],
            "predicted_contributions": [
                {**contribution.to_dict(), "status": "predicted"} for contribution in selected.contributions
            ],
            "predicted_need_changes": self._predicted_needs(selected.id),
            "unknown_dimensions": list(appraisal.unknown_dimensions),
            "readset": sorted(selected.readset),
        }

    # What the proposal predicts of each need: from the level observed now and its state, the
    # expected change, the level the policy predicts it to leave, a range where the level or the
    # change is unknown, and the reduction of urgency; the prediction is never an observation, and
    # the host's observations after an applied attempt are what count.
    # am[implements a-v2m-snapshot-identity-1019@118a4b] am[rests-on c-gc-v2-authority-boundary-1019@5d2caf]
    # am[implements a-v2r-predicted-level-1020]
    def _predicted_needs(self, action: str) -> list[dict[str, object]]:
        if self.motivation is None:
            return []
        predicted = []
        for need in self.derived.domain.needs:
            level, change = self.motivation.level(need.id), self.motivation.change(action, need.id)
            reduction = self.motivation.reduction(action, need.id)
            predicted.append({
                "need": need.id,
                "goal": need.goal,
                "expected_change": change.change,
                "change_estimator": change.estimator,
                "observed_level": level.value,
                "level_state": level.state,
                "predicted_level": {"low": reduction.predicted_level[0], "high": reduction.predicted_level[1]},
                "reduction": {"low": round(reduction.low, 6), "high": round(reduction.high, 6)},
                "status": "predicted",
            })
        return predicted

    # am[implements a-rel-status-answer-1016@c302a1]
    def _candidate(self, candidate: Candidate) -> dict[str, object]:
        appraisal = self.ranking.appraisals[candidate.id]
        eliminated = next(
            (
                {"step": step.name, "reason": item.reason}
                for step in self.ranking.steps
                for item in step.eliminated
                if item.action == candidate.id
            ),
            None,
        )
        return {
            "action": candidate.id,
            "deontic": self.ranking.standing[candidate.id],
            "modes": sorted(candidate.modes),
            "eliminated": eliminated,
            "effects": [quantity.to_dict() for quantity in candidate.profile.quantities],
            "conflicts": [conflict.to_dict() for conflict in candidate.profile.conflicts],
            "contributions": [contribution.to_dict() for contribution in candidate.contributions],
            "paths": [path.to_dict() for path in appraisal.paths],
            "need_paths": [path.to_dict() for path in appraisal.need_paths],
            "aggregates": {rule: value.to_dict() for rule, value in appraisal.aggregates.items()},
            "local": {rule: value.to_dict() for rule, value in appraisal.local.items()},
            "hive": {rule: value.to_dict() for rule, value in appraisal.hive.items()},
            "projection": round(appraisal.projection, 6),
            "unknown_dimensions": list(appraisal.unknown_dimensions),
            "action_authority_ceiling": appraisal.action_authority_ceiling,
            "licensed_authority_ceiling": appraisal.licensed_authority_ceiling,
            "authority_limits": [limit.to_dict() for limit in appraisal.authority_limits],
            "readset": sorted(candidate.readset),
        }

    # A contested signal has a fact from its preferred reading and a live contrary the preference
    # overruled; a conflicted one has no fact. In a domain with needs, every need's level enters
    # every candidate's paths, so each need whose level is unobserved or expired, or conflicted, is
    # missing, and so is each candidate's expected change that is unknown; a domain without needs
    # lists none.
    # am[implements a-rel-rr-p-escalation-1018@86a7bb] am[implements a-v2r-undecided-need-named-1020]
    def _missing(self) -> dict[str, object]:
        derived = self.derived
        readings = derived.readings
        levels = () if self.motivation is None else self.motivation.levels
        candidates = {candidate.id for candidate in derived.candidates}
        return {
            "unknown_signals": [name for name in sorted(derived.readset) if readings[name].state == "unknown"],
            "conflicted_signals": [name for name in sorted(derived.readset) if readings[name].state == "conflicted"],
            "contested_signals": [name for name in sorted(derived.readset) if readings[name].contested],
            "decayed_readings": [
                reading.to_dict() for _, effective in sorted(readings.items()) for reading in effective.decayed
            ],
            "unestimated_dimensions": list(derived.domain.unestimated_dimensions),
            "unknown_needs": [level.need for level in levels if level.state in ("unobserved", "expired")],
            "conflicted_needs": [level.need for level in levels if level.state == "conflicted"],
            "unknown_need_changes": [] if self.motivation is None else [
                {"action": change.action, "need": change.need}
                for change in self.motivation.changes if change.action in candidates and not change.known
            ],
        }
