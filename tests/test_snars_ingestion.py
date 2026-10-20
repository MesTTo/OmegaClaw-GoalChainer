"""Purpose: test the gc-reading fact SNARS ingests: its grammar refuses anything but a well-formed
reading, every fact that can be built reads back as itself and no other can be built, a declaration
admits only the facts it asks, and importing the SNARS core imports no semantic reader."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from hypothesis import given, settings, strategies as st

import goal_chainer
from goal_chainer.domains.readings import is_reading_symbol
from goal_chainer.errors import InvalidInputError
from goal_chainer.sexpr.codec import SexprCodec
from goal_chainer.snars_ingestion import ReadingFact, reading_facts
from reading_support import INCIDENT as TABLE

MODEL = TABLE.model
# The fields of a semantic reading that reading_facts reads, for one decided proposition.
READING = SimpleNamespace(model=MODEL, propositions=(SimpleNamespace(
    proposition=SimpleNamespace(id="sensitive-data"), answer="supported", probability=0.9, key="k",
    grounding=None),))


# The grammar refuses anything but a well-formed reading, the store boundary's whole defence. A
# well-formed reading of a proposition or answer no declaration here asks is the declaration's to
# refuse, which the admission test below shows.
# am[verifies a-jev-fact-grammar-one-1018@0f04e2]
@pytest.mark.parametrize(
    "fact",
    [
        '(hb tree hb1 (sh-atom (tag C c NoRoles ()) "safe"))',
        '(attack now)',
        '(gc-reading "s" 1.5 sensitive-data supported 0.9 (provenance "m" "k" "p"))',
        '(gc-reading "s" 1.0 sensitive-data supported -0.1 (provenance "m" "k" "p"))',
        '(gc-reading "s" 1.0 sensitive-data supported nan (provenance "m" "k" "p"))',
        '(gc-reading s 1.0 sensitive-data supported 0.9 (provenance "m" "k" "p"))',
        '(gc-reading "s" 1.0 sensitive-data supported 0.9 (provenance "m" "k"))',
        '(gc-reading "s" 1.0 sensitive-data supported 0.9 (import! &self attack))',
        '(gc-reading "s" 1.0 "sensitive-data" supported 0.9 (provenance "m" "k" "p"))',
        '(gc-reading "s" 1.0 $x supported 0.9 (provenance "m" "k" "p"))',
        '(gc-reading "s" 1.0 sensitive-data 0.5 0.9 (provenance "m" "k" "p"))',
        '(gc-reading "s" 1.0 sensitive-data supported 0.9 (provenance "m" "k" "p")',
    ],
)
def test_the_fact_grammar_refuses_anything_but_a_well_formed_reading(fact) -> None:
    codec = SexprCodec()
    with pytest.raises(InvalidInputError):
        ReadingFact.parse(fact, codec)


# Printing then parsing gives the same fact for every fact that can be built, whatever its texts
# hold (quotes, backslashes, newlines, any script) and whatever reading symbols name its proposition
# and answer, and a fact parse would refuse cannot be built.
# am[verifies a-jev-fact-total-1016@c8ddbd] am[verifies a-dr-one-name-1018@beba5e]
@settings(deadline=None, database=None)
@given(
    source=st.text(),
    trust=st.floats(0.0, 1.0),
    reading_id=st.text(min_size=1).filter(is_reading_symbol),
    answer=st.text(min_size=1).filter(is_reading_symbol),
    probability=st.floats(0.0, 1.0),
    model=st.text(),
    key=st.text(),
    passage=st.text(),
)
def test_a_fact_reads_back_as_itself(source, trust, reading_id, answer, probability, model, key, passage) -> None:
    codec = SexprCodec()
    fact = ReadingFact(source, trust, reading_id, answer, probability, model, key, passage)

    assert ReadingFact.parse(fact.emit(codec), codec) == fact


@pytest.mark.parametrize(
    "change",
    [{"trust": 1.5}, {"trust": float("nan")}, {"probability": -0.1}, {"probability": True},
     {"reading_id": "two words"}, {"reading_id": "$x"}, {"reading_id": "(x)"}, {"reading_id": ""},
     {"answer": "0.5"}, {"answer": 'say"'}, {"answer": "a;b"}, {"passage": None},
     {"trust": 10**400}, {"probability": 10**400}, {"trust": 10**5000}, {"probability": -(10**5000)},
     {"reading_id": 10**5000}, {"answer": 10**5000}],
)
# am[verifies a-jev-fact-total-1016@c8ddbd] am[verifies a-integrate-reader-numeric-refusal-closure-1018@54efbb]
def test_a_fact_the_grammar_would_refuse_cannot_be_built(change) -> None:
    fields = {"source": "s", "trust": 1.0, "reading_id": "sensitive-data", "answer": "supported",
              "probability": 0.9, "model": MODEL, "key": "k", "passage": "p"}
    with pytest.raises(InvalidInputError):
        ReadingFact(**{**fields, **change})


# reading_facts leaves its caller's trust to ReadingFact, the grammar's one check, so a trust that is
# not a number from 0 to 1 is refused as a malformed fact, an integer too large for a float or for
# repr included, and an accepted trust is written as its float.
# am[verifies a-integrate-reader-numeric-refusal-closure-1018@54efbb]
@pytest.mark.parametrize("trust", [
    pytest.param(10**400, id="beyond-float"), pytest.param(10**5000, id="beyond-repr"),
    pytest.param(float("nan"), id="nan"), pytest.param(1.5, id="above-one"),
    pytest.param(True, id="bool"), pytest.param("1", id="text")])
def test_reading_facts_refuses_a_trust_the_grammar_refuses(trust) -> None:
    with pytest.raises(InvalidInputError, match="trust is not a number from 0 to 1"):
        reading_facts(READING, source="s", trust=trust, codec=SexprCodec())


# am[verifies a-integrate-reader-numeric-refusal-closure-1018@54efbb]
def test_reading_facts_writes_an_integer_trust_as_its_float() -> None:
    codec = SexprCodec()
    written = reading_facts(READING, source="s", trust=1, codec=codec)
    assert written == reading_facts(READING, source="s", trust=1.0, codec=codec)
    assert written[0].startswith('(gc-reading "s" 1.0 sensitive-data supported 0.9 ')


# A well-formed fact is admitted only by a declaration that asks its proposition and answer.
# am[verifies a-dr-explicit-table-1018@bba9ce]
@pytest.mark.parametrize("change", [{"reading_id": "attack"}, {"answer": "maybe"}, {"reading_id": "mood"}])
def test_the_declaration_admits_only_what_it_asks(change) -> None:
    fields = {"source": "s", "trust": 1.0, "reading_id": "sensitive-data", "answer": "supported",
              "probability": 0.9, "model": MODEL, "key": "k", "passage": "p"}
    admitted = ReadingFact(**fields)
    assert TABLE.admit(admitted) is admitted
    with pytest.raises(InvalidInputError, match="not one the incident reading declaration asks"):
        TABLE.admit(ReadingFact(**{**fields, **change}))


# A SNARS session reads with the reader its caller gives it, so a fresh interpreter that imports
# every SNARS core module, from the fact grammar and the answers it parses to the batch, its world,
# its store and the session, never imports the semantic reader. The child's PYTHONPATH names the
# tree this test imported, so it imports that tree and not a copy installed elsewhere.
# am[verifies a-sib-home-snars-ingestion-1018@5727d2]
def test_importing_the_snars_core_imports_no_semantic_reader() -> None:
    core = [f"goal_chainer.{name}" for name in (
        "snars_ingestion", "snars_models", "snars_protocol", "snars_program", "snars_store",
        "snars_engine", "snars_reasoner")]
    probe = (
        "import importlib, json, sys\n"
        f"for name in {core!r}:\n"
        "    importlib.import_module(name)\n"
        "print(json.dumps({'package': sys.modules['goal_chainer'].__file__, 'loaded': sorted(sys.modules)}))\n"
    )
    tree = Path(goal_chainer.__file__).resolve().parents[1]
    path = os.pathsep.join(filter(None, (str(tree), os.environ.get("PYTHONPATH"))))
    child = subprocess.run([sys.executable, "-c", probe], env={**os.environ, "PYTHONPATH": path},
                           check=True, capture_output=True, text=True)
    report = json.loads(child.stdout.splitlines()[-1])

    assert Path(report["package"]).resolve().parents[1] == tree
    assert set(core) <= set(report["loaded"])
    assert "goal_chainer.semantic_reader" not in report["loaded"]
