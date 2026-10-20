"""Purpose: read a neutral domain's optional bigraph section, its gc-brs-* forms, into one data-only
BigraphSection: the signature's controls, the declared entities, where each sits, what each entity
port links to, the entity and links each knowledge literal is anchored on, and each action's
reaction as the bigraph kernel's terms; and answer the section's facts, which the domain loader's
validation runner checks against the section's fault tables in bigraph.metta.

    (gc-brs-control NAME (Ports PORT ...) KIND)          KIND atomic, active or passive
    (gc-brs-entity ID CONTROL ["description"])           a declared entity
    (gc-brs-in ID PARENT)                                PARENT an entity or (Root J)
    (gc-brs-link ID PORT LINK)                           LINK (Edge E), closed, or (Name Y), open
    (gc-brs-literal L (On ENTITY) [(Via LINK ...)])      L (Signal SIGNAL) or (Statement TREE)
    (gc-brs-reaction ACTION (Redex TERM) (Reactum TERM) (Eta ...) (Conditions ...))

This module reads each form's shape only. What the forms must satisfy together, such as every
entity's control being declared or every literal naming a declared signal, is checked by the
section's fault tables (CHECKS, through the typed entry ENTRY) over the facts FACTS answers. A
literal and a reaction's terms stay the atoms pymetta parsed, since their
meaning belongs to their readers: the planner reads a literal with the procedure library's literal
grammar, and the bigraph kernel reads the terms. The vocabulary mirrors BigraphER's model language,
so a section exports to BigraphER for the kernel's differential.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .forms import TopLevelForm
from .model import DomainError

# The section's form heads; the domain loader hands every form with one of these heads to
# read_section, so it never reads the section itself.
# am[implements a-rel-brs-section-1018@b63f59] am[rests-on c-rel-pj-loader-imports-section-readers-1018@4e1a4e]
HEADS = frozenset({"gc-brs-control", "gc-brs-entity", "gc-brs-in", "gc-brs-link", "gc-brs-literal", "gc-brs-reaction"})
# A control's kind as the kernel reads it: an atomic node holds nothing, a passive node holds
# nodes no reaction reaches into, and an active one admits reactions inside it.
# am[implements a-rel-brs-section-1018@b63f59]
KINDS = ("atomic", "active", "passive")
# The section's fault tables, their typed entry and their warm-up, which the domain loader's validation
# runner loads into its domain-checks module group: it warms the tables once per process and calls the
# entry with the domain's facts.
# am[implements a-rel-nd-validation-runner-1018] am[implements a-rel-nd-section-warm-ups-1018]
CHECKS = Path(__file__).resolve().with_name("bigraph.metta")
ENTRY = "gc-brs-run-faults"
WARM_UP = "gc-brs-checks-warm-up"


# am[implements a-rel-brs-section-1018@b63f59]
@dataclass(frozen=True, slots=True)
class Control:
    """A control of the signature: its name, its ports by name in positional order, and its kind."""

    name: str
    ports: tuple[str, ...]
    kind: str


# am[implements a-rel-brs-section-1018@b63f59]
@dataclass(frozen=True, slots=True)
class Entity:
    """An observed entity of the declared world, with its control and an optional description."""

    id: str
    control: str
    description: str = ""


# am[implements a-rel-brs-section-1018@b63f59]
@dataclass(frozen=True, slots=True)
class Root:
    """The J-th root, a region of the declared world."""

    index: int


# am[implements a-rel-brs-section-1018@b63f59]
@dataclass(frozen=True, slots=True)
class Placement:
    """Where an entity sits: under another entity, or at a root."""

    entity: str
    parent: str | Root


# am[implements a-rel-brs-section-1018@b63f59]
@dataclass(frozen=True, slots=True)
class Edge:
    """A closed link, named only inside the section."""

    name: str


# am[implements a-rel-brs-section-1018@b63f59]
@dataclass(frozen=True, slots=True)
class Name:
    """An open link, an outer name of the declared world."""

    name: str


# am[implements a-rel-brs-section-1018@b63f59]
@dataclass(frozen=True, slots=True)
class PortLink:
    """What one named port of an entity links to."""

    entity: str
    port: str
    link: Edge | Name


# The literal stays the atom pymetta read, (Signal SIGNAL) or (Statement TREE): the planner reads it
# with the procedure library's literal grammar, so two spellings of one statement are one literal.
# am[implements a-rel-brs-section-1018@b63f59]
@dataclass(frozen=True, slots=True)
class Anchor:
    """The entity a knowledge literal is about, and the links its subject reaches through `via`."""

    literal: Any
    entity: str
    via: tuple[str, ...] = ()


# The terms stay the atoms pymetta read, the kernel's (Bigraph ...) redex and reactum, the reactum
# sites' map (Eta (J I) ...) and the application conditions (Conditions ...), which the kernel checks.
# am[implements a-rel-brs-section-1018@b63f59]
@dataclass(frozen=True, slots=True)
class Reaction:
    """An action's structural effect, one reaction rule over the signature."""

    action: str
    redex: Any
    reactum: Any
    eta: Any
    conditions: Any


# am[implements a-rel-brs-section-1018@b63f59]
@dataclass(frozen=True, slots=True)
class BigraphSection:
    """A domain's bigraph section, each kind of form in the order the file declares it."""

    controls: tuple[Control, ...] = ()
    entities: tuple[Entity, ...] = ()
    placements: tuple[Placement, ...] = ()
    links: tuple[PortLink, ...] = ()
    anchors: tuple[Anchor, ...] = ()
    reactions: tuple[Reaction, ...] = ()


# am[implements a-rel-brs-section-1018@b63f59]
_SHAPES = {
    "gc-brs-control": "(gc-brs-control NAME (Ports PORT ...) KIND) with KIND atomic, active or passive",
    "gc-brs-entity": '(gc-brs-entity ID CONTROL ["description"])',
    "gc-brs-in": "(gc-brs-in ID PARENT) with PARENT an entity or (Root J)",
    "gc-brs-link": "(gc-brs-link ID PORT LINK) with LINK (Edge E) or (Name Y)",
    "gc-brs-literal": "(gc-brs-literal L (On ENTITY) [(Via LINK ...)])",
    "gc-brs-reaction": "(gc-brs-reaction ACTION (Redex TERM) (Reactum TERM) (Eta ...) (Conditions ...))",
}


# Each form is read by its head into one record; any form of the wrong shape raises DomainError
# naming the source, the form's text and the shape it should have.
# Time: linear in the forms' atoms.
# am[implements a-rel-brs-section-1018@b63f59] am[rests-on c-rel-pj-loader-imports-section-readers-1018@4e1a4e]
def read_section(forms: Iterable[tuple[TopLevelForm, Any]], source: str) -> BigraphSection:
    """The bigraph section the (form, atom) pairs of HEADS forms declare; `source` names the file."""

    read: dict[str, list[Any]] = {head: [] for head in HEADS}
    for form, atom in forms:
        parts = _children(atom)
        head = _symbol(parts[0]) if parts else None
        if head not in HEADS:
            raise DomainError(f"{source}: {form.text} is not a bigraph section form ({', '.join(sorted(HEADS))})")
        record = _READERS[head](parts[1:])
        if record is None:
            raise DomainError(f"{source}: {form.text} should be {_SHAPES[head]}")
        read[head].append(record)
    return BigraphSection(
        controls=tuple(read["gc-brs-control"]),
        entities=tuple(read["gc-brs-entity"]),
        placements=tuple(read["gc-brs-in"]),
        links=tuple(read["gc-brs-link"]),
        anchors=tuple(read["gc-brs-literal"]),
        reactions=tuple(read["gc-brs-reaction"]),
    )


# Each reader answers its record, or None when the arguments do not have the form's shape.
# am[implements a-rel-brs-section-1018@b63f59]
def _control(args: tuple[Any, ...]) -> Control | None:
    if len(args) != 3:
        return None
    name, ports, kind = _symbol(args[0]), _headed(args[1], "Ports"), _symbol(args[2])
    names = _symbols(ports)
    if name is None or names is None or kind not in KINDS:
        return None
    return Control(name, names, kind)


# am[implements a-rel-brs-section-1018@b63f59]
def _entity(args: tuple[Any, ...]) -> Entity | None:
    if len(args) not in (2, 3):
        return None
    entity, control = _symbol(args[0]), _symbol(args[1])
    description = _string(args[2]) if len(args) == 3 else ""
    if entity is None or control is None or description is None:
        return None
    return Entity(entity, control, description)


# am[implements a-rel-brs-section-1018@b63f59]
def _placement(args: tuple[Any, ...]) -> Placement | None:
    if len(args) != 2:
        return None
    entity, parent = _symbol(args[0]), _symbol(args[1])
    root = _headed(args[1], "Root")
    if parent is None and root is not None and len(root) == 1 and _natural(root[0]) is not None:
        parent = Root(_natural(root[0]))
    if entity is None or parent is None:
        return None
    return Placement(entity, parent)


# am[implements a-rel-brs-section-1018@b63f59]
def _port_link(args: tuple[Any, ...]) -> PortLink | None:
    if len(args) != 3:
        return None
    entity, port = _symbol(args[0]), _symbol(args[1])
    edge, name = _headed(args[2], "Edge"), _headed(args[2], "Name")
    link: Edge | Name | None = None
    if edge is not None and len(edge) == 1 and _symbol(edge[0]) is not None:
        link = Edge(_symbol(edge[0]))
    elif name is not None and len(name) == 1 and _symbol(name[0]) is not None:
        link = Name(_symbol(name[0]))
    if entity is None or port is None or link is None:
        return None
    return PortLink(entity, port, link)


# am[implements a-rel-brs-section-1018@b63f59]
def _anchor(args: tuple[Any, ...]) -> Anchor | None:
    if len(args) not in (2, 3) or _children(args[0]) is None:
        return None
    on = _headed(args[1], "On")
    entity = _symbol(on[0]) if on is not None and len(on) == 1 else None
    via = _symbols(_headed(args[2], "Via")) if len(args) == 3 else ()
    if entity is None or via is None:
        return None
    return Anchor(args[0], entity, via)


# am[implements a-rel-brs-section-1018@b63f59]
def _reaction(args: tuple[Any, ...]) -> Reaction | None:
    if len(args) != 5:
        return None
    action, redex, reactum = _symbol(args[0]), _headed(args[1], "Redex"), _headed(args[2], "Reactum")
    if (action is None or redex is None or len(redex) != 1 or reactum is None or len(reactum) != 1
            or _headed(args[3], "Eta") is None or _headed(args[4], "Conditions") is None):
        return None
    return Reaction(action, redex[0], reactum[0], args[3], args[4])


# am[implements a-rel-brs-section-1018@b63f59]
_READERS = {
    "gc-brs-control": _control,
    "gc-brs-entity": _entity,
    "gc-brs-in": _placement,
    "gc-brs-link": _port_link,
    "gc-brs-literal": _anchor,
    "gc-brs-reaction": _reaction,
}


# --- facts ---------------------------------------------------------------------------------------
# The section as the plain facts the validation runner reads (a-dr-readings-facts-1018): each fact is
# (HEAD, ARG, ...), HEAD an inert head's name and every ARG a string or a tuple of the same shape, so
# every list carries a head of its own and a root index is its canonical text. bigraph.metta's header
# lists them. A literal that is neither (Signal NAME) nor (Statement TREE) is the fact (Literal TEXT),
# which a row refuses. Each entity declared with a description is also (Described ID), since the facts
# carry no text and the reading section's binding rows refuse an undescribed entity a binding offers.
# Time: linear in the section's records and in the nodes of its reactions' terms.
# am[implements a-rel-nd-validation-runner-1018] am[related a-dr-readings-facts-1018]
# am[implements a-bnd-faults-1019@b5dc70] am[rests-on c-bnd-bigraph-facts-omit-description-1019@9ce542]
def FACTS(section: BigraphSection) -> tuple[tuple[Any, ...], ...]:  # noqa: N802 (the runner's section interface)
    """The section's facts in declaration order, kind by kind."""

    return (
        *(("Control", control.name, ("Ports", *control.ports), control.kind) for control in section.controls),
        *(("Entity", entity.id, entity.control) for entity in section.entities),
        *(("Described", entity.id) for entity in section.entities if entity.description),
        *(("Placed", placement.entity,
           ("Root", str(placement.parent.index)) if isinstance(placement.parent, Root) else placement.parent)
          for placement in section.placements),
        *(("PortLink", link.entity, link.port, ("Edge" if isinstance(link.link, Edge) else "Name", link.link.name))
          for link in section.links),
        *(("Anchor", _literal_fact(anchor.literal), anchor.entity, ("Via", *anchor.via)) for anchor in section.anchors),
        *(("Reaction", reaction.action, ("Controls", *_controls(reaction.redex), *_controls(reaction.reactum)))
          for reaction in section.reactions),
    )


# am[implements a-rel-nd-validation-runner-1018]
def _literal_fact(atom: Any) -> tuple[Any, ...]:
    parts = _children(atom) or ()
    head = _symbol(parts[0]) if len(parts) == 2 else None
    if head == "Signal" and _symbol(parts[1]) is not None:
        return ("Signal", _symbol(parts[1]))
    if head == "Statement" and _children(parts[1]) is not None:
        return ("Statement", str(parts[1]))
    return ("Literal", str(atom))


# The control of every (N ID CONTROL) row of a (Bigraph ...) term's Nodes; any other term has none,
# and the kernel refuses it before the planner plans.
# am[implements a-rel-nd-validation-runner-1018]
def _controls(term: Any) -> tuple[Any, ...]:
    sections = (_children(term) or ())[1:]
    nodes = next((rows for rows in (_headed(part, "Nodes") for part in sections) if rows is not None), ())
    return tuple(_term_fact(row[2]) for row in (_children(node) for node in nodes) if row is not None and len(row) == 3)


# A term as a fact argument: an expression as its head's name and its arguments', a string as itself,
# and any other atom as its text.
# am[implements a-rel-nd-validation-runner-1018]
def _term_fact(atom: Any) -> Any:
    parts = _children(atom)
    if parts:
        return (_symbol(parts[0]) or str(parts[0]), *(_term_fact(part) for part in parts[1:]))
    text = _string(atom)
    return text if text is not None else str(atom)


# --- atoms ---------------------------------------------------------------------------------------
# A name is a symbol, never a string, a number or a variable, so it reads back as itself in every
# term the planner and the kernel build from it.


# am[implements a-rel-brs-section-1018@b63f59] am[related a-rel-nd-pymetta-atoms-1018@f047df]
def _children(atom: Any) -> tuple[Any, ...] | None:
    from metta import Expression  # noqa: PLC0415 (pymetta is imported once a form is parsed)

    return tuple(atom.children) if isinstance(atom, Expression) else None


# am[implements a-rel-brs-section-1018@b63f59]
def _symbol(atom: Any) -> str | None:
    from metta import Symbol  # noqa: PLC0415

    return str(atom) if isinstance(atom, Symbol) else None


# am[implements a-rel-brs-section-1018@b63f59]
def _string(atom: Any) -> str | None:
    from metta import Grounded  # noqa: PLC0415

    return atom.value if isinstance(atom, Grounded) and isinstance(atom.value, str) else None


# am[implements a-rel-brs-section-1018@b63f59]
def _natural(atom: Any) -> int | None:
    from metta import Grounded  # noqa: PLC0415

    value = atom.value if isinstance(atom, Grounded) else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


# The arguments of an expression headed HEAD, or None for any other atom.
# am[implements a-rel-brs-section-1018@b63f59]
def _headed(atom: Any, head: str) -> tuple[Any, ...] | None:
    parts = _children(atom)
    return parts[1:] if parts and _symbol(parts[0]) == head else None


# The names of a list of symbols, or None when it is missing or holds anything else.
# am[implements a-rel-brs-section-1018@b63f59]
def _symbols(atoms: tuple[Any, ...] | None) -> tuple[str, ...] | None:
    if atoms is None:
        return None
    names = tuple(_symbol(atom) for atom in atoms)
    return None if any(name is None for name in names) else names


__all__ = [
    "Anchor",
    "BigraphSection",
    "CHECKS",
    "Control",
    "Edge",
    "ENTRY",
    "Entity",
    "FACTS",
    "HEADS",
    "KINDS",
    "Name",
    "Placement",
    "PortLink",
    "Reaction",
    "Root",
    "read_section",
]
