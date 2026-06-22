from goal_chainer.deontic import resolve_norms
from goal_chainer.models import Norm


def test_forbid_blocks_lower_priority_permission():
    norms = (
        Norm("permit-low", "permit", "act", "ordinary case", priority=1),
        Norm("forbid-high", "forbid", "act", "privacy override", priority=5),
    )

    result = resolve_norms("act", norms)

    assert result.status == "forbidden"
    assert result.blocks_action
    assert result.priority == 5


def test_equal_priority_deontic_conflict_is_explicit():
    norms = (
        Norm("permit", "permit", "act", "coordination", priority=7),
        Norm("forbid", "forbid", "act", "privacy", priority=7),
    )

    result = resolve_norms("act", norms)

    assert result.status == "conflict"
    assert result.blocks_action

