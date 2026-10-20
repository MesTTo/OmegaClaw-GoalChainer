"""Purpose: answer every PLN statement set recorded in data/pettachainer_petta_beliefs.json with PeTTaChainer on PeTTa, the oracle test_evidence_chainer.py compares evidence_chainer.grade with, and write each set's answers back into the record with the PeTTa, PeTTaChainer and SWI-Prolog that gave them. It runs where PeTTa and a system SWI-Prolog are, which the package does not run on, for example `python tests/record_pettachainer_petta_beliefs.py --petta ../PeTTa --pettachainer ../PeTTaChainer`. A new statement set joins the record as a case with its label, statements and targets."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from goal_chainer.evidence_chainer import BACKWARD_PREMISE_PREFILTER, QUERY_STEPS
from goal_chainer.runtime.checkouts import PETTACHAINER, Checkout, checkout_dir
from goal_chainer.runtime.engine import child_environment
from goal_chainer.sexpr.codec import SexprCodec


# The statement sets, their targets and what PeTTaChainer answered on PeTTa.
# am[implements a-hh-gp-recorder-1018]
RECORDED = Path(__file__).resolve().parent / "data" / "pettachainer_petta_beliefs.json"

# am[implements a-hh-gp-recorder-1018]
PETTA = Checkout("PeTTa", "PeTTa", ("GOALCHAINER_PETTA_DIR", "PETTA_PATH"), "src/main.pl")

# What PeTTa prints before the answers: true for each import and for the prefilter, then added for
# the statements. The program collapses the statements' compilation into that one line because
# PeTTa otherwise echoes each compiled statement, and the echo of a statement about a target has an
# answer's shape.
# am[implements a-hh-gp-recorder-1018] am[addresses i-hh-pc-oracle-echo-1018]
PRELUDE = ["true", "true", "true", "added"]


# The program the differential ran through run_metta before the package stopped running PeTTa:
# every statement compiled into the knowledge base gckb, then one query per target in order. Each
# set runs in a fresh PeTTa process, so no set sees another's knowledge base, proofs or caches, and
# the program file is written into PeTTaChainer's metta/ directory because PeTTa resolves its
# imports against the program's directory. There is no time limit: a recording waits for PeTTa.
# Answers every target's answers in PeTTa's order, an empty list where it proved nothing.
# Time: one PeTTa start and PeTTaChainer load, one compileadd per statement, one query per target.
# am[implements a-hh-gp-recorder-1018] am[rests-on c-hh-pc-oracle-inputs-1018]
def petta_answers(statements: list[str], targets: list[str], petta: Path,
                  chainer: Path) -> list[list[tuple[float, float, str]]]:
    # PeTTa refuses a literal (superpose ()), and a set without statements compiles nothing.
    adds = " ".join(f"(compileadd gckb {statement})" for statement in statements)
    compiled = f"(collapse (superpose ({adds})))" if statements else "()"
    queries = "".join(f"!(query {QUERY_STEPS} gckb (: $prf {target} $tv))\n" for target in targets)
    program = ("!(import! &self petta_chainer)\n!(import! &self logic_configs/pln)\n"
               f"!(set-backward-premise-prefilter gckb {str(BACKWARD_PREMISE_PREFILTER).lower()})\n"
               f"!(let $added {compiled} added)\n{queries}")
    with tempfile.NamedTemporaryFile("w", suffix=".metta", dir=chainer / "pettachainer" / "metta",
                                     delete=False, encoding="utf-8") as handle:
        handle.write(program)
    try:
        result = subprocess.run(
            ["swipl", "--stack_limit=8g", "-q", "-s", str(petta / "src" / "main.pl"), "--", handle.name, "--silent"],
            cwd=petta, env=child_environment(), capture_output=True, text=True, check=False,
        )
    finally:
        Path(handle.name).unlink()
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if result.returncode != 0 or lines[:len(PRELUDE)] != PRELUDE:
        raise RuntimeError(f"PeTTa failed with PeTTaChainer at {chainer}, exit {result.returncode}:\n"
                           f"{result.stdout[-2000:]}\n{result.stderr[-2000:]}")
    codec = SexprCodec()
    claims = [codec.emit(codec.parse(target)) for target in targets]
    answers: list[list[tuple[float, float, str]]] = [[] for _ in targets]
    for line in lines[len(PRELUDE):]:
        index, strength, confidence = _answer(codec, codec.parse(line), claims)
        if index is None:
            raise RuntimeError(f"PeTTa printed {line!r} where only answers about the targets belong.")
        answers[index].append((strength, confidence, line))
    return answers


# An answer (: PROOF CLAIM (STV S C)) as the index of the target it is about and its truth value,
# or no index for anything else.
# am[implements a-hh-gp-recorder-1018]
def _answer(codec: SexprCodec, answer: Any, claims: list[str]) -> tuple[int | None, float, float]:
    truth = answer[3] if isinstance(answer, list) and len(answer) == 4 else None
    if (not isinstance(truth, list) or len(truth) != 3 or answer[0] != codec.Symbol(":")
            or truth[0] != codec.Symbol("STV") or not all(isinstance(value, codec.Symbol) for value in truth[1:])
            or codec.emit(answer[2]) not in claims):
        return None, 0.0, 0.0
    return claims.index(codec.emit(answer[2])), float(truth[1].text), float(truth[2].text)


# The commit a tree is at, refused while a tracked file differs from it, so the record names
# exactly what answered.
# am[implements a-hh-gp-recorder-1018]
def revision(tree: Path) -> str:
    git = ["git", "-C", str(tree)]
    changed = subprocess.run([*git, "status", "--porcelain", "--untracked-files=no"],
                             capture_output=True, text=True, check=True).stdout
    if changed:
        raise SystemExit(f"{tree} differs from its commit, so no commit names what answered:\n{changed}")
    return subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()


# Every PeTTaChainer tree answers every recorded set, and a set they answer differently stops the
# recording, so a record names every tree that gave its answers.
# Time: one PeTTa run per set and tree.
# am[implements a-hh-gp-recorder-1018] am[implements a-rt-pv-recorder-default-1018]
def main() -> None:
    parser = argparse.ArgumentParser(description="Answer the recorded PLN statement sets on PeTTa.")
    parser.add_argument(
        "--petta", required=not any(os.environ.get(variable) for variable in PETTA.variables),
        help="a separate PeTTa checkout; required unless GOALCHAINER_PETTA_DIR or PETTA_PATH is set",
    )
    parser.add_argument("--pettachainer", action="append",
                        help="a PeTTaChainer checkout to answer with, repeatable, all of them answering alike; "
                             "by default GOALCHAINER_PETTACHAINER_DIR or external/PeTTaChainer")
    arguments = parser.parse_args()
    petta = checkout_dir(PETTA, arguments.petta)
    chainers = [checkout_dir(PETTACHAINER, tree) for tree in arguments.pettachainer or [None]]
    swipl = subprocess.run(["swipl", "--version"], capture_output=True, text=True, check=True).stdout.strip()
    oracle = {"petta": revision(petta), "pettachainer": [revision(chainer) for chainer in chainers], "swipl": swipl}
    cases = []
    for case in json.loads(RECORDED.read_text(encoding="utf-8"))["cases"]:
        answers = [petta_answers(case["statements"], case["targets"], petta, chainer) for chainer in chainers]
        if any(other != answers[0] for other in answers[1:]):
            raise SystemExit(f"The PeTTaChainer trees {oracle['pettachainer']} answer {case['label']} differently: {answers}")
        cases.append({"label": case["label"], "statements": case["statements"], "targets": case["targets"],
                      "answers": answers[0]})
    record = {"oracle": oracle, "query_steps": QUERY_STEPS, "prefilter": BACKWARD_PREMISE_PREFILTER, "cases": cases}
    RECORDED.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
