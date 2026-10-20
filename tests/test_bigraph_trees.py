"""Purpose: property tests of the bigraph kernel's search trees on mixed MeTTa keys: a tree built from
sorted distinct rows and a tree grown by insertions hold their rows in msort order, find every key and
no other, keep the red-black invariants, and keep the last row inserted under a key; a set answers
membership as Python's set does; and a pick yields each element with the others, the first first."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from goal_chainer.bigraph import kernel
from goal_chainer.runtime.budget import RunBudget
from goal_chainer.runtime.engine import metta_engine
from goal_chainer.runtime.evaluator import prepare

# Numbers, symbols, compound ids and strings, so keys of different kinds meet in one tree.
KEYS = st.one_of(
    st.integers(-50, 50).map(str),
    st.text("abxyz", min_size=1, max_size=3).map(lambda s: "k" + s),
    st.tuples(st.sampled_from("rs"), st.text("ab", min_size=1, max_size=2), st.integers(0, 3)).map(
        lambda t: f"(new {t[0]} {t[1]} {t[2]})"),
    st.text("ab", min_size=1, max_size=2).map(lambda s: f'"{s}"'),
)


# am[verifies a-brs-k-st-trees-1018@2f963f]
def run(source: str):
    """The one answer of SOURCE in the kernel group's space."""

    prepare(kernel.GROUP, budget=RunBudget(inference_budget=None, timeout_seconds=600))
    with metta_engine(None) as engine:
        answers = engine.space(kernel.GROUP.space).run(source)
    assert len(answers) == 1 and len(answers[0]) == 1, answers
    return answers[0][0]


# am[verifies a-brs-k-st-trees-1018@2f963f]
def text(atom) -> str:
    return " ".join(repr(atom).split())


# am[verifies a-brs-k-st-trees-1018@2f963f]
def walk(tree) -> tuple[int, list]:
    """(black height, rows in order) of a tree atom, asserting the red-black invariants on the way."""

    if text(tree) == "BgLeaf":
        return 1, []
    colour, left, row, right = tree.children[1:]
    left_height, left_rows = walk(left)
    right_height, right_rows = walk(right)
    assert left_height == right_height, "every path holds the same number of black nodes"
    if text(colour) == "BgRed":
        assert all(text(c) == "BgLeaf" or text(c.children[1]) == "BgBlack" for c in (left, right)), "a red node's children are black"
    return left_height + (text(colour) == "BgBlack"), left_rows + [row] + right_rows


# am[verifies a-brs-k-st-trees-1018@2f963f]
def sorted_texts(keys) -> list[str]:
    return [text(k) for k in run(f"!(msort ({' '.join(keys)}))").children] if keys else []


# am[verifies a-brs-k-st-trees-1018@2f963f]
@settings(deadline=None, max_examples=100)
@given(keys=st.lists(KEYS, unique=True, max_size=40), missing=KEYS)
def test_a_tree_built_from_sorted_rows_keeps_the_invariants_and_finds_exactly_its_keys(keys, missing):
    rows = " ".join(f"(BgKey {k} v{i})" for i, k in enumerate(keys))
    tree = run(f"!(bg--tree (msort ({rows})))")
    _, in_order = walk(tree)
    if keys:
        assert text(tree.children[1]) == "BgBlack", "the root is black"
    assert [text(row.children[1]) for row in in_order] == sorted_texts(keys)
    probes = keys + ([] if missing in keys else [missing])
    found = run(f"!(let $t (bg--tree (msort ({rows}))) (map-atom ({' '.join(probes)}) $k (bg--tree-row $k $t)))")
    for i, row in enumerate(found.children[:len(keys)]):
        assert text(row.children[2]) == f"v{i}"
    if missing not in keys:
        assert text(found.children[-1]) == "()"


# am[verifies a-brs-k-st-trees-1018@2f963f]
@settings(deadline=None, max_examples=100)
@given(keys=st.lists(KEYS, max_size=40))
def test_insertion_keeps_the_invariants_and_the_last_row_under_each_key(keys):
    rows = " ".join(f"(BgKey {k} v{i})" for i, k in enumerate(keys))
    tree = run(f"!(foldl-atom ({rows}) BgLeaf $t $row (bg--tree-insert $row $t))")
    _, in_order = walk(tree)
    last = {}
    for i, k in enumerate(keys):
        last[text(run(f"!(let $x {k} $x)"))] = f"v{i}"
    assert [text(row.children[1]) for row in in_order] == sorted_texts(sorted(set(keys)))
    for row in in_order:
        assert text(row.children[2]) == last[text(row.children[1])]


# am[verifies a-brs-k-st-trees-1018@2f963f]
@settings(deadline=None, max_examples=60)
@given(members=st.lists(KEYS, max_size=20), probes=st.lists(KEYS, max_size=10))
def test_a_set_answers_membership_like_a_python_set(members, probes):
    if not probes:
        return
    answers = run(f"!(let $s (bg--set ({' '.join(members)})) (map-atom ({' '.join(probes)}) $k (bg--in? $k $s)))")
    member_texts = {text(run(f"!(let $x {m} $x)")) for m in members}
    for probe, answer in zip(probes, answers.children):
        assert answer.value is (text(run(f"!(let $x {probe} $x)")) in member_texts)


# am[verifies a-brs-k-st-trees-1018@2f963f] am[verifies a-brs-k-st-iso-1018@7fcfce]
def test_a_pick_yields_each_element_with_the_others_first_element_first():
    assert text(run("!(collapse (bg--pick (a b c)))")) == "((BgPick a (b c)) (BgPick b (a c)) (BgPick c (a b)))"
    assert text(run("!(collapse (once (bg--pick (a b c))))")) == "((BgPick a (b c)))"
    assert text(run("!(collapse (bg--pick ()))")) == "()"
