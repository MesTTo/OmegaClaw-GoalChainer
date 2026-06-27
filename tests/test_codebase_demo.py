import json

from goal_chainer.codebase_demo import inspect_demo_repo, regenerate_demo_repo, run_codebase_demo


REQUEST = """
I have a checkout status repo with a bug. Please read the docs and tests,
figure out why the customer update is leaking incident data, and fix it.
"""


def test_generated_codebase_demo_fails_reasons_patches_and_passes(tmp_path):
    payload = run_codebase_demo(REQUEST, tmp_path / "checkout-status-demo")

    assert payload["skill"] == "goalchainer-codebase-demo"
    assert payload["success"] is True
    assert payload["pre_patch_tests"]["exit_code"] != 0
    assert payload["post_patch_tests"]["exit_code"] == 0
    assert payload["reasoning"]["repair_contract"]["raw_log_passthrough"] is True
    assert payload["post_patch_contract"]["raw_log_passthrough"] is False
    assert payload["post_patch_contract"]["implementation_returns"] == [
        "service",
        "status",
        "summary",
        "diagnostics",
        "next_update",
    ]
    assert "redact_incident_log" in payload["patch"]["diff"]
    assert any(finding["id"] == "implementation-leak" for finding in payload["reasoning"]["findings"])
    assert any(proposition["id"] == "code-bug-1" for proposition in payload["reasoning"]["propositions"])
    assert any(
        counterfactual["status"] == "blocked"
        for counterfactual in payload["reasoning"]["counterfactuals"]
    )
    assert payload["reasoning"]["goal_model"]["individual_goals"][0]["id"] == "protect-customer-data"
    assert len(payload["git_log"]) == 2


def test_generated_repo_contract_is_read_from_docs_and_source(tmp_path):
    repo = tmp_path / "checkout-status-demo"
    regenerate_demo_repo(repo)

    contract = inspect_demo_repo(repo)

    assert contract.restricted_fields == (
        "customer_email",
        "order_id",
        "request_payload",
        "access_token",
        "stack_trace",
        "raw_log",
    )
    assert contract.customer_update_fields == (
        "service",
        "status",
        "summary",
        "diagnostics",
        "next_update",
    )
    assert contract.diagnostic_fields == ("error_code",)
    assert contract.implementation_returns == ("service", "status", "summary", "raw_log")
    assert contract.implementation_sources["raw_log"] == "raw_log"
    assert contract.raw_log_passthrough is True


def test_codebase_demo_payload_is_json_serializable(tmp_path):
    payload = run_codebase_demo(REQUEST, tmp_path / "checkout-status-demo")

    encoded = json.dumps(payload, sort_keys=True)

    assert "checkout-status-demo" in encoded
