"""Purpose: check the domain loader's grammar, its dead-declaration checks, its digest, the packaged task-control domain and the `goalchainer relevance domain` command."""

from __future__ import annotations

import json
import math
import re
import sys
from importlib import resources
from pathlib import Path

import pytest

from goal_chainer import relevance_cli
from goal_chainer.cli import main
from goal_chainer.domains.forms import FormsUnreadable, parsed_forms
from goal_chainer.domains.loader import (
    SECTION_HEADS,
    load_domain,
    packaged_domain,
    packaged_domain_names,
    read_domain,
    selected_domain,
)
from goal_chainer.domains import readings
from goal_chainer.domains.model import DomainError
from goal_chainer.models import Goal
from goal_chainer.relevance.policy import items, term
from goal_chainer.runtime.budget import InferenceBudgetExceeded, RunBudget
from goal_chainer.sexpr.forms import top_level_forms
from relevance_support import BEYOND_FLOAT, FLOAT_EDGE, helper_call, packet, reading, reviewed
from request_support import CLI_LIMITS
from request_support import budget as request_budget

HEADER = """
(gc-domain "probe")
(gc-policy-version probe-v1)
(gc-authority advisory 1 "advise")
(gc-estimator-ceiling measured advisory)
(gc-estimator-ceiling deterministic advisory)
(gc-estimator-ceiling receipt-calibrated advisory)
(gc-estimator-ceiling model-proposed advisory)
(gc-estimator-ceiling human-asserted advisory)
(gc-action act "Act" "do it" (authority advisory))
(gc-goal served owner individual 0.5 "served" (priority-source human:test))
(gc-dimension cost cost "what it costs")
"""


# am[related a-rel-domain-1016@6f8fc8]
def domain_text(extra: str) -> str:
    return HEADER + extra


# am[related a-rel-finite-priority-1017@262e4d]
def goal_priority(priority: str) -> str:
    """A readable probe domain whose one goal, served, has the given priority."""

    text = domain_text('(gc-signal used "read")\n(normally r1 (signal used) (candidate act))\n')
    return text.replace("individual 0.5", f"individual {priority}")


# The packaged task-control domain declares the paper's typed graph as its bigraph section:
# section 8.1.1's node types with section 3.4's seats as controls, ports named for section 8.1.2's
# edge types, the focal task in the seat that owns it, each closed edge linking the task to one
# entity, every declared signal anchored once and the checkpoint store's restore on the checkpoint,
# so the packaged procedures plan on the packaged domain without a caller's topology.
# am[verifies a-rel-tc-topology-1018@c19624]
def test_packaged_task_control_declares_the_papers_typed_graph() -> None:
    domain = packaged_domain("task-control", budget=request_budget())
    section = domain.bigraph

    assert section is not None
    assert {control.name: (control.ports, control.kind) for control in section.controls} == {
        "Seat": ((), "active"), "Task": (("occupies", "contributes-to", "reviewed-by"), "active"),
        "Goal": (("contributes-to",), "passive"), "Resource": (("occupies",), "passive"),
        "Checkpoint": ((), "passive"), "Review": (("reviewed-by",), "passive"),
    }
    assert {placement.entity: placement.parent for placement in section.placements}["task"] == "seat"
    linked: dict[str, list[str]] = {}
    for link in section.links:
        linked.setdefault(link.link.name, []).append(link.entity)
    assert linked == {"occupancy": ["task", "resource"], "contribution": ["task", "parent_goal"],
                      "reviewing": ["task", "review"]}
    anchored = [str(anchor.literal) for anchor in section.anchors]
    assert sorted(literal for literal in anchored if literal.startswith("(Signal ")) == sorted(
        f"(Signal {signal})" for signal in domain.signal_ids)
    restores, = (anchor for anchor in section.anchors if str(anchor.literal).startswith("(Statement "))
    assert restores.entity == "checkpoint"
    assert domain.unread_signals == ()


# am[verifies a-rel-domain-1016@6f8fc8]
def test_packaged_task_control_domain_loads_with_its_declared_vocabulary() -> None:
    domain = packaged_domain("task-control", budget=request_budget())

    assert "task-control" in packaged_domain_names()
    assert (len(domain.actions), len(domain.goals), len(domain.dimensions)) == (12, 6, 12)
    assert (len(domain.signals), len(domain.authorities)) == (21, 6)
    assert domain.policy_version == "task-control-v1"
    assert domain.goal("least_commitment").priority_source == "policy:planning-doctrine"
    # The five dimensions no rule estimates are reported, never read as neutral.
    assert domain.unestimated_dimensions == (
        "expected-goal-delta",
        "contribution-belief",
        "contribution-confidence",
        "urgency",
        "hazard-severity",
    )


# am[verifies a-rel-domain-1016@6f8fc8]
def test_the_packaged_file_and_a_path_load_to_the_same_digest() -> None:
    entry = resources.files("goal_chainer") / "domains" / "data" / "task_control.metta"
    with resources.as_file(entry) as path:
        from_path = load_domain(path, budget=request_budget())

    assert from_path.digest == packaged_domain("task-control", budget=request_budget()).digest
    assert from_path.digest.startswith("sha256:")


# A caller selects a domain by exactly one of a file path or a packaged name: either reads the same
# domain, and naming neither, both, a missing file or an unknown name is a DomainError.
# am[verifies a-ie-sr-select-domain-1018@577734]
def test_a_domain_is_selected_by_exactly_one_path_or_packaged_name(tmp_path) -> None:
    entry = resources.files("goal_chainer") / "domains" / "data" / "task_control.metta"
    with resources.as_file(entry) as path:
        by_path = selected_domain(path=path, budget=request_budget())
        with pytest.raises(DomainError, match="exactly one"):
            selected_domain(path=path, packaged="task-control", budget=request_budget())
    by_name = selected_domain(packaged="task-control", budget=request_budget())

    assert by_path.digest == by_name.digest
    with pytest.raises(DomainError, match="exactly one"):
        selected_domain(budget=request_budget())
    with pytest.raises(DomainError, match="missing.metta"):
        selected_domain(path=tmp_path / "missing.metta", budget=request_budget())
    with pytest.raises(DomainError, match="no packaged domain named nothing"):
        selected_domain(packaged="nothing", budget=request_budget())


READING_SECTION = """
(gc-reading-domain probe)
(gc-reading-model "jev-1.13.0")
(gc-reading-language "en")
(gc-reading-instructions "Read the request.")
(gc-reading-option yes for "the text says it")
(gc-reading-option no against "the text denies it")
(gc-reading-option unclear none "the text leaves it open")
(gc-reading-proposition leaked "Customer data left the system." "Does the text say customer data left the system?")
(gc-ranking-instruction "Rank the passages that bear on the question.")
"""
BIGRAPH_SECTION = """
(gc-brs-control Task (Ports occupies) active)
(gc-brs-control Seat (Ports) passive)
(gc-brs-entity seat Seat "the owner's seat")
(gc-brs-entity task Task)
(gc-brs-in seat (Root 0))
(gc-brs-in task seat)
(gc-brs-link task occupies (Edge occupancy))
(gc-brs-literal (Signal leaked) (On task))
"""
THEORY = "(normally r1 (signal used) (candidate act))\n(normally r2 (signal leaked) (candidate act))\n"


# A domain names each proposition once: its reading section declares it, the domain reads it as
# one of its signals after the gc-signal ones, and the section's records and digest are the ones
# the section gives read alone.
# am[verifies a-rel-nd-reading-section-1018@98f298] am[verifies c-rel-agrees-dr-pj-api-1018@3ef2d8]
def test_a_reading_section_declares_each_proposition_as_one_of_the_domains_signals() -> None:
    domain = read_domain(domain_text('(gc-signal used "read by a rule")\n' + READING_SECTION + THEORY), "probe", budget=request_budget())

    alone = readings.read_section(parsed_forms(READING_SECTION, budget=None), Path("probe"))
    assert domain.readings is not None and domain.readings.digest == alone.digest
    assert [proposition.id for proposition in domain.readings.propositions] == ["leaked"]
    assert domain.signal_ids == ("used", "leaked")
    assert domain.signals[1].description == "Customer data left the system."
    assert domain.bigraph is None


# am[verifies a-rel-nd-reading-section-1018@98f298]
def test_a_proposition_and_a_gc_signal_share_one_id_namespace() -> None:
    text = domain_text('(gc-signal leaked "declared twice")\n' + READING_SECTION + THEORY.replace("used", "leaked", 1))

    with pytest.raises(DomainError, match="signal leaked is declared more than once"):
        read_domain(text, "probe", budget=request_budget())


# A section's own refusal reaches the caller as the DomainError every other fault of the file is.
# am[verifies a-rel-nd-reading-section-1018@98f298] am[verifies a-rel-nd-sections-1018@c1f2c6]
@pytest.mark.parametrize(
    "section, message",
    [
        (READING_SECTION.replace('"Does the text say customer data left the system?"', ""), "probe: A reading declaration is not well formed"),
        (READING_SECTION.replace('(gc-reading-language "en")\n', ""), "exactly once"),
        (BIGRAPH_SECTION.replace("(gc-brs-in task seat)", "(gc-brs-in task)"), "probe: "),
    ],
)
def test_a_malformed_section_form_is_a_domain_error_naming_the_file(section: str, message: str) -> None:
    text = domain_text('(gc-signal used "read by a rule")\n' + READING_SECTION + section + THEORY)

    with pytest.raises(DomainError, match=message):
        read_domain(text, "probe", budget=request_budget())


# am[verifies a-rel-nd-sections-1018@c1f2c6] am[related a-rel-brs-section-1018@b63f59]
def test_a_bigraph_section_is_read_into_the_domain_and_a_domain_without_sections_has_none() -> None:
    domain = read_domain(domain_text('(gc-signal used "read by a rule")\n' + READING_SECTION + BIGRAPH_SECTION + THEORY), "probe", budget=request_budget())

    assert domain.bigraph is not None
    assert [control.name for control in domain.bigraph.controls] == ["Task", "Seat"]
    assert [entity.id for entity in domain.bigraph.entities] == ["seat", "task"]
    bare = read_domain(domain_text('(gc-signal used "read by a rule")\n(normally r1 (signal used) (candidate act))\n'),
                       "probe", budget=request_budget())
    assert (bare.readings, bare.bigraph) == (None, None)


# A signal no rule body reads changes nothing a review concludes, but a shared domain may declare a
# condition only planning reads, so the domain lists it, as the review record does, and refuses
# nothing; a rule reading (signal ?s) reads every signal.
# am[verifies a-rel-nd-unread-signals-1018@f57790] am[verifies i-rel-deadsignal-1016@c0cf3b]
def test_a_declared_signal_no_rule_reads_is_listed_rather_than_refused() -> None:
    text = domain_text(
        '(gc-signal used "read by a rule")\n(gc-signal dead "read by nothing")\n'
        '(gc-signal idle "read by nothing either")\n'
        "(normally r1 (signal used) (candidate act))\n"
        "(normally r2 (candidate act) (contributes act served positive))\n"
    )

    domain = read_domain(text, "probe", budget=request_budget())
    assert domain.unread_signals == ("dead", "idle")
    assert reviewed(domain, packet(reading("used"))).to_dict()["domain"]["unread_signals"] == ["dead", "idle"]
    schematic = read_domain(text + "(normally r3 (signal ?s) (candidate act))\n", "probe", budget=request_budget())
    assert schematic.unread_signals == ()


# am[verifies a-rel-domain-1016@6f8fc8]
@pytest.mark.parametrize(
    "theory, message",
    [
        ("(happens e 1)", "not a form the review can trace"),
        ("(prefer r1 rMissing)", "must name at least two rule labels the theory declares"),
        ("(normally r1 (signal used) (candidate act))", "rule label r1 labels more than one rule"),
    ],
)
def test_untraceable_or_dangling_theory_forms_are_rejected(theory: str, message: str) -> None:
    text = domain_text(
        '(gc-signal used "read")\n(normally r1 (signal used) (candidate act))\n' + theory + "\n"
    )

    with pytest.raises(DomainError, match=message):
        read_domain(text, "probe", budget=request_budget())


# The one reader of domain and declaration files (c-rel-agrees-dr-pymetta-atoms-1018): each form's
# exact text with the atom pymetta parses from it, strings unescaped, and a FormsUnreadable naming
# the problem and where it is for a directive or any text outside a form.
# am[verifies a-rel-nd-pymetta-atoms-1018@f047df]
def test_parsed_forms_answers_each_forms_text_and_atom_and_refuses_text_outside_a_form() -> None:
    from goal_chainer.runtime.evaluator import plain_value

    text = '; a comment\n(gc-signal used "a \\"quoted\\" word")\n(normally r1 (signal used) (candidate act))\n'
    forms = parsed_forms(text, budget=None)

    assert [form.text for form, _ in forms] == [
        '(gc-signal used "a \\"quoted\\" word")', "(normally r1 (signal used) (candidate act))"
    ]
    assert plain_value(forms[0][1])[2] == 'a "quoted" word'
    for bad, problem in (("(a)\n!(b)\n", "text outside a form: '!'"), ('(a)\n"stray"\n', "text outside a form: '\"'")):
        with pytest.raises(FormsUnreadable) as raised:
            parsed_forms(bad, budget=None)
        assert raised.value.problem == problem and bad.count("\n", 0, raised.value.index) == 1


# am[verifies a-rel-domain-1016@6f8fc8]
def test_text_outside_a_form_is_rejected_so_a_domain_cannot_carry_executable_metta() -> None:
    text = domain_text('(gc-signal used "read")\n!(normally r1 (signal used) (candidate act))\n')

    with pytest.raises(DomainError, match="text outside a form"):
        read_domain(text, "probe", budget=request_budget())


# A string literal between forms is text outside a form too, refused at its line and never
# skipped as if it were a comment.
# am[verifies a-rel-domain-1016@6f8fc8] am[verifies a-rt-metta-forms-shared-1017@db105c]
def test_a_string_literal_outside_every_form_is_rejected_at_its_line() -> None:
    text = domain_text('(gc-signal used "read")\n"a stray note"\n(normally r1 (signal used) (candidate act))\n')
    line = text.splitlines().index('"a stray note"') + 1

    with pytest.raises(DomainError, match=re.escape(f"probe:{line}: text outside a form: '\"'")):
        read_domain(text, "probe", budget=request_budget())


# am[verifies a-rel-domain-1016@6f8fc8] am[rests-on c-rel-absent-cue-refutes-1016@26eafb]
def test_signals_take_no_text_cues() -> None:
    text = domain_text('(gc-signal used "read" (cues "words"))\n(normally r1 (signal used) (candidate act))\n')

    with pytest.raises(DomainError, match='gc-signal ID "description"'):
        read_domain(text, "probe", budget=request_budget())


# Error is MeTTa's error constructor, so a form that writes the symbol is refused at its line,
# naming the expression that writes it, whether as an id, inside a rule or in a section.
# am[verifies a-ev-pk-error-name-refused-1018@ce3a7f] am[verifies c-ev-pk-error-symbol-poisons-lists-1018@8f8f6b]
@pytest.mark.parametrize(
    "written, term",
    [
        ('(gc-action Error "Act" "do it" (authority advisory))', '(gc-action Error "Act" "do it" (authority advisory))'),
        ('(gc-signal Error "read")', '(gc-signal Error "read")'),
        ('(gc-goal Error owner individual 0.5 "served" (priority-source human:test))',
         '(gc-goal Error owner individual 0.5 "served" (priority-source human:test))'),
        ("(normally r2 (signal Error) (candidate act))", "(signal Error)"),
        ("(gc-brs-entity Error Task)", "(gc-brs-entity Error Task)"),
        ('(gc-reading-proposition Error "Data left." "Did data leave?")',
         '(gc-reading-proposition Error "Data left." "Did data leave?")'),
    ],
    ids=["an action", "a signal", "a goal", "inside a rule", "a bigraph entity", "a reading proposition"],
)
def test_a_form_that_writes_the_symbol_error_is_refused_at_its_line(written: str, term: str) -> None:
    text = domain_text('(gc-signal used "read")\n(normally r1 (signal used) (candidate act))\n' + written + "\n")
    line = text.splitlines().index(written) + 1

    with pytest.raises(DomainError, match=re.escape(f"probe:{line}: {term} writes the symbol Error")):
        read_domain(text, "probe", budget=request_budget())


# The string "Error" is data and a longer symbol is a name like any other.
# am[verifies a-ev-pk-error-name-refused-1018@ce3a7f]
def test_a_string_error_and_a_longer_symbol_stay_data_and_names() -> None:
    text = domain_text('(gc-signal Errors "Error, as a word in a description")\n(normally r1 (signal Errors) (candidate act))\n')

    domain = read_domain(text, "probe", budget=request_budget())

    assert domain.signal_ids == ("Errors",)
    assert domain.signals[0].description == "Error, as a word in a description"


# am[verifies a-rel-domain-1016@6f8fc8]
def test_the_digest_ignores_comments_and_layout_but_not_a_rule() -> None:
    base = domain_text('(gc-signal used "read")\n(normally r1 (signal used) (candidate act))\n')
    relaid = base.replace("(normally r1 (signal used) (candidate act))", "; a note\n(normally   r1\n  (signal used)\n  (candidate act))")
    changed = base.replace("(candidate act)", "(must (do act))")

    digest = read_domain(base, "a", budget=request_budget()).digest
    assert read_domain(relaid, "b", budget=request_budget()).digest == digest
    assert read_domain(changed, "c", budget=request_budget()).digest != digest


# The digest covers what the review reads, the core's forms and the signals the sections declare,
# each whole: the packaged task-control section and a reading question leave it alone, while
# renaming a proposition, changing what it states, or changing a core form the review reads moves it.
# am[verifies a-rel-nd-review-digest-scope-1018@96d474] am[verifies i-rel-digest-covers-unread-sections-1018@975b71]
def test_the_digest_covers_the_core_and_the_signals_sections_declare_and_nothing_else() -> None:
    packaged = (resources.files("goal_chainer") / "domains" / "data" / "task_control.metta").read_text(encoding="utf-8")
    # Whole forms are dropped by their head, through the scanner the loader reads with, so a section
    # form spanning several lines, such as a reaction, goes whole.
    bare = "\n".join(form.text for form in top_level_forms(packaged)
                     if form.text[1:].split(None, 1)[0] not in SECTION_HEADS)
    assert read_domain(bare, "bare", budget=request_budget()).bigraph is None
    assert read_domain(bare, "bare", budget=request_budget()).digest == packaged_domain("task-control", budget=request_budget()).digest

    with_readings = domain_text('(gc-signal used "read by a rule")\n' + READING_SECTION + THEORY)
    reworded = with_readings.replace("Does the text say customer data left the system?", "Did customer data leave?")
    renamed = with_readings.replace("(gc-reading-proposition leaked", "(gc-reading-proposition escaped").replace(
        "(signal leaked)", "(signal escaped)")
    restated = with_readings.replace('"Customer data left the system."', '"Customer data was copied out."')
    reruled = with_readings.replace("(normally r1 (signal used) (candidate act))", "(normally r1 (signal used) (must (do act)))")
    digest = read_domain(with_readings, "a", budget=request_budget()).digest
    assert read_domain(reworded, "b", budget=request_budget()).digest == digest
    for moved in (renamed, restated, reruled):
        assert moved != with_readings
        assert read_domain(moved, "c", budget=request_budget()).digest != digest


# am[verifies a-rel-domain-1016@6f8fc8]
def test_a_dimension_only_a_schematic_rule_estimates_is_not_reported_unestimated() -> None:
    text = domain_text(
        '(gc-dimension risk cost "risk")\n(gc-signal used "read")\n'
        "(normally r1 (signal used) (candidate act))\n"
        "(normally r2 (candidate ?a) (effect ?a ?d neutral deterministic))\n"
    )

    assert read_domain(text, "probe", budget=request_budget()).unestimated_dimensions == ()


# A priority multiplies and sums into every path through its goal, so one that is NaN, infinite
# or negative is refused with the goal named, an integer float() cannot convert included, and zero
# of either sign is still a priority.
# am[verifies a-rel-finite-priority-1017@262e4d] am[verifies a-rel-finite-number-1017@924176]
# am[verifies a-integrate-relevance-numeric-boundaries-1018@4c2a7d] am[verifies c-rel-num-loader-overflow-1018@69c7d2]
@pytest.mark.parametrize(
    ("priority", "message"),
    [
        ("nan", "probe: priority of goal served is not a finite number: nan"),
        ("inf", "probe: priority of goal served is not a finite number: inf"),
        ("-inf", "probe: priority of goal served is not a finite number: -inf"),
        ("-0.5", "probe: goal priority must be a finite non-negative number: served has -0.5"),
        ("1" + "0" * 400, f"probe: priority of goal served is not a finite number: {BEYOND_FLOAT}"),
        ("-1" + "0" * 400, f"probe: priority of goal served is not a finite number: {BEYOND_FLOAT}"),
    ],
    ids=["nan", "inf", "minus-inf", "negative", "ten-to-the-400", "minus-ten-to-the-400"],
)
def test_a_goal_priority_that_is_not_a_finite_non_negative_number_is_refused(priority: str, message: str) -> None:
    with pytest.raises(DomainError, match=re.escape(message)):
        read_domain(goal_priority(priority), "probe", budget=request_budget())


# Priorities whose sum, added in declaration order as the ranking's fold adds paths, passes the
# largest double are refused, so no review records an inf: two of 1e308, and three just below the
# largest double whose exact sum math.fsum still rounds to it but whose fold overflows, as the
# policy's own sum-over-paths shows.
# am[verifies a-v2m-priority-sum-finite-1020@7596cf] am[verifies c-v2m-priority-sum-bound-1020@7fb487]
def test_goals_whose_priorities_sum_past_the_largest_double_are_refused() -> None:
    largest = sys.float_info.max
    near = (largest - math.ulp(largest), 0.75 * math.ulp(largest), 0.6 * math.ulp(largest))
    goals = "".join(f"(gc-goal g{index} owner individual {priority!r} \"g\" (priority-source human:test))\n"
                    for index, priority in enumerate(near))
    folded = helper_call("gc-relevance-fold", term("gc-relevance-rule-named", "sum-over-paths"), items(near))

    assert math.isinf(folded) and math.isfinite(math.fsum(near))
    for priorities in (goal_priority("1e308").replace("(gc-dimension", "(gc-goal again owner individual 1e308 \"g\" "
                                                      "(priority-source human:test))\n(gc-dimension"),
                       goal_priority("0").replace("(gc-dimension", goals + "(gc-dimension")):
        with pytest.raises(DomainError, match="added in declaration order, pass the largest double"):
            read_domain(priorities, "probe", budget=request_budget())


# At the bound, two goals of half the largest double that one action serves fully, the review
# records the largest double as that action's projection, in a record JSON holds with no inf.
# am[verifies a-v2m-priority-sum-finite-1020@7596cf] am[verifies c-v2m-priority-sum-bound-1020@7fb487]
def test_priorities_summing_to_the_largest_double_are_recorded() -> None:
    half = repr(sys.float_info.max / 2)
    text = goal_priority(half).replace(
        "(gc-dimension", f'(gc-goal again owner individual {half} "g" (priority-source human:test))\n(gc-dimension')
    text += ("(normally r2 (candidate act) (contributes act served strongly-positive))\n"
             "(normally r3 (candidate act) (contributes act again strongly-positive))\n")

    record = reviewed(read_domain(text, "probe", budget=request_budget()), packet(reading("used"))).to_dict()

    assert next(item for item in record["candidates"] if item["action"] == "act")["projection"] == sys.float_info.max
    json.dumps(record, allow_nan=False)


# am[verifies a-rel-finite-number-1017@924176]
# am[verifies a-integrate-relevance-numeric-boundaries-1018@4c2a7d] am[verifies c-rel-num-loader-overflow-1018@69c7d2]
@pytest.mark.parametrize(("rank", "shown"), [("nan", "nan"), ("inf", "inf"), ("-inf", "-inf"), ("1" + "0" * 400, BEYOND_FLOAT)],
                         ids=["nan", "inf", "minus-inf", "ten-to-the-400"])
def test_an_authority_rank_that_is_not_finite_is_refused_as_a_domain_error(rank: str, shown: str) -> None:
    text = goal_priority("0.5").replace("(gc-authority advisory 1 ", f"(gc-authority advisory {rank} ")

    with pytest.raises(DomainError, match=re.escape(f"probe: rank of authority advisory is not a finite number: {shown}")):
        read_domain(text, "probe", budget=request_budget())


# am[verifies a-rel-finite-priority-1017@262e4d]
@pytest.mark.parametrize("priority", ["0", "-0.0", "1e-300"])
def test_a_zero_or_tiny_goal_priority_loads(priority: str) -> None:
    assert [goal.weight for goal in read_domain(goal_priority(priority), "probe", budget=request_budget()).goals] == [float(priority)]


# Every integer float() converts is still a priority, read as its float, up to the largest float.
# am[verifies a-integrate-relevance-numeric-boundaries-1018@4c2a7d] am[verifies c-rel-num-loader-overflow-1018@69c7d2]
@pytest.mark.parametrize("priority", ["1" + "0" * 308, str(FLOAT_EDGE - 1)], ids=["ten-to-the-308", "below-float-edge"])
def test_a_priority_up_to_the_largest_float_loads_as_its_float(priority: str) -> None:
    goals = read_domain(goal_priority(priority), "probe", budget=request_budget()).goals

    assert [goal.weight for goal in goals] == [float(int(priority))]


# pymetta reads an integer literal of any length as an int, and the interpreter writes one of more
# digits than its limit only by raising ValueError, so no digest, rendering or refusal could write a
# form holding one: it is refused at the form's line, at any depth, before the Error check renders it.
# am[verifies a-integrate-relevance-numeric-boundaries-1018@4c2a7d] am[verifies c-rel-num-loader-unwritable-1018@75a0e7]
@pytest.mark.parametrize(
    ("form", "head"),
    [("(gc-goal served owner individual {huge} \"served\" (priority-source human:test))", "gc-goal"),
     ("(normally r2 (signal used) (candidate act (cost {huge})))", "normally"),
     ("(normally r2 (signal used) (Error (cost {huge})))", "normally")],
    ids=["priority", "inside-a-rule", "beside-error"],
)
def test_a_form_writing_an_integer_too_long_to_write_is_refused_at_its_line(form: str, head: str) -> None:
    huge = "1" + "0" * sys.get_int_max_str_digits()
    text = goal_priority("0.5") + form.format(huge=huge) + "\n"
    line = text.count("\n", 0, text.rindex(f"({head} ")) + 1

    message = (f"probe:{line}: ({head} ...) writes an integer of more than {sys.get_int_max_str_digits()} digits, "
               "which the interpreter cannot write as text")
    with pytest.raises(DomainError, match=f"^{re.escape(message)}$"):
        read_domain(text, "probe", budget=request_budget())


# A Goal is a priority every path through it multiplies by, so it refuses a weight with no finite
# float with its ValueError, an integer float() cannot convert included, rather than OverflowError.
# am[verifies a-integrate-relevance-numeric-boundaries-1018@4c2a7d] am[verifies c-rel-num-goal-direct-only-1018@21acd2]
@pytest.mark.parametrize("weight", [10**400, -10**400, FLOAT_EDGE], ids=["ten-to-the-400", "minus-ten-to-the-400", "float-edge"])
def test_a_goal_whose_weight_has_no_finite_float_is_refused_with_its_value_error(weight: int) -> None:
    with pytest.raises(ValueError) as raised:
        Goal(id="served", owner="owner", statement="served", weight=weight, kind="individual")

    assert str(raised.value) == f"goal priority must be a finite non-negative number: served has {BEYOND_FLOAT}"


# A finite non-negative weight is kept exactly as given: an int stays that int.
# am[verifies a-integrate-relevance-numeric-boundaries-1018@4c2a7d] am[verifies a-rel-finite-priority-1017@262e4d]
@pytest.mark.parametrize("weight", [3, 0, 0.5, FLOAT_EDGE - 1], ids=["three", "zero", "half", "below-float-edge"])
def test_a_goal_keeps_a_finite_non_negative_weight_as_given(weight: float) -> None:
    goal = Goal(id="served", owner="owner", statement="served", weight=weight, kind="individual")

    assert goal.weight == weight and type(goal.weight) is type(weight)


# A bound the command line gives is read as written: an inference bound as a whole number of any
# size, never through float, and a timeout as a positive finite float, up to the largest float.
# am[verifies a-integrate-relevance-numeric-boundaries-1018@4c2a7d] am[verifies c-rel-num-cli-int-bound-1018@db268a]
@pytest.mark.parametrize(
    ("bound", "written", "read"),
    [("--inference-budget", "1" + "0" * 400, 10**400), ("--inference-budget", "7", 7),
     ("--timeout-seconds", "1.7976931348623157e308", sys.float_info.max), ("--timeout-seconds", "0.5", 0.5)],
    ids=["inferences-ten-to-the-400", "inferences-seven", "timeout-largest-float", "timeout-half"],
)
def test_the_domain_command_reads_a_positive_bound_as_written(bound: str, written: str, read: float, monkeypatch, capsys) -> None:
    seen = []
    monkeypatch.setattr(relevance_cli, "_result", lambda args: seen.append(args) or {})
    limits = dict(zip(CLI_LIMITS[::2], CLI_LIMITS[1::2], strict=True)) | {bound: written}

    assert main(["relevance", "domain", "--json", *(f"{flag}={value}" for flag, value in limits.items())]) == 0
    (args,) = seen
    budget = relevance_cli._limits(args)
    kept = budget.inference_budget if bound == "--inference-budget" else budget.timeout_seconds
    assert kept == read and type(kept) is type(read)


# A bound that is no positive number is a usage error before any budget is made.
# am[verifies a-integrate-relevance-numeric-boundaries-1018@4c2a7d] am[verifies c-rel-num-cli-int-bound-1018@db268a]
@pytest.mark.parametrize(
    ("bound", "written", "said"),
    [("--inference-budget", "0", "must be a positive finite number"),
     ("--inference-budget", "-1" + "0" * 400, "must be a positive finite number"),
     ("--inference-budget", "1.5", "not a number"),
     ("--timeout-seconds", "1e400", "must be a positive finite number"),
     ("--timeout-seconds", "nan", "must be a positive finite number"),
     ("--timeout-seconds", "-inf", "must be a positive finite number"),
     ("--timeout-seconds", "0", "must be a positive finite number")],
    ids=["inferences-zero", "inferences-minus-ten-to-the-400", "inferences-fraction", "timeout-overflowing",
         "timeout-nan", "timeout-minus-inf", "timeout-zero"],
)
def test_the_domain_command_refuses_a_bound_that_is_no_positive_number(bound: str, written: str, said: str, capsys) -> None:
    limits = dict(zip(CLI_LIMITS[::2], CLI_LIMITS[1::2], strict=True)) | {bound: written}

    with pytest.raises(SystemExit) as usage:
        main(["relevance", "domain", "--json", *(f"{flag}={value}" for flag, value in limits.items())])
    assert usage.value.code == 2 and said in capsys.readouterr().err


# am[verifies a-rel-cli-1016@8f8ec8]
def test_the_domain_command_lists_the_packaged_domain_as_json(capsys: pytest.CaptureFixture[str]) -> None:
    domain = packaged_domain("task-control", budget=request_budget())

    assert main(["relevance", "domain", "--json", *CLI_LIMITS]) == 0
    listed = json.loads(capsys.readouterr().out)

    assert listed["source"] == "goal_chainer/domains/data/task_control.metta"
    assert listed["digest"] == domain.digest
    assert [action["id"] for action in listed["actions"]] == list(domain.action_ids)
    assert [signal["id"] for signal in listed["signals"]] == list(domain.signal_ids)
    assert listed["unestimated_dimensions"] == list(domain.unestimated_dimensions)
    assert listed["unread_signals"] == [] == list(domain.unread_signals)
    assert listed["rules"] == len(domain.rules)


# The check command compares a stored review with the current packet under the packet's budget,
# loading the engine whose identity it compares within that budget: the packet the stale-worker
# review was decided on leaves it fresh, and one where the graph-quality reading it rested on moved
# makes it stale, each printed as the freshness report.
# am[verifies a-rel-cli-1016@8f8ec8] am[verifies a-ie-host-freshness-1018@ff618a]
def test_the_check_command_reports_a_stored_review_fresh_or_stale(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    worker = (
        reading("review_open"),
        reading("stale_parent_goal", "detected", "deterministic", source="goal-graph"),
        reading("active_parent_path", "refuted", "deterministic", source="goal-graph"),
        reading("authority_unavailable", "refuted", "deterministic", source="policy"),
    )
    decided = packet(*worker, reading("low_graph_quality", "refuted", "measured"))
    moved = packet(*worker, reading("low_graph_quality", "detected", "measured"))
    stored = tmp_path / "review.json"
    stored.write_text(json.dumps(reviewed(packaged_domain("task-control", budget=request_budget()), decided).to_dict()),
                      encoding="utf-8")
    reports = []
    for current in (decided, moved):
        written = tmp_path / "packet.json"
        written.write_text(json.dumps(current.to_dict()), encoding="utf-8")
        assert main(["relevance", "check", "--review", str(stored), "--packet", str(written), "--json"]) == 0
        reports.append(json.loads(capsys.readouterr().out))

    assert [report["status"] for report in reports] == ["fresh", "stale"]
    assert [change["signal"] for change in reports[1]["changes"]] == ["low_graph_quality"]


# am[verifies a-rel-cli-1016@8f8ec8]
def test_the_domain_command_reads_a_domain_file_and_prints_a_summary(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "probe.metta"
    path.write_text(domain_text('(gc-signal used "read")\n(normally r1 (signal used) (candidate act))\n'), encoding="utf-8")

    assert main(["relevance", "domain", "--domain-file", str(path), *CLI_LIMITS]) == 0
    printed = capsys.readouterr().out.splitlines()

    assert printed[0] == f"probe (probe-v1, {read_domain(path.read_text(encoding='utf-8'), 'probe', budget=request_budget()).digest})"
    assert printed[1] == "  1 actions, 1 goals, 1 signals, 1 dimensions, 1 rules"
    assert printed[2] == "  no rule estimates: cost"


# am[verifies a-rel-cli-1016@8f8ec8]
# am[verifies a-rel-finite-priority-1017@262e4d]
@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--domain", "no-such-domain"], "no packaged domain named no-such-domain"),
        (["--domain-file", "{missing}"], "cannot be read as UTF-8 text: no such file"),
        (["--domain-file", "{binary}"], "cannot be read as UTF-8 text: invalid start byte at byte 0"),
        (["--domain-file", "{unknown}"], "unknown declaration gc-signals"),
        (["--domain-file", "{nan}"], "priority of goal served is not a finite number: nan"),
    ],
    ids=["unknown-name", "missing-file", "binary-file", "unknown-declaration", "nan-priority"],
)
def test_a_domain_that_cannot_be_read_is_a_typed_error_with_exit_status_one(
    arguments: list[str], message: str, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    unknown = tmp_path / "unknown.metta"
    unknown.write_text(domain_text('(gc-signals used "read")\n'), encoding="utf-8")
    nan = tmp_path / "nan.metta"
    nan.write_text(goal_priority("nan"), encoding="utf-8")
    binary = tmp_path / "binary.metta"
    binary.write_bytes(b"\xff")
    filled = [part.format(missing=tmp_path / "absent.metta", unknown=unknown, nan=nan, binary=binary)
              for part in arguments]

    assert main(["relevance", "domain", *filled, "--json", *CLI_LIMITS]) == 1
    error = json.loads(capsys.readouterr().out)
    assert error["ok"] is False
    assert error["error"]["code"] == "invalid-domain"
    assert message in error["error"]["message"]

    assert main(["relevance", "domain", *filled, *CLI_LIMITS]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("goalchainer relevance error [invalid-domain]: ")


# Every way a caller's path or file can fail to be domain text is a DomainError naming it, never an
# escaping decode, path or OS error, while what reading valid text raises, such as the caller's
# budget running out, passes through as it is.
# am[verifies a-integrate-domain-file-failures-1018@359226] am[verifies a-rel-file-text-normalizes-1018@2afe58]
def test_a_file_that_is_not_domain_text_is_a_domain_error_naming_it(tmp_path, monkeypatch) -> None:
    binary = tmp_path / "binary.metta"
    binary.write_bytes(b"(gc-domain \"probe\")\n\xff\n")
    valid = tmp_path / "valid.metta"
    valid.write_text(goal_priority("0.5"), encoding="utf-8")

    for path, message in ((binary, r"binary\.metta: cannot be read as UTF-8 text: invalid start byte at byte 20"),
                          (tmp_path / "absent.metta", r"absent\.metta: cannot be read as UTF-8 text: no such file"),
                          (tmp_path, "cannot be read as UTF-8 text: it is a directory"),
                          ("bad\x00domain.metta", r"'bad\\x00domain\.metta': cannot be read as UTF-8 text: it is no usable path"),
                          ("~user-that-does-not-exist/domain.metta",
                           r"'~user-that-does-not-exist/domain\.metta': cannot be read as UTF-8 text: it is no usable path")):
        with pytest.raises(DomainError, match=message):
            load_domain(path, budget=request_budget())
    with pytest.raises(InferenceBudgetExceeded):
        load_domain(valid, budget=RunBudget(inference_budget=1, timeout_seconds=600))

    # A file the process may not read fails the same way whatever user runs the test.
    # am[verifies a-integrate-domain-file-failures-1018@359226]
    def refuse(self: Path, *_: object, **__: object) -> str:
        raise PermissionError(13, "Permission denied", str(self))

    monkeypatch.setattr(Path, "read_text", refuse)
    with pytest.raises(DomainError, match=r"valid\.metta: cannot be read as UTF-8 text: Permission denied"):
        load_domain(valid, budget=request_budget())
