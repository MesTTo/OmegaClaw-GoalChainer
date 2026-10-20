"""Purpose: test that the SNARS command and its JSON dispatch read text only with the reading section of a domain their caller selects, refuse text without one and any selected domain that declares no readings, and answer statement operations alike whether or not a domain is selected."""

from __future__ import annotations

import argparse
import json
import re
from importlib import resources
from pathlib import Path

import pytest

from goal_chainer import cli, omegaclaw_skill, snars_cli
from goal_chainer.domains.loader import load_domain
from goal_chainer.errors import InvalidInputError
from goal_chainer.semantic_evaluation import CORPUS_PATH
from goal_chainer.snars_ingestion import ReadingFact
from goal_chainer.sexpr.codec import SexprCodec
from goal_chainer.snars_reasoner import SnarsSession
from reading_support import INCIDENT, reading_statement, section_text
from request_support import CLI_LIMITS, LIMITS, budget

# A corpus text whose Jev answers are recorded, so reading it asks no hosted model.
# am[verifies a-ie-sr-tests-docs-1018@81e23c]
TEXT = next(text["text"] for text in json.loads(CORPUS_PATH.read_text(encoding="utf-8"))["texts"]
            if text["id"] == "t25")
TASK_CONTROL = Path(str(resources.files("goal_chainer").joinpath("domains", "data", "task_control.metta")))
STATEMENT = '(sn p so "is" ((arg s (sn c "a")) (arg o (sn c "b"))))'


# A supplied domain that is not the incident's: the packaged task-control domain with a reading
# section of its own, the incident section's questions under another name and other proposition ids.
# Jev's answer cache keys a question by its wording, never its id, so the recorded answers replay.
# am[verifies a-ie-sr-tests-docs-1018@81e23c]
@pytest.fixture(scope="module")
def supplied(tmp_path_factory) -> Path:
    section = section_text(INCIDENT).replace("(gc-reading-domain incident)", "(gc-reading-domain task-review)")
    for proposition in INCIDENT.propositions:
        section = section.replace(f"(gc-reading-proposition {proposition.id} ",
                                  f"(gc-reading-proposition tr-{proposition.id} ")
    path = tmp_path_factory.mktemp("supplied") / "task_review.metta"
    path.write_text(TASK_CONTROL.read_text(encoding="utf-8") + "\n" + section, encoding="utf-8")
    return path


# One operation from the command line, answered as the exit code and the printed JSON.
# am[verifies a-ie-sr-tests-docs-1018@81e23c]
def _cli(capsys, operation: str, *flags: str) -> tuple[int, dict]:
    exit_code = cli.main(["snars", *CLI_LIMITS, operation, *flags, "--json"])
    return exit_code, json.loads(capsys.readouterr().out)


# One operation as the JSON dispatch takes it.
# am[verifies a-ie-sr-tests-docs-1018@81e23c]
def _dispatch(group: str, operation: str, **fields) -> dict:
    return snars_cli.run_snars_request({"group": group, "operation": operation, **fields}, budget=budget())


# A result without the engine's clock, which an inspection reports, parsed and in its raw text, and
# which advances with every batch the process runs, whatever that batch reads.
# am[verifies a-ie-sr-readerless-session-1018@9ffb9b]
_CLOCK = re.compile(r"\(clock \d+\)")


# am[verifies a-ie-sr-readerless-session-1018@9ffb9b]
def _without_clock(value):
    if isinstance(value, str):
        return _CLOCK.sub("(clock)", value)
    if isinstance(value, list):
        return [_without_clock(item) for item in value if not (isinstance(item, list) and item[:1] == ["clock"])]
    if isinstance(value, dict):
        return {key: _without_clock(item) for key, item in value.items()}
    return value


# Text needs a domain its caller selected, and a selected domain must declare readings, since a
# session reads a domain for its reading section alone, whether or not it is given text. Each
# refusal is InvalidInputError: a nonzero exit with the typed JSON error from the command line, and
# the error itself from the dispatch.
# am[verifies a-ie-sr-text-needs-domain-1018@8f7f0b] am[verifies a-ie-sr-select-domain-1018@577734]
@pytest.mark.parametrize("fields, flags, message", [
    ({"request": TEXT}, ["--request", TEXT], "the domain its caller selects"),
    ({"request": TEXT, "domain": {"packaged": "task-control"}}, ["--request", TEXT, "--domain", "task-control"],
     "declares no semantic readings"),
    ({"domain": {"packaged": "task-control"}}, ["--domain", "task-control"], "declares no semantic readings"),
    ({"request": TEXT, "domain": {"packaged": "no-such-domain"}}, ["--request", TEXT, "--domain", "no-such-domain"],
     "no packaged domain named no-such-domain"),
], ids=["text-without-domain", "no-readings-with-text", "no-readings-without-text", "unknown-domain"])
def test_text_needs_a_selected_domain_that_declares_readings(capsys, fields, flags, message) -> None:
    exit_code, printed = _cli(capsys, "inspect", *flags)
    with pytest.raises(InvalidInputError, match=message):
        _dispatch("trust-discovery", "inspect", **fields)

    assert exit_code == 1
    assert printed["ok"] is False and printed["error"]["code"] == "invalid_input"
    assert message in printed["error"]["message"]


# The dispatch takes a domain as a domain request does, an object with exactly one of path or
# packaged, and refuses any other value; a missing file is the loader's refusal naming it. The skill's
# envelope hands its request on unchanged, so the skill refuses text without a domain too.
# am[verifies a-ie-sr-select-domain-1018@577734] am[verifies a-ie-sr-text-needs-domain-1018@8f7f0b]
def test_the_dispatch_selects_a_domain_as_a_domain_request_does(tmp_path) -> None:
    for domain, message in (
        ({"path": "a.metta", "packaged": "incident"}, "exactly one path or packaged name"),
        ({}, "exactly one path or packaged name"),
        ("incident", "domain must be a JSON object"),
        ({"packaged": ""}, "domain.packaged must be nonempty text"),
        ({"path": str(tmp_path / "missing.metta")}, "missing.metta"),
    ):
        with pytest.raises(InvalidInputError, match=message):
            _dispatch("trust-discovery", "inspect", domain=domain)
    with pytest.raises(InvalidInputError, match="the domain its caller selects"):
        omegaclaw_skill.run_skill("goalchainer-snars-dispatch", json.dumps(
            {**LIMITS, "group": "trust-discovery", "operation": "inspect", "request": TEXT}))


# The command line takes one domain or the other, never both.
# am[verifies a-ie-sr-select-domain-1018@577734]
def test_the_command_takes_one_domain_option_or_none(supplied) -> None:
    parser = argparse.ArgumentParser()
    snars_cli.add_snars_arguments(parser)

    with pytest.raises(SystemExit):
        parser.parse_args(["inspect", "--domain", "incident", "--domain-file", str(supplied)])


# A supplied declaration reads the text, from the command line and from the dispatch alike: the
# stored ingestion's facts are readings of its own propositions, which it admits and the incident
# declaration refuses, and the text moves the truth of its proposition's statement and leaves the
# incident proposition's untouched.
# am[verifies a-ie-sr-text-needs-domain-1018@8f7f0b] am[verifies a-ie-sr-select-domain-1018@577734]
def test_a_supplied_declaration_reads_the_text_with_its_own_propositions(supplied, tmp_path, capsys) -> None:
    declaration = load_domain(supplied, budget=budget()).readings
    database = tmp_path / "snars.sqlite3"

    exit_code, printed = _cli(capsys, "inspect", "--domain-file", str(supplied), "--request", TEXT,
                              "--database", str(database))
    with SnarsSession.persistent(database, budget=budget()) as session:
        (event,) = session.store.events()
    codec = SexprCodec()
    facts = [ReadingFact.parse(fact, codec) for fact in event.payload["facts"]]

    assert exit_code == 0 and printed["state"]["event_count"] == 1
    assert {fact.reading_id for fact in facts} == {f"tr-{proposition.id}" for proposition in INCIDENT.propositions}
    assert [declaration.admit(fact) for fact in facts] == facts
    with pytest.raises(InvalidInputError, match="not one the incident reading declaration asks"):
        INCIDENT.admit(facts[0])

    def truth(proposition: str, **text) -> dict:
        return _dispatch("trust-discovery", "truth", statement=reading_statement(proposition),
                         domain={"path": str(supplied)}, **text)["result"]

    assert truth("tr-customer-emails", request=TEXT) != truth("tr-customer-emails")
    assert truth("customer-emails", request=TEXT) == truth("customer-emails")


# An operation on statements alone needs no domain, and selecting one changes nothing it answers:
# a session without a reader carries the policy with no rows, which believe no reading either way.
# Only the engine's clock, which moves between any two batches, may differ.
# am[verifies a-ie-sr-readerless-session-1018@9ffb9b]
@pytest.mark.parametrize("operation, flags", [
    ("inspect", []),
    ("trust", []),
    ("structural", []),
    ("control", ["--budget", "8"]),
    ("explain", ["--statement", STATEMENT]),
    ("truth", ["--statement", STATEMENT]),
    ("compiled-prove", ["--statement", STATEMENT]),
    ("what-if", ["--hypothesis", STATEMENT, "--query", STATEMENT]),
])
def test_a_statement_operation_answers_alike_with_and_without_a_domain(operation, flags) -> None:
    parser = argparse.ArgumentParser()
    snars_cli.add_snars_arguments(parser)

    without = snars_cli.run_snars_command(parser.parse_args([operation, *flags]), budget=budget())
    selected = snars_cli.run_snars_command(parser.parse_args([operation, *flags, "--domain", "incident"]),
                                           budget=budget())

    assert _without_clock([without["state"], without["result"]]) == _without_clock([selected["state"], selected["result"]])


# A session opened without a reader reads no text, and says so as the builder does.
# am[verifies a-ie-sr-readerless-session-1018@9ffb9b]
def test_a_session_opened_without_a_reader_refuses_text() -> None:
    with SnarsSession.ephemeral(budget=budget()) as session:
        with pytest.raises(InvalidInputError, match="needs the reader its session was opened with"):
            session.ingest_text(TEXT)
        assert session.state_payload()["event_count"] == 0
