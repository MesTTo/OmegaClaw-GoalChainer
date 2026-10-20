"""Purpose: verify that a domain's procedures file reads into typed procedures and investigators
only when the procedure policy accepts it: the packaged task-control file loads, every malformed
shape, undeclared name, literal the domain's bigraph section does not anchor, duplicate, dangling or
cyclic After order, contradictory prediction, cycle of Derives undoing one another and directive is
refused naming its problem, Derives that undo one another only across a signal no Derive writes are
kept, negation folds to one representation, a library reads at most one track promotion, a count of
trials and a probability, and on generated libraries with random names and step graphs the
policy's verdict and problems equal an independent oracle's."""

from __future__ import annotations

import dataclasses

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from goal_chainer.domains.loader import packaged_domain
from goal_chainer.planning.procedures import (
    AchieveStep,
    ActStep,
    NegatedLiteral,
    ProcedureError,
    Promotion,
    SignalLiteral,
    StatementLiteral,
    literal_text,
    load_procedures,
    negate,
    packaged_procedures,
    read_literal,
    read_procedures,
)
from planning_support import RESTORES, UNANCHORED, task_domain
from request_support import budget

DOMAIN = task_domain()


# am[verifies a-ev-pl-ag-representation-1017@ca0cfc] am[verifies a-ev-pl-ag-procedures-file-1017@70f843]
def test_the_packaged_task_control_procedures_load_in_declared_order() -> None:
    library = packaged_procedures(DOMAIN, budget=budget())
    assert library.policy_version == DOMAIN.policy_version
    assert [procedure.name for procedure in library.procedures] == [
        "release-by-pause", "reach-safe-point", "release-by-handoff", "ask-receiving-owner", "reach-by-release",
    ]
    pause = library.procedures[0]
    assert pause.achieves == (NegatedLiteral(SignalLiteral("resource_contention")),)
    assert pause.when[2] == StatementLiteral(RESTORES)
    assert pause.steps == (
        AchieveStep("reach", SignalLiteral("safe_point_reachable"), ()),
        ActStep("pause", "pause_recoverably", ("reach",)),
    )
    released = NegatedLiteral(SignalLiteral("resource_contention"))
    assert [p.name for p in library.achieving(released)] == ["release-by-pause", "release-by-handoff"]
    assert [i.name for i in library.investigators_of(StatementLiteral(RESTORES))] == ["restore-drill"]
    assert library.digest.startswith("sha256:")


# A statement keeps the one spelling SNARS's codec emits, whatever whitespace the file used.
# am[verifies a-ev-pl-ag-representation-1017@ca0cfc]
def test_a_statement_keeps_snars_spelling_of_its_tree() -> None:
    text = ("(gc-procedures task-control-v1)\n(gc-procedure p (Achieves (Signal review_open))"
            ' (When (Statement (sn  p so "restores"\n ((arg s (sn c "checkpoint-store")) (arg o (sn c "task-state"))))))'
            " (Steps (Step s act escalate (After))))")
    library = read_procedures(text, "spelling.metta", DOMAIN, budget=budget())
    assert library.procedures[0].when == (StatementLiteral(RESTORES),)


# am[verifies a-ev-pl-ag-representation-1017@ca0cfc]
def test_negation_folds_and_never_nests() -> None:
    signal = SignalLiteral("review_open")
    assert negate(negate(signal)) == signal
    with pytest.raises(TypeError):
        NegatedLiteral(NegatedLiteral(signal))  # type: ignore[arg-type]
    text = ("(gc-procedures task-control-v1)\n(gc-procedure p (Achieves (Not (Not (Signal review_open))))"
            " (When) (Steps (Step s act escalate (After))))")
    assert read_procedures(text, "fold.metta", DOMAIN, budget=budget()).procedures[0].achieves == (signal,)


# A goal literal a caller such as the CLI reads goes through the library's own grammar.
# am[verifies a-ev-pk-python-api-1018@db9b94]
@pytest.mark.parametrize(
    "text, literal",
    [
        ("(Signal review_open)", SignalLiteral("review_open")),
        ("(Not (Not (Not (Signal review_open))))", NegatedLiteral(SignalLiteral("review_open"))),
        (f"(Statement {RESTORES.replace(' ', '  ')})", StatementLiteral(RESTORES)),
    ],
)
def test_a_goal_literal_reads_through_the_library_grammar(text: str, literal) -> None:
    assert read_literal(text, "goal", budget=budget()) == literal


# am[verifies a-ev-pk-python-api-1018@db9b94]
@pytest.mark.parametrize(
    "text, expected",
    [
        ("(Signal review_open) (Signal review_open)", "a literal is one form"),
        ("!(Signal review_open)", "goal: text outside a form: '!'"),
        ("", "a literal is one form"),
        ('(Signal "review_open")', "(Signal NAME)"),
        ("(Statement (if a b))", "is not a SNARS statement"),
        ("(Signal review_open", "goal: unbalanced ("),
        ("Signal", "goal: text outside a form: 'S'"),
    ],
)
def test_a_goal_literal_that_is_not_one_literal_is_refused(text: str, expected: str) -> None:
    with pytest.raises(ProcedureError, match="^goal") as refused:
        read_literal(text, "goal", budget=budget())
    assert expected in str(refused.value)


STATEMENTS = (RESTORES, '(sn p so "serves" ((arg s (sn c "task")) (arg o (sn c "parent-goal"))))')


# am[verifies a-ev-pk-python-api-1018@db9b94]
@settings(max_examples=40, deadline=None)
@given(st.one_of(st.sampled_from(DOMAIN.signal_ids).map(SignalLiteral),
                 st.sampled_from(STATEMENTS).map(lambda text: read_literal(f"(Statement {text})", "drawn", budget=budget()))),
       st.booleans())
def test_literal_text_reads_back_to_the_same_literal(positive, negated: bool) -> None:
    literal = negate(positive) if negated else positive
    assert read_literal(literal_text(literal), "round-trip", budget=budget()) == literal


# A domain declaring no bigraph section anchors nothing, so the planner could judge none of the
# library's literals and the policy refuses each; the packaged domain declares one, so it is taken away.
# am[verifies a-ev-pk-acceptance-anchors-1018@cb1e61]
def test_a_domain_without_a_bigraph_section_refuses_every_literal() -> None:
    bare = dataclasses.replace(packaged_domain("task-control", budget=budget()), bigraph=None)
    with pytest.raises(ProcedureError) as refused:
        packaged_procedures(bare, budget=budget())
    assert "unanchored-literal (release-by-pause (Signal resource_contention))" in str(refused.value)
    assert "unanchored-literal (restore-drill (Statement" in str(refused.value)


# A procedures path that is unusable, missing, a directory or not UTF-8 text is the caller's malformed
# input, refused as a ProcedureError naming the path and the cause rather than escaping as a path, OS or
# decoding error.
# am[verifies a-integrate-planner-input-failures-1018@b84418] am[verifies c-integrate-request-input-leaks-762662a-1018@380521]
def test_a_procedures_file_that_is_not_utf8_text_is_refused_naming_it(tmp_path) -> None:
    path = tmp_path / "procedures.metta"
    path.write_bytes(b"(gc-procedures task-control-v1)\n\xff\n")
    read = {path: "invalid start byte at byte 32", tmp_path / "missing.metta": "no such file",
            tmp_path: "it is a directory"}
    for unreadable, cause in read.items():
        with pytest.raises(ProcedureError) as refused:
            load_procedures(unreadable, DOMAIN, budget=budget())
        assert str(refused.value) == f"{unreadable.resolve()}: cannot be read as UTF-8 text: {cause}"
    for unusable in ("bad\x00procedures.metta", "~nobody-here/x.metta"):
        with pytest.raises(ProcedureError) as refused:
            load_procedures(unusable, DOMAIN, budget=budget())
        assert str(refused.value).startswith(f"{unusable!r}: cannot be read as UTF-8 text: it is no usable path (")


VERSION = "(gc-procedures task-control-v1)\n"
STEP = "(Steps (Step s act escalate (After)))"
# Two Derives turning completion_proximate over and back once review_open holds, and two copying review_open
# into completion_proximate, one per value.
DERIVE_CYCLE = ("(gc-procedure d1 (Achieves (Not (Signal completion_proximate))) (When) (Steps "
                "(Step s achieve (Signal review_open) (After)) (Step t achieve (Signal completion_proximate) (After))))"
                "(gc-procedure d2 (Achieves (Signal completion_proximate)) (When) (Steps "
                "(Step s achieve (Signal review_open) (After)) (Step t achieve (Not (Signal completion_proximate)) (After))))")
MIRROR_PAIR = ("(gc-procedure copy-on (Achieves (Signal completion_proximate)) (When) "
               "(Steps (Step s achieve (Signal review_open) (After))))"
               "(gc-procedure copy-off (Achieves (Not (Signal completion_proximate))) (When) "
               "(Steps (Step s achieve (Not (Signal review_open)) (After))))")


# Each malformed file is refused, naming its problem.
# am[verifies a-ev-pl-ag-representation-1017@ca0cfc] am[verifies a-ev-fb-achieves-once-1018@ba60a9]
@pytest.mark.parametrize(
    "text, expected",
    [
        ("!(gc-procedures task-control-v1)", ":1: text outside a form: '!'"),
        ("(gc-procedures task-control-v1)\n!(gc-procedure p)", ":2: text outside a form: '!'"),
        ("(gc-procedures task-control-v1) (gc-procedure p", ":1: unbalanced ("),
        ("(gc-procedure p (Achieves (Signal review_open)) (When) " + STEP + ")", "found 0"),
        (VERSION + VERSION, "found 2"),
        ("(gc-procedures task-control-v9)", "written for policy version task-control-v9"),
        (VERSION + "(gc-domain x)", "is not gc-procedures, gc-procedure, gc-investigator or gc-track-promotion"),
        (VERSION + "(gc-track-promotion (Trials 3) (Threshold 0.5))" * 2, "declare the track promotion at most once"),
        (VERSION + "(gc-track-promotion (Trials 3))", "(gc-track-promotion (Trials N) (Threshold THETA))"),
        (VERSION + "(gc-track-promotion (Threshold 0.5) (Trials 3))", "(gc-track-promotion (Trials N) (Threshold THETA))"),
        (VERSION + "(gc-track-promotion (Trials 3.0) (Threshold 0.5))", "Trials must be a positive integer, not 3.0"),
        (VERSION + "(gc-track-promotion (Trials 0) (Threshold 0.5))", "Trials must be a positive integer, not 0"),
        (VERSION + "(gc-track-promotion (Trials 3) (Threshold 0))", "Threshold must be a finite number in (0, 1], not 0"),
        (VERSION + "(gc-track-promotion (Trials 3) (Threshold 1.5))", "Threshold must be a finite number in (0, 1], not 1.5"),
        (VERSION + '(gc-track-promotion (Trials 3) (Threshold "half"))', "Threshold must be a finite number in (0, 1]"),
        (VERSION + "(gc-procedure p (Achieves (Signal review_open)) " + STEP + ")", "(gc-procedure NAME"),
        (VERSION + "(gc-procedure p (Goal (Signal review_open)) (When) " + STEP + ")", "(gc-procedure NAME"),
        (VERSION + "(gc-procedure p (Achieves (Signal review_open)) (When) (Steps (Step s run escalate (After))))",
         "(Step ID act ACTION"),
        (VERSION + "(gc-procedure p (Achieves (Signal review_open)) (When) (Steps (Step s act (escalate) (After))))",
         "(Step ID act ACTION"),
        (VERSION + "(gc-procedure p (Achieves (Signal review_open)) (When) (Steps (Step s act escalate (Before))))",
         "(Step ID act ACTION"),
        (VERSION + "(gc-procedure p (Achieves (Reading review_open)) (When) " + STEP + ")", "(Signal NAME)"),
        (VERSION + '(gc-procedure p (Achieves (Signal "review_open")) (When) ' + STEP + ")", "(Signal NAME)"),
        (VERSION + "(gc-procedure p (Achieves (Statement (if a b))) (When) " + STEP + ")", "is not a SNARS statement"),
        (VERSION + "(gc-procedure p (Achieves (Statement (sn c $x))) (When) " + STEP + ")", "is not a SNARS statement"),
        (VERSION + "(gc-procedure p (Achieves (Signal nonesuch)) (When) " + STEP + ")", "undeclared-signal (p nonesuch)"),
        (VERSION + "(gc-procedure p (Achieves (Signal review_open)) (When) (Steps (Step s act fly (After))))",
         "undeclared-action (p s fly)"),
        (VERSION + "(gc-procedure p (Achieves) (When) " + STEP + ")", "achieves-nothing p"),
        (VERSION + "(gc-procedure p (Achieves (Signal review_open)) (When) (Steps))", "no-steps p"),
        (VERSION + "(gc-procedure p (Achieves (Signal review_open) (Not (Signal review_open))) (When) " + STEP + ")",
         "contradictory-achieves (p (Signal review_open))"),
        (VERSION + "(gc-procedure p (Achieves (Signal review_open) (Signal review_open)) (When) " + STEP + ")",
         "(duplicate (achieves p)) (Signal review_open)"),
        (VERSION + "(gc-procedure p (Achieves (Signal review_open)) (When) "
         "(Steps (Step a act escalate (After b)) (Step b act escalate (After a))))", "cyclic-after (p (a b))"),
        (VERSION + "(gc-procedure p (Achieves (Signal review_open)) (When) "
         "(Steps (Step a act escalate (After a))))", "cyclic-after (p (a))"),
        (VERSION + DERIVE_CYCLE, "cyclic-undo (d1 d2)"),
        (VERSION + MIRROR_PAIR + "(gc-procedure d3 (Achieves (Signal review_open)) (When) "
         "(Steps (Step s achieve (Signal safe_point_reachable) (After))))", "cyclic-undo (copy-on copy-off)"),
        (VERSION + "(gc-procedure p (Achieves (Signal review_open)) (When) "
         "(Steps (Step a act escalate (After ghost))))", "dangling-after (p a ghost)"),
        (VERSION + "(gc-procedure p (Achieves (Signal review_open)) (When) "
         "(Steps (Step a act escalate (After)) (Step a act escalate (After))))", "(duplicate (step p)) a"),
        (VERSION + "(gc-procedure p (Achieves (Signal review_open)) (When) " + STEP + ")"
         "(gc-procedure p (Achieves (Signal review_open)) (When) " + STEP + ")", "(duplicate procedure) p"),
        (VERSION + "(gc-investigator i (Signal review_open)) (gc-investigator i (Signal review_open))",
         "(duplicate investigator) i"),
        (VERSION + "(gc-investigator i)", "observes-nothing i"),
        (VERSION + "(gc-investigator i (Signal nonesuch))", "undeclared-signal (i nonesuch)"),
        (VERSION + f"(gc-procedure p (Achieves (Signal {UNANCHORED[0]})) (When) " + STEP + ")",
         f"unanchored-literal (p (Signal {UNANCHORED[0]}))"),
        (VERSION + f"(gc-investigator i (Not (Signal {UNANCHORED[1]})))", f"unanchored-literal (i (Signal {UNANCHORED[1]}))"),
        (VERSION + "(gc-procedure p (Achieves (Signal review_open)) (When (Statement (sn c \"elsewhere\"))) " + STEP + ")",
         'unanchored-literal (p (Statement (sn c "elsewhere")))'),
    ],
)
def test_a_malformed_library_is_refused_naming_its_problem(text: str, expected: str) -> None:
    with pytest.raises(ProcedureError) as refused:
        read_procedures(text, "case.metta", DOMAIN, budget=budget())
    assert expected in str(refused.value)


# Two Derives copying review_open into completion_proximate, one for each value, undo each other's write
# but read review_open both ways, which no Derive writes, so they never alternate in one settling and the
# library is kept; DERIVE_CYCLE's d1 and d2 turn completion_proximate over and back once review_open holds,
# reading it both ways while they write it, the smallest cycle c-jk-pf-cx-derive-cycle-1019 found.
# am[verifies a-ev-pc-r2-policy-1019@05d393] am[verifies a-jk-pc-r2-undo-graph-1019@fc3557]
def test_derives_undoing_each_other_across_a_signal_no_derive_writes_are_kept() -> None:
    library = read_procedures(VERSION + MIRROR_PAIR, "case.metta", DOMAIN, budget=budget())
    assert [procedure.name for procedure in library.procedures] == ["copy-on", "copy-off"]


# A library declares its track promotion at most once, its trials a count and its threshold a probability, 1
# included; with none declared no record can hold.
# am[verifies a-ev-fb-promotion-1018@2ae86c] am[verifies c-ev-fb-promotion-in-library-1018@943bd4]
@pytest.mark.parametrize("declared, promotion", [
    ("", None),
    ("(gc-track-promotion (Trials 3) (Threshold 0.5))", Promotion(3, 0.5)),
    ("(gc-track-promotion (Trials 1) (Threshold 1))", Promotion(1, 1)),
])
def test_a_library_reads_its_one_track_promotion(declared: str, promotion) -> None:
    library = read_procedures(VERSION + "(gc-procedure p (Achieves (Signal review_open)) (When) " + STEP + ")\n" + declared,
                              "case.metta", DOMAIN, budget=budget())
    assert library.promotion == promotion


# --- generated libraries against an independent oracle --------------------------------------------

NAMES = st.text(alphabet="abcdefghij-", min_size=1, max_size=4).filter(lambda name: name[0] != "-")
SIGNALS = st.sampled_from(DOMAIN.signal_ids + ("ghost_signal",))
ACTIONS = st.sampled_from(DOMAIN.action_ids + ("ghost_action",))


@st.composite
def literals(draw):
    literal = (draw(SIGNALS), draw(st.booleans()))
    return literal


@st.composite
def procedures(draw):
    step_ids = draw(st.lists(NAMES, min_size=0, max_size=4))
    steps = []
    for step_id in step_ids:
        after = draw(st.lists(st.one_of(st.sampled_from(step_ids or ["x"]), NAMES), max_size=2))
        kind = draw(st.sampled_from(["act", "investigate", "achieve"]))
        target = draw(ACTIONS) if kind == "act" else draw(literals())
        steps.append((step_id, kind, target, after))
    return (draw(NAMES), draw(st.lists(literals(), max_size=3)), draw(st.lists(literals(), max_size=2)), steps)


def _literal_text(literal) -> str:
    signal, negated = literal
    return f"(Not (Signal {signal}))" if negated else f"(Signal {signal})"


def _text(procs, investigators) -> str:
    rows = ["(gc-procedures task-control-v1)"]
    for name, achieves, when, steps in procs:
        step_text = " ".join(
            f"(Step {sid} {kind} {target if kind == 'act' else _literal_text(target)} (After {' '.join(after)}))"
            for sid, kind, target, after in steps
        )
        rows.append(f"(gc-procedure {name} (Achieves {' '.join(map(_literal_text, achieves))}) "
                    f"(When {' '.join(map(_literal_text, when))}) (Steps {step_text}))")
    for name, observes in investigators:
        rows.append(f"(gc-investigator {name} {' '.join(map(_literal_text, observes))})")
    return "\n".join(rows)


# am[verifies a-ev-pl-ag-representation-1017@ca0cfc] am[verifies a-ev-pk-acceptance-anchors-1018@cb1e61]
# am[verifies a-ev-fb-achieves-once-1018@ba60a9]
def _oracle(procs, investigators) -> set[str]:
    """The problem kinds a library has, computed here without the policy."""

    problems: set[str] = set()
    declared = set(DOMAIN.signal_ids)

    # A declared signal must also be anchored; an undeclared one is reported as undeclared alone.
    def literal_problem(signal: str) -> str | None:
        if signal not in declared:
            return "undeclared-signal"
        return "unanchored-literal" if signal in UNANCHORED else None

    if len({p[0] for p in procs}) < len(procs):
        problems.add("(duplicate procedure)")
    if len({i[0] for i in investigators}) < len(investigators):
        problems.add("(duplicate investigator)")
    for name, achieves, when, steps in procs:
        # Negation folds, so (Signal s) and (Not (Signal s)) are the only two spellings.
        if not achieves:
            problems.add("achieves-nothing")
        if not steps:
            problems.add("no-steps")
        if any((signal, not negated) in achieves for signal, negated in achieves):
            problems.add("contradictory-achieves")
        # One literal predicted twice would let one observation grade both copies (a-ev-fb-achieves-once-1018).
        if len(set(achieves)) < len(achieves):
            problems.add("(duplicate (achieves")
        targets = [t for _, kind, t, _ in steps if kind != "act"]
        problems |= {p for signal, _ in [*achieves, *when, *targets] if (p := literal_problem(signal))}
        ids = [sid for sid, *_ in steps]
        if len(set(ids)) < len(ids):
            problems.add("(duplicate (step")
        if any(kind == "act" and target not in DOMAIN.action_ids for _, kind, target, _ in steps):
            problems.add("undeclared-action")
        if any(a not in ids for *_, after in steps for a in after):
            problems.add("dangling-after")
        # Kahn's order over the steps' After names, a name no step has never satisfied.
        done: set[str] = set()
        remaining = list(steps)
        while True:
            ready = [s for s in remaining if all(a in done or a not in ids for a in s[3])]
            if not ready:
                break
            done |= {s[0] for s in ready}
            remaining = [s for s in remaining if s[0] not in done]
        if remaining:
            problems.add("cyclic-after")
    for name, observes in investigators:
        if not observes:
            problems.add("observes-nothing")
        problems |= {p for signal, _ in observes if (p := literal_problem(signal))}
    if _undo_cycle(procs):
        problems.add("cyclic-undo")
    return problems


# The Derives on a cycle of the live undo graph, by the rule's text (a-jk-pc-r2-undo-graph-1019): a Derive
# has steps, all achieve steps, reads its When and their literals and writes the Achieves it does not read;
# one undoes another when it writes the negation of the other's write, unless they read a signal no Derive
# writes opposite ways. A Derive never undoes itself: writing a literal and its negation is
# contradictory-achieves. A literal here is (signal, negated), so its negation flips the flag.
# am[verifies a-ev-pc-r2-policy-1019@05d393]
def _undo_cycle(procs) -> set[str]:
    derives = []
    for name, achieves, when, steps in procs:
        if steps and all(kind == "achieve" for _, kind, _, _ in steps):
            reads = {*when, *(target for _, _, target, _ in steps)}
            derives.append((name, reads, {literal for literal in achieves if literal not in reads}))
    written = {signal for _, _, writes in derives for signal, _ in writes}

    def undoes(source, target) -> bool:
        (_, source_reads, source_writes), (_, target_reads, target_writes) = source, target
        return (any((signal, not negated) in target_writes for signal, negated in source_writes)
                and not any((signal, not negated) in target_reads and signal not in written
                            for signal, negated in source_reads))

    edges = {(source[0], target[0]) for position, source in enumerate(derives) for other, target in enumerate(derives)
             if position != other and undoes(source, target)}
    kept = {name for name, _, _ in derives}
    while True:
        among = {(source, target) for source, target in edges if source in kept and target in kept}
        following = {name for name in kept
                     if any(target == name for _, target in among) and any(source == name for source, _ in among)}
        if following == kept:
            return kept
        kept = following


# am[verifies a-ev-pl-ag-representation-1017@ca0cfc]
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(procedures(), max_size=3), st.lists(st.tuples(NAMES, st.lists(literals(), max_size=2)), max_size=2))
def test_the_policy_refuses_exactly_what_an_independent_oracle_finds(procs, investigators) -> None:
    expected = _oracle(procs, investigators)
    text = _text(procs, investigators)
    if not expected:
        library = read_procedures(text, "generated.metta", DOMAIN, budget=budget())
        assert [p.name for p in library.procedures] == [p[0] for p in procs]
        return
    with pytest.raises(ProcedureError) as refused:
        read_procedures(text, "generated.metta", DOMAIN, budget=budget())
    message = str(refused.value)
    for kind in expected:
        assert kind in message, (kind, message)
    for kind in {"(duplicate procedure)", "(duplicate investigator)", "achieves-nothing", "no-steps",
                 "contradictory-achieves", "(duplicate (achieves", "undeclared-signal", "(duplicate (step",
                 "undeclared-action", "dangling-after", "cyclic-after", "observes-nothing", "unanchored-literal",
                 "cyclic-undo"} - expected:
        assert kind not in message, (kind, message)
