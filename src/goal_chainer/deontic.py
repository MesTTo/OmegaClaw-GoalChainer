"""Small deontic resolver mirroring the OmegaClaw deontic branch vocabulary."""

from __future__ import annotations

from dataclasses import dataclass

from .models import Norm


@dataclass(frozen=True)
class NormResolution:
    status: str
    reasons: tuple[str, ...]
    priority: int

    @property
    def blocks_action(self) -> bool:
        return self.status in {"forbidden", "conflict"}


def resolve_norms(action_id: str, norms: tuple[Norm, ...]) -> NormResolution:
    applicable = [norm for norm in norms if norm.target_action == action_id]
    if not applicable:
        return NormResolution("unregulated", (), 0)

    max_priority = max(norm.priority for norm in applicable)
    strongest = [norm for norm in applicable if norm.priority == max_priority]
    modes = {norm.mode for norm in strongest}
    reasons = tuple(f"{norm.mode}:{norm.reason}" for norm in strongest)

    if "forbid" in modes and ("permit" in modes or "oblige" in modes):
        return NormResolution("conflict", reasons, max_priority)
    if "forbid" in modes:
        return NormResolution("forbidden", reasons, max_priority)
    if "oblige" in modes:
        return NormResolution("obligated", reasons, max_priority)
    return NormResolution("permitted", reasons, max_priority)

