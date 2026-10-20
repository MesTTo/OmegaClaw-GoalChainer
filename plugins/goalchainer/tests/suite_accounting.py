"""Purpose: judge one run of a plugin MeTTa suite by counting its checks. A suite passes only when its
run exited 0, reported no failed check and reported exactly as many checks as its source declares
test forms in its directives, at least one, so a run that stopped after a passing prefix and a source
with no test form both fail.

    <python> suite_accounting.py SUITE STATUS < TRANSCRIPT

SUITE is the suite's .metta file, STATUS its run's exit status, and standard input the run's
transcript. It prints one line, PASS or FAIL with the counts and, for a failure, the reason, and
exits 0 for a pass and 1 otherwise."""

from __future__ import annotations

import re
import sys
from collections.abc import Iterator
from pathlib import Path

from goal_chainer.sexpr.forms import top_level_forms
from goal_chainer.sexpr.syntax import Atom, Symbol, parse

# The pinned engine's test prints one line per check it runs, 'is <value>, should <expected>. ✅'
# or the same with ❌, and throws on the ❌, so each mark that ends a line is one reported check.
# am[implements a-integrate-mettaspeak-assertion-accounting-1019@905c82]
# am[rests-on c-acc-pinned-test-output-1019@6ae21c]
REPORT = re.compile(r"(✅|❌) *$", re.MULTILINE)


# <tree> and every atom inside it, depth first.
# am[implements a-integrate-mettaspeak-assertion-accounting-1019@905c82]
def _walk(tree: Atom) -> Iterator[Atom]:
    yield tree
    if isinstance(tree, list):
        for item in tree:
            yield from _walk(item)


# The line of each test form a suite declares. A directive runs once, where it is written, so every
# (test ...) inside one runs once, at the top level or inside a let that binds what it needs; a test
# inside a definition runs only if something calls it, so it declares nothing. A test with other than
# two arguments still counts: the engine prints it as a partial application and reports nothing, so
# the count shows it never reported. GoalChainer's form scanner splits the source and its parser reads
# each directive, discarding comments before test forms are counted.
# Time: n + sum(p_i) character scans plus directive atom walks; n = source length,
# p_i = each directive's source offset. Line numbers rescan those prefixes.
# am[rests-on c-integrate-accounting-prefix-cost-1019@d8e027]
# am[implements a-integrate-mettaspeak-assertion-accounting-1019@905c82]
# am[rests-on c-integrate-mettaspeak-counted-tests-source-1019@11562c] am[rests-on c-acc-pinned-test-output-1019@6ae21c]
# am[implements a-integrate-accounting-comment-contract-1019@c974ce]
def declared(source: str) -> list[int]:
    """The line of each test form in the source's directives. Raises ValueError for text the form
    scanner or the parser cannot read, including a comment between ! and its form."""

    lines = []
    for form in top_level_forms(source):
        if not form.directive:
            continue
        line = source.count("\n", 0, form.index) + 1
        body = form.text[1:].lstrip()
        if not body.startswith("("):
            raise ValueError(f"line {line} has a comment between its ! and its form")
        for atom in _walk(parse(body)):
            if isinstance(atom, list) and atom and atom[0] == Symbol("test"):
                lines.append(line)
    return lines


# One verdict line for a suite, and whether it passed: MeTTaSpeak's rule, that a suite passes only
# when it declares at least one assertion and reports exactly as many, none failed and nothing else
# wrong, with the run's exit status as the something else.
# am[implements a-integrate-mettaspeak-assertion-accounting-1019@905c82]
# am[rests-on c-integrate-mettaspeak-counted-tests-source-1019@11562c]
def judge(name: str, source: str, status: int, transcript: str) -> tuple[bool, str]:
    try:
        tests = declared(source)
    except ValueError as error:
        return False, f"FAIL  {name}  (its test forms cannot be counted: {error})"
    reports = [mark == "✅" for mark in REPORT.findall(transcript)]
    failed = reports.count(False)
    if not tests:
        reason = "its source declares no test"
    elif failed:
        reason = f"{failed} failed"
    elif status != 0:
        reason = f"the run exited {status}"
    elif len(reports) < len(tests):
        reason = f"the run stopped after {len(reports)} of its {len(tests)} checks"
    elif len(reports) > len(tests):
        reason = f"the run reported {len(reports)} checks for {len(tests)} test forms"
    else:
        return True, f"PASS  {name}  ({len(tests)} checks)"
    return False, f"FAIL  {name}  ({len(reports)} of {len(tests)} checks reported, exit {status}): {reason}"


# The command line run.sh runs for each suite.
# am[implements a-integrate-mettaspeak-assertion-accounting-1019@905c82]
def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: suite_accounting.py SUITE STATUS < TRANSCRIPT", file=sys.stderr)
        return 2
    suite = Path(argv[1])
    passed, verdict = judge(suite.name, suite.read_text(encoding="utf-8"), int(argv[2]),
                            sys.stdin.buffer.read().decode("utf-8", errors="replace"))
    print(verdict)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
