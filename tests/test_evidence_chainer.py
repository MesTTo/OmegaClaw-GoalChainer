from pathlib import Path

import pytest

from goal_chainer import evidence_chainer
from goal_chainer.evidence import extract_evidence
from goal_chainer.evidence_chainer import chainer_metta_dir, grade_beliefs


REQUEST = """
Checkout is down. Engineering wants to paste raw logs into the incident room.
Support says the logs may include customer emails, order IDs, and request payloads.
"""


def test_chainer_metta_dir_prefers_vendored_checkout(monkeypatch):
    monkeypatch.delenv("GOALCHAINER_PETTACHAINER_DIR", raising=False)

    root = Path(__file__).resolve().parents[1]

    assert chainer_metta_dir() == root / "external/PeTTaChainer/pettachainer/metta"


def test_chainer_metta_dir_honors_explicit_checkout(tmp_path, monkeypatch):
    metta_dir = tmp_path / "pettachainer/metta"
    metta_dir.mkdir(parents=True)
    (metta_dir / "petta_chainer.metta").write_text("", encoding="utf-8")
    monkeypatch.setenv("GOALCHAINER_PETTACHAINER_DIR", str(tmp_path))

    assert chainer_metta_dir() == metta_dir


def test_chainer_metta_dir_rejects_invalid_override(tmp_path, monkeypatch):
    monkeypatch.setenv("GOALCHAINER_PETTACHAINER_DIR", str(tmp_path))

    with pytest.raises(RuntimeError) as caught:
        chainer_metta_dir()
    assert str(tmp_path) in str(caught.value)


@pytest.mark.parametrize(
    "incident_text",
    (
        REQUEST,
        "The public outage report contains no sensitive data and is ready to share.",
        "Checkout is down, customer emails may be present, and the facts are not ready.",
    ),
)
def test_backward_premise_prefilter_preserves_goal_beliefs(incident_text, monkeypatch):
    evidence = extract_evidence(incident_text)
    monkeypatch.setattr(evidence_chainer, "BACKWARD_PREMISE_PREFILTER", False)
    without_filter, without_program, _outputs = grade_beliefs(evidence)
    monkeypatch.setattr(evidence_chainer, "BACKWARD_PREMISE_PREFILTER", True)
    with_filter, with_program, _outputs = grade_beliefs(evidence)

    assert "!(set-backward-premise-prefilter gckb false)" in without_program
    assert "!(set-backward-premise-prefilter gckb true)" in with_program
    assert with_filter == without_filter


def test_goal_beliefs_use_prefilter_and_keep_named_proofs(monkeypatch):
    monkeypatch.delenv("GOALCHAINER_PETTACHAINER_DIR", raising=False)

    beliefs, program, _outputs = grade_beliefs(extract_evidence(REQUEST))

    assert "!(set-backward-premise-prefilter gckb true)" in program
    assert "risk_to_accept raw_risk" in beliefs["publish_raw_log"].proof
    assert "redaction_to_accept red_redacted" in beliefs["publish_redacted_summary"].proof
    assert "support_to_accept red_support" in beliefs["publish_redacted_summary"].proof
    assert "protect_to_accept hold_protect" in beliefs["hold_external_update"].proof
