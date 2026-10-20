"""Purpose: verify stable attention ordering, native fallbacks and repeatable hook installation."""

from pathlib import Path
import random

import pytest
from snars_differential import canonical, tree

from goal_chainer.sexpr.forms import top_level_forms
from goal_chainer.runtime.budget import RunBudget, run_bounded
from goal_chainer.runtime.modules import load_metta_module, register_metta_library
from goal_chainer.runtime.engine import metta_engine
from goal_chainer.snars_engine import prepare_snars_world
from goal_chainer.snars_program import SNARS_DIRECTORY, SNARS_LIBRARY

POLICY = Path(__file__).parents[1] / "src/goal_chainer/policy"
CONTROL = POLICY / "goalchainer_attention_control.metta"


# Definitions precede their invocation; every fixture runs inside one speculative native batch.
# am[verifies a-integrate-ecan-packaged-hook-1017]
def _run(body, *, replays=0, query=False):
    assert CONTROL.is_file()
    modules = "\n".join((POLICY / name).read_text() for name in (
        "goalchainer_attention.metta", "goalchainer_attention_graph.metta", CONTROL.name,
    ))
    directives = "\n".join(form.text for form in top_level_forms(CONTROL.read_text()) if form.directive)
    source = (modules + "\n" + (directives + "\n") * replays
              + ((POLICY / "goalchainer_attention_query.metta").read_text() if query else "")
              + f"(= (attention-control-case) {body})\n!(attention-control-result (attention-control-case))")
    world = prepare_snars_world()
    with metta_engine(None) as engine:
        space = engine.space(world.space)
        with space.speculative(), space.capture():
            answers, _ = run_bounded(space, source, budget=RunBudget(
                inference_budget=None, timeout_seconds=900))
        lines = [str(atom) for group in answers for atom in group]
    found = [line for line in lines if line.startswith("(attention-control-result ")]
    assert len(found) == 1, lines
    return tree(found[0])[1]


# Distinct identities retain observable tie order; duplicates remain duplicate queue occurrences.
# am[verifies a-integrate-ecan-packaged-hook-1017]
def _cases():
    rng = random.Random(20261017)
    cases = [[]]
    for size in (1, 2, 3, 7, 16, 31):
        for _ in range(5):
            rows = [(rng.choice((0, 0.0, 0.5, 1, 1.0, 2)), rng.randrange(5), f"j{i}",
                     rng.choice((0.0, 0.25, 0.5, 1.0))) for i in range(size)]
            if size > 1:
                rows[-1] = rows[0]
            cases.append(rows)
    return cases


# The same queue is sorted and selected with attention inactive, zero, or populated.
# Time: one stable rekey and one native selection per generated queue.
# am[verifies a-integrate-ecan-packaged-hook-1017]
def _ordering_program(mode):
    cases = []
    for index, rows in enumerate(_cases()):
        items = " ".join(f"(Fr {raw!r} {tick} {name} right)" for raw, tick, name, _ in rows)
        ranks = dict((name, 0.0 if mode == "zero" else value) for _, _, name, value in rows)
        ranks["right"] = 0.0
        facts = " ".join(f"(gc-attention-row (AttentionStatement {name}) {value!r} ())"
                         for name, value in ranks.items())
        cases.append(f"(Case {index} ({items}) ({facts}))")
    active = "True" if mode == "inactive" else "(add-atom &self (gc-attention-active))"
    return (
        f"(let* (($active {active}) ($decay (sn config decay)) "
        f"($results (collapse (let (Case $index $items $facts) (superpose ({' '.join(cases)})) "
        "(let* (($added (collapse (let $fact (superpose $facts) (add-atom &self $fact)))) "
        "($ordered (gc-attention-rekey $items)) "
        "($selected (sn fr-best $items 5 NoItem -1.0)) "
        "($removed (collapse (let $fact (superpose $facts) (remove-atom &self $fact))))) "
        "(Order $index $ordered $selected)))))) (Orders $decay $results))"
    )


# Python's stable numeric sort is independent of the MeTTa run formation and merge.
# Zero attention must preserve ordering at equal work, without claiming equal computation costs.
# am[verifies a-integrate-ecan-packaged-hook-1017]
@pytest.mark.parametrize("mode", ["inactive", "zero", "attention"])
def test_current_attention_rekeys_stably_and_preserves_native_ties(mode):
    tag, decay, answers = _run(_ordering_program(mode))
    assert tag == "Orders"
    assert len(answers) == len(_cases())
    for (_, index, actual, selected), rows in zip(answers, _cases(), strict=True):
        assert int(index) < len(answers)
        # am[verifies a-integrate-ecan-packaged-hook-1017]
        def importance(row):
            return row[3] if mode == "attention" else 0.0
        ordered = sorted(rows, key=lambda row: (-importance(row), -row[0]))
        wanted = [["Fr", str(raw), str(tick), name, "right"] for raw, tick, name, _ in ordered]
        assert actual == wanted
        best = max(rows, key=lambda row: (importance(row), row[0] * float(decay) ** (5 - row[1])), default=None)
        assert (selected if selected == "NoItem" else selected[3]) == (best[2] if best else "NoItem")


# Saved worlds replay directives, not definitions. Every repeat must retain one original and wrapper.
# am[rests-on c-rt-rebind-lifecycle-guarded-1017]
# am[verifies a-integrate-ecan-packaged-hook-1017]
def test_install_directives_are_idempotent_and_keep_native_equations():
    body = """(Installed
      (size-atom (collapse (match &self (= (sn fr-before $a $av $b $bv) $body) True)))
      (size-atom (collapse (match &self (= (sn fr-touch! $sid) $body) True)))
      (size-atom (collapse (match &self (= (gc-attention-native-before $a $av $b $bv) $body) True)))
      (size-atom (collapse (match &self (= (gc-attention-native-touch! $sid) $body) True)))
      (collapse (sn fr-before (Fr 2 0 a b) 2 (Fr 1 0 c d) 1)))"""
    first = _run(body)
    assert first[:5] == ["Installed", "1", "1", "1", "1"]
    assert first[5] in (["True"], ["true"])
    assert _run(body, replays=2) == first


# Distinct premise values must remain independent in the two row lookups.
# am[verifies a-integrate-ecan-packaged-hook-1017]
def test_premise_mean_uses_both_distinct_rows():
    body = """(let* (($active (add-atom &self (gc-attention-active)))
       ($left (add-atom &self (gc-attention-row (AttentionStatement left) 0.5 ())))
       ($right (add-atom &self (gc-attention-row (AttentionStatement right) 0.0 ()))))
      (DistinctMean (gc-attention-importance (Fr 1.0 0 left right))
       (sn fr-before (Fr 1.0 0 left right) 1.0 (Fr 2.0 0 right right) 2.0)))"""
    tag, value, before = _run(body)
    assert tag == "DistinctMean" and float(value) == 0.25
    assert before in ("True", "true")


# The saved native touch body must keep both conditional directions and admit only supported ends.
# Zero attention leaves the original keys decisive while exercising graph growth on every touch.
# am[verifies a-integrate-ecan-packaged-hook-1017]
@pytest.mark.parametrize("direction", ["modus ponens", "abduction"])
def test_attention_touch_keeps_both_conditional_partner_directions(direction):
    from test_snars_conditional_candidates import DIRECTIONS, _frontier_program

    native = _frontier_program("the edge before its premise", direction, "binary")
    body = ("(let* (($active (add-atom &self (gc-attention-active))) "
            f"($result {native})) (Touch $result (gc-attention-rows)))")
    tag, result, rows = _run(body)
    assert tag == "Touch"
    _, premise, target, edge, frontier, step, proofs, evidence, feedback = result
    assert {(item[3], item[4]) for item in frontier} == {(premise, edge)}
    assert step == [["stmt", target, ["sn-ref", target]]]
    assert proofs == [[DIRECTIONS[direction][2], premise, edge]]
    assert evidence[1:3] != ["0.0", "0.0"]
    assert feedback == []
    assert {("AttentionStatement", sid) for sid in (premise, target, edge)} <= {
        tuple(node) for _, node, _, _ in rows
    }
    assert all(float(value) == 0.0 for _, _, value, _ in rows)


# A failed installation must restore the entire native body, including every touching clause.
# am[verifies a-integrate-import-transaction-1017]
# am[verifies a-integrate-ecan-hook-installation-review-1017]
def test_failed_attention_module_restores_native_hooks_and_can_be_retried(tmp_path):
    source = CONTROL.read_text()
    module = tmp_path / "attention_install.metta"
    module.write_text(source + "\n!(py-call (operator.truediv 1 0))\n")
    native = """!(Native
      (collapse (match &self (= (sn fr-before $a $av $b $bv) $body) $body))
      (collapse (match &self (= (sn fr-touch! $sid) $body) $body)))"""
    installed = """!(Installed
      (size-atom (collapse (match &self (= (sn fr-before $a $av $b $bv) $body) True)))
      (size-atom (collapse (match &self (= (sn fr-touch! $sid) $body) True)))
      (size-atom (collapse (match &self (= (gc-attention-native-before $a $av $b $bv) $body) True)))
      (size-atom (collapse (match &self (= (gc-attention-native-touch! $sid) $body) True))))"""
    with metta_engine(None) as engine:
        space = engine.space("&attention-failed-install")
        register_metta_library(SNARS_LIBRARY.name, SNARS_DIRECTORY, budget=None)
        load_metta_module(engine, SNARS_LIBRARY, space=space)
        for name in ("goalchainer_attention.metta", "goalchainer_attention_graph.metta"):
            load_metta_module(engine, POLICY / name, space=space)
        before = canonical(str(space.run(native)[0][0]), frozenset())
        with pytest.raises(Exception) as caught:
            load_metta_module(engine, module, space=space)
        assert type(caught.value).__name__ == "EngineError"
        assert canonical(str(space.run(native)[0][0]), frozenset()) == before
        module.write_text(source)
        first = load_metta_module(engine, module, space=space)
        assert load_metta_module(engine, module, space=space) == first
        assert str(space.run(installed)[0][0]) == "(Installed 1 1 1 1)"
