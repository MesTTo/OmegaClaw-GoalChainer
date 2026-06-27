"""Generated codebase repair demo for GoalChainer."""

from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hyperbase import make_proposition
from .ontology import load_colore_context


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DEMO_REPO = REPO_ROOT / "artifacts/codebase-demo/checkout-status-demo"


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": list(self.command),
            "exit_code": self.exit_code,
            "stdout": self.stdout.strip(),
            "stderr": self.stderr.strip(),
        }


@dataclass(frozen=True)
class CodebaseContract:
    restricted_fields: tuple[str, ...]
    customer_update_fields: tuple[str, ...]
    diagnostic_fields: tuple[str, ...]
    implementation_returns: tuple[str, ...]
    implementation_sources: dict[str, str]
    raw_log_passthrough: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "restricted_fields": list(self.restricted_fields),
            "customer_update_fields": list(self.customer_update_fields),
            "diagnostic_fields": list(self.diagnostic_fields),
            "implementation_returns": list(self.implementation_returns),
            "implementation_sources": dict(self.implementation_sources),
            "raw_log_passthrough": self.raw_log_passthrough,
        }


def run_codebase_demo(request: str = "", repo_path: str | Path | None = None) -> dict[str, Any]:
    repo = Path(repo_path) if repo_path is not None else _default_demo_repo()
    regenerate_demo_repo(repo)
    initial_commit = _git(repo, "rev-parse", "--short", "HEAD").stdout.strip()
    pre_tests = _run_tests(repo)
    contract = inspect_demo_repo(repo)
    reasoning = analyze_demo_repo(repo, request, contract)
    apply_demo_fix(repo, contract)
    patch_diff = _git(repo, "diff", "--", "src/checkout_status/update_builder.py").stdout
    post_tests = _run_tests(repo)
    post_contract = inspect_demo_repo(repo)
    _git(repo, "add", "src/checkout_status/update_builder.py")
    _git(repo, "commit", "-m", "Fix customer update redaction")
    fixed_commit = _git(repo, "rev-parse", "--short", "HEAD").stdout.strip()
    return {
        "skill": "goalchainer-codebase-demo",
        "request": " ".join(request.split()),
        "repo_path": str(repo),
        "issue": {
            "title": "Customer update leaks restricted checkout incident data",
            "file": "ISSUE.md",
        },
        "workflow": [
            "regenerate local buggy repo",
            "run failing tests",
            "read docs, tests, and implementation",
            "emit HyperBase-ready propositions",
            "rank the root cause and patch plan",
            "apply fix and rerun tests",
        ],
        "initial_commit": initial_commit,
        "fixed_commit": fixed_commit,
        "pre_patch_tests": pre_tests.to_dict(),
        "reasoning": reasoning,
        "patch": {
            "files_changed": ["src/checkout_status/update_builder.py"],
            "diff": patch_diff,
        },
        "post_patch_tests": post_tests.to_dict(),
        "post_patch_contract": post_contract.to_dict(),
        "success": pre_tests.exit_code != 0 and post_tests.exit_code == 0,
        "git_log": _git(repo, "log", "--oneline", "-2").stdout.strip().splitlines(),
    }


def regenerate_demo_repo(repo: Path) -> None:
    if repo.exists():
        shutil.rmtree(repo)
    _write_demo_files(repo)
    _git(repo, "init")
    _git(repo, "config", "user.name", "Ahmad Mesto")
    _git(repo, "config", "user.email", "metta.mestto@gmail.com")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Seed checkout status service bug")


def inspect_demo_repo(repo: Path) -> CodebaseContract:
    policy = (repo / "docs/customer_update_policy.md").read_text(encoding="utf-8")
    status_contract = (repo / "docs/status_contract.md").read_text(encoding="utf-8")
    implementation = _inspect_update_builder(repo / "src/checkout_status/update_builder.py")
    return CodebaseContract(
        restricted_fields=tuple(_extract_backtick_list(policy, "Restricted data keys")),
        customer_update_fields=tuple(_extract_backtick_list(status_contract, "Returned customer update keys")),
        diagnostic_fields=tuple(_extract_backtick_list(status_contract, "Allowed diagnostic keys")),
        implementation_returns=tuple(implementation["returned_fields"]),
        implementation_sources=dict(implementation["field_sources"]),
        raw_log_passthrough=bool(implementation["raw_log_passthrough"]),
    )


def analyze_demo_repo(
    repo: Path,
    request: str = "",
    contract: CodebaseContract | None = None,
) -> dict[str, Any]:
    contract = contract or inspect_demo_repo(repo)
    ontology = load_colore_context()
    propositions = _codebase_propositions(repo, contract)
    findings = _findings(repo, contract)
    return {
        "documents_examined": [
            _source_ref(repo, "ISSUE.md", "raw checkout logs"),
            _source_ref(repo, "docs/customer_update_policy.md", "Restricted data keys"),
            _source_ref(repo, "docs/status_contract.md", "Returned customer update keys"),
            _source_ref(repo, "tests/test_update_builder.py", "assert secret not in dumped"),
            _source_ref(repo, "src/checkout_status/update_builder.py", "raw_log"),
        ],
        "repair_contract": contract.to_dict(),
        "hyperbase_contract": {
            "shape": '(hb tree ID (sh (tag P v so ()) "predicate" ...))',
            "purpose": "make docs, tests, and code claims queryable as structured propositions",
        },
        "propositions": [proposition.to_dict() for proposition in propositions],
        "goal_model": _goal_model(contract),
        "ontology": {
            "source_available": ontology.source_available,
            "source_path": str(ontology.source_path),
            "projection_rules": list(ontology.projection_rules),
        },
        "findings": findings,
        "counterfactuals": _counterfactuals(contract),
        "selected_fix": {
            "id": "redact-before-customer-update",
            "reason": (
                "The policy names restricted fields, the status contract names the permitted "
                "customer update shape, and the implementation returns raw_log unchanged."
            ),
            "ordered_steps": [
                "read raw incident log",
                "redact restricted fields",
                "build external customer update",
                "keep allowed diagnostic context",
            ],
        },
        "request_match": {
            "mentions_codebase": any(word in request.lower() for word in ("repo", "code", "test", "bug")),
            "mentions_documentation": any(word in request.lower() for word in ("doc", "policy", "readme")),
        },
    }


def apply_demo_fix(repo: Path, contract: CodebaseContract | None = None) -> None:
    contract = contract or inspect_demo_repo(repo)
    _write(repo / "src/checkout_status/update_builder.py", _fixed_update_builder(contract))


def _write_demo_files(repo: Path) -> None:
    _write(
        repo / "README.md",
        """# Checkout Status Service

This small service builds customer-facing incident updates for checkout outages.
The current issue is intentionally seeded for the GoalChainer codebase demo.
""",
    )
    _write(
        repo / "ISSUE.md",
        """# Issue: customer update leaks restricted checkout data

Support reported that checkout incident updates may include raw checkout logs.
Those logs can contain customer emails, order IDs, request payloads, access
tokens, and internal traces. Fix the update builder so the customer-facing
message keeps useful operational context without exposing restricted data.
""",
    )
    _write(
        repo / "docs/customer_update_policy.md",
        """# Customer Update Policy

External customer updates must not include raw checkout logs or restricted
checkout fields.

## Restricted data keys

- `customer_email`
- `order_id`
- `request_payload`
- `access_token`
- `stack_trace`
- `raw_log`

Redaction must happen before any external customer update is built.
""",
    )
    _write(
        repo / "docs/status_contract.md",
        """# Status Builder Contract

`build_customer_update(incident)` returns the object that can be sent to
customers during an incident.

## Returned customer update keys

- `service`
- `status`
- `summary`
- `diagnostics`
- `next_update`

## Allowed diagnostic keys

- `error_code`

The returned object must never contain restricted values from `raw_log`.
""",
    )
    _write(repo / "pyproject.toml", _demo_pyproject())
    _write(repo / "src/checkout_status/__init__.py", "from .update_builder import build_customer_update\n")
    _write(repo / "src/checkout_status/update_builder.py", _buggy_update_builder())
    _write(repo / "tests/test_update_builder.py", _demo_tests())


def _buggy_update_builder() -> str:
    return '''"""Build customer-facing checkout incident updates."""


def build_customer_update(incident):
    """Return the update payload sent to customers."""
    return {
        "service": incident["service"],
        "status": incident["status"],
        "summary": incident["summary"],
        "raw_log": incident["raw_log"],
    }
'''


def _fixed_update_builder(contract: CodebaseContract) -> str:
    restricted_fields = tuple(field for field in contract.restricted_fields if field != "raw_log")
    diagnostic_fields = tuple(contract.diagnostic_fields)
    return f'''"""Build customer-facing checkout incident updates."""

RESTRICTED_FIELDS = {_format_tuple_literal(restricted_fields)}
ALLOWED_DIAGNOSTICS = {_format_tuple_literal(diagnostic_fields)}


def redact_incident_log(raw_log):
    """Return incident details that are safe for customer status updates."""
    diagnostics = {{}}
    for key, value in raw_log.items():
        if key in RESTRICTED_FIELDS:
            diagnostics[key] = "[redacted]"
        elif key in ALLOWED_DIAGNOSTICS:
            diagnostics[key] = value
    return diagnostics


def build_customer_update(incident):
    """Return the update payload sent to customers."""
    return {{
        "service": incident["service"],
        "status": incident["status"],
        "summary": incident["summary"],
        "diagnostics": redact_incident_log(incident.get("raw_log", {{}})),
        "next_update": incident.get("next_update", "15 minutes"),
    }}
'''


def _demo_tests() -> str:
    return '''import json

from checkout_status import build_customer_update


def incident():
    return {
        "service": "checkout",
        "status": "degraded",
        "summary": "Checkout payment retries are timing out.",
        "next_update": "15 minutes",
        "raw_log": {
            "customer_email": "ava@example.com",
            "order_id": "ORD-19942",
            "request_payload": "{card_token: tok_live_secret}",
            "access_token": "tok_live_secret",
            "stack_trace": "Traceback: internal checkout worker path",
            "error_code": "PAYMENT_TIMEOUT",
        },
    }


def test_customer_update_excludes_restricted_values():
    update = build_customer_update(incident())
    dumped = json.dumps(update)

    for secret in ("ava@example.com", "ORD-19942", "tok_live_secret", "Traceback"):
        assert secret not in dumped
    assert "[redacted]" in dumped


def test_customer_update_preserves_operational_context():
    update = build_customer_update(incident())

    assert update["service"] == "checkout"
    assert update["status"] == "degraded"
    assert "payment retries" in update["summary"]
    assert update["diagnostics"]["error_code"] == "PAYMENT_TIMEOUT"
    assert update["next_update"] == "15 minutes"
'''


def _demo_pyproject() -> str:
    return """[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "checkout-status-demo"
version = "0.1.0"
requires-python = ">=3.11"

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
"""


def _codebase_propositions(repo: Path, contract: CodebaseContract):
    restricted = ", ".join(contract.restricted_fields)
    returned = ", ".join(contract.implementation_returns)
    specs = (
        {
            "prop_id": "doc-policy-1",
            "sentence": f"External customer updates forbid these restricted fields: {restricted}.",
            "predicate": "forbids",
            "subject": "customer update policy",
            "object_": "restricted checkout fields",
            "source": _format_source(repo, "docs/customer_update_policy.md", "Restricted data keys"),
        },
        {
            "prop_id": "test-contract-1",
            "sentence": "The regression test rejects restricted checkout values in the customer update.",
            "predicate": "rejects",
            "subject": "privacy regression test",
            "object_": "restricted checkout values",
            "source": _format_source(repo, "tests/test_update_builder.py", "assert secret not in dumped"),
        },
        {
            "prop_id": "code-bug-1",
            "sentence": f"The update builder returns these fields: {returned}.",
            "predicate": "returns",
            "subject": "build_customer_update",
            "object_": "raw_log unchanged" if contract.raw_log_passthrough else "customer update object",
            "source": _format_source(repo, "src/checkout_status/update_builder.py", '"raw_log"'),
        },
        {
            "prop_id": "fix-order-1",
            "sentence": "Redaction happens before external customer update.",
            "predicate": "before",
            "subject": "redaction",
            "object_": "external customer update",
            "source": "COLORE timepoints/lp_ordering/a1",
            "ontology_hint": "COLORE before transitivity keeps the fix order explicit",
        },
    )
    return tuple(make_proposition(**spec) for spec in specs)


def _findings(repo: Path, contract: CodebaseContract) -> list[dict[str, Any]]:
    findings = [
        {
            "id": "policy-contract",
            "severity": "blocking",
            "source": _source_ref(repo, "docs/customer_update_policy.md", "Restricted data keys"),
            "claim": f"Customer updates cannot contain {', '.join(contract.restricted_fields)}.",
        },
        {
            "id": "test-contract",
            "severity": "blocking",
            "source": _source_ref(repo, "tests/test_update_builder.py", "assert secret not in dumped"),
            "claim": "The regression tests check exact restricted values and required context.",
        },
    ]
    restricted_returns = sorted(set(contract.implementation_returns) & set(contract.restricted_fields))
    if contract.raw_log_passthrough or restricted_returns:
        findings.append(
            {
                "id": "implementation-leak",
                "severity": "blocking",
                "source": _source_ref(repo, "src/checkout_status/update_builder.py", '"raw_log"'),
                "claim": "The implementation copies a restricted raw_log field into the external update.",
            }
        )
    return findings


def _goal_model(contract: CodebaseContract) -> dict[str, Any]:
    return {
        "individual_goals": [
            {
                "id": "protect-customer-data",
                "statement": "Do not expose customer identifiers, tokens, payloads, or traces.",
                "required": True,
                "evidence": list(contract.restricted_fields),
            }
        ],
        "collective_goals": [
            {
                "id": "maintain-service-trust",
                "statement": "Give customers useful status context without publishing internal logs.",
                "required": True,
                "evidence": list(contract.customer_update_fields),
            },
            {
                "id": "coordinate-incident-response",
                "statement": "Keep non-sensitive diagnostics that help responders identify the failure mode.",
                "required": True,
                "evidence": list(contract.diagnostic_fields),
            },
        ],
        "norms": [
            {
                "id": "forbid-restricted-customer-update",
                "status": "forbid",
                "target": "external update containing restricted fields",
                "priority": 100,
            },
            {
                "id": "oblige-inform-customers",
                "status": "oblige",
                "target": "external update with safe operational context",
                "priority": 70,
            },
        ],
    }


def _counterfactuals(contract: CodebaseContract) -> list[dict[str, Any]]:
    return [
        {
            "action": "return raw_log unchanged",
            "status": "blocked",
            "violates": ["protect-customer-data", "forbid-restricted-customer-update"],
            "evidence": {
                "returned_fields": list(contract.implementation_returns),
                "restricted_overlap": sorted(set(contract.implementation_returns) & set(contract.restricted_fields)),
            },
        },
        {
            "action": "delete diagnostics entirely",
            "status": "weak",
            "violates": ["coordinate-incident-response"],
            "evidence": {
                "required_context": list(contract.diagnostic_fields),
            },
        },
        {
            "action": "redact restricted fields and keep allowed diagnostics",
            "status": "selected",
            "satisfies": [
                "protect-customer-data",
                "maintain-service-trust",
                "coordinate-incident-response",
                "oblige-inform-customers",
            ],
        },
    ]


def _inspect_update_builder(path: Path) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    returned_fields: list[str] = []
    field_sources: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "build_customer_update":
            for child in ast.walk(node):
                if isinstance(child, ast.Return) and isinstance(child.value, ast.Dict):
                    for key_node, value_node in zip(child.value.keys, child.value.values):
                        key = _literal_string(key_node)
                        if key is None:
                            continue
                        returned_fields.append(key)
                        source = _incident_source_key(value_node) or ast.unparse(value_node)
                        field_sources[key] = source
    return {
        "returned_fields": returned_fields,
        "field_sources": field_sources,
        "raw_log_passthrough": field_sources.get("raw_log") == "raw_log",
    }


def _incident_source_key(node: ast.AST) -> str | None:
    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == "incident"
    ):
        return _literal_string(node.slice)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "incident"
        and node.args
    ):
        return _literal_string(node.args[0])
    return None


def _literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _extract_backtick_list(text: str, heading: str) -> list[str]:
    items: list[str] = []
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower() == f"## {heading}".lower():
            in_section = True
            continue
        if not in_section:
            continue
        if stripped.startswith("## ") and items:
            break
        if not stripped:
            continue
        if items and not stripped.startswith("-"):
            break
        if not stripped.startswith("-"):
            continue
        match = re.search(r"`([^`]+)`", stripped)
        if match:
            items.append(match.group(1))
    return items


def _format_tuple_literal(values: tuple[str, ...]) -> str:
    if not values:
        return "()"
    return repr(values)


def _format_source(repo: Path, relative_path: str, needle: str) -> str:
    source = _source_ref(repo, relative_path, needle)
    return f"{source['path']}:{source['line']}"


def _source_ref(repo: Path, relative_path: str, needle: str) -> dict[str, Any]:
    path = repo / relative_path
    line_no = 1
    if path.exists():
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if needle in line:
                line_no = index
                break
    return {"path": relative_path, "line": line_no, "needle": needle}


def _run_tests(repo: Path) -> CommandResult:
    return _run(repo, sys.executable, "-m", "pytest", "-q")


def _git(repo: Path, *args: str) -> CommandResult:
    result = _run(repo, "git", *args)
    if result.exit_code != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed in {repo}:\n{result.stderr or result.stdout}"
        )
    return result


def _run(repo: Path, *command: str) -> CommandResult:
    result = subprocess.run(command, cwd=repo, check=False, capture_output=True, text=True)
    return CommandResult(command=tuple(command), exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _default_demo_repo() -> Path:
    return Path(os.environ.get("GOALCHAINER_CODEBASE_DEMO_REPO", DEFAULT_DEMO_REPO))
