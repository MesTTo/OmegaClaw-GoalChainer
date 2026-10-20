"""Purpose: hand a domain's rules to the MeTTa readset policy once per domain, and ask it which signals one review rests on.

`policy/readset.metta` owns the rule: a conclusion's dependency cone is every signal reachable
backwards through the rules whose heads can match it, the defeasible-logic proof condition, so
what removed a rival or kept it from being a candidate is in a readset as surely as what
supports the winner (`c-rel-cone-sound-1016`). This module encodes the domain's parsed rules as
atoms, keeps the four kinds of cone the policy answers, and reads back the readsets of a review.

    dependency_index(domain, budget=budget).readsets(candidate_ids, budget=budget)
      -> Readsets(review=frozenset of signals, candidates={action: frozenset of signals})
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ..domains.model import Domain, Pattern
from ..runtime.budget import RunBudget, caller_budget
from .errors import RelevanceError
from .policy import evaluate, items, symbol, term, text


# am[implements a-rel-compiler-1016@c69c38] am[rests-on c-rel-cone-sound-1016@092cec]
@dataclass(frozen=True)
class Readsets:
    """The signals a whole review rests on, and those each candidate's own standing rests on."""

    review: frozenset[str]
    candidates: dict[str, frozenset[str]]


# am[implements a-rel-compiler-1016@c69c38] am[rests-on c-rel-cone-sound-1016@092cec]
@dataclass(frozen=True)
class DependencyIndex:
    """The signals each kind of conclusion about each action can depend on, for one domain."""

    candidacy: dict[str, frozenset[str]]
    appraisal: dict[str, frozenset[str]]
    requirement: frozenset[str]
    norms: frozenset[str]

    # am[implements a-rel-mig-callers-1018@da2f3e]
    def readsets(self, candidates: Iterable[str], *, budget: RunBudget) -> Readsets:
        """What a review with these candidates rests on, charged to `budget`."""

        answer = evaluate("gc-relevance-review-readset", self._cones(), items(list(candidates)), budget=budget)
        try:
            if not isinstance(answer, tuple) or len(answer) != 3 or symbol(answer[0]) != "Readsets":
                raise ValueError(f"expected (Readsets ...), got {answer!r}")
            return Readsets(review=frozenset(map(text, answer[1])), candidates=_table(answer[2]))
        except (ValueError, TypeError) as error:
            raise RelevanceError("engine-output-invalid", f"the readset policy answered {error}") from error

    def _cones(self) -> Any:
        return term(
            "Cones",
            _rows(self.candidacy),
            _rows(self.appraisal),
            items(sorted(self.requirement)),
            items(sorted(self.norms)),
        )


_INDEXES: dict[Domain, DependencyIndex] = {}


# The cones are a property of the domain alone, so they are computed once per domain and process
# and cached. A domain can be any file a packet's caller names, so the computation is ordinary
# review work: it is charged to the request's budget and stopped by its inference bound or its
# deadline, a stopped computation caches nothing, and a warm request is cheaper by exactly the
# work it did not repeat. A call without a RunBudget is refused before the cache is read, so it
# fails alike in a fresh process and a warm one.
# Time: about p patterns reached times r rule heads matched, once per domain.
# am[implements a-rel-compiler-1016@c69c38] am[rests-on c-rel-cone-sound-1016@092cec]
# am[rests-on c-rel-one-deadline-1016@75de2a] am[implements a-rel-mig-callers-1018@da2f3e]
def dependency_index(domain: Domain, *, budget: RunBudget) -> DependencyIndex:
    budget = caller_budget(budget, "a domain's dependency cones")
    cached = _INDEXES.get(domain)
    if cached is not None:
        return cached
    answer = evaluate("gc-relevance-cones", _cone_input(domain), budget=budget)
    try:
        if not isinstance(answer, tuple) or len(answer) != 5 or symbol(answer[0]) != "Cones":
            raise ValueError(f"expected (Cones ...), got {answer!r}")
        _, candidacy, appraisal, requirement, norms = answer
        index = DependencyIndex(
            candidacy=_table(candidacy),
            appraisal=_table(appraisal),
            requirement=frozenset(map(text, requirement)),
            norms=frozenset(map(text, norms)),
        )
    except (ValueError, TypeError) as error:
        raise RelevanceError("engine-output-invalid", f"the readset policy answered {error}") from error
    _INDEXES[domain] = index
    return index


# am[implements a-rel-compiler-1016@c69c38]
def _cone_input(domain: Domain) -> Any:
    return term(
        "ConeInput",
        items(domain.signal_ids),
        items(domain.action_ids),
        items(term("Rule", items(map(_literal, rule.body)), items(map(_literal, rule.heads))) for rule in domain.rules),
        items(_literal(norm) for rule in domain.rules for norm in rule.norms),
    )


# A `?name` argument is a variable; any other argument, a nested term included, is a constant
# compared by its text, as the domain loader renders it.
# am[implements a-rel-compiler-1016@c69c38]
def _literal(pattern: Pattern) -> Any:
    return term(
        "Lit",
        pattern.functor,
        items(term("Var", arg[1:]) if arg.startswith("?") else term("Const", arg) for arg in pattern.args),
    )


# am[implements a-rel-compiler-1016@c69c38]
def _rows(table: dict[str, frozenset[str]]) -> Any:
    return items(term("For", action, items(sorted(signals))) for action, signals in table.items())


# am[implements a-rel-compiler-1016@c69c38]
def _table(rows: Any) -> dict[str, frozenset[str]]:
    table: dict[str, frozenset[str]] = {}
    for row in rows:
        if not isinstance(row, tuple) or len(row) != 3 or symbol(row[0]) != "For":
            raise ValueError(f"expected (For ACTION SIGNALS), got {row!r}")
        table[text(row[1])] = frozenset(map(text, row[2]))
    return table
