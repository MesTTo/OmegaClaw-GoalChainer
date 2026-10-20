"""Purpose: verify the reading section's relational checks in the domain checks' own module group:
goal_chainer.domains.readings.FACTS answers the section's facts in the validation runner's shape, a
consistent section has no fault, each way a section's values can disagree is the fault its table row
names, a missing option is reported without the missing decided one it implies, every fault is
reported once and all of them at once, for generated declarations given any set of disagreements
too, and the domain loader runs the tables and renders their faults among the domain's other checks
when it reads a domain."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from goal_chainer.domains import readings
from goal_chainer.domains.loader import CHECKS_GROUP, _fact_atom, _packaged_directory, read_domain
from goal_chainer.domains.model import DomainError
from goal_chainer.domains.readings import Choice
from goal_chainer.runtime.evaluator import evaluate, plain_value
from reading_support import INCIDENT, SYMBOLS, declarations, section, section_text
from request_support import budget

BASE = [
    "(gc-reading-domain probe)",
    '(gc-reading-model "jev-1.13.0")',
    '(gc-reading-language "en")',
    '(gc-reading-instructions "Read the request.")',
    '(gc-reading-option yes for "the text says it")',
    '(gc-reading-option no against "the text denies it")',
    '(gc-reading-option unclear none "the text leaves it open")',
    '(gc-reading-proposition leaked "Customer data left the system." "Did customer data leave the system?")',
    '(gc-reading-choice mood "Is the request a question or an order?" ((query "a question") (directive "an order")))',
    '(gc-ranking-instruction "Rank the passages that bear on the question.")',
]
OPTIONS, READINGS = BASE[4:7], BASE[7:9]


# A fact or fault as plain names: each symbol and string its text, each nested term a tuple.
# am[verifies a-dr-dt-tables-1018@5ec9b6]
def _named(value):
    return tuple(_named(part) for part in value) if isinstance(value, tuple) else str(value)


# The (reason, failing fact) of each fault the section's tables find over its facts, in the order the
# tables report them.
# am[verifies a-dr-dt-tables-1018@5ec9b6]
def _faults(declaration) -> list[tuple[str, tuple]]:
    answer = plain_value(evaluate(CHECKS_GROUP, readings.ENTRY, _fact_atom(("Domain", *readings.FACTS(declaration))),
                                  budget=budget()))
    assert all(str(fault[0]) == "Fault" for fault in answer), answer
    return [(fault[1], _named(fault[2])) for fault in answer]


# am[verifies a-dr-dt-tables-1018@5ec9b6]
def _read(forms) -> readings.ReadingDeclaration:
    return section("\n".join(forms), Path("checks.metta"))


# am[verifies a-dr-dt-tables-1018@5ec9b6] am[verifies a-dr-declaration-checks-on-shared-reader-1018@7af2b0]
def test_a_consistent_section_has_no_fault() -> None:
    assert _faults(_read(BASE)) == []
    assert _faults(INCIDENT) == []


# Each row of the section's tables, by the forms that break it: dropped forms, replaced text or an
# added form. Two copies of one option fail alike and are one fault; a section with no option at all
# is reported once, not again for the decided option it therefore lacks; and two choices sharing an
# id, the core's fault, make neither one's options look repeated.
@pytest.mark.parametrize(
    "drop, swap, add, expected",
    [
        ((), {}, ['(gc-reading-option yes for "it says so again")'],
         [("duplicate-answer", ("Option", "yes", "for"))]),
        ((), {}, ['(gc-reading-option yes none "it may say so")'],
         [("duplicate-answer", ("Option", "yes", "for")), ("duplicate-answer", ("Option", "yes", "none"))]),
        ((), {"yes for": "yes none", "no against": "no none"}, [], [("no-decided-option", ("Readings", "probe"))]),
        (OPTIONS, {}, [], [("no-answer-option", ("Readings", "probe"))]),
        (READINGS, {}, [], [("no-reading", ("Readings", "probe"))]),
        ((), {"gc-reading-choice mood": "gc-reading-choice leaked"}, [],
         [("choice-is-proposition", ("Choice", "leaked", ("Options", "query", "directive")))]),
        ((), {'((query "a question") (directive "an order"))': "()"}, [], [("empty-choice", ("Choice", "mood", ("Options",)))]),
        ((), {'(directive "an order")': '(query "a question again")'}, [],
         [("duplicate-choice-option", ("Choice", "mood", ("Options", "query", "query")))]),
        ((), {}, ['(gc-reading-choice mood "Is it a statement?" ((statement "a statement")))'], []),
    ],
)
# am[verifies a-dr-dt-tables-1018@5ec9b6] am[verifies a-dr-dt-facts-1018@2ca5b0]
def test_each_disagreement_is_the_fault_its_row_names(drop, swap: dict[str, str], add: list[str], expected) -> None:
    assert all(any(old in form for form in BASE) for old in swap) and set(drop) <= set(BASE)
    forms = []
    for form in BASE:
        if form in drop:
            continue
        for old, new in swap.items():
            form = form.replace(old, new)
        forms.append(form)
    assert _faults(_read([*forms, *add])) == expected


# Any declaration whose values agree reads back from its forms with no fault, and given any set of
# disagreements it reports each once, in table order: every direction made none, the first option
# repeated, and choices added that share a proposition's id, offer nothing, or offer one option twice.
# am[verifies a-dr-dt-tables-1018@5ec9b6] am[verifies a-dr-dt-facts-1018@2ca5b0] am[verifies a-dr-dt-split-1018@03cfbb]
@settings(max_examples=40, deadline=None)
@given(declaration=declarations(), data=st.data())
def test_any_set_of_disagreements_is_reported_once_each_in_table_order(declaration, data) -> None:
    injected = data.draw(st.sets(st.sampled_from(
        ("undecided", "repeated-answer", "proposition-choice", "empty-choice", "repeated-option"))))
    taken = {declaration.name, *declaration.answers, *(p.id for p in declaration.propositions),
             *(c.id for c in declaration.choices), *(option for c in declaration.choices for option, _ in c.options)}
    fresh = data.draw(st.lists(SYMBOLS.filter(lambda name: name not in taken), min_size=3, max_size=3, unique=True))
    options, choices, expected = list(declaration.options), list(declaration.choices), []
    if "undecided" in injected:
        options = [replace(option, direction="none") for option in options]
        expected.append(("no-decided-option", ("Readings", declaration.name)))
    if "repeated-answer" in injected:
        options.append(options[0])
        expected.append(("duplicate-answer", ("Option", options[0].name, options[0].direction)))
    if "proposition-choice" in injected and declaration.propositions:
        shared = declaration.propositions[0].id
        choices.append(Choice(shared, "Which one?", ((fresh[0], "the first"),)))
        expected.append(("choice-is-proposition", ("Choice", shared, ("Options", fresh[0]))))
    if "empty-choice" in injected:
        choices.append(Choice(fresh[1], "Which one?", ()))
        expected.append(("empty-choice", ("Choice", fresh[1], ("Options",))))
    if "repeated-option" in injected:
        choices.append(Choice(fresh[2], "Which one?", ((fresh[0], "the first"), (fresh[0], "the first again"))))
        expected.append(("duplicate-choice-option", ("Choice", fresh[2], ("Options", fresh[0], fresh[0]))))
    disagreeing = replace(declaration, options=tuple(options), choices=tuple(choices))

    read_back = section(section_text(disagreeing), declaration.module)
    assert read_back == disagreeing
    assert _faults(read_back) == expected


# The facts a declaration gives the domain validation runner, in the runner's shape: the section,
# each proposition declared as a signal in the core's id table and again as a proposition, each choice
# declared in that table and again with its options, each answer option with its direction, and each
# decided one, in declaration order within each kind.
# am[verifies a-dr-readings-facts-1018@64445a] am[verifies a-dr-dt-facts-1018@2ca5b0]
def test_a_declaration_s_facts_take_the_runners_shape() -> None:
    def shaped(value) -> bool:
        return isinstance(value, str) or (isinstance(value, tuple) and len(value) >= 1 and isinstance(value[0], str)
                                          and all(shaped(argument) for argument in value[1:]))

    facts = readings.FACTS(INCIDENT)
    ids = [proposition.id for proposition in INCIDENT.propositions]

    assert all(isinstance(fact, tuple) and shaped(fact) for fact in facts)
    assert facts == (
        ("Readings", "incident"),
        *(("Declared", "signal", reading) for reading in ids),
        ("Declared", "choice", "mood"),
        *(("Proposition", reading) for reading in ids),
        ("Option", "supported", "for"), ("Option", "contradicted", "against"), ("Option", "unknown", "none"),
        ("Decided", "supported"), ("Decided", "contradicted"),
        ("Choice", "mood", ("Options", "query", "directive", "declarative")),
    )


# The warm-up the domain checks' group runs once per process answers True, which it does only when
# every table read its subjects and found the five faults it plants.
# am[verifies a-dr-dt-tables-1018@5ec9b6] am[verifies a-rel-nd-section-warm-ups-1018@df1a66]
def test_the_warm_up_answers_true() -> None:
    assert plain_value(evaluate(CHECKS_GROUP, readings.WARM_UP, budget=budget())) is True


# The loader runs the section's tables among the domain's checks and lists every fault in one
# DomainError: the packaged task-control domain with a consistent section reads into Domain.readings,
# and with a section that disagrees five ways and declares one choice twice it fails once, listing
# the core's duplicate before the section's faults, each section fact written whole before its row's
# message, while a value that is not well formed is refused as the section is read.
# am[verifies a-dr-dt-module-1018@8da5f7] am[verifies a-dr-declaration-checks-on-shared-reader-1018@7af2b0]
# am[verifies a-rel-nd-validation-runner-1018@f3f0b6]
def test_the_loader_runs_the_sections_tables_among_the_domains_checks() -> None:
    text = (_packaged_directory() / "task_control.metta").read_text(encoding="utf-8")
    domain = read_domain(f"{text}\n" + "\n".join(BASE), "task-control", budget=budget())
    assert domain.readings is not None and [p.id for p in domain.readings.propositions] == ["leaked"]

    broken = [form.replace("yes for", "yes none").replace("no against", "no none") for form in BASE]
    broken += ['(gc-reading-option unclear none "the text leaves it open again")',
               '(gc-reading-choice leaked "Which one?" ((a "the first") (a "the first again")))',
               '(gc-reading-choice empty "Which one?" ())',
               '(gc-reading-choice mood "Is it a statement?" ((statement "a statement")))']
    with pytest.raises(DomainError) as raised:
        read_domain(f"{text}\n" + "\n".join(broken), "task-control", budget=budget())
    assert raised.value.faults == (
        "choice mood is declared more than once",
        '(Readings "probe") declares no gc-reading-option whose direction is for or against, so no answer is evidence',
        '(Option "unclear" "none") is not the only gc-reading-option of its name',
        '(Choice "leaked" (Options "a" "a")) shares its id with a gc-reading-proposition, so the two would be one Jev '
        "question",
        '(Choice "leaked" (Options "a" "a")) offers one option more than once',
        '(Choice "empty" (Options)) offers no option',
    )

    with pytest.raises(DomainError, match="option maybe has the direction 'perhaps'"):
        read_domain(f"{text}\n" + "\n".join([*BASE, '(gc-reading-option maybe perhaps "it might")']), "task-control",
                    budget=budget())
