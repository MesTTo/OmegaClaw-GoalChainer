"""Purpose: rerun every console sample in the guides DOCUMENTS lists and compare its output, and hold the relevance guide's receipt tables to the policy's, so the docs stay true.

A sample is a fenced `console` block: each `$ ` line is a command and the lines after it, up to
the next command, are its expected output, where `...` matches anything (doctest's ELLIPSIS).
The blocks of one file run in order in one scratch directory, so a later sample can read a file
an earlier one wrote. `goalchainer` resolves to this checkout's CLI under the running
interpreter, and every command must exit 0.

The relevance guide's table of reasons an observation is not counted and its table of receipt
faults name the policy's own rows, in the policy's order, read from the policy itself.
"""

from __future__ import annotations

import doctest
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from goal_chainer.relevance.policy import text

from relevance_support import helper_call

ROOT = Path(__file__).resolve().parents[1]
RELEVANCE_GUIDE = ROOT / "docs" / "relevance-review.md"
# Every guide whose console samples are rerun; the planning guide's are the derived planning demo's.
# am[verifies a-dd-doc-1018@da16cf]
DOCUMENTS = [RELEVANCE_GUIDE, ROOT / "docs" / "planning.md"]
_BLOCK = re.compile(r"^```console\n(.*?)^```", re.DOTALL | re.MULTILINE)


# am[related a-rel-docs-1016@98979d]
def samples(document: Path) -> list[tuple[str, str]]:
    """Each (command, expected output) of a document, in document order."""

    found: list[tuple[str, str]] = []
    for block in _BLOCK.findall(document.read_text(encoding="utf-8")):
        command, expected = None, []
        for line in block.splitlines():
            if line.startswith("$ "):
                if command is not None:
                    found.append((command, "\n".join(expected)))
                command, expected = line[2:], []
            else:
                expected.append(line)
        if command is not None:
            found.append((command, "\n".join(expected)))
    return found


# am[verifies a-rel-docs-1016@98979d]
@pytest.mark.parametrize("document", DOCUMENTS, ids=lambda path: path.name)
def test_every_documented_relevance_command_runs_and_prints_what_the_document_shows(document: Path, tmp_path: Path) -> None:
    found = samples(document)
    assert found, f"{document} has no console samples"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shim = bin_dir / "goalchainer"
    shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" -m goal_chainer.cli "$@"\n', encoding="utf-8")
    shim.chmod(0o755)
    (tmp_path / "examples").symlink_to(ROOT / "examples")
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "PYTHONPATH": os.pathsep.join(filter(None, [str(ROOT / "src"), os.environ.get("PYTHONPATH")])),
    }
    checker = doctest.OutputChecker()

    for command, expected in found:
        completed = subprocess.run(
            ["bash", "-c", command], cwd=tmp_path, env=env, capture_output=True, text=True, check=False
        )
        assert completed.returncode == 0, f"{command}\n{completed.stderr}"
        want = expected + "\n" if expected else ""
        assert checker.check_output(want, completed.stdout, doctest.ELLIPSIS), (
            f"{command}\n--- documented\n{want}--- printed\n{completed.stdout}"
        )


# am[related a-rel-docs-1016@98979d]
def table(document: str, header: str) -> list[str]:
    """The code-quoted first cell of each row of the table whose first column is `header`."""

    found = re.search(rf"^\| {header} \|.*\n\| --- \|.*\n((?:\|.*\n)+)", document, re.MULTILINE)
    assert found, f"no table headed {header}"
    return [re.match(r"\| `([^`]+)` \|", row).group(1) for row in found.group(1).splitlines()]


# am[related a-rel-docs-1016@98979d]
def reasons(*tables: str) -> tuple[str, ...]:
    """The reason of each row of the named policy tables, in order."""

    return tuple(text(row[1]) for name in tables for row in helper_call(name))


# am[verifies a-rel-docs-1016@98979d] am[verifies a-rel-rcpt-v2-metta-rules-1018@c22bf6]
# am[verifies a-rel-rcpt-v2-counting-1017@ae46fe]
def test_the_receipt_tables_list_the_policys_reasons_and_faults_in_order() -> None:
    guide = RELEVANCE_GUIDE.read_text(encoding="utf-8")

    assert tuple(table(guide, "Reason")) == reasons("gc-relevance-counting-table")
    assert tuple(table(guide, "Fault")) == reasons(
        "gc-relevance-receipt-table", "gc-relevance-observation-table", "gc-relevance-assessment-table"
    )
