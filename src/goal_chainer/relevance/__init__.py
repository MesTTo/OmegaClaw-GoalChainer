"""Purpose: the relevance review, a bounded typed proposal over a declarative task-control domain.

Built to the goal relevance governor paper (Goertzel, goal_relevance_governor_v3.pdf), whose
section 11 specifies this layer and whose section 11.2 fixes the approach: an adapter and an
extended skill surface, not a rewrite of GoalChainer and not reuse of its decide-and-execute
path. The outer contract is section 7.7:

    committed state -> bounded review -> typed proposal -> policy gate -> receipt

This package owns the bounded review and the typed proposal. It never applies an effect,
grants authority or certifies a goal; the policy gate, the executor and the verifier belong to
the host.

    from goal_chainer.domains.loader import packaged_domain
    from goal_chainer.relevance import parse_packet, review

    packet = parse_packet(packet_json)
    budget = packet.budget.run_budget()
    domain = packaged_domain("task-control", budget=budget)
    record = review(domain, packet, budget=budget).to_dict()
    record["disposition"]            # propose, escalate, blocked or no-candidates
"""

from .errors import ERROR_CODES, RelevanceError
from .freshness import FRESHNESS_PROTOCOL, FreshnessReport, check_freshness
from .packet import PACKET_PROTOCOL, ReviewBudget, ReviewPacket, parse_packet
# am[implements a-rel-assess-attempt-1018@20e6ca] am[implements a-rel-check-receipt-public-1018@ac8018]
from .receipt import (
    ASSESSMENT_PROTOCOL,
    RECEIPT_PROTOCOL,
    Receipt,
    assess_attempt,
    assess_receipt,
    check_receipt,
    parse_receipt,
)
from .review import REVIEW_PROTOCOL, ReviewResult, engine_identity, prepare_service, review
from .signals import EffectiveReading, SignalReading, SignalState

__all__ = [
    "ASSESSMENT_PROTOCOL",
    "ERROR_CODES",
    "FRESHNESS_PROTOCOL",
    "PACKET_PROTOCOL",
    "RECEIPT_PROTOCOL",
    "REVIEW_PROTOCOL",
    "EffectiveReading",
    "FreshnessReport",
    "Receipt",
    "RelevanceError",
    "ReviewBudget",
    "ReviewPacket",
    "ReviewResult",
    "SignalReading",
    "SignalState",
    "assess_attempt",
    "assess_receipt",
    "check_receipt",
    "check_freshness",
    "engine_identity",
    "parse_packet",
    "parse_receipt",
    "prepare_service",
    "review",
]
