"""COLORE ontology context for GoalChainer."""

from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_COLORE_FIXTURE = Path(
    "/home/user/Dev/mettabase/tests/petta/data-colore.metta"
)

MODULE_RE = re.compile(r'^\(colore module (?P<module>\S+) "(?P<uri>[^"]+)"\)$')
AXIOM_RE = re.compile(r"^\(colore axiom (?P<module>\S+) (?P<axiom_id>\S+) (?P<kind>\S+) (?P<expr>.+)\)$")
GLOSS_RE = re.compile(r'^\(colore gloss (?P<module>\S+) (?P<axiom_id>\S+) "(?P<text>.*)"\)$')
PRED_RE = re.compile(r"^\(colore pred (?P<module>\S+) (?P<predicate>\S+) (?P<arity>\d+)\)$")


@dataclass(frozen=True)
class ColoreAxiom:
    module: str
    axiom_id: str
    kind: str
    expression: str
    gloss: str = ""

    @property
    def source(self) -> str:
        return f"{self.module}/{self.axiom_id}"

    def to_dict(self) -> dict[str, str]:
        return {
            "source": self.source,
            "module": self.module,
            "axiom_id": self.axiom_id,
            "kind": self.kind,
            "expression": self.expression,
            "gloss": self.gloss,
        }


@dataclass(frozen=True)
class OntologyContext:
    source_path: Path
    source_available: bool
    module_count: int
    axiom_count: int
    predicate_count: int
    gloss_count: int
    axiom_kinds: dict[str, int]
    selected_axioms: tuple[ColoreAxiom, ...]
    projection_rules: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "source_available": self.source_available,
            "module_count": self.module_count,
            "axiom_count": self.axiom_count,
            "predicate_count": self.predicate_count,
            "gloss_count": self.gloss_count,
            "axiom_kinds": dict(self.axiom_kinds),
            "selected_axioms": [axiom.to_dict() for axiom in self.selected_axioms],
            "projection_rules": list(self.projection_rules),
        }


def load_colore_context(path: str | Path | None = None) -> OntologyContext:
    source_path = Path(path) if path is not None else _default_colore_fixture()
    if not source_path.exists():
        return OntologyContext(
            source_path=source_path,
            source_available=False,
            module_count=0,
            axiom_count=0,
            predicate_count=0,
            gloss_count=0,
            axiom_kinds={},
            selected_axioms=(),
            projection_rules=_projection_rules({}),
        )

    modules: list[str] = []
    predicates: list[tuple[str, str, int]] = []
    axiom_rows: list[ColoreAxiom] = []
    gloss_rows: list[tuple[str, str]] = []
    axioms: dict[tuple[str, str], ColoreAxiom] = {}
    glosses: dict[tuple[str, str], str] = {}

    for raw_line in source_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        if match := MODULE_RE.match(line):
            modules.append(match.group("module"))
            continue
        if match := PRED_RE.match(line):
            predicates.append(
                (match.group("module"), match.group("predicate"), int(match.group("arity")))
            )
            continue
        if match := GLOSS_RE.match(line):
            gloss_rows.append((match.group("module"), match.group("axiom_id")))
            glosses[(match.group("module"), match.group("axiom_id"))] = match.group("text")
            continue
        if match := AXIOM_RE.match(line):
            key = (match.group("module"), match.group("axiom_id"))
            axiom = ColoreAxiom(
                module=match.group("module"),
                axiom_id=match.group("axiom_id"),
                kind=match.group("kind"),
                expression=match.group("expr"),
            )
            axiom_rows.append(axiom)
            axioms[key] = axiom

    axioms = {
        key: ColoreAxiom(
            module=axiom.module,
            axiom_id=axiom.axiom_id,
            kind=axiom.kind,
            expression=axiom.expression,
            gloss=glosses.get(key, ""),
        )
        for key, axiom in axioms.items()
    }
    selected = tuple(
        axiom
        for key in _SELECTED_AXIOM_KEYS
        if (axiom := axioms.get(key)) is not None
    )
    return OntologyContext(
        source_path=source_path,
        source_available=True,
        module_count=len(modules),
        axiom_count=len(axiom_rows),
        predicate_count=len(predicates),
        gloss_count=len(gloss_rows),
        axiom_kinds=dict(Counter(axiom.kind for axiom in axiom_rows)),
        selected_axioms=selected,
        projection_rules=_projection_rules(axioms),
    )


def _default_colore_fixture() -> Path:
    return Path(os.environ.get("GOALCHAINER_COLORE_FIXTURE", str(DEFAULT_COLORE_FIXTURE)))


_SELECTED_AXIOM_KEYS = (
    ("timepoints/lp_ordering", "a1"),
    ("kinship/definitions/hasGrandchild", "HGC-1"),
    ("kinship/definitions/hasSibling", "HS-1"),
)


def _projection_rules(axioms: dict[tuple[str, str], ColoreAxiom]) -> tuple[dict[str, Any], ...]:
    specs = (
        {
            "id": "time-before-transitivity",
            "key": ("timepoints/lp_ordering", "a1"),
            "from": ["before(x, y)", "before(y, z)"],
            "to": "before(x, z)",
            "demo_use": "sequence security review before external update before public follow-up",
        },
        {
            "id": "relation-composition-grandchild",
            "key": ("kinship/definitions/hasGrandchild", "HGC-1"),
            "from": ["hasChild(x, y)", "hasChild(y, z)"],
            "to": "hasGrandchild(x, z)",
            "demo_use": "shows COLORE definitions can compile into goal-directed composition rules",
        },
        {
            "id": "relation-composition-sibling",
            "key": ("kinship/definitions/hasSibling", "HS-1"),
            "from": ["hasChild(z, x)", "hasChild(z, y)", "x != y"],
            "to": "hasSibling(x, y)",
            "demo_use": "shows an ontology-derived relation can stay queryable without guessing",
        },
    )
    rows = []
    for spec in specs:
        key = spec["key"]
        axiom = axioms.get(key)
        rows.append(
            {
                "id": spec["id"],
                "source": f"{key[0]}/{key[1]}",
                "available": axiom is not None,
                "kind": axiom.kind if axiom else None,
                "from": spec["from"],
                "to": spec["to"],
                "gloss": axiom.gloss if axiom else "",
                "demo_use": spec["demo_use"],
            }
        )
    return tuple(rows)
