"""Canonical TNF form and content-addressed statement ids for SNARS statements.

The canonical form is the typed projection (`typed_projection.edge_to_typed_metta`)
normalized so that one statement has exactly one spelling, hence one sid:

- tags are always 4-slot ``(tag <type> <subtype> <roles> <amr>)`` — the 4th slot
  is the AMR sense slot (`()` when no concept has been promoted),
- predicate subtypes normalize to ``d`` (parser-build provenance, not semantics),
- voice roles normalize to the subject (``p``/``a`` → ``s``),
- args are ordered by canonical role precedence and the connector roles string
  is rebuilt to match,
- labels are string literals,
- nested statements are referenced as ``(sn-ref <sid>)``, never inlined.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ..sexpr.syntax import Atom, StringLiteral, Symbol, emit, parse

NO_SUBTYPE = "NoSubtype"
NO_ROLES = "NoRoles"
UNKNOWN_ROLE = "UnknownRole"
SID_PREFIX = "s"
RECEIPT_PREFIX = "h"
SID_DIGEST_SIZE = 16
RECEIPT_DIGEST_SIZE = 8

ROLE_PRECEDENCE = "scioxtjr"
VOICE_ROLES = {"p": "s", "a": "s"}
PREDICATE_SUBTYPE = "d"

# truth-preserving auxiliary/copula lemma forms (do-support, passive copulas,
# perfect aspect); modals (can/may/must/...) are NOT here — they make a
# different statement and must keep their own identity
AUX_FORMS = frozenset(
    ["is", "are", "was", "were", "am", "be", "been", "being", "does", "do", "did", "has", "have", "had"]
)
AGENT_MARKER = "by"

# the relational-extraction (O9) surface: copula + genitive builder rewrites
# to a relational predication keyed by the compound concept
COPULA_FORMS = frozenset(["is", "are", "was", "were", "am", "be", "been", "being"])
GENITIVE_LABELS = frozenset(["of", "'s"])


@dataclass(frozen=True, slots=True)
class PeelNotes:
    """Decorations consumed by the TNF peel pass."""

    determiners: tuple[str, ...] = ()
    negated: bool = False
    auxiliaries: tuple[str, ...] = ()


def _as_tree(tree: str | Atom) -> Atom:
    return parse(tree) if isinstance(tree, str) else tree


def _head(node: Atom) -> str:
    if isinstance(node, list) and node and isinstance(node[0], Symbol):
        return node[0].text
    return ""


def _label_literal(label: Atom) -> Atom:
    if isinstance(label, Symbol) and not label.text.startswith("$"):
        return StringLiteral(label.text)
    return label


def _role_key(role: str) -> tuple[int, str]:
    index = ROLE_PRECEDENCE.find(role)
    return (index, "") if index >= 0 else (len(ROLE_PRECEDENCE), role)


def _canonical_role(role: Atom) -> Atom:
    if isinstance(role, Symbol):
        return Symbol(VOICE_ROLES.get(role.text, role.text))
    return role


def _canonical_tag(tag: Atom, role_letters: list[str] | None = None) -> Atom:
    if not (isinstance(tag, list) and _head(tag) == "tag" and len(tag) >= 4):
        return tag
    main_type, subtype, roles = tag[1], tag[2], tag[3]
    amr: Atom = tag[4] if len(tag) >= 5 else []
    if isinstance(main_type, Symbol) and main_type.text == "P" and isinstance(subtype, Symbol):
        subtype = Symbol(PREDICATE_SUBTYPE)
    if role_letters is not None and isinstance(roles, Symbol):
        roles = Symbol("".join(role_letters) or NO_ROLES)
    return [Symbol("tag"), main_type, subtype, roles, amr]


def _split_args(args_expr: Atom) -> list[Atom] | None:
    """Return the arg items of an ``(args (...))`` expression, or None."""
    if not (isinstance(args_expr, list) and _head(args_expr) == "args" and len(args_expr) == 2):
        return None
    items = args_expr[1]
    if not isinstance(items, list):
        return None
    return items


def _canonical_args(
    args_expr: Atom, surfaces: list[tuple[Atom, Atom]] | None = None
) -> tuple[Atom, list[str] | None]:
    """Canonicalize an args expression; return it plus sorted role letters."""
    items = _split_args(args_expr)
    if items is None:
        return args_expr, None

    pairs: list[tuple[Atom, Atom]] = []
    for item in items:
        if isinstance(item, list) and _head(item) == "arg" and len(item) == 3:
            pairs.append((_canonical_role(item[1]), canonical_tree(item[2], surfaces)))
        else:
            return [Symbol("args"), [canonical_tree(it, surfaces) for it in items]], None

    sortable = all(isinstance(role, Symbol) and len(role.text) == 1 for role, _ in pairs)
    if sortable:
        pairs.sort(key=lambda pair: _role_key(pair[0].text))
        letters = [role.text for role, _ in pairs]
    else:
        letters = None

    rebuilt = [[Symbol("arg"), role, child] for role, child in pairs]
    return [Symbol("args"), rebuilt], letters


def _amr_concept(tag: Atom) -> Atom | None:
    """Return the promoted AMR concept of a 4-slot tag, or None."""
    if not (isinstance(tag, list) and _head(tag) == "tag" and len(tag) >= 5):
        return None
    amr = tag[4]
    if isinstance(amr, list) and _head(amr) == "amr" and len(amr) >= 2:
        return amr[1]
    return None


def _canonical_label(tag: Atom, label: Atom, surfaces: list[tuple[Atom, Atom]] | None) -> Atom:
    """Sense-resolved nodes are labelled BY THE AMR ATOM; strings are display-only.

    The world model stores, matches, and chains over sense atoms — when the
    tag's AMR slot is filled, the surface label is replaced by the concept
    (buy/purchase-01 and purchase/purchase-01 are the same node) and the
    surface string is reported through ``surfaces`` for `(sn label ...)` facts.
    Unresolved nodes keep their surface label as identity.
    """
    concept = _amr_concept(tag)
    if concept is None:
        return _label_literal(label)
    if surfaces is not None and isinstance(label, (Symbol, StringLiteral)):
        text = label.text if isinstance(label, Symbol) else label.value
        if not text.startswith("$") and text != _concept_text(concept):
            surfaces.append((concept, StringLiteral(text)))
    return concept


def _concept_text(concept: Atom) -> str:
    if isinstance(concept, Symbol):
        return concept.text
    if isinstance(concept, StringLiteral):
        return concept.value
    return emit(concept)


def canonical_tree(node: str | Atom, surfaces: list[tuple[Atom, Atom]] | None = None) -> Atom:
    """Return the canonical TNF form of a typed SH tree.

    ``surfaces`` (optional) collects (concept, surface-string) pairs displaced
    by sense resolution, for emission as `(sn label ...)` facts.
    """
    node = _as_tree(node)
    if not isinstance(node, list):
        return node

    head = _head(node)
    if head == "sh-atom" and len(node) == 3:
        return [node[0], _canonical_tag(node[1]), _canonical_label(node[1], node[2], surfaces)]
    if head == "sh" and len(node) == 4:
        args, letters = _canonical_args(node[3], surfaces)
        return [
            node[0],
            _canonical_tag(node[1], letters),
            _canonical_label(node[1], node[2], surfaces),
            args,
        ]
    if head == "sh-conn" and len(node) == 3:
        args, _letters = _canonical_args(node[2], surfaces)
        return [node[0], canonical_tree(node[1], surfaces), args]
    if head == "tag":
        return _canonical_tag(node)
    if head in ("sn-ref", "sn"):
        return node
    return [canonical_tree(child, surfaces) for child in node]


def canonicalize(tree: str | Atom, surfaces: list[tuple[Atom, Atom]] | None = None) -> str:
    """Render the canonical TNF text of a typed SH tree."""
    return emit(canonical_tree(tree, surfaces))


def surface_labels(tree: str | Atom) -> list[tuple[str, str]]:
    """Collect (concept, surface) display pairs displaced by sense resolution."""
    surfaces: list[tuple[Atom, Atom]] = []
    canonical_tree(tree, surfaces)
    seen: set[tuple[str, str]] = set()
    pairs: list[tuple[str, str]] = []
    for concept, surface in surfaces:
        pair = (emit(concept), emit(surface))
        if pair not in seen:
            seen.add(pair)
            pairs.append(pair)
    return pairs


def predicate_subtype(tree: str | Atom) -> str | None:
    """Return the root predicate's original SH subtype (the speech-act mood).

    The canonical form flattens it to ``d``: ``v`` declarative, ``i``
    interrogative, ``j`` imperative, ``n`` nominal/copular, ``e`` existential,
    ``x`` unclassified. Captured as metadata so the full SH form survives the
    canonicalization that keeps sids stable: a question, a command and a
    statement of the same proposition share one sid (one world-model fact) but
    keep distinct moods downstream (the SNARS-SH Mapping §1.3 routing).
    """
    node = _as_tree(tree)
    if not (isinstance(node, list) and _head(node) == "sh" and len(node) == 4):
        return None
    tag = node[1]
    if not (isinstance(tag, list) and _head(tag) == "tag" and len(tag) >= 3):
        return None
    main, sub = tag[1], tag[2]
    if isinstance(main, Symbol) and main.text == "P" and isinstance(sub, Symbol):
        return sub.text
    return None


def statement_sid(tree: str | Atom) -> str:
    """Content-addressed statement id: blake2b of the canonical form.

    Sense identity rides the AMR atom by construction — resolved labels ARE
    the concept atoms in the canonical form, so no separate identity view.
    """
    canonical = canonicalize(tree)
    digest = hashlib.blake2b(canonical.encode("utf-8"), digest_size=SID_DIGEST_SIZE)
    return SID_PREFIX + digest.hexdigest()


def receipt_hash(sid: str, sigma: str, salt: str | None = None) -> str:
    """Content-addressed receipt id for one (statement, source) observation."""
    payload = f"{sid}|{sigma}|{salt or ''}"
    digest = hashlib.blake2b(payload.encode("utf-8"), digest_size=RECEIPT_DIGEST_SIZE)
    return RECEIPT_PREFIX + digest.hexdigest()


def _label_text(label: Atom) -> str | None:
    if isinstance(label, StringLiteral):
        return label.value
    if isinstance(label, Symbol):
        return label.text
    return None


def _tag_type(tag: Atom) -> str | None:
    if isinstance(tag, list) and _head(tag) == "tag" and len(tag) >= 4 and isinstance(tag[1], Symbol):
        return tag[1].text
    return None


def _single_wrapped(node: Atom) -> Atom | None:
    """The lone wrapped child of a one-arg ``(sh TAG LABEL (args ((arg _ X))))``."""
    items = _split_args(node[3]) if isinstance(node, list) and len(node) == 4 else None
    if (
        items is not None
        and len(items) == 1
        and isinstance(items[0], list)
        and _head(items[0]) == "arg"
        and len(items[0]) == 3
    ):
        return items[0][2]
    return None


def _unwrap_agent(item: Atom, determiners: list[str], polarity: list[bool], auxiliaries: list[str]) -> Atom:
    """Passive-agent unwrap: ``(arg s (sh (tag T ..) "by" (args ((arg _ X)))))`` -> X.

    Applied only to subject args of a predicate rebuilt from a passive
    connector form, where the by-phrase is provably the agent.
    """
    if not (isinstance(item, list) and _head(item) == "arg" and len(item) == 3):
        return item
    role, child = item[1], item[2]
    if not (isinstance(role, Symbol) and VOICE_ROLES.get(role.text, role.text) == "s"):
        return item
    if (
        isinstance(child, list)
        and _head(child) == "sh"
        and len(child) == 4
        and _tag_type(child[1]) == "T"
        and _label_text(child[2]) == AGENT_MARKER
    ):
        wrapped = _single_wrapped(child)
        if wrapped is not None:
            return [item[0], role, _peel_node(wrapped, determiners, polarity, auxiliaries)]
    return item


def _np_parts(node: Atom, determiners: list[str]) -> tuple[list[str], str] | None:
    """(modifier labels, head label) of a concept NP subtree, or None.

    Consumes determiners into the peel notes; flattens noun-noun (+/B)
    compounds left-to-right; modifier order is outermost-first.
    """
    if not isinstance(node, list):
        return None
    head = _head(node)
    if head == "sh-atom" and len(node) == 3 and _tag_type(node[1]) == "C":
        text = _label_text(node[2])
        return ([], text) if text is not None else None
    if head == "sh" and len(node) == 4:
        tag, label = node[1], node[2]
        ttype = _tag_type(tag)
        wrapped = _single_wrapped(node)
        if ttype == "M" and isinstance(tag[2], Symbol) and wrapped is not None:
            text = _label_text(label)
            if tag[2].text == "d":
                if text is not None:
                    determiners.append(text)
                return _np_parts(wrapped, determiners)
            if tag[2].text == "a" and text is not None:
                inner = _np_parts(wrapped, determiners)
                if inner is None:
                    return None
                mods, head_lbl = inner
                return ([text, *mods], head_lbl)
            return None
        if ttype == "B" and _label_text(label) == "+":
            items = _split_args(node[3])
            if items is None or len(items) != 2:
                return None
            by_role: dict[str, Atom] = {}
            for item in items:
                if isinstance(item, list) and _head(item) == "arg" and len(item) == 3 and isinstance(item[1], Symbol):
                    by_role[item[1].text] = item[2]
            if set(by_role) != {"a", "m"}:
                return None
            aux = _np_parts(by_role["a"], determiners)
            main = _np_parts(by_role["m"], determiners)
            if aux is None or main is None:
                return None
            return ([*aux[0], aux[1], *main[0]], main[1])
    return None


def _genitive_parts(node: Atom) -> tuple[Atom, Atom] | None:
    """(np-side, relatum-side) of a genitive builder node, matched by role."""
    if not (isinstance(node, list) and _head(node) == "sh" and len(node) == 4):
        return None
    if _tag_type(node[1]) != "B" or _label_text(node[2]) not in GENITIVE_LABELS:
        return None
    items = _split_args(node[3])
    if items is None or len(items) != 2:
        return None
    by_role: dict[str, Atom] = {}
    for item in items:
        if isinstance(item, list) and _head(item) == "arg" and len(item) == 3 and isinstance(item[1], Symbol):
            by_role[item[1].text] = item[2]
    if set(by_role) != {"a", "m"}:
        return None
    return by_role["m"], by_role["a"]


def _relational_rewrite(
    node: Atom, determiners: list[str], polarity: list[bool], auxiliaries: list[str]
) -> Atom | None:
    """O9: ``(is X (of/'s m:NP a:Y))`` -> relational predication NP(X, Y).

    The compound concept becomes the amr key (`(amr (great pibling))`), the
    NP's surface becomes the display label, and the by-role match makes the
    rewrite order-insensitive (`of/Bx.ma` and `'s/Bx.am` both land here).
    """
    label = _label_text(node[2])
    if label is None or label.lower() not in COPULA_FORMS:
        return None
    items = _split_args(node[3])
    if items is None or len(items) != 2:
        return None
    by_role: dict[str, Atom] = {}
    for item in items:
        if isinstance(item, list) and _head(item) == "arg" and len(item) == 3 and isinstance(item[1], Symbol):
            by_role[VOICE_ROLES.get(item[1].text, item[1].text)] = item[2]
    if set(by_role) != {"s", "o"}:
        return None
    genitive = _genitive_parts(by_role["o"])
    if genitive is None:
        return None
    np_node, relatum = genitive
    parts = _np_parts(np_node, determiners)
    if parts is None:
        return None
    mods, head_lbl = parts
    key: Atom = [Symbol(m) for m in [*mods, head_lbl]] if mods else Symbol(head_lbl)
    surface = " ".join([*mods, head_lbl])
    return [
        Symbol("sh"),
        [Symbol("tag"), Symbol("P"), Symbol("d"), Symbol("so"), [Symbol("amr"), key]],
        StringLiteral(surface),
        [
            Symbol("args"),
            [
                [Symbol("arg"), Symbol("s"), _peel_node(by_role["s"], determiners, polarity, auxiliaries)],
                [Symbol("arg"), Symbol("o"), _peel_node(relatum, determiners, polarity, auxiliaries)],
            ],
        ],
    ]


def _peel_node(
    node: Atom, determiners: list[str], polarity: list[bool], auxiliaries: list[str]
) -> Atom:
    if not isinstance(node, list):
        return node

    head = _head(node)
    if head == "sh" and len(node) == 4:
        tag, label = node[1], node[2]
        wrapped = _single_wrapped(node)
        if _tag_type(tag) == "M" and isinstance(tag[2], Symbol) and wrapped is not None:
            if tag[2].text == "d":
                text = _label_text(label)
                if text is not None:
                    determiners.append(text)
                return _peel_node(wrapped, determiners, polarity, auxiliaries)
            if tag[2].text == "n":
                polarity[0] = not polarity[0]
                return _peel_node(wrapped, determiners, polarity, auxiliaries)
            if tag[2].text == "m":
                text = _label_text(label)
                if text is not None and text.lower() in AUX_FORMS:
                    auxiliaries.append(text)
                    return _peel_node(wrapped, determiners, polarity, auxiliaries)
        if _tag_type(tag) == "P":
            relational = _relational_rewrite(node, determiners, polarity, auxiliaries)
            if relational is not None:
                return relational

    if head == "sh-conn" and len(node) == 3:
        conn = _peel_node(node[1], determiners, polarity, auxiliaries)
        args = node[2]
        # the connector peeled down to a bare predicate atom (aux/negation
        # consumed): rebuild the plain predicate statement form, unwrapping a
        # passive by-agent in the subject slot
        if (
            isinstance(conn, list)
            and _head(conn) == "sh-atom"
            and len(conn) == 3
            and _tag_type(conn[1]) == "P"
        ):
            items = _split_args(args)
            if items is not None:
                peeled_items = [
                    _unwrap_agent(
                        [it[0], it[1], _peel_node(it[2], determiners, polarity, auxiliaries)]
                        if isinstance(it, list) and _head(it) == "arg" and len(it) == 3
                        else _peel_node(it, determiners, polarity, auxiliaries),
                        determiners,
                        polarity,
                        auxiliaries,
                    )
                    for it in items
                ]
                return [Symbol("sh"), conn[1], conn[2], [Symbol("args"), peeled_items]]
        return [node[0], conn, _peel_node(args, determiners, polarity, auxiliaries)]

    return [_peel_node(child, determiners, polarity, auxiliaries) for child in node]


def peel(tree: str | Atom) -> tuple[Atom, PeelNotes]:
    """Consume TNF decorations from a typed SH tree.

    Strips determiners, negation, and auxiliaries, collapsing aux-wrapped
    connector forms (passive voice, do-support) onto the plain predicate
    statement.
    """
    determiners: list[str] = []
    polarity = [False]
    auxiliaries: list[str] = []
    peeled = _peel_node(_as_tree(tree), determiners, polarity, auxiliaries)
    return peeled, PeelNotes(
        determiners=tuple(determiners),
        negated=polarity[0],
        auxiliaries=tuple(auxiliaries),
    )


def compounds(tree: str | Atom) -> list[tuple[str, str]]:
    """(compound, head) pairs for modifier-applied concepts (M.a edges).

    Interning a compound grows the taxonomy before any assertion is read:
    each pair backs a structural `<compound --> head>` edge (pipeline step 2).
    """
    found: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(pair: tuple[str, str]) -> None:
        if pair not in seen:
            seen.add(pair)
            found.append(pair)

    def walk(node: Atom) -> None:
        if not isinstance(node, list):
            return
        if _head(node) == "sh" and len(node) == 4:
            tag = node[1]
            items = _split_args(node[3])
            if (
                isinstance(tag, list)
                and _head(tag) == "tag"
                and len(tag) >= 4
                and isinstance(tag[1], Symbol)
                and tag[1].text == "M"
                and isinstance(tag[2], Symbol)
                and tag[2].text == "a"
                and items is not None
                and len(items) == 1
                and isinstance(items[0], list)
                and _head(items[0]) == "arg"
                and len(items[0]) == 3
            ):
                add((emit(node), emit(items[0][2])))
            # a composite relation key — (amr (great pibling)) on a P tag —
            # backs the same analytic edge as the spelled-out modifier form
            if _tag_type(tag) == "P":
                concept = _amr_concept(tag)
                if (
                    isinstance(concept, list)
                    and len(concept) >= 2
                    and all(isinstance(part, Symbol) for part in concept)
                ):
                    add(_key_compound_pair(concept))
        for child in node:
            walk(child)

    walk(canonical_tree(tree))
    return found


def _key_compound_pair(key: list[Symbol]) -> tuple[str, str]:
    """Reconstruct (compound-node, head-node) texts from a composite key."""
    head_tok = key[-1].text
    head_node: Atom = [
        Symbol("sh-atom"),
        [Symbol("tag"), Symbol("C"), Symbol("c"), Symbol(NO_ROLES), [Symbol("amr"), Symbol(head_tok)]],
        StringLiteral(head_tok),
    ]
    node = head_node
    for mod in reversed(key[:-1]):
        node = [
            Symbol("sh"),
            [Symbol("tag"), Symbol("M"), Symbol("a"), Symbol(NO_ROLES), [Symbol("amr"), mod]],
            StringLiteral(mod.text),
            [Symbol("args"), [[Symbol("arg"), Symbol(UNKNOWN_ROLE), node]]],
        ]
    return emit(node), emit(head_node)


def term_key(tree: str | Atom) -> str | None:
    """Coarse adjacency key (O18): atom label, else connector label.

    Mirrors the MeTTa `(sn term-key ...)` rule exactly — collisions only add
    verification candidates, never wrong results.
    """
    node = _as_tree(tree)
    if not isinstance(node, list):
        return None
    head = _head(node)
    if head == "sh-atom" and len(node) == 3:
        return emit(node[2])
    if head == "sh" and len(node) == 4:
        return emit(node[2])
    if head == "sh-conn" and len(node) == 3:
        return term_key(node[1])
    return None
