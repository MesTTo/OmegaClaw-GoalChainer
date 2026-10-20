"""Purpose: run calls to a policy module group's helpers in its own space, returning every answer or asserting exactly one."""

from typing import Any

from goal_chainer.evidence_policy import EVIDENCE_POLICY
from goal_chainer.runtime.budget import run_bounded
from goal_chainer.runtime.engine import metta_engine
from goal_chainer.runtime.evaluator import ModuleGroup, plain_value, prepare
from request_support import budget


# evaluate calls only an entry with a declared type, since an untyped one would evaluate its hole
# data; a test of a rule's own helpers, such as the status join, the mass product or the shared
# membership, runs the call in the group's space instead, which runtime's evaluator names for tests.
# am[verifies a-rt-rb-migrate-evidence-1018@4fa74b] am[verifies a-rel-mig-tests-1018@3b8517]
def group_answers(group: ModuleGroup, source: str, **holes: Any) -> list[Any]:
    """Every answer of MeTTa `source`, e.g. "(gc-has {items} {item})", in the group's space, as
    plain values in the order the engine gave them."""

    prepare(group, budget=budget())
    with metta_engine(None) as engine:
        space = engine.space(group.space)
        with space.speculative():
            answers, _ = run_bounded(space, "!" + source, budget=budget(), **holes)
    return [plain_value(answer) for answered in answers for answer in answered]


# am[verifies a-rt-rb-migrate-evidence-1018@4fa74b] am[verifies a-ie-s5-incident-host-1018@53176a]
def policy_call(source: str, *, group: ModuleGroup = EVIDENCE_POLICY, **holes: Any) -> Any:
    """The one answer of MeTTa `source` in `group`, e.g. "(gc-status-join {a} {b})", as plain values."""

    answers = group_answers(group, source, **holes)
    assert len(answers) == 1, (source, answers)
    return answers[0]
