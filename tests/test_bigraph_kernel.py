"""Purpose: acceptance tests of the bigraph structural kernel through its Python boundary: well-formedness
and rule faults, the contract's instantiation and named-identity cases, positional ports, links, sites,
multiple regions, active context, application conditions, priority classes, transitions with their
representative occurrences, fresh ids under repeated reaction, and the module's namespace."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from metta import S, parse

from bigraph_oracle import Big, Control, from_atom, isomorphic, signature_text, term, well_formed
from metta_scope_lint import rebound_variables
from goal_chainer.bigraph import kernel
from goal_chainer.runtime.budget import RunBudget
from goal_chainer.runtime.engine import metta_engine
from goal_chainer.runtime.evaluator import prepare

SIGNATURE = {
    c.name: c
    for c in (
        Control("Host", 0, "active"), Control("Store", 0, "active"), Control("Online", 0, "atomic"),
        Control("Box", 0, "active"), Control("Item", 0, "active"), Control("Tag", 0, "atomic"),
        Control("Mark", 0, "atomic"), Control("Tok", 0, "atomic"), Control("Server", 1, "active"),
        Control("Client", 1, "active"), Control("A", 2, "active"), Control("M", 0, "atomic"),
        Control("L", 1, "atomic"), Control("Cell", 0, "passive"), Control("Room", 0, "active"),
        Control("C", 0, "active"), Control("D", 0, "atomic"), Control("E", 0, "atomic"),
        Control("P", 0, "active"), Control("Q", 0, "active"),
    )
}
SIG = parse(signature_text(SIGNATURE))


# am[verifies a-integrate-brs-structural-kernel-1018@dc4d19]
def budget() -> RunBudget:
    return RunBudget(inference_budget=None, timeout_seconds=300)


# am[verifies a-integrate-brs-structural-kernel-1018@dc4d19]
def text(atom) -> str:
    """An atom's MeTTa text on one line: pymetta's repr breaks long expressions across lines."""

    return " ".join(repr(atom).split())


# A MeTTa caller's view of the kernel: CALL run in the kernel group's space, each term a quoted hole a let
# pattern unwraps so a domain symbol naming a function stays data, every answer collapsed.
# am[verifies a-integrate-brs-structural-kernel-1018@dc4d19]
def in_group(call: str, **terms):
    prepare(kernel.GROUP, budget=budget())
    unwrap = " ".join(f"((quote ${name}) {{{name}}})" for name in terms)
    with metta_engine(None) as engine:
        answers = engine.space(kernel.GROUP.space).run(f"!(let* ({unwrap}) (collapse {call}))",
                                                       **{name: S.quote(t) for name, t in terms.items()})
    return tuple(answers[0][0].children)


# am[verifies a-integrate-brs-structural-kernel-1018@dc4d19]
def big(roots=1, outer=(), nodes=(), place=(), links=(), sites=0, inner=()) -> Big:
    """A bigraph from rows: nodes (id, control), place (child, parent) with ("root", j) and ("site", k),
    links (id, port, ("edge"|"name", x)) and (("inner", x), link)."""

    b = Big(sites, tuple(inner), roots, tuple(outer), dict(nodes), dict(place))
    for row in links:
        if row[0] == "inner":
            b.links[("inner", row[1])] = row[2]
        else:
            b.links[("port", row[0], row[1])] = row[2]
    return b


R0, R1, S0, S1 = ("root", 0), ("root", 1), ("site", 0), ("site", 1)


# am[verifies a-integrate-brs-structural-kernel-1018@dc4d19]
def rule(name, redex: Big, reactum: Big, eta=(), conditions="", priority=0):
    eta_text = " ".join(f"({k} {j})" for k, j in eta)
    return parse(f"(Rule {name} {term(redex)} {term(reactum)} (Eta {eta_text}) (Conditions {conditions}) (Priority {priority}))")


# am[verifies a-integrate-brs-structural-kernel-1018@dc4d19]
def state(b: Big):
    return parse(term(b))


# am[verifies a-integrate-brs-structural-kernel-1018@dc4d19]
def successors(rules, b: Big, sig=SIG):
    return kernel.successors(sig, tuple(rules), state(b), budget=budget())


# am[verifies a-integrate-brs-structural-kernel-1018@dc4d19]
def closure(rules, start: Big, sig=SIG):
    """Every state reachable from START, one per isomorphism class, with the number of transitions and
    of occurrences, as BigraphER's full mode counts them."""

    states, frontier, transitions, occurrences = [state(start)], [state(start)], 0, 0
    while frontier:
        current = frontier.pop(0)
        for t in kernel.transitions(sig, tuple(rules), current, budget=budget()):
            successor = t.children[1]
            occurrences += sum(int(f.children[2].value) for f in t.children[2].children)
            transitions += 1
            if not any(kernel.isomorphic(successor, known, budget=budget()) for known in states):
                states.append(successor)
                frontier.append(successor)
    return states, transitions, occurrences


# ----- well-formedness -------------------------------------------------------------------------------
# am[verifies a-brs-k-term-1018@9429da]
def test_a_well_formed_state_has_no_faults():
    s = big(nodes=[("h", "Host"), ("s", "Store")], place=[("h", R0), ("s", R0)])
    assert kernel.faults(SIG, state(s), budget=budget()) == ()


# am[verifies a-brs-k-term-1018@9429da]
def test_faults_name_every_violation_of_the_term():
    bad = parse(
        "(Bigraph (Inner 0 ()) (Outer 1 (x)) (Nodes (N h Host) (N h Store) (N o Online) (N q Online) "
        "(N z Zed) (N (Edge 1) Host) (N c Host) (N d Host)) "
        "(Place (In h (Root 0)) (In q o) (In o (Root 0)) (In y (Root 0)) (In (Edge 1) (Root 7)) (In c d) (In d c)) "
        "(Link (P h 0 (Edge e)) (P c 0 (Name w))))"
    )
    found = {text(f) for f in kernel.faults(SIG, bad, budget=budget())}
    assert {"(DuplicateNode h)", "(AtomicParent o)", "(UndeclaredControl z Zed)", "(UnknownChild y)",
            "(ReservedId (Edge 1))", "(UnknownParent (Root 7))", "(NoParent z)", "(Cycle c)", "(Cycle d)",
            "(BadPort (BgPort c 0))", "(UnknownName w)"} <= found


# am[verifies a-brs-k-term-1018@9429da] am[verifies c-brs-k-solid-redex-1018@7d9a0b]
@pytest.mark.parametrize(
    ("redex", "fault"),
    [
        (big(roots=2, nodes=[("H", "Host")], place=[("H", R0)]), "(NotSolid r (IdleRoot (Root 1)))"),
        (big(sites=1, nodes=[("H", "Host")], place=[("H", R0), (S0, R0)]), "(NotSolid r (SiteUnderRoot (Root 0)))"),
        (big(sites=2, nodes=[("H", "Host")], place=[("H", R0), (S0, "H"), (S1, "H")]), "(NotSolid r (TwoSites H))"),
        (big(outer=("x",), nodes=[("H", "Host")], place=[("H", R0)]), "(NotSolid r (IdleName (Name x)))"),
        (big(outer=("x",), inner=("w",), nodes=[("C", "Client")], place=[("C", R0)],
             links=[("C", 0, ("name", "x")), ("inner", "w", ("name", "x"))]), "(NotSolid r (InnerNameOnName (Name x)))"),
        (big(inner=("w", "v"), nodes=[("C", "Client")], place=[("C", R0)],
             links=[("C", 0, ("edge", "e")), ("inner", "w", ("edge", "e")), ("inner", "v", ("edge", "e"))]),
         "(NotSolid r (SharedInnerName (Edge e)))"),
        (big(inner=("w",), nodes=[("H", "Host")], place=[("H", R0)], links=[("inner", "w", ("edge", "e"))]),
         "(NotSolid r (PortlessEdge (Edge e)))"),
    ],
)
# am[verifies a-integrate-brs-structural-kernel-1018@dc4d19]
def test_rule_faults_refuse_a_redex_that_is_not_solid(redex, fault):
    found = {text(f) for f in kernel.rule_faults(SIG, rule("r", redex, redex), budget=budget())}
    assert fault in found


# am[verifies a-brs-k-term-1018@9429da]
def test_rule_faults_check_interfaces_eta_conditions_priority_and_groundness():
    host_site = big(sites=1, nodes=[("H", "Host")], place=[("H", R0), (S0, "H")])
    two_roots = big(roots=2, nodes=[("H", "Host"), ("G", "Host")], place=[("H", R0), ("G", R1)])
    found = {text(f) for f in kernel.rule_faults(SIG, rule("r", host_site, two_roots, eta=[(0, 3)]), budget=budget())}
    assert "(OuterFaceMismatch r Roots)" in found
    found = {text(f) for f in kernel.rule_faults(SIG, rule("r", host_site, host_site, eta=[(0, 3)]), budget=budget())}
    assert "(BadEta r (0 3))" in found and "(BadEta r (Untaken 0))" in found
    bad_condition = f"(Present (Parameter 4) {term(big(nodes=[('L', 'Online')], place=[('L', R0)]))})"
    found = {text(f) for f in kernel.rule_faults(SIG, rule("r", host_site, host_site, eta=[(0, 0)], conditions=bad_condition), budget=budget())}
    assert any(f.startswith("(BadCondition r") and "BadLocation" in f for f in found)
    found = {text(f) for f in kernel.rule_faults(SIG, rule("r", host_site, host_site, eta=[(0, 0)], priority='"high"'), budget=budget())}
    assert "(BadPriority r (Priority \"high\"))" in found
    non_ground = parse(f"(Rule r {term(host_site)} {term(host_site)} (Eta (0 $j)) (Conditions) (Priority 0))")
    assert [text(f) for f in kernel.rule_faults(SIG, non_ground, budget=budget())] == ["(NonGround r)"]
    assert kernel.rule_faults(SIG, rule("r", host_site, host_site, eta=[(0, 0)]), budget=budget()) == ()


# ----- the contract's instantiation, named identity and fresh ids (section 4.3) ----------------------
BOX_MARK = big(sites=1, nodes=[("B", "Box"), ("K", "Mark")], place=[("B", R0), ("K", "B"), (S0, "B")])
DUP = rule("dup", BOX_MARK,
           big(sites=2, nodes=[("B", "Box"), ("C", "Box")], place=[("B", R0), (S0, "B"), ("C", R0), (S1, "C")]),
           eta=[(0, 0), (1, 0)])
CLEAR = rule("clear", BOX_MARK, big(nodes=[("B", "Box")], place=[("B", R0)]))


# am[verifies a-integrate-brs-structural-kernel-1018@dc4d19]
def seed(inner_rows) -> Big:
    rows = [("(new seed b)", "Box", R0), ("(new seed m)", "Mark", "(new seed b)")] + list(inner_rows)
    return big(nodes=[(i, c) for i, c, _ in rows], place=[(i, p) for i, _, p in rows])


ITEM = [("(new seed i)", "Item", "(new seed b)"), ("(new seed t)", "Tag", "(new seed i)")]


# am[verifies a-brs-k-react-1018@41ec8d] am[verifies c-brs-k-instantiation-shares-links-1018@fe57cf]
def test_duplicate_copies_the_parameter_with_everything_beneath_it():
    (step,) = successors([DUP], seed(ITEM))
    after = from_atom(step.children[3])
    expected = big(nodes=[("(new e 0)", "Box"), ("(new e 1)", "Item"), ("(new e 2)", "Tag"),
                          ("(new e 3)", "Box"), ("(new e 4)", "Item"), ("(new e 5)", "Tag")],
                   place=[("(new e 0)", R0), ("(new e 1)", "(new e 0)"), ("(new e 2)", "(new e 1)"),
                          ("(new e 3)", R0), ("(new e 4)", "(new e 3)"), ("(new e 5)", "(new e 4)")])
    assert well_formed(after, SIGNATURE)
    assert isomorphic(after, expected)


# am[verifies a-brs-k-react-1018@41ec8d]
def test_discard_removes_the_parameter_with_everything_beneath_it():
    (step,) = successors([CLEAR], seed(ITEM))
    after = from_atom(step.children[3])
    assert well_formed(after, SIGNATURE)
    assert isomorphic(after, big(nodes=[("(new e 0)", "Box")], place=[("(new e 0)", R0)]))


# am[verifies a-brs-k-react-1018@41ec8d] am[verifies c-brs-k-instantiation-shares-links-1018@fe57cf]
def test_a_copy_links_to_the_originals_links_internal_edges_included():
    agent = seed([("(new seed s)", "Server", "(new seed b)"), ("(new seed c)", "Client", "(new seed b)")])
    agent.links[("port", "(new seed s)", 0)] = ("edge", "e")
    agent.links[("port", "(new seed c)", 0)] = ("edge", "e")
    (step,) = successors([DUP], agent)
    after = from_atom(step.children[3])
    on_e = [pt for pt, link in after.links.items() if link == ("edge", "e")]
    assert len(on_e) == 4 and well_formed(after, SIGNATURE)


# am[verifies a-brs-k-react-1018@41ec8d]
def test_copying_a_named_node_is_refused_and_discarding_it_is_legal():
    hosted = seed([("h", "Host", "(new seed b)")])
    (outcome,) = kernel.outcomes(SIG, DUP, state(hosted), budget=budget())
    assert text(outcome.children[0]) == "Refused" and text(outcome.children[3]) == "(DuplicatesNamed (h))"
    assert successors([DUP], hosted) == ()
    (step,) = successors([CLEAR], hosted)
    after = from_atom(step.children[3])
    assert "h" not in after.controls and well_formed(after, SIGNATURE)


# An occurrence kept from an earlier state is refused once the state no longer has it: its named image
# changed control, a condition on its parameter turned false, or its named image moved to another host.
# The changed state's own occurrences still apply.
# am[verifies a-brs-k-checked-apply-1018@f3812e]
def test_apply_refuses_an_occurrence_the_state_no_longer_has():
    def lab(lamp="Item", other="Item", lamp_host="h1"):
        return big(nodes=[("r1", "Room"), ("h1", "Host"), ("r2", "Room"), ("h2", "Host"), ("lamp", lamp), ("(new g i)", other)],
                   place=[("r1", R0), ("h1", "r1"), ("r2", R0), ("h2", "r2"), ("lamp", lamp_host), ("(new g i)", "h1")])

    use = rule("use", big(sites=1, nodes=[("R", "Room"), ("H", "Host"), ("I", "Item")], place=[("R", R0), ("H", "R"), ("I", "H"), (S0, "H")]),
               big(sites=1, nodes=[("R", "Room"), ("H", "Host"), ("O", "Online")], place=[("R", R0), ("H", "R"), ("O", "H"), (S0, "H")]),
               eta=[(0, 0)], conditions=f"(Absent (Parameter 0) {term(ONLINE)})")
    kept = next(o for o in kernel.occurrences(SIG, use, state(lab()), budget=budget()) if "(Image I lamp)" in text(o))
    assert text(kernel.apply(SIG, use, state(lab()), kept, budget=budget()).children[0]) == "Successor"
    for changed in (lab(lamp="Online"), lab(other="Online"), lab(lamp_host="h2")):
        with pytest.raises(kernel.BigraphFault) as refused:
            kernel.apply(SIG, use, state(changed), kept, budget=budget())
        assert refused.value.operation == "the occurrence"
        assert [text(f) for f in refused.value.faults] == ["(NotAnOccurrence use)"]
        for current in kernel.occurrences(SIG, use, state(changed), budget=budget()):
            assert text(kernel.apply(SIG, use, state(changed), current, budget=budget()).children[0]) == "Successor"
    moved = kernel.occurrences(SIG, use, state(lab(lamp_host="h2")), budget=budget())
    assert any("(Image I lamp)" in text(o) and "(Image H h2)" in text(o) for o in moved)


# am[verifies a-brs-k-react-1018@41ec8d] am[rests-on c-ev-brs-fresh-ids-disjoint-1018@e864ac]
def test_repeated_duplication_keeps_fresh_ids_disjoint_and_matches_bigrapher_counts():
    tok_dup = rule("dup", big(sites=1, nodes=[("B", "Box"), ("K", "Tok")], place=[("B", R0), ("K", "B"), (S0, "B")]),
                   big(sites=2, nodes=[("B", "Box"), ("C", "Box")], place=[("B", R0), (S0, "B"), ("C", R0), (S1, "C")]),
                   eta=[(0, 0), (1, 0)])
    start = big(nodes=[("(new seed b)", "Box"), ("(new seed k1)", "Tok"), ("(new seed k2)", "Tok"),
                       ("(new seed i)", "Item"), ("(new seed t)", "Tag")],
                place=[("(new seed b)", R0), ("(new seed k1)", "(new seed b)"), ("(new seed k2)", "(new seed b)"),
                       ("(new seed i)", "(new seed b)"), ("(new seed t)", "(new seed i)")])
    states, transitions, occurrences = closure([tok_dup], start)
    # BigraphER 89ba35f7 on Box.(Tok | Tok | Item.Tag) with this rule: 4 states, 3 transitions, 5
    # occurrences (runs/bigraph-instantiation-3.log in the evidence planning probes).
    assert (len(states), transitions, occurrences) == (4, 3, 5)
    for s in states:
        b = from_atom(s)
        assert well_formed(b, SIGNATURE), term(b)


# am[verifies a-brs-k-react-1018@41ec8d]
def test_fresh_ids_take_the_smallest_suffix_no_id_has():
    s = parse(term(big(nodes=[("(new r O 0)", "Online"), ("(new r O 1)", "Online")], place=[("(new r O 0)", R0), ("(new r O 1)", R0)])))
    assert [text(a) for a in in_group("(bg-fresh (new r O) $s)", s=s)] == ["(new r O 2)"]
    ids = parse("((new r O 0) (new r O 2))")
    assert [text(a) for a in in_group("(bg-fresh-among (new r O) $ids)", ids=ids)] == ["(new r O 1)"]


# ----- ports, links, sites and regions ---------------------------------------------------------------
# BigraphER's A{x,y} -> A{y,x} on ions: each A holds a site, which the reactum keeps.
SWAP = rule("swap", big(sites=1, outer=("x", "y"), nodes=[("Q", "A")], place=[("Q", R0), (S0, "Q")], links=[("Q", 0, ("name", "x")), ("Q", 1, ("name", "y"))]),
            big(sites=1, outer=("x", "y"), nodes=[("Q", "A")], place=[("Q", R0), (S0, "Q")], links=[("Q", 0, ("name", "y")), ("Q", 1, ("name", "x"))]),
            eta=[(0, 0)])


# am[verifies a-brs-k-occurrence-1018@0ed298] am[verifies c-integrate-brs-positional-oracle-1018@6f9f3a]
def test_swapped_ports_on_open_names_are_a_different_state():
    agent = big(outer=("x", "y"), nodes=[("(new s a)", "A"), ("(new s m)", "M")], place=[("(new s a)", R0), ("(new s m)", "(new s a)")],
                links=[("(new s a)", 0, ("name", "x")), ("(new s a)", 1, ("name", "y"))])
    (step,) = successors([SWAP], agent)
    assert not kernel.isomorphic(step.children[3], state(agent), budget=budget())
    states, transitions, _ = closure([SWAP], agent)
    # Positional ports give two states; BigraphER's port multiset gives one, a self-loop
    # (runs/bigrapher-ports in the evidence planning probes).
    assert (len(states), transitions) == (2, 2)


# am[verifies a-brs-k-occurrence-1018@0ed298]
def test_an_open_name_shared_by_a_server_and_two_clients_admits_each_client():
    agent = big(outer=("ch",), nodes=[("srv", "Server"), ("c1", "Client"), ("c2", "Client")],
                place=[("srv", R0), ("c1", R0), ("c2", R0)],
                links=[("srv", 0, ("name", "ch")), ("c1", 0, ("name", "ch")), ("c2", 0, ("name", "ch"))])
    client = big(outer=("x",), nodes=[("C", "Client")], place=[("C", R0)], links=[("C", 0, ("name", "x"))])
    occurrences = kernel.occurrences(SIG, rule("c", client, client), state(agent), budget=budget())
    images = sorted(text(kernel_image(o, "C")) for o in occurrences)
    assert images == ["c1", "c2"]
    for o in occurrences:
        assert text(kernel_image(o, "(Name x)")) == "(Name ch)"


# am[verifies a-integrate-brs-structural-kernel-1018@dc4d19]
def kernel_image(occurrence, key):
    (answer,) = in_group(f"(bg-image $occ {key})", occ=occurrence)
    return answer


# am[verifies a-brs-k-occurrence-1018@0ed298] am[verifies c-brs-k-closed-edge-exact-1018@5cb9f0]
def test_a_closed_redex_edge_matches_only_an_edge_with_exactly_its_ports():
    pair = big(nodes=[("S", "Server"), ("C", "Client")], place=[("S", R0), ("C", R0)],
               links=[("S", 0, ("edge", "e")), ("C", 0, ("edge", "e"))])
    exact = big(nodes=[("s", "Server"), ("c", "Client")], place=[("s", R0), ("c", R0)],
                links=[("s", 0, ("edge", "k")), ("c", 0, ("edge", "k"))])
    wider = big(nodes=[("s", "Server"), ("c", "Client"), ("d", "Client")], place=[("s", R0), ("c", R0), ("d", R0)],
                links=[("s", 0, ("edge", "k")), ("c", 0, ("edge", "k")), ("d", 0, ("edge", "k"))])
    (occurrence,) = kernel.occurrences(SIG, rule("p", pair, pair), state(exact), budget=budget())
    assert text(kernel_image(occurrence, "(Edge e)")) == "(Edge k)"
    assert kernel.occurrences(SIG, rule("p", pair, pair), state(wider), budget=budget()) == ()


# am[verifies a-brs-k-occurrence-1018@0ed298] am[verifies c-brs-k-open-names-function-1018@71fa97]
def test_two_outer_names_may_reach_one_link_but_never_a_matched_closed_edge():
    two = big(outer=("x", "y"), nodes=[("C", "Client"), ("D", "Client")], place=[("C", R0), ("D", R0)],
              links=[("C", 0, ("name", "x")), ("D", 0, ("name", "y"))])
    agent = big(nodes=[("c", "Client"), ("d", "Client")], place=[("c", R0), ("d", R0)],
                links=[("c", 0, ("edge", "k")), ("d", 0, ("edge", "k"))])
    assert len(kernel.occurrences(SIG, rule("t", two, two), state(agent), budget=budget())) == 2


# am[verifies a-brs-k-occurrence-1018@0ed298]
def test_an_inner_name_admits_parameter_ports_on_a_redex_edge_and_no_context_port():
    redex = big(sites=1, inner=("w",), nodes=[("S", "Server"), ("R", "Room")], place=[("R", R0), ("S", "R"), (S0, "R")],
                links=[("S", 0, ("edge", "e")), ("inner", "w", ("edge", "e"))])
    inside = big(nodes=[("r", "Room"), ("s", "Server"), ("c", "Client")], place=[("r", R0), ("s", "r"), ("c", "r")],
                 links=[("s", 0, ("edge", "k")), ("c", 0, ("edge", "k"))])
    outside = big(nodes=[("r", "Room"), ("s", "Server"), ("c", "Client")], place=[("r", R0), ("s", "r"), ("c", R0)],
                  links=[("s", 0, ("edge", "k")), ("c", 0, ("edge", "k"))])
    r = rule("in", redex, redex, eta=[(0, 0)])
    assert len(kernel.occurrences(SIG, r, state(inside), budget=budget())) == 1
    assert kernel.occurrences(SIG, r, state(outside), budget=budget()) == ()


# am[verifies a-brs-k-occurrence-1018@0ed298]
def test_a_passive_node_above_the_match_blocks_it():
    host = big(nodes=[("H", "Host")], place=[("H", R0)])
    nested = big(nodes=[("cell", "Cell"), ("h", "Host")], place=[("cell", R0), ("h", "cell")])
    top = big(nodes=[("cell", "Cell"), ("h", "Host")], place=[("cell", R0), ("h", R0)])
    r = rule("touch", host, host)
    assert kernel.occurrences(SIG, r, state(nested), budget=budget()) == ()
    assert len(kernel.occurrences(SIG, r, state(top), budget=budget())) == 1


# am[verifies a-brs-k-occurrence-1018@0ed298] am[verifies a-brs-k-successors-1018@311dd0]
def test_symmetric_reactum_on_two_regions_keeps_both_occurrences():
    # C || C -> D || E on A.(C) || B.(C), BigraphER's occurrence_equivalence/direct.big without its F.
    redex = big(roots=2, nodes=[("X", "C"), ("Y", "C")], place=[("X", R0), ("Y", R1)])
    reactum = big(roots=2, nodes=[("U", "D"), ("V", "E")], place=[("U", R0), ("V", R1)])
    agent = big(roots=2, nodes=[("a", "P"), ("b", "Q"), ("(new s 1)", "C"), ("(new s 2)", "C")],
                place=[("a", R0), ("b", R1), ("(new s 1)", "a"), ("(new s 2)", "b")])
    found = kernel.transitions(SIG, (rule("r", redex, reactum),), state(agent), budget=budget())
    assert len(found) == 2
    assert all(int(t.children[2].children[0].children[2].value) == 1 for t in found)


# ----- conditions ------------------------------------------------------------------------------------
ONLINE = big(nodes=[("L", "Online")], place=[("L", R0)])
HOST_SITE = big(sites=1, nodes=[("H", "Host")], place=[("H", R0), (S0, "H")])
HOST_ONLINE = big(sites=1, nodes=[("H", "Host"), ("O", "Online")], place=[("H", R0), ("O", "H"), (S0, "H")])


# am[verifies c-brs-k-conditions-occur-1018@c9b346]
def test_conditions_read_the_parameter_and_the_context():
    start = big(nodes=[("h", "Host"), ("s", "Store")], place=[("h", R0), ("s", R0)])
    connect = rule("connect", HOST_SITE, HOST_ONLINE, eta=[(0, 0)], conditions=f"(Absent (Parameter 0) {term(ONLINE)})")
    (step,) = successors([connect], start)
    assert successors([connect], from_atom(step.children[3])) == ()
    store = big(nodes=[("S", "Store")], place=[("S", R0)])
    with_store = rule("w", HOST_SITE, HOST_ONLINE, eta=[(0, 0)], conditions=f"(Present Context {term(store)})")
    without = rule("w", HOST_SITE, HOST_ONLINE, eta=[(0, 0)], conditions=f"(Absent Context {term(store)})")
    assert len(successors([with_store], start)) == 1
    assert successors([without], start) == ()


# am[verifies c-brs-k-conditions-occur-1018@c9b346]
def test_a_condition_no_clause_decides_is_an_error_not_a_silent_refusal():
    r = rule("u", HOST_SITE, HOST_SITE, eta=[(0, 0)], conditions="(Mystery 1)")
    with pytest.raises(kernel.BigraphKernelError):
        kernel.occurrences(SIG, r, state(big(nodes=[("h", "Host")], place=[("h", R0)])), budget=budget())


# ----- priorities and transitions --------------------------------------------------------------------
# am[verifies a-brs-k-successors-1018@311dd0] am[verifies c-brs-k-priority-scan-1018@ffad25]
def test_a_higher_priority_class_preempts_and_an_unenabled_class_falls_through():
    start = big(nodes=[("h", "Host")], place=[("h", R0)])
    low = rule("low", HOST_SITE, HOST_ONLINE, eta=[(0, 0)], priority=0)
    high = rule("high", HOST_SITE, HOST_SITE, eta=[(0, 0)], priority=5)
    assert {text(s.children[1]) for s in successors([low, high], start)} == {"high"}
    blocked = rule("high", HOST_SITE, HOST_SITE, eta=[(0, 0)], priority=5, conditions=f"(Present Context {term(ONLINE)})")
    assert {text(s.children[1]) for s in successors([low, blocked], start)} == {"low"}


# am[verifies a-brs-k-successors-1018@311dd0] am[verifies c-brs-k-witness-agreed-1018@2d9ea2]
def test_transitions_merge_isomorphic_successors_and_keep_counts_and_a_representative():
    agent = big(nodes=[("r", "Room"), ("(new s 1)", "Tag"), ("(new s 2)", "Tag")], place=[("r", R0), ("(new s 1)", "r"), ("(new s 2)", "r")])
    take = rule("take", big(sites=1, nodes=[("R", "Room"), ("T", "Tag")], place=[("R", R0), ("T", "R"), (S0, "R")]), big(sites=1, nodes=[("R", "Room")], place=[("R", R0), (S0, "R")]), eta=[(0, 0)])
    (transition,) = kernel.transitions(SIG, (take,), state(agent), budget=budget())
    (fired,) = transition.children[2].children
    assert text(fired.children[1]) == "take" and int(fired.children[2].value) == 2
    redo = kernel.apply(SIG, take, state(agent), fired.children[3], budget=budget())
    assert kernel.isomorphic(redo.children[3], transition.children[1], budget=budget())


# ----- BigraphER 89ba35f7's own fixtures (contract section 4.4) -------------------------------------
# Expected counts are BigraphER's under its GBS solver, the ground truth these fixtures' comments name:
# its default solver's symmetry breaking under-counts occurrences (runs/bigrapher-fixtures in the
# evidence planning probes: stoch_g6_GBS.tra rate 12, pbrs_norm_GBS.tra 0.666667 and 0.333333).
# am[verifies a-brs-k-successors-1018@311dd0]
def fixture_signature(*controls) -> object:
    return parse(signature_text({c.name: c for c in controls}))


# am[verifies a-brs-k-successors-1018@311dd0] am[verifies a-brs-k-occurrence-1018@0ed298]
def test_bigrapher_direct_keeps_two_symmetric_occurrences():
    sig = fixture_signature(*(Control(c, 0, "active") for c in "ABG"), *(Control(c, 0, "atomic") for c in "CDEF"))
    redex = big(roots=3, nodes=[("X", "C"), ("Y", "C"), ("Z", "F")], place=[("X", R0), ("Y", R1), ("Z", ("root", 2))])
    reactum = big(roots=3, nodes=[("X", "D"), ("Y", "E"), ("Z", "F")], place=[("X", R0), ("Y", R1), ("Z", ("root", 2))])
    start = big(roots=3, nodes=[("a", "A"), ("b", "B"), ("g", "G"), ("(new s 1)", "C"), ("(new s 2)", "C"), ("(new s 3)", "F")],
                place=[("a", R0), ("b", R1), ("g", ("root", 2)), ("(new s 1)", "a"), ("(new s 2)", "b"), ("(new s 3)", "g")])
    states, transitions, occurrences = closure([rule("r", redex, reactum)], start, sig)
    assert (len(states), transitions, occurrences) == (3, 2, 2)


# am[verifies a-brs-k-successors-1018@311dd0] am[verifies a-brs-k-occurrence-1018@0ed298]
def test_bigrapher_wildcard_matches_parametric_controls_exactly():
    sig = fixture_signature(Control("R", 2, "active"), Control("Id", 0, "atomic"), *(Control(c, 0, "atomic") for c in ("P1", "P2", "P3")))
    ports = [("Q", 0, ("name", "a")), ("Q", 1, ("name", "b"))]

    def held(first, second):
        return big(outer=("a", "b"), nodes=[("Q", "R"), ("X", first), ("Y", second)],
                   place=[("Q", R0), ("X", "Q"), ("Y", "Q")], links=ports)

    rules = [rule("r1", held("(Id 1)", "(Id 2)"), held("P1", "P2")),
             rule("r2", held("(Id 2)", "(Id 1)"), held("P3", "P1")),
             rule("r3", held("(Id 1)", "(Id 1)"), held("P2", "P2"))]
    start = big(outer=("a", "b"), nodes=[("q", "R"), ("(new s 1)", "(Id 1)"), ("(new s 2)", "(Id 2)")],
                place=[("q", R0), ("(new s 1)", "q"), ("(new s 2)", "q")],
                links=[("q", 0, ("name", "a")), ("q", 1, ("name", "b"))])
    states, transitions, occurrences = closure(rules, start, sig)
    assert (len(states), transitions, occurrences) == (3, 2, 2)


# am[verifies a-brs-k-successors-1018@311dd0]
def test_bigrapher_test_dup_succ_merges_two_rules_reaching_one_state():
    sig = fixture_signature(Control("A", 0, "active"), Control("B", 0, "active"))
    rules = [rule(name, big(nodes=[("X", "A")], place=[("X", R0)]), big(nodes=[("X", "B")], place=[("X", R0)])) for name in ("to_b1", "to_b2")]
    states, transitions, occurrences = closure(rules, big(nodes=[("(new s a)", "A")], place=[("(new s a)", R0)]), sig)
    assert (len(states), transitions, occurrences) == (2, 1, 2)
    (transition,) = kernel.transitions(sig, tuple(rules), state(big(nodes=[("(new s a)", "A")], place=[("(new s a)", R0)])), budget=budget())
    assert sorted((text(f.children[1]), int(f.children[2].value)) for f in transition.children[2].children) == [("to_b1", 1), ("to_b2", 1)]


# am[verifies a-brs-k-successors-1018@311dd0] am[verifies c-brs-k-witness-agreed-1018@2d9ea2]
def test_bigrapher_pbrs_norm_counts_give_its_probabilities():
    sig = fixture_signature(*(Control(c, 0, "atomic") for c in "ABCD"))
    rules = [rule("r1", big(nodes=[("X", "B")], place=[("X", R0)]), big(nodes=[("X", "C")], place=[("X", R0)])),
             rule("r2", big(nodes=[("X", "A"), ("Y", "A")], place=[("X", R0), ("Y", R0)]), big(nodes=[("Z", "D")], place=[("Z", R0)]))]
    start = big(nodes=[("(new s b)", "B"), ("(new s 1)", "A"), ("(new s 2)", "A")],
                place=[("(new s b)", R0), ("(new s 1)", R0), ("(new s 2)", R0)])
    counts = sorted((text(f.children[1]), int(f.children[2].value))
                    for t in kernel.transitions(sig, tuple(rules), state(start), budget=budget()) for f in t.children[2].children)
    assert counts == [("r1", 1), ("r2", 2)]  # weights 1 and 1: probabilities 1/3 and 2/3
    states, transitions, occurrences = closure(rules, start, sig)
    assert (len(states), transitions, occurrences) == (4, 4, 6)


# am[verifies a-brs-k-successors-1018@311dd0]
def test_bigrapher_stoch_g6_counts_all_six_embeddings():
    sig = fixture_signature(Control("A", 0, "atomic"), Control("B", 0, "atomic"))
    redex = big(nodes=[("W", "B"), ("X", "A"), ("Y", "A"), ("Z", "A")], place=[("W", R0), ("X", R0), ("Y", R0), ("Z", R0)])
    reactum = big(nodes=[("W", "B"), ("X", "A")], place=[("W", R0), ("X", R0)])
    start = big(nodes=[("(new s b)", "B")] + [(f"(new s {i})", "A") for i in range(3)],
                place=[("(new s b)", R0)] + [(f"(new s {i})", R0) for i in range(3)])
    states, transitions, occurrences = closure([rule("remove3", redex, reactum)], start, sig)
    assert (len(states), transitions, occurrences) == (2, 1, 6)  # rate 6 x sigma = 12


# ----- the module itself -----------------------------------------------------------------------------
KERNEL_TEXT = Path(kernel.KERNEL).read_text()


# am[verifies c-brs-k-inert-heads-1018@e36b32]
def test_every_symbol_the_kernel_defines_starts_bg():
    heads = set(re.findall(r"^\(= \(([^\s()]+)", KERNEL_TEXT, flags=re.MULTILINE))
    assert heads and all(h.startswith("bg-") for h in heads), sorted(h for h in heads if not h.startswith("bg-"))


# am[verifies c-brs-k-inert-heads-1018@e36b32] am[rests-on c-brs-k-function-heads-evaluate-1018@90a5f4]
def test_ids_and_controls_named_like_functions_pass_through_unevaluated():
    sig = parse("(Signature (Control Host 0 active) (Control Online 0 atomic) (Control max 1 active))")
    s0 = parse("(Bigraph (Inner 0 ()) (Outer 1 ()) (Nodes (N h Host) (N (max 1 2) max)) "
               "(Place (In h (Root 0)) (In (max 1 2) (Root 0))) (Link (P (max 1 2) 0 (Edge (id 3)))))")
    connect = parse(f"(Rule id {term(HOST_SITE)} {term(HOST_ONLINE)} (Eta (0 0)) (Conditions) (Priority 0))")
    (step,) = kernel.successors(sig, (connect,), s0, budget=budget())
    after = text(step.children[3])
    assert "(N (max 1 2) max)" in after and "(Edge (id 3))" in after and text(step.children[1]) == "id"


# am[verifies a-brs-k-scope-lint-1018@5831fe] am[verifies c-brs-k-case-vars-clause-scoped-1018@de7554]
def test_no_equation_binds_a_pattern_variable_twice_in_one_scope(tmp_path_factory):
    assert rebound_variables(Path(kernel.KERNEL)) == []
    bad = Path(__file__).with_name("data") / "bigraph" / "rebound.metta"
    found = rebound_variables(bad)
    assert [(where, name) for where, name, _ in found] == [("bad-pair", "$other")]


# lib_functional's is-member answers True once per occurrence of its element, so a branch on it answers
# once per occurrence: a redex with two inner names on one closed edge gave each occurrence twice. The
# kernel calls no is-member, and its membership test answers once.
# am[verifies a-brs-k-member-once-1018@ed3afd] am[rests-on c-ev-pk-is-member-per-occurrence-1018@c8243c]
def test_membership_answers_once_however_often_the_element_occurs():
    code = "\n".join(line.split(";", 1)[0] for line in KERNEL_TEXT.splitlines())
    assert "is-member" not in code
    assert [a.value for a in in_group("(bg--member? a (a b a))")] == [True]
    assert [a.value for a in in_group("(bg--member? c (a b a))")] == [False]
    sig = parse("(Signature (Control Server 1 active) (Control Client 1 active))")
    redex = ("(Bigraph (Inner 1 (x1 x2)) (Outer 1 ()) (Nodes (N S Server)) (Place (In S (Root 0)) (In (Site 0) S)) "
             "(Link (P S 0 (Edge e)) (I x1 (Edge e)) (I x2 (Edge e))))")
    shared = parse(f"(Rule keep {redex} {redex} (Eta (0 0)) (Conditions) (Priority 0))")
    agent = parse("(Bigraph (Inner 0 ()) (Outer 1 ()) (Nodes (N s Server) (N (new g c1) Client) (N (new g c2) Client)) "
                  "(Place (In s (Root 0)) (In (new g c1) s) (In (new g c2) s)) "
                  "(Link (P s 0 (Edge E)) (P (new g c1) 0 (Edge E)) (P (new g c2) 0 (Edge E))))")
    assert len(in_group("(bg-occurrence $sig $rule $g)", sig=sig, rule=shared, g=agent)) == 1
