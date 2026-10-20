"""Purpose: define the incident example host's execution result, goalchainer-execution-v1, whose facets the host's settlement policy derives and keeps separate."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import KW_ONLY, InitVar, dataclass, field
from pathlib import Path
from typing import Any, Literal

from metta import S

from ...errors import ProtocolError
from ...runtime import evaluator
from ...runtime.budget import RunBudget
from ...runtime.evaluator import ModuleGroup, plain_value

CONTRACT = "goalchainer-execution-v1"
Audience = Literal["external", "internal"]
CONDITION_NAMES = (
    "Admissible",
    "Authorized",
    "ArtifactPrepared",
    "PrivacyVerified",
    "ReleaseEligible",
    "EffectConfirmed",
)
# The host's settlement policy, its blocking cut included, loaded into a module group of its own.
# am[implements a-ie-s5-incident-host-1018@53176a] am[rests-on c-ie-host-keeps-explicit-cut-1018@7116c5]
# am[implements a-ie-s2a-blocking-cut-home-1018@dd66bf]
SETTLEMENT = ModuleGroup("incident-host", (Path(__file__).resolve().with_name("settlement.metta"),))


# The one answer of `(FUNCTION ARGUMENT ...)` in the host's settlement policy, as plain values, each
# argument entering as a hole, under the caller's budget.
# am[implements a-ie-s5-incident-host-1018@53176a]
def settle(function: str, *arguments: Any, budget: RunBudget) -> Any:
    return plain_value(evaluator.evaluate(SETTLEMENT, function, *arguments, budget=budget))


# am[implements a-ev-execution-contract@7acc73]
def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


# am[implements a-ev-execution-contract@7acc73]
def _sha256(value: Any) -> str:
    return _sha256_text(_canonical(value))


# am[implements a-ev-execution-contract@7acc73]
def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# am[implements a-ev-execution-contract@7acc73]
@dataclass(frozen=True, slots=True)
class Condition:
    """One facet of an execution, after Kubernetes status conditions.

    ``status`` is True, False, or None when nothing observed settles it. None is
    never a refutation: a consumer testing ``if condition.status`` reads an
    unknown facet as not established, which is the fail-closed reading.
    """

    status: bool | None
    reason: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "reason": self.reason, "message": self.message}


# am[implements a-ev-execution-contract@7acc73]
@dataclass(frozen=True, slots=True)
class PrivacyCheck:
    """A containment check of one artifact against restricted raw-log values.

    ``covered_fields`` names the restricted fields whose values were searched for,
    so a pass says those values are absent, not that the artifact holds no
    sensitive information of any other kind.
    """

    method: str
    covered_fields: tuple[str, ...]
    leaked_fields: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.leaked_fields

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "covered_fields": list(self.covered_fields),
            "leaked_fields": list(self.leaked_fields),
            "passed": self.passed,
        }


# am[implements a-ev-execution-contract@7acc73]
@dataclass(frozen=True)
class PreparedArtifact:
    """What an executor prepared for one action. GoalChainer delivers nothing itself.

    The payload survives only a passed privacy check: a withheld artifact keeps
    its digest and leaked field names and nothing a caller could publish. The
    payload is held as the canonical JSON its digest and check were computed on,
    and ``payload`` returns a fresh copy, so changing a copy changes nothing
    released. Build one with ``checked``, which applies both rules.
    """

    action_id: str
    kind: str
    audience: Audience
    intended_effect: str
    digest: str
    privacy: PrivacyCheck
    sealed: str | None

    def __post_init__(self) -> None:
        if (self.sealed is None) == self.privacy.passed:
            raise ValueError(
                "A prepared artifact keeps its payload exactly when its privacy check passed."
            )
        if self.sealed is not None and _sha256_text(self.sealed) != self.digest:
            raise ValueError("A sealed payload must match the artifact digest.")

    @classmethod
    def checked(
        cls,
        *,
        action_id: str,
        kind: str,
        audience: Audience,
        intended_effect: str,
        payload: Mapping[str, Any],
        privacy: PrivacyCheck,
    ) -> PreparedArtifact:
        """Seal a payload after its check: keep its canonical JSON only if it passed.

        A payload that is not finite JSON raises ValueError, so nothing unsealable
        reaches a host.
        """

        text = _canonical(payload)
        return cls(
            action_id=action_id,
            kind=kind,
            audience=audience,
            intended_effect=intended_effect,
            digest=_sha256_text(text),
            privacy=privacy,
            sealed=text if privacy.passed else None,
        )

    @property
    def payload(self) -> dict[str, Any] | None:
        """A fresh copy of the releasable payload, or None for a withheld artifact."""

        return None if self.sealed is None else json.loads(self.sealed)

    @property
    def observation_id(self) -> str:
        """Identity of the privacy observation, the same for the same artifact and verdict.

        Two executions that prepare the same artifact observe the same thing, so
        evidence keyed by this id is recorded once.
        """

        return _sha256(
            {
                "action_id": self.action_id,
                "artifact": self.digest,
                "privacy": self.privacy.to_dict(),
            }
        )

    @property
    def term(self) -> Any:
        """The artifact as the settlement policy reads it: the verdict of its privacy check."""

        return S.Artifact(S.NoRestrictedValues if self.privacy.passed else S.RestrictedValuesFound)


# am[implements a-ev-mr-python@f08ebd]
def artifact_term(artifact: PreparedArtifact | None) -> Any:
    return S.NoArtifact if artifact is None else artifact.term


# am[implements a-ev-execution-contract@7acc73]
@dataclass(frozen=True)
class Authorization:
    """The host's decision whether to take the step for this action, and who made it.

    A review never makes one: its proposal leaves authorization unresolved, and the host decides
    and then publishes, if it does, under its own adjudication.
    """

    granted: bool
    reason: str
    authority: str
    message: str
    detail: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "granted": self.granted,
            "reason": self.reason,
            "authority": self.authority,
            "message": self.message,
            "detail": dict(self.detail),
        }


# am[implements a-ev-execution-contract@7acc73]
# am[addresses i-ev-privacy-fails-open@8ec490]
# am[implements a-ev-rb-pipeline-budget-1018@988a39]
@dataclass(frozen=True)
class ExecutionResult:
    """One execution: its primitive inputs, with every other facet derived from them.

    An artifact exists exactly when the step was authorized, and a withheld
    artifact holds no payload at all. The conditions are settled by
    the host's settlement policy, settlement.metta, when the result is made, so no facet can
    disagree with the primitives; ``EffectConfirmed`` stays unknown because
    GoalChainer performs no host effect and holds no host receipt. Settling is
    charged to ``budget``, the request's, which the result does not keep.
    """

    action_id: str
    norm_status: str
    authorization: Authorization
    artifact: PreparedArtifact | None
    readset: Mapping[str, Any]
    _: KW_ONLY
    budget: InitVar[RunBudget]
    conditions: Mapping[str, Condition] = field(init=False, repr=False, compare=False)

    def __post_init__(self, budget: RunBudget) -> None:
        if self.authorization.granted != (self.artifact is not None):
            raise ValueError(
                "An execution carries a prepared artifact exactly when it was authorized."
            )
        if self.artifact is not None and self.artifact.action_id != self.action_id:
            raise ValueError("The prepared artifact belongs to another action.")
        object.__setattr__(self, "conditions", self._settle(budget))
        if self.authorization.granted and not self.admissible:
            raise ValueError(
                f"A {self.norm_status} action cannot be authorized for execution."
            )

    @property
    def admissible(self) -> bool:
        return self.conditions["Admissible"].status is True

    @property
    def release_eligible(self) -> bool:
        return self.conditions["ReleaseEligible"].status is True

    @property
    def execution_id(self) -> str:
        """Identity of this attempt: the contract, the action and what the decision read."""

        return _sha256(
            {"contract": CONTRACT, "action_id": self.action_id, "readset": dict(self.readset)}
        )

    # am[implements a-ev-mr-python@f08ebd]
    # am[implements a-ev-rb-pipeline-budget-1018@988a39]
    def _settle(self, budget: RunBudget) -> dict[str, Condition]:
        answer = settle(
            "gc-settle-conditions",
            S[self.norm_status],
            S.Authorization(self.authorization.granted, S[self.authorization.reason]),
            artifact_term(self.artifact),
            budget=budget,
        )
        if not (isinstance(answer, tuple) and answer[:1] == (S.Conditions,)):
            raise ProtocolError("The settlement policy answered no conditions.", details={"answer": str(answer)})
        conditions = {}
        for _, name, status, reason in answer[1:]:
            name = str(name)
            reason = _reason(str(reason[1])) if name == "Admissible" else str(reason)
            conditions[name] = Condition(
                None if status == S.Unknown else status,
                reason,
                self._message(name, reason),
            )
        if tuple(conditions) != CONDITION_NAMES:
            raise ProtocolError("The settlement policy answered other conditions.", details={"names": list(conditions)})
        return conditions

    # The policy decides each facet; this only words it for a reader.
    # am[implements a-ev-mr-python@f08ebd]
    def _message(self, name: str, reason: str) -> str:
        artifact = self.artifact
        if name == "Admissible":
            return f"lib_deontic derived {self.norm_status} for {self.action_id}."
        if name == "Authorized":
            return self.authorization.message
        if artifact is None:
            return {
                "ArtifactPrepared": "No artifact was prepared because the step was not authorized.",
                "PrivacyVerified": "Nothing was prepared, so nothing was checked.",
                "ReleaseEligible": "There is no artifact to release.",
                "EffectConfirmed": "GoalChainer prepared nothing, so it predicts no effect.",
            }[name]
        privacy = artifact.privacy
        return {
            ("ArtifactPrepared", "Prepared"): f"Prepared a {artifact.kind} for an {artifact.audience} audience.",
            ("PrivacyVerified", "NoRestrictedValues"): (
                f"{privacy.method} found none of the values of "
                f"{', '.join(privacy.covered_fields) or 'no restricted field'}."
            ),
            ("PrivacyVerified", "RestrictedValuesFound"): (
                f"{privacy.method} found the values of {', '.join(privacy.leaked_fields)}."
            ),
            ("ReleaseEligible", "PrivacyVerified"): (
                "The host may release the artifact to its audience after its own adjudication."
            ),
            ("ReleaseEligible", "PrivacyCheckFailed"): (
                "The artifact is withheld; only its digest and leaked field names are kept."
            ),
            ("EffectConfirmed", "AwaitingHostReceipt"): (
                "GoalChainer performs no host effect; only a host receipt can confirm that "
                f"{artifact.intended_effect}."
            ),
            ("EffectConfirmed", "NoEffectExpected"): "The artifact is withheld, so GoalChainer predicts no effect.",
        }[(name, reason)]

    def to_dict(self) -> dict[str, Any]:
        artifact = self.artifact
        return {
            "contract": CONTRACT,
            "execution_id": self.execution_id,
            "action_id": self.action_id,
            "norm_status": self.norm_status,
            "authorization": self.authorization.to_dict(),
            "conditions": {
                name: condition.to_dict() for name, condition in self.conditions.items()
            },
            "artifact": None
            if artifact is None
            else {
                "kind": artifact.kind,
                "audience": artifact.audience,
                "intended_effect": artifact.intended_effect,
                "digest": artifact.digest,
                "payload": artifact.payload,
                "privacy": artifact.privacy.to_dict(),
                "observation_id": artifact.observation_id,
            },
            "readset": dict(self.readset),
        }


# am[implements a-ev-execution-contract@7acc73]
def _reason(norm_status: str) -> str:
    return "".join(part.capitalize() for part in norm_status.replace("_", "-").split("-"))


__all__ = [
    "CONTRACT",
    "CONDITION_NAMES",
    "Authorization",
    "Condition",
    "ExecutionResult",
    "PreparedArtifact",
    "PrivacyCheck",
    "artifact_term",
]
