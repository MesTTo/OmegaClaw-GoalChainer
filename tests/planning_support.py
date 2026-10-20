"""Purpose: build the task-control domain with a bigraph section for the planner's tests: the packaged
domain with a synthetic topology whose task sits in a seat and holds a resource through its occupancy
link, anchoring every declared signal but two on the task and the checkpoint store's restore statement
on the checkpoint, so the procedure policy's anchoring rule is exercised both ways; and the receipted
history of a procedure's attempts, with the packaged library under a promotion rule, from which the
planner's tracks come."""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from datetime import datetime, timedelta
from importlib import resources
from typing import Any

from goal_chainer.domains.bigraph import HEADS, read_section
from goal_chainer.domains.forms import parsed_forms
from goal_chainer.domains.loader import packaged_domain
from goal_chainer.domains.model import Domain
from goal_chainer.planning.procedures import ProcedureLibrary, read_procedures
from goal_chainer.planning.projection import Dispatched, Finished, JournalEvent, Receipt, Started
from goal_chainer.relevance.receipt import RECEIPT_PROTOCOL, parse_receipt
from goal_chainer.relevance.receipt import Receipt as ReceiptDocument
from request_support import budget

# Declared signals the section leaves unanchored, so a library literal over one is refused.
UNANCHORED = ("sunk_cost_argument", "no_safe_step")
RESTORES = '(sn p so "restores" ((arg s (sn c "checkpoint-store")) (arg o (sn c "task-state"))))'
# A handoff over a one-port Task: the task moves from seat A to seat B, keeping its occupancy link
# through the outer name occ. The packaged library's hand step binds T, A and B, so every topology
# the packaged library plans on declares this reaction or the packaged domain's own.
# am[verifies a-ev-pk-bind-table-1018@761a0f]
HANDOFF_REACTION = """(gc-brs-reaction handoff
  (Redex (Bigraph (Inner 3 ()) (Outer 2 (occ)) (Nodes (N A Seat) (N B Seat) (N T Task))
                  (Place (In A (Root 0)) (In B (Root 1)) (In T A) (In (Site 0) A) (In (Site 1) B) (In (Site 2) T))
                  (Link (P T 0 (Name occ)))))
  (Reactum (Bigraph (Inner 3 ()) (Outer 2 (occ)) (Nodes (N A Seat) (N B Seat) (N T Task))
                    (Place (In A (Root 0)) (In B (Root 1)) (In T B) (In (Site 0) A) (In (Site 1) B) (In (Site 2) T))
                    (Link (P T 0 (Name occ)))))
  (Eta (0 0) (1 1) (2 2)) (Conditions))"""


# The task sits in its seat beside a receiving seat, holds a resource through its occupancy link and
# can be handed off; the checkpoint store holds the restore statement.
# am[verifies a-ev-pk-acceptance-anchors-1018@cb1e61] am[verifies a-ev-pk-bind-table-1018@761a0f]
def task_section_text(signals: tuple[str, ...]) -> str:
    """The synthetic task-control section, anchoring each of `signals` but UNANCHORED on the task."""

    return "\n".join([
        "(gc-brs-control Task (Ports occupies) active)",
        "(gc-brs-control Seat (Ports) active)",
        "(gc-brs-control Checkpoint (Ports) passive)",
        "(gc-brs-entity seat Seat)",
        "(gc-brs-entity receiving_seat Seat)",
        "(gc-brs-entity task Task)",
        "(gc-brs-entity checkpoint Checkpoint)",
        "(gc-brs-in seat (Root 0))",
        "(gc-brs-in receiving_seat (Root 0))",
        "(gc-brs-in task seat)",
        "(gc-brs-in checkpoint (Root 0))",
        "(gc-brs-link task occupies (Edge occupancy))",
        *(f"(gc-brs-literal (Signal {signal}) (On task))" for signal in signals if signal not in UNANCHORED),
        f"(gc-brs-literal (Statement {RESTORES}) (On checkpoint))",
        HANDOFF_REACTION,
    ])


# am[verifies a-ev-pk-acceptance-anchors-1018@cb1e61]
def task_domain() -> Domain:
    """The packaged task-control domain with the synthetic section as its bigraph section."""

    domain = packaged_domain("task-control", budget=budget())
    section = read_section(parsed_forms(task_section_text(domain.signal_ids), budget=None), "tests/planning_support.py")
    return dataclasses.replace(domain, bigraph=section)


# A domain file supplying its own topology starts from the packaged task-control text without the
# packaged section, since a second section beside it would declare every control and entity twice;
# every other form is kept as written.
# am[verifies a-ev-pk-packaged-topology-1018@440efe]
def sectionless_task_control_text() -> str:
    """The packaged task-control domain's text with every bigraph section form removed."""

    text = (resources.files("goal_chainer.domains") / "data" / "task_control.metta").read_text(encoding="utf-8")
    return "\n".join(form.text for form, atom in parsed_forms(text, budget=None) if str(atom.children[0]) not in HEADS)


# A promotion three confirmations meet and two do not. SNARS's track-record belief is s / (s + f + 2) and Holds
# needs it above the threshold, so 3 successes give 0.6 and hold, while 2 successes, or 3 and a failure, give
# 0.5 and stay Undecided (c-ev-fb-snars-track-cut-1018).
PROMOTION = "(gc-track-promotion (Trials 3) (Threshold 0.5))"


# am[verifies a-ev-fb-promotion-1018@2ae86c]
def promoting_task_library() -> ProcedureLibrary:
    """The packaged task-control procedures with PROMOTION declared, read as a caller's library file is."""

    text = (resources.files("goal_chainer.planning") / "library" / "task_control.metta").read_text(encoding="utf-8")
    return read_procedures(f"{text}\n{PROMOTION}", "tests/planning_support.py", task_domain(), budget=budget())


# Per outcome, an instance of `procedure` is started, its act `step` dispatched under its own witness digest,
# applied a minute later, receipted and finished, each ten minutes after the last from `start`, so every
# attempt's window closes before the next one's observation. Each receipt-v2 document observes `achieves`,
# the Achieves literal as literal_text writes it, confirmed or contradicted as the outcome says, measured and
# produced by the attempt itself; None observes nothing.
# am[verifies a-ev-fb-request-receipts-1018@4c8f23] am[verifies a-ev-fb-trials-1018@775554]
def receipted_history(procedure: str, step: str, action: str, achieves: str, outcomes: Sequence[str | None], *,
                      start: datetime, tag: str) -> tuple[list[JournalEvent], dict[str, dict[str, Any]]]:
    """The journal's events and each Receipt id's receipt-v2 document, as a request carries them."""

    events: list[JournalEvent] = []
    documents: dict[str, dict[str, Any]] = {}
    for k, outcome in enumerate(outcomes):
        at = start + timedelta(minutes=10 * k)
        instance, attempt, receipt, decision = f"{tag}-i{k}", f"{tag}-a{k}", f"{tag}-r{k}", f"sha256:{tag}-w{k}"
        events += [Started(instance, procedure, f"{tag}-j{k}"), Dispatched(instance, step, attempt, decision, at),
                   Receipt(receipt, instance, step, attempt, True), Finished(instance)]
        observations = [] if outcome is None else [{
            "about": "achieves", "target": achieves, "outcome": outcome, "estimator": "measured",
            "source": f"probe:{tag}-{k}", "observed_at": (at + timedelta(minutes=2)).isoformat(), "produced_by": attempt,
        }]
        documents[receipt] = {
            "protocol": RECEIPT_PROTOCOL, "review_fingerprint": decision, "action": action, "attempt": attempt,
            "applied_at": (at + timedelta(minutes=1)).isoformat(), "issued_at": (at + timedelta(minutes=3)).isoformat(),
            "observations": observations,
        }
    return events, documents


# am[verifies a-ev-fb-request-receipts-1018@4c8f23]
def parsed(documents: dict[str, dict[str, Any]]) -> dict[str, ReceiptDocument]:
    """Each document as parse_receipt reads it, as plan takes them."""

    return {receipt: parse_receipt(document, budget=budget()) for receipt, document in documents.items()}
