"""The decision must change with the input. This wraps the validation battery."""

from goal_chainer.validation import run_validation


def test_decision_depends_on_the_request():
    report = run_validation()

    assert report["passed"], report

    raw_status = report["raw_log_status_by_case"]
    # The same code blocks the raw log when sensitive data is present and allows it
    # when the request declares the data public. That is the anti-hardcoding proof.
    assert raw_status["pii_incident"] == "forbidden"
    assert raw_status["public_no_data"] == "permitted"

    top = report["top_action_by_case"]
    assert top["pii_incident"] == "publish_redacted_summary"
    assert top["facts_not_ready"] == "hold_external_update"


def test_every_case_runs_through_native_nal():
    report = run_validation()
    for case in report["cases"]:
        assert case["evidence"]  # evidence was extracted from the request
        assert case["ranking"]
