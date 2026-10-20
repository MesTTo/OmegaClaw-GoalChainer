"""Purpose: verify structured MeTTa guard programs against the packaged s(CASP) solver."""

from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st

from goal_chainer.errors import InvalidInputError, MettaEngineError
from goal_chainer.snars_engine import run_snars_batch
from goal_chainer.snars_program import SnarsProgramBuilder
from goal_chainer.snars_protocol import atom_to_python
from goal_chainer.snars_reasoner import SnarsSession
from goal_chainer.sexpr.codec import SexprCodec
from request_support import budget


# am[verifies a-integrate-guard-metta-gate-1019@1bf9e1]
@pytest.mark.parametrize("rules,goal,expected", [
    (("(safe redacted)",), "(safe redacted)", True),
    (("(safe redacted)",), "(safe raw)", False),
    (("(ready)",), "(ready)", True),
    (("(pair a b)", "(:- (same $x) (pair $x $x))"), "(same a)", False),
    (("(pair a a)", "(:- (same $x) (pair $x $x))"), "(same a)", True),
    (("(has (box red))", "(color red)",
      "(:- (packed $x) (, (has (box $x)) (color $x)))"), "(packed red)", True),
    (("(isa tweety \"bird\")", "(ab penguin)",
      "(:- (flies $x) (, (isa $x \"bird\") (not (ab $x))))"), "(flies tweety)", True),
    (("(isa penguin \"bird\")", "(ab penguin)",
      "(:- (flies $x) (, (isa $x \"bird\") (not (ab $x))))"), "(flies penguin)", False),
    (("(- (flies penguin))",), "(- (flies penguin))", True),
    (("(selected a)", "(blocked a)", "(:- (, (selected $x) (blocked $x)))"), "(selected a)", False),
    (("(:- (large $x) (#> $x 3))",), "(large 4)", True),
    (("(:- (large $x) (#> $x 3))",), "(large 2)", False),
    (("(:- (p) (not (q)))", "(:- (q) (not (p)))"), "(p)", True),
    (("(:- (p) (not (q)))", "(:- (q) (not (p)))"), "(q)", True),
])
def test_guard_terms_keep_the_solver_semantics(rules, goal, expected):
    codec = SexprCodec()
    with SnarsSession.ephemeral(budget=budget(), include_goalchainer_policy=False) as session:
        result = session.guard(goal, rules=rules)
    assert result.operation == "guard"
    assert result.payload[1] == ["goal", atom_to_python(codec.parse(goal), codec)]
    assert result.payload[2] == ["proves", str(expected)]
    assert (result.payload[3][1] != "no") == expected


# am[verifies a-integrate-guard-metta-gate-1019@1bf9e1]
@pytest.mark.parametrize("source", ["", "safe(redacted).", '"safe(redacted)"', "42", "()", "$x", "(safe a) (safe b)"])
@pytest.mark.parametrize("position", ["goal", "rule"])
def test_guard_rejects_non_expression_input_before_execution(source, position):
    def should_not_run(*args):
        pytest.fail("Invalid guard text reached the executor")

    with SnarsSession.ephemeral(budget=budget(), execute=should_not_run,
                                include_goalchainer_policy=False) as session:
        with pytest.raises(InvalidInputError):
            session.guard(source if position == "goal" else "(safe a)",
                          rules=(source,) if position == "rule" else ())


# am[verifies a-integrate-guard-metta-gate-1019@1bf9e1]
def test_solver_errors_are_errors_and_do_not_leave_rules_in_the_next_batch():
    with SnarsSession.ephemeral(budget=budget(), include_goalchainer_policy=False) as session:
        with pytest.raises(MettaEngineError):
            session.guard("(broken)", rules=("(:- (broken) (is $x (/ 1 0)))",))
        first = session.guard("(only first)", rules=("(only first)",))
        second = session.guard("(only first)", rules=("(only second)",))
    assert first.payload[2] == ["proves", "True"]
    assert second.payload[2] == ["proves", "False"]


# am[verifies a-integrate-guard-metta-gate-1019@1bf9e1]
@settings(max_examples=16, deadline=None)
@given(st.recursive(
    st.one_of(st.integers(min_value=-100, max_value=100),
              st.text(alphabet="abc XYZ,()\"\\é", max_size=12).map(SexprCodec().string)),
    lambda children: st.lists(children, min_size=1, max_size=3).map(
        lambda values: SexprCodec().expression("node", *values)),
    max_leaves=12,
))
def test_guard_preserves_ground_term_structure(term):
    codec = SexprCodec()
    fact = codec.emit(codec.expression("contains", term))
    different = codec.emit(codec.expression("contains", codec.expression("different", term)))
    with SnarsSession.ephemeral(budget=budget(), include_goalchainer_policy=False) as session:
        assert session.guard(fact, rules=(fact,)).payload[2] == ["proves", "True"]
        assert session.guard(different, rules=(fact,)).payload[2] == ["proves", "False"]


# am[verifies a-integrate-guard-metta-gate-1019@1bf9e1]
@pytest.mark.parametrize("same_variable", [False, True])
def test_guard_query_variables_remain_unbound_in_the_echo(same_variable):
    goal = "(pair $x $x)" if same_variable else "(pair $x $y)"
    with SnarsSession.ephemeral(budget=budget(), include_goalchainer_policy=False) as session:
        result = session.guard(goal, rules=("(pair a b)",))
    head, left, right = result.payload[1][1]
    assert head == "pair"
    assert left.startswith("$") and right.startswith("$")
    assert (left == right) == same_variable
    assert result.payload[2] == ["proves", str(not same_variable)]


# am[verifies a-integrate-guard-metta-gate-1019@1bf9e1]
@pytest.mark.parametrize("goal,expected", [("(- (flies penguin))", "True"),
                                         ("(- (flies tweety))", "False")])
def test_direct_metta_guard_heads_accept_quoted_rules(goal, expected):
    builder = SnarsProgramBuilder()
    batch = builder.batch(
        builder.codec.parse(f"(sn guard-proves? (quote {goal}))"),
        effects=("(sn guard-rule! (quote (- (flies penguin))))",),
        includes={"guard"},
    )
    assert run_snars_batch(batch, budget=budget()).output_lines == (expected,)


# am[verifies a-integrate-guard-metta-gate-1019@1bf9e1]
@pytest.mark.parametrize("expression", ['"safe(redacted)"', "()", "(1 x)", "($head x)"])
def test_native_guard_boundary_refuses_non_terms(expression):
    builder = SnarsProgramBuilder()
    batch = builder.batch(builder.codec.parse(f"(sn guard? (quote {expression}))"),
                          includes={"guard"})
    with pytest.raises(MettaEngineError):
        run_snars_batch(batch, budget=budget())
