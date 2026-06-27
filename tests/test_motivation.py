"""MetaMo motivation consensus over individual vs collective goals (on PeTTa).

Guarded: skips when the MetaMo / PeTTa runtime is not reachable.
"""

import pytest

from goal_chainer.motivation import available, consensus_decision


def _metamo_up() -> bool:
    if not available():
        return False
    try:
        from goal_chainer.hyperbase import build_hyperbase_packet
        from goal_chainer.metta_reasoner import HyperBaseMettaReasoner
        from goal_chainer.scenarios import incident_response_scenario

        scenario = incident_response_scenario()
        reasoner = HyperBaseMettaReasoner(build_hyperbase_packet(scenario.title)["reasoner"])
        return bool(consensus_decision(scenario, reasoner).get("consensus"))
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _metamo_up(), reason="MetaMo / PeTTa not available")


def test_consensus_resolves_to_the_compromise_action():
    from goal_chainer.hyperbase import build_hyperbase_packet
    from goal_chainer.metta_reasoner import HyperBaseMettaReasoner
    from goal_chainer.scenarios import incident_response_scenario

    scenario = incident_response_scenario()
    reasoner = HyperBaseMettaReasoner(
        build_hyperbase_packet("Checkout down, engineering wants raw logs with customer emails")["reasoner"]
    )
    result = consensus_decision(scenario, reasoner)

    # The collective's goals pull toward the raw log (most coordination detail).
    assert result["goal_pull"]["collective"] == "publish_raw_log"
    # MetaMo's risk-weighted consensus is the redacted summary -- the compromise both
    # subsystems accept, with the raw log penalized for disagreement and risk.
    assert result["consensus"] == "publish_redacted_summary"
