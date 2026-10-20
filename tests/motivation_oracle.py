"""Purpose: the motivation snapshot's sample, no-sample, learning and exclusion rules written from
their definitions, apart from the policy's traversal, so a differential test can hold the policy to
them on any stream: every applied attempt is compared with every other record directly, nothing is
sorted or swept, and the answer is written as the snapshot's to_dict writes it."""

from __future__ import annotations

import random
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

from goal_chainer.domains.model import Domain
from goal_chainer.motivation import Attempt, NeedObservation
from goal_chainer.relevance.canonical import fingerprint_of


# The excluded observations, samples, unsampled attempts and learned changes of a history at
# `as_of`, by the rules in motivation.metta's header: an observation counts when its need is
# declared on its scale with a vocabulary class; an applied attempt at or before as_of samples each
# need it produced an observation of unless another applied attempt shares its instant, its
# outcome is the latest of those products after it and not after the stream's next applied
# instant or as_of, its baseline the need's latest counted observations at or before its
# application that are still valid then, and both agree on one level and establish.
# Time: m * (m + p * n) for m attempts, n observations and p needs, which a test can afford.
# am[verifies a-v2m-snapshot-sweep-1020@fefbd6] am[verifies c-v2m-receipt-window-1019@9fe31b] am[verifies c-v2m-window-subject-1019@077441]
def expected(regulated: Domain, observations: Iterable[NeedObservation], attempts: Iterable[Attempt], as_of: datetime,
             *, classes: Sequence[str], establishing: set[str]) -> dict[str, list[dict[str, Any]]]:
    held = {o.id: o for o in observations}
    stated = {a.attempt: a for a in attempts}
    needs = {need.id: need for need in regulated.needs}
    past = sorted((o for o in held.values() if o.observed_at <= as_of), key=lambda o: (o.observed_at, o.id))
    excluded, counted = [], []
    for o in past:
        reason = ("undeclared-need" if o.need not in needs
                  else "scale-changed" if o.scale != needs[o.need].scale
                  else "unknown-estimator" if o.estimator not in classes else None)
        (counted.append(o) if reason is None else excluded.append({"observation": o.id, "reason": reason}))
    applied = sorted((a for a in stated.values() if a.applied_at is not None and a.applied_at <= as_of),
                     key=lambda a: (a.applied_at, a.attempt))

    def establishes(group: list[NeedObservation]) -> bool:
        return any(o.estimator in establishing for o in group)

    not_sampled, raw = [], []
    for a in applied:
        later = [b.applied_at for b in applied if b.applied_at > a.applied_at]
        end = min(later) if later else as_of
        for need in regulated.needs:
            products = [o for o in counted if o.produced_by == a.attempt and o.need == need.id]
            if not products:
                continue
            reason = None
            if any(b.attempt != a.attempt and b.applied_at == a.applied_at for b in applied):
                reason = "simultaneous-attempt"
            else:
                outcomes = [o for o in products if a.applied_at < o.observed_at <= end]
                after = _latest(outcomes)
                history = [o for o in counted if o.need == need.id and o.observed_at <= a.applied_at]
                group = _latest(history)
                before = [o for o in group if o.valid_until is None or o.valid_until >= a.applied_at]
                reason = ("outside-window" if not outcomes
                          else "conflicted-outcome" if len({o.level for o in after}) > 1
                          else "outcome-not-establishing" if not establishes(after)
                          else "no-baseline" if not history
                          else "baseline-expired" if not before
                          else "conflicted-baseline" if len({o.level for o in before}) > 1
                          else "baseline-not-establishing" if not establishes(before) else None)
                if reason is None:
                    raw.append((a, need.id, sorted(o.id for o in before), sorted(o.id for o in after),
                                after[0].level - before[0].level))
            if reason is not None:
                not_sampled.append({"attempt": a.attempt, "need": need.id, "reason": reason})

    samples, changes = [], []
    for action in regulated.action_ids:
        for need in regulated.needs:
            declared = next((e for e in regulated.need_expectations if (e.action, e.need) == (action, need.id)), None)
            mean = None if declared is None else declared.change
            count, keys = 0, []
            for a, _, before, after, change in sorted((r for r in raw if (r[0].action, r[1]) == (action, need.id)),
                                                      key=lambda r: r[0].applied_at):
                samples.append({"attempt": a.attempt, "before": before, "after": after, "action": action,
                                "need": need.id, "change": change, "expected": mean,
                                "residual": None if mean is None else change - mean})
                mean = change if mean is None else mean * (count / (count + 1.0)) + change / (count + 1.0)
                count += 1
                keys.append({"attempt": a.attempt, "before": before, "after": after})
            state = "measured" if count else "declared" if declared is not None else "unknown"
            changes.append({
                "action": action, "need": need.id, "state": state,
                "change": mean if count or declared is not None else None,
                "estimator": "receipt-calibrated" if count else None if declared is None else declared.estimator,
                "samples": sorted(keys, key=lambda key: (key["attempt"], key["before"], key["after"])),
                "count": count,
            })
            changes[-1]["samples_digest"] = fingerprint_of({"samples": changes[-1]["samples"]})
    return {"excluded": excluded, "samples": samples, "not_sampled": not_sampled, "changes": changes}


# The observations sharing the latest instant among `group`, or none for an empty group.
# am[verifies a-v2m-snapshot-sweep-1020@fefbd6]
def _latest(group: list[NeedObservation]) -> list[NeedObservation]:
    if not group:
        return []
    top = max(o.observed_at for o in group)
    return [o for o in group if o.observed_at == top]


# A random stream over the companion domain's needs and actions: a noise level drawn per stream sets
# the share of records that should not count or not attribute (an undeclared need, another scale, a
# class the vocabulary lacks or one that does not establish, an unknown or no producer, an expiry,
# an unapplied attempt), so most streams sample some attempts and many give every reason. Instants
# come from a small range, so attempts and observations share them often.
# am[verifies a-v2m-snapshot-sweep-1020@fefbd6]
def random_stream(pick: random.Random, actions: Sequence[str]) -> tuple[list[NeedObservation], list[Attempt], float]:
    from motivation_support import Att, Obs, at  # noqa: PLC0415 (tests' fixtures)

    noise = pick.random()
    ids = [f"a{i}" for i in range(pick.randint(0, 8))]
    attempts = [Att(i, pick.choice(actions), None if pick.random() < noise / 3 else at(pick.randint(0, 20))) for i in ids]
    observations = []
    for index in range(pick.randint(0, 24)):
        t, odd = pick.randint(0, 22), pick.random() < noise
        observations.append(Obs(
            pick.choice(("thirst", "nurture", "calm")) if odd and pick.random() < 0.3 else pick.choice(("nurture", "calm")),
            pick.choice((0.2, 0.5, 0.8)), at(t),
            scale=(0.0, 2.0) if odd and pick.random() < 0.3 else (0.0, 1.0),
            estimator=(pick.choice(("astrology", "model-proposed", "receipt-calibrated")) if odd and pick.random() < 0.5
                       else pick.choice(("measured", "human-asserted"))),
            valid_until=at(t + pick.randint(0, 4)) if pick.random() < noise / 2 else None,
            produced_by=(pick.choice((None, "ghost")) if not ids or (odd and pick.random() < 0.5) else pick.choice(ids)),
            name=f"s{index}"))
    return observations, attempts, float(pick.randint(5, 24))
