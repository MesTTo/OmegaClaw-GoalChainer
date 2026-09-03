"""PII-flow STV-atom handoff test.

Feeds realistic petta-memory handoff-cache items (STV atoms as produced by
promoted BeliefContent clusters for the PII incident flow) into solve_incident
and asserts the memory evidence shifts the belief grading as expected.
"""
import time

from goal_chainer.pipeline import solve_incident

PII_REQUEST = (
    "Customer asks for the raw incident export including email addresses and "
    "phone numbers after the outage; decide what to publish externally."
)

# Handoff-cache items as emitted by the petta-memory goalchainer_slot filter:
# promoted STV atom + EC EvidencePacket sharing provenance (dedup target),
# plus an independent STV atom opposing raw-log publication.
MEM_ITEMS = [
    {
        "atom": "(Acceptable publish_redacted_summary) (STV 0.9000 0.7000)",
        "goalchainer_slot": "acceptability-belief-evidence",
        "belief_id": "bel-pii-redact",
        "cluster_id": "clu-pii-1",
        "promotion_event": "promo-pii-1",
        "promotion_domain": "incident-response",
    },
    {
        "atom": "(EvidencePacket (Acceptable publish_redacted_summary) (EC 9.0 1.0))",
        "goalchainer_slot": "contextual-appraisal-evidence",
        "belief_id": "bel-pii-redact",
        "cluster_id": "clu-pii-1",
        "promotion_event": "promo-pii-1",
        "promotion_domain": "incident-response",
    },
    {
        "atom": "(Acceptable publish_raw_log) (STV 0.0500 0.8000)",
        "goalchainer_slot": "acceptability-belief-evidence",
        "belief_id": "bel-pii-raw-block",
        "cluster_id": "clu-pii-2",
        "promotion_event": "promo-pii-2",
        "promotion_domain": "incident-response",
    },
    # Noise: wrong slot + unparseable atom must be skipped silently.
    {"atom": "(Acceptable publish_raw_log) (STV 1.0 1.0)", "goalchainer_slot": "other"},
    {"atom": "not-an-atom", "goalchainer_slot": "acceptability-belief-evidence"},
]


def _belief_for(result, action_id):
    for d in result["decisions"]:
        if d["action_id"] == action_id:
            return d
    raise AssertionError(f"missing decision for {action_id}")


def test_pii_stv_handoff_recommends_redacted():
    base = solve_incident(PII_REQUEST)
    with_mem = solve_incident(PII_REQUEST, memory_items=MEM_ITEMS)

    assert with_mem["decided"] == "publish_redacted_summary"
    # Memory support must not decrease the redacted-summary belief strength.
    b0 = _belief_for(base, "publish_redacted_summary")
    b1 = _belief_for(with_mem, "publish_redacted_summary")
    assert b1["evidence"]["strength"] >= b0["evidence"]["strength"]
    # Raw-log publication must stay non-recommended.
    raw = _belief_for(with_mem, "publish_raw_log")
    assert raw["status"] != "recommended"


def test_pii_stv_handoff_provenance_dedup():
    # STV+EC pair sharing belief_id must fuse as ONE ground, not two:
    # compare against a run with only the STV atom - results must match.
    stv_only = solve_incident(PII_REQUEST, memory_items=[MEM_ITEMS[0], MEM_ITEMS[2]])
    both = solve_incident(PII_REQUEST, memory_items=MEM_ITEMS)
    for aid in ("publish_redacted_summary", "publish_raw_log"):
        s1 = _belief_for(stv_only, aid)["evidence"]["strength"]
        c1 = _belief_for(stv_only, aid)["evidence"]["confidence"]
        s2 = _belief_for(both, aid)["evidence"]["strength"]
        c2 = _belief_for(both, aid)["evidence"]["confidence"]
        assert abs(s1 - s2) < 1e-9 and abs(c1 - c2) < 1e-9


def test_pii_stv_handoff_perf():
    t0 = time.time()
    solve_incident(PII_REQUEST, memory_items=MEM_ITEMS)
    assert time.time() - t0 < 2.0
