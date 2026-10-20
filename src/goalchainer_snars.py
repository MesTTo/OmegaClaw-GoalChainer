"""Purpose: the Python functions GoalChainer's SNARS library calls through py-call: statement
canonicalisation, sids, receipt hashes, peeling, labels, compounds, a Beta draw and the proof-tree
drawing, over the term-normal-form, S-expression and English modules in goal_chainer.snars_python.

py-call resolves one dot, module.function, so these live in a top-level module, as Mettabase's
mettabase_petta facade did; the functions are Mettabase c079c89's snars_* wrappers from
mettabase/petta/extension.py with their imports pointed at goal_chainer.snars_python."""

from __future__ import annotations

import json
import random

from goal_chainer.snars_python.english import hb_en
from goal_chainer.sexpr.syntax import StringLiteral, Symbol, emit, metta_string, parse
from goal_chainer.snars_python.tnf import (
    canonicalize,
    compounds,
    peel,
    predicate_subtype,
    receipt_hash,
    statement_sid,
    surface_labels,
)


# A plain-text view of a py-call argument: a string unquoted at the top level, a nested list or
# tuple re-emitted as a MeTTa expression. Mettabase's mettabase.ops.fuzzy.atom_text.
# am[implements a-rt-snars-python-helpers-1017@e0faec] am[rests-on c-rt-snars-python-closure-1017@7b1856]
def atom_text(atom) -> str:
    if isinstance(atom, (list, tuple)):
        return _expression_text(atom)
    get_object = getattr(atom, "get_object", None)
    if get_object is not None:
        try:
            value = get_object()
        except TypeError:
            value = None
        if isinstance(value, str):
            return value
    get_name = getattr(atom, "get_name", None)
    if get_name is not None:
        return get_name()
    text = str(atom)
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1]
    return text


# am[implements a-rt-snars-python-helpers-1017@e0faec]
def _expression_text(items: list | tuple) -> str:
    return "(" + " ".join(_expression_item_text(item) for item in items) + ")"


# am[implements a-rt-snars-python-helpers-1017@e0faec]
def _expression_item_text(atom) -> str:
    if isinstance(atom, (list, tuple)):
        return _expression_text(atom)
    text = atom_text(atom).replace('\\"', '"')
    if isinstance(atom, str) and _requires_string_literal(text):
        return json.dumps(text, ensure_ascii=False)
    return text


# am[implements a-rt-snars-python-helpers-1017@e0faec]
def _requires_string_literal(text: str) -> bool:
    return not text or any(ch.isspace() or ch in {"(", ")", '"', "'"} for ch in text)


# The canonical SNARS statement form.
# am[implements a-rt-snars-python-helpers-1017@e0faec]
def snars_canonical(tree) -> str:
    return canonicalize(atom_text(tree))


# (Peeled <canonical> <True|False> <mood>): the decorations peeled, the negation flag that routes
# complement evidence, and the root predicate's SH subtype, NoMood for a non-predicate root.
# am[implements a-rt-snars-python-helpers-1017@e0faec]
def snars_peel(tree) -> str:
    peeled, notes = peel(atom_text(tree))
    negated = "True" if notes.negated else "False"
    mood = predicate_subtype(peeled) or "NoMood"
    return f"(Peeled {canonicalize(peeled)} {negated} {mood})"


# (Notes (dets "the" ...) (aux "will" ...)): what peel records beside the peeled form.
# am[implements a-rt-snars-python-helpers-1017@e0faec]
def snars_peel_notes(tree) -> str:
    _, notes = peel(atom_text(tree))
    dets = " ".join(f'"{d}"' for d in notes.determiners)
    aux = " ".join(f'"{a}"' for a in notes.auxiliaries)
    return f"(Notes (dets {dets}) (aux {aux}))"


# The content-addressed statement id.
# am[implements a-rt-snars-python-helpers-1017@e0faec]
def snars_sid(tree) -> str:
    return statement_sid(atom_text(tree))


# A Thompson draw from Beta(alpha, beta), both shapes clamped off zero so a fresh trust cell samples
# at the boundary instead of failing.
# am[implements a-rt-snars-python-helpers-1017@e0faec]
def snars_beta_sample(alpha, beta) -> float:
    a = max(1e-9, float(atom_text(alpha)))
    b = max(1e-9, float(atom_text(beta)))
    return random.betavariate(a, b)


# A proof DAG, (PfLeaf "english") or (PfNode "english" kind (child ...)), drawn as an indented
# tree in one MeTTa string, each node annotated with its rule kind; an (hb en TREE) node is
# rendered as an English sentence.
# Time: linear in the DAG's size.
# am[implements a-rt-snars-python-helpers-1017@e0faec] am[rests-on c-rt-snars-english-renderer-scope-1017@30f765]
def snars_draw_tree(dag) -> str:
    def text(node) -> str:
        if isinstance(node, StringLiteral):
            return node.value
        if isinstance(node, Symbol):
            return node.text
        if (
            isinstance(node, list)
            and len(node) == 3
            and isinstance(node[0], Symbol)
            and node[0].text == "hb"
            and isinstance(node[1], Symbol)
            and node[1].text == "en"
        ):
            return hb_en(emit(node[2]))
        return emit(node)

    lines: list[str] = []

    def walk(node, prefix: str, last: bool, root: bool) -> None:
        head = node[0].text if isinstance(node, list) and node and isinstance(node[0], Symbol) else ""
        branch = "" if root else ("\\- " if last else "+- ")
        if head == "PfLeaf":
            lines.append(f"{prefix}{branch}{text(node[1])}  [obs]")
            return
        if head == "PfNode":
            lines.append(f"{prefix}{branch}{text(node[1])}  [{text(node[2])}]")
            kids = node[3] if len(node) > 3 and isinstance(node[3], list) else []
            child_prefix = prefix + ("" if root else ("   " if last else "|  "))
            for i, kid in enumerate(kids):
                walk(kid, child_prefix, i == len(kids) - 1, root=False)
            return
        lines.append(f"{prefix}{branch}{text(node)}")

    walk(parse(atom_text(dag)), "", last=True, root=True)
    return metta_string("\n".join(lines))


# (concept surface) display pairs as one expression.
# am[implements a-rt-snars-python-helpers-1017@e0faec]
def snars_labels(tree) -> str:
    pairs = surface_labels(atom_text(tree))
    return "(" + " ".join(f"({concept} {surface})" for concept, surface in pairs) + ")"


# (compound head) pairs for structural edges.
# am[implements a-rt-snars-python-helpers-1017@e0faec]
def snars_compounds(tree) -> str:
    pairs = compounds(atom_text(tree))
    return "(" + " ".join(f"({compound} {head})" for compound, head in pairs) + ")"


# A receipt id for one (statement, source) pair.
# am[implements a-rt-snars-python-helpers-1017@e0faec]
def snars_receipt_hash(sid, sigma) -> str:
    return receipt_hash(atom_text(sid), atom_text(sigma))
