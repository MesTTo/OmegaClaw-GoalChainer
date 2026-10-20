"""Purpose: an independent finite reference model of the justification kernel, for tests only.

It reaches the kernel's answer by another route than planning/justification.metta. The kernel
evaluates specialised set closures; this model writes AgenticMind's rules as a ground normal
logic program, one rule schema per line of grounded.lp, claim.lp and rules.lp that the kernel
ports, and computes that program's well-founded model with Van Gelder's alternating fixpoint
over least models of reducts. The evidence rows are compiled to an abstract frame by a second,
separately written reading of the same contract. Terms are pymetta plain values: tuples for
expressions, metta.Symbol for symbols, str, int and bool.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any, Iterable

from metta import Symbol, Variable

Term = Any

FROM = Symbol("From")
WITHDRAWN = Symbol("Withdrawn")
NOT = Symbol("Not")
FOREVER = Symbol("Forever")
UNTIL = Symbol("Until")
CLAIM = Symbol("Claim")
OBSERVATION = Symbol("Observation")
ROW = Symbol("Row")
STATED = Symbol("Stated")
ESTIMATORS = ("measured", "deterministic", "receipt-calibrated", "model-proposed", "human-asserted")
ESTABLISHING = ("measured", "deterministic", "human-asserted")


# One abstract frame: what AgenticMind's argument layer reads, with every link named.
# am[implements a-jk-reference-model-1018@ef9091]
@dataclass(frozen=True)
class Frame:
    arguments: frozenset[Term]
    supports: frozenset[tuple[Term, Term, Term]]
    attacks: frozenset[tuple[Term, Term, Term]]
    undercuts: frozenset[tuple[Term, Term]]
    established: frozenset[Term]


# The labelling the kernel answers for one frame: STATUS and CHECK per argument, STATE per link.
# am[implements a-jk-reference-model-1018@ef9091]
@dataclass(frozen=True)
class Labelling:
    status: dict[Term, str]
    check: dict[Term, str]
    links: dict[Term, str]


# Time: one pass per round over r rules of total body length b, at most a rounds for a atoms.
# am[implements a-jk-reference-model-1018@ef9091]
def least_model(rules: Iterable[tuple[Term, tuple[Term, ...], tuple[Term, ...]]], assumed: set) -> set:
    """The least model of the reduct by `assumed`: a rule keeps its positive body when none of its
    negated atoms is assumed, and is dropped otherwise (Gelfond and Lifschitz's reduct)."""

    reduct = [(head, positive) for head, positive, negative in rules if not any(n in assumed for n in negative)]
    model: set = set()
    changed = True
    while changed:
        changed = False
        for head, positive in reduct:
            if head not in model and all(atom in model for atom in positive):
                model.add(head)
                changed = True
    return model


# Van Gelder's alternating fixpoint: true = lfp of the doubled reduct operator, possible = one
# more application. [source: Van Gelder, "The alternating fixpoint of logic programs with
# negation", JCSS 47(1):185-221, 1993]
# Time: at most a + 1 rounds of two least models, a = atoms.
# am[implements a-jk-reference-model-1018@ef9091]
def well_founded(rules: list) -> tuple[set, set]:
    true: set = set()
    while True:
        possible = least_model(rules, true)
        refined = least_model(rules, possible)
        if refined == true:
            return true, possible
        true = refined


# Each schema is the ground instance of one AgenticMind rule over unreasoned links:
#   ans  grounded.lp answered_attack: the attacker is defeated or the link withdrawn
#   acc  grounded.lp accepted_argument: every declared attack slot answered
#   def  grounded.lp defeated_argument: an accepted attacker over a holding link
#   hold rules.lp edge_holds for a link no reason supports: declared and not undercut
#   uc   rules.lp edge_undercut: the undercut's reason is in and well founded
#   wf   claim.lp well_founded: nothing offered and not refuted, or held up by a holding,
#        accepted, well-founded supporter and not refuted
# am[implements a-jk-reference-model-1018@ef9091] am[rests-on c-jk-am-wfs-reading-1018@a6fd08]
def program(frame: Frame) -> list:
    rules: list = []
    links = {link for link, _, _ in frame.supports} | {link for link, _, _ in frame.attacks}
    into: dict[Term, list[Term]] = {argument: [] for argument in frame.arguments}
    for link, attacker, target in frame.attacks:
        rules.append((("ans", link), (("def", attacker),), ()))
        rules.append((("ans", link), (), (("hold", link),)))
        rules.append((("def", target), (("acc", attacker), ("hold", link)), ()))
        into[target].append(link)
    for argument in frame.arguments:
        rules.append((("acc", argument), tuple(("ans", link) for link in into[argument]), ()))
    for link in links:
        rules.append((("hold", link), (), (("uc", link),)))
    for link, reason in frame.undercuts:
        rules.append((("uc", link), (("acc", reason), ("wf", reason)), ()))
    offered = {target for _, _, target in frame.supports}
    for argument in frame.arguments - offered:
        rules.append((("wf", argument), (), (("def", argument),)))
    for link, supporter, target in frame.supports:
        rules.append((("wf", target), (("hold", link), ("acc", supporter), ("wf", supporter)), (("def", target),)))
    return rules


# STATUS: refuted when definitely defeated; accepted when definitely accepted and well founded;
# unsupported when grounds were offered and none can reach a founded entry even through
# supporters that are only undecided (c-jk-contested-not-lost-1018); undecided otherwise.
# CHECK follows claim.lp's verified and checked without tags: established and standing itself,
# or held up through a holding link by a standing established supporter, and not refuted.
# Time: the well-founded model, then a least closure over s supports, at most n rounds.
# am[implements a-jk-reference-model-1018@ef9091] am[rests-on c-jk-contested-not-lost-1018@34e299]
def label(frame: Frame) -> Labelling:
    true, possible = well_founded(program(frame))
    accepted = {a for a in frame.arguments if ("acc", a) in true}
    refuted = {a for a in frame.arguments if ("def", a) in true}
    founded = {a for a in frame.arguments if ("wf", a) in true}
    links = {link for link, _, _ in frame.supports} | {link for link, _, _ in frame.attacks}
    holds = {link for link in links if ("uc", link) not in possible}
    may_hold = {link for link in links if ("uc", link) not in true}
    offered = {target for _, _, target in frame.supports}
    possibly_founded: set = set()
    changed = True
    while changed:
        changed = False
        for argument in frame.arguments - possibly_founded - refuted:
            if argument not in offered or any(
                link in may_hold and supporter not in refuted and supporter in possibly_founded
                for link, supporter, target in frame.supports
                if target == argument
            ):
                possibly_founded.add(argument)
                changed = True
    status: dict[Term, str] = {}
    check: dict[Term, str] = {}
    standing = {s for s in frame.established if s in accepted and s in founded}
    for argument in frame.arguments:
        if argument in refuted:
            status[argument] = "Refuted"
        elif argument in accepted and argument in founded:
            status[argument] = "Accepted"
        elif argument in offered and argument not in possibly_founded:
            status[argument] = "Unsupported"
        else:
            status[argument] = "Undecided"
        checked = argument not in refuted and (
            argument in standing
            or any(link in holds and supporter in standing for link, supporter, target in frame.supports if target == argument)
        )
        check[argument] = "Checked" if checked else "Unchecked"
    states = {
        link: "Holds" if link in holds else ("Withdrawn" if link not in may_hold else "Undecided") for link in links
    }
    return Labelling(status, check, states)


# --- the evidence rows -------------------------------------------------------------------------


# am[implements a-jk-reference-model-1018@ef9091]
class Refused(ValueError):
    """The rows break the contract; `kinds` are the kernel's problem kinds, in its own spelling."""

    def __init__(self, kinds: set[str]) -> None:
        super().__init__(", ".join(sorted(kinds)))
        self.kinds = kinds


# am[implements a-jk-reference-model-1018@ef9091]
def is_negation(term: Term) -> bool:
    return isinstance(term, tuple) and len(term) == 2 and term[0] == NOT


# am[implements a-jk-reference-model-1018@ef9091]
def contrary(claim: Term) -> Term:
    return claim[1] if is_negation(claim) else (NOT, claim)


# am[implements a-jk-reference-model-1018@ef9091]
def is_ground(term: Term) -> bool:
    if isinstance(term, tuple):
        return all(is_ground(child) for child in term)
    return not isinstance(term, Variable)


# An observation of the contract's one shape: (KIND ID ESTIMATOR VALIDITY), ESTIMATOR a known class
# and VALIDITY Forever or (Until NUMBER).
# am[implements a-jk-reference-model-1018@ef9091] am[implements a-jk-typed-boundary-1018@dee690]
def is_observation(term: Term) -> bool:
    return (
        isinstance(term, tuple)
        and len(term) == 4
        and isinstance(term[2], str)
        and term[2] in ESTIMATORS
        and (term[3] == FOREVER or (isinstance(term[3], tuple) and len(term[3]) == 2 and term[3][0] == UNTIL
                                    and is_number(term[3][1])))
    )


# A MeTTa Number: an int or a float, never a bool, which MeTTa types Bool.
# am[implements a-jk-reference-model-1018@ef9091]
def is_number(value: Term) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# A reference (CATEGORY TERM) of one of `categories`.
# am[implements a-jk-typed-boundary-1018@dee690]
def is_reference(term: Term, *categories: Symbol) -> bool:
    return isinstance(term, tuple) and len(term) == 2 and term[0] in categories


# am[implements a-jk-typed-boundary-1018@dee690]
def is_from(term: Term) -> bool:
    return isinstance(term, tuple) and len(term) == 3 and term[0] == FROM


# The model's own name for each public category, and back.
INTERNAL = {CLAIM: "claim", OBSERVATION: "observation", ROW: "row", STATED: "stated"}
PUBLIC = {name: symbol for symbol, name in INTERNAL.items()}


# The rows' reading, written apart from the kernel's MeTTa compile: each From row is an argument
# premised on the source it names and supporting its claim; contrary rows rebut each other when the
# attacker's tier is at least the target's, and an establishing row refutes the contrary claim;
# a withdrawal or an expired source undercuts every link the row speaks through, the withdrawal by
# the argument its reason names. Every source and reason names its category, (Claim C),
# (Observation O), (Row R) or (Stated X), so a term's role never depends on what else the rows
# hold, and the model's own identities, the stale reason ("stale", AT) and its links, are tuples no
# caller term can equal.
# Problems are found in the kernel's two stages: the time and each row's shape, and only when
# those hold, the references against the whole snapshot.
# Time: r^2 row pairs for the contraries, r = rows.
# am[implements a-jk-reference-model-1018@ef9091] am[rests-on c-jk-rows-as-arguments-1018@57a47d]
# am[implements a-jk-id-tagged-1018@d1757d] am[implements a-jk-typed-boundary-1018@dee690]
def compile_rows(at: int, rows: Iterable[Term]) -> tuple[Frame, list[Term]]:
    """The frame for `rows` at `at` and its From rows. Raises Refused like the kernel."""

    if not is_number(at):
        raise Refused({"MalformedTime"})
    rows = list(dict.fromkeys(rows))
    froms = [row for row in rows if is_ground(row) and is_from(row)]
    withdrawals = [
        row for row in rows
        if is_ground(row) and isinstance(row, tuple) and len(row) == 3 and row[0] == WITHDRAWN and is_from(row[1])
    ]
    shape = set()
    for row in rows:
        if not is_ground(row):
            shape.add("NonGround")
        elif row in froms:
            if is_negation(row[1]) and is_negation(row[1][1]):
                shape.add("DoubleNegation")
            source = row[2]
            if not (is_reference(source, CLAIM) or (is_reference(source, OBSERVATION) and is_observation(source[1]))):
                shape.add("MalformedSource")
        elif row in withdrawals:
            reason = row[2]
            if not (
                is_reference(reason, CLAIM, STATED)
                or (is_reference(reason, OBSERVATION) and is_observation(reason[1]))
                or (is_reference(reason, ROW) and is_from(reason[1]))
            ):
                shape.add("MalformedReason")
        else:
            shape.add("MalformedRow")
    if shape:
        raise Refused(shape)
    claims = {row[1] for row in froms}
    references = [row[2] for row in froms] + [row[2] for row in withdrawals]
    problems = set()
    if any(is_reference(r, CLAIM) and r[1] not in claims for r in references):
        problems.add("DanglingClaim")
    if any(is_reference(r, ROW) and r[1] not in froms for r in references):
        problems.add("DanglingRow")
    if any(row[1] not in froms for row in withdrawals):
        problems.add("DanglingWithdrawal")
    if problems:
        raise Refused(problems)
    observations = {r[1] for r in references if is_reference(r, OBSERVATION)}
    stated = {r[1] for r in references if is_reference(r, STATED)}

    def internal(reference: Term) -> tuple:
        return (INTERNAL[reference[0]], reference[1])

    def tier(row: Term) -> int:
        return 1 if is_reference(row[2], OBSERVATION) and row[2][1][2] in ESTABLISHING else 0

    def expired(row: Term) -> bool:
        validity = row[2][1][3] if is_reference(row[2], OBSERVATION) else FOREVER
        return validity != FOREVER and validity[1] < at

    supports = set()
    attacks = set()
    outgoing: dict[Term, set[Term]] = {row: {("infers", row)} for row in froms}
    for row in froms:
        supports.add((("premise", row), internal(row[2]), ("row", row)))
        supports.add((("infers", row), ("row", row), ("claim", row[1])))
    for first in froms:
        for second in froms:
            if second[1] == contrary(first[1]) and tier(first) >= tier(second):
                link = ("rebut", first, second)
                attacks.add((link, ("row", first), ("row", second)))
                outgoing[first].add(link)
        if tier(first) == 1 and contrary(first[1]) in claims:
            link = ("refute", first)
            attacks.add((link, ("row", first), ("claim", contrary(first[1]))))
            outgoing[first].add(link)
    undercuts = set()
    for _, row, reason in withdrawals:
        undercuts |= {(link, internal(reason)) for link in outgoing[row]}
    stale = ("stale", at)
    expiring = [row for row in froms if expired(row)]
    for row in expiring:
        undercuts |= {(link, stale) for link in outgoing[row]}
    established = {("observation", o) for o in observations if o[2] in ESTABLISHING} | {
        ("row", row) for row in froms if tier(row) == 1
    }
    arguments = frozenset(
        {("claim", c) for c in claims}
        | {("observation", o) for o in observations}
        | {("row", r) for r in froms}
        | {("stated", x) for x in stated}
        | ({stale} if expiring else set())
    )
    return Frame(arguments, frozenset(supports), frozenset(attacks), frozenset(undercuts), frozenset(established)), froms


# The kernel's answer for rows, as sets: one (Label REF STATUS CHECK) for every claim, observation,
# From row and stated reason, under its public reference, and one (Link (Row ROW) STATE) per From
# row, the state of the row's support of its claim alone; the stale reason is left out.
# am[implements a-jk-reference-model-1018@ef9091] am[implements a-jk-rr-row-report-1018@6747d2]
# am[implements a-jk-typed-boundary-1018@dee690]
def justify(at: int, rows: Iterable[Term]) -> tuple[set, set]:
    frame, froms = compile_rows(at, rows)
    labelling = label(frame)
    labels = {
        (Symbol("Label"), (PUBLIC[category], term), Symbol(labelling.status[(category, term)]),
         Symbol(labelling.check[(category, term)]))
        for category, term in frame.arguments
        if category != "stale"
    }
    links = {(Symbol("Link"), (ROW, row), Symbol(labelling.links[("infers", row)])) for row in froms}
    return labels, links


# What an answer knows about a literal: True from (Claim L)'s Accepted label and False from
# (Claim (Not L))'s, each with that label's check; None, Unknown, otherwise.
# am[implements a-jk-reference-model-1018@ef9091] am[implements a-jk-typed-boundary-1018@dee690]
def knowledge(literal: Term, labels: set) -> tuple[bool | None, str | None]:
    status = {label[1]: (str(label[2]), str(label[3])) for label in labels}
    for value, term in ((True, literal), (False, contrary(literal))):
        found = status.get((CLAIM, term))
        if found is not None and found[0] == "Accepted":
            return value, found[1]
    return None, None


# --- exhaustive grounded semantics, a third route for plain attack graphs -----------------------


# The grounded labelling is the complete labelling with the least IN set: IN iff every attacker
# is OUT, OUT iff some attacker is IN [source: Caminada, "On the issue of reinstatement in
# argumentation", JELIA 2006, Def. 5 and Theorem 1]. Time: 3^n labellings of n arguments.
# am[implements a-jk-reference-model-1018@ef9091]
def grounded_by_enumeration(arguments: list[Term], attacks: set[tuple[Term, Term]]) -> dict[Term, str]:
    best = None
    for labels in product(("in", "out", "undec"), repeat=len(arguments)):
        labelling = dict(zip(arguments, labels))
        attackers = {a: [b for b, t in attacks if t == a] for a in arguments}
        complete = all(
            (labelling[a] == "in") == all(labelling[b] == "out" for b in attackers[a])
            and (labelling[a] == "out") == any(labelling[b] == "in" for b in attackers[a])
            for a in arguments
        )
        if complete:
            ins = {a for a in arguments if labelling[a] == "in"}
            if best is None or ins < {a for a in arguments if best[a] == "in"}:
                best = labelling
    assert best is not None
    return best
