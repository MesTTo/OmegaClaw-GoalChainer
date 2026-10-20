"""Purpose: give tests the packaged incident domain's reading declaration, read once per test process
under a test budget, read a reading section from text as the domain loader hands one over,
generate reading declarations whose values are well formed and agree, and name the SNARS
statement a session believes a declared proposition's readings as."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from hypothesis import assume, strategies as st

from goal_chainer.domains.forms import parsed_forms
from goal_chainer.domains.loader import packaged_domain
from goal_chainer.domains.readings import (
    DIRECTIONS,
    AnswerOption,
    Choice,
    Proposition,
    ReadingDeclaration,
    forms,
    is_reading_symbol,
    read_section,
)
from goal_chainer.semantic_reader import SemanticReader, default_reader
from goal_chainer.sexpr.codec import SexprCodec
from goal_chainer.snars_program import binary_statement
from request_support import budget

# The packaged incident domain's file, whose reading section the process's default reader reads
# with (semantic_reader.default_reader).
# am[verifies a-dr-sr-tests-1018@ae8cd4]
INCIDENT_FILE = Path(str(resources.files("goal_chainer").joinpath("domains", "data", "incident.metta")))

# Its reading declaration, read here under a test budget, so reading it never builds the process's
# default reader, whose configuration a test may set first.
# am[verifies a-dr-sr-tests-1018@ae8cd4]
INCIDENT: ReadingDeclaration = packaged_domain("incident", budget=budget()).readings


# am[verifies a-dr-sr-tests-1018@ae8cd4]
def section(text: str, module: Path = Path("section.metta")) -> ReadingDeclaration:
    """The declaration the reading forms in text declare, read as the domain loader reads a domain
    file's reading section, module naming the file they came from."""

    return read_section(parsed_forms(text, budget=None), module)


# am[verifies a-dr-sr-tests-1018@ae8cd4]
def section_text(declaration: ReadingDeclaration) -> str:
    """The declaration's reading section as domain-file text, one form a line."""

    return "\n".join(forms(declaration)) + "\n"


# The process's reader of the incident declaration, which a test opens a SNARS session reading the
# incident domain with; making it loads no model.
# am[verifies a-dr-sr-snars-batch-declaration-1018@5c965d]
def incident_reader() -> SemanticReader:
    return default_reader(budget=budget())


# Reading symbols as a domain file spells them, and declaration texts: any text but the surrogates,
# which UTF-8 cannot carry, the control characters included, since the codec writes every string as
# pymetta's reader reads it (a-dr-codec-pymetta-strings-1018).
# am[verifies a-dr-codec-pymetta-strings-1018@7fc480]
SYMBOLS = st.from_regex(r"[A-Za-z][A-Za-z0-9_.:/+*?<>=@!-]{0,15}", fullmatch=True).filter(is_reading_symbol)
TEXTS = st.text(st.characters(blacklist_categories=("Cs",)), min_size=1).filter(str.strip)


# Any declaration whose values are well formed and agree, so the section's tables find no fault in
# it: answer names, reading ids and each choice's options distinct, at least one reading id, every
# choice offering an option, and at least one answer giving evidence.
# am[verifies a-dr-sr-snars-batch-declaration-1018@5c965d] am[verifies a-dr-dt-tables-1018@5ec9b6]
@st.composite
def declarations(draw) -> ReadingDeclaration:
    options, propositions, choices = (draw(st.integers(low, high)) for low, high in ((1, 3), (0, 4), (0, 2)))
    names = draw(st.lists(SYMBOLS, min_size=1 + options + propositions + choices,
                          max_size=1 + options + propositions + choices, unique=True))
    directions = draw(st.lists(st.sampled_from(DIRECTIONS), min_size=options, max_size=options))
    assume(any(direction != "none" for direction in directions) and propositions + choices > 0)
    answers, ids = names[1:1 + options], names[1 + options:]
    return ReadingDeclaration(
        name=names[0],
        model=draw(TEXTS),
        language=draw(TEXTS),
        instructions=draw(TEXTS),
        options=tuple(AnswerOption(name, direction, draw(TEXTS)) for name, direction in zip(answers, directions)),
        propositions=tuple(Proposition(reading, draw(TEXTS), draw(TEXTS)) for reading in ids[:propositions]),
        choices=tuple(
            Choice(reading, draw(TEXTS), tuple((option, draw(TEXTS)) for option in
                                               draw(st.lists(SYMBOLS, min_size=1, max_size=3, unique=True))))
            for reading in ids[propositions:]
        ),
        ranking_instruction=draw(TEXTS),
        module=Path("probe.metta"),
    )


# The statement (has-property "request" ID) the policy believes each source's readings of a declared
# proposition as, so a test reads what a session believes of a proposition with
# SnarsSession.belief(reading_statement(ID)), e.g. reading_statement("sensitive-data").
# am[verifies a-ie-s7-tests-1018@5c72ce]
def reading_statement(proposition_id: str) -> str:
    return SexprCodec().emit(binary_statement("has-property", "request", proposition_id))
