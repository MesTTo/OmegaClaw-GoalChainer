"""Purpose: find MeTTa equations that bind one pattern variable twice in one scope. pymetta 0.9.4 compiles
an equation to one Prolog clause, so a case or let pattern reusing a name bound earlier in the clause must
equal it and silently fails to match, while map-atom, filter-atom and foldl-atom lambdas take fresh
variables per element (c-brs-k-case-vars-clause-scoped-1018)."""

from __future__ import annotations

import re
from pathlib import Path


# am[implements a-brs-k-scope-lint-1018@5831fe]
def _tokens(text: str) -> list[str]:
    text = re.sub(r";[^\n]*", "", text)
    return re.findall(r'"(?:\\.|[^"])*"|[()]|[^\s()]+', text)


# am[implements a-brs-k-scope-lint-1018@5831fe]
def _forms(tokens: list[str]) -> list:
    stack: list[list] = [[]]
    for token in tokens:
        if token == "(":
            stack.append([])
        elif token == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(token)
    return stack[0]


# am[implements a-brs-k-scope-lint-1018@5831fe]
def _variables(form) -> set[str]:
    if isinstance(form, str):
        return {form} if form.startswith("$") else set()
    out: set[str] = set()
    for part in form:
        out |= _variables(part)
    return out


# am[implements a-brs-k-scope-lint-1018@5831fe]
def _bind(names: set[str], site: str, scope: dict[str, str], problems: list, where: str) -> None:
    for name in sorted(names):
        if name in scope:
            problems.append((where, name, f"{site} rebinds a variable bound by {scope[name]}"))
        scope[name] = site


# Time: one visit per atom of the file.
# am[implements a-brs-k-scope-lint-1018@5831fe] am[rests-on c-brs-k-case-vars-clause-scoped-1018@de7554]
def _walk(form, scope: dict[str, str], problems: list, where: str) -> None:
    if isinstance(form, str) or not form:
        return
    head = form[0]
    if head in ("map-atom", "filter-atom") and len(form) == 4:
        _walk(form[1], scope, problems, where)
        inner = dict(scope)
        _bind(_variables(form[2]), f"the {head} parameter", inner, problems, where)
        _walk(form[3], inner, problems, where)
    elif head == "foldl-atom" and len(form) == 6:
        _walk(form[1], scope, problems, where)
        _walk(form[2], scope, problems, where)
        inner = dict(scope)
        _bind(_variables(form[3]) | _variables(form[4]), "the foldl-atom parameters", inner, problems, where)
        _walk(form[5], inner, problems, where)
    elif head == "case" and len(form) == 3:
        _walk(form[1], scope, problems, where)
        branches = [b for b in form[2] if isinstance(b, list) and len(b) == 2]
        # case commits to the first branch whose pattern matches, so branches are alternatives: one may
        # reuse another's names, none may reuse the clause's, and what any branch binds stays bound
        # for whatever follows the case in the clause.
        bound: set[str] = set()
        for pattern, _ in branches:
            bound |= _variables(pattern)
        _bind(bound, "a case pattern", scope, problems, where)
        after = dict(scope)
        for _, body in branches:
            branch_scope = dict(scope)
            _walk(body, branch_scope, problems, where)
            after.update(branch_scope)
        scope.update(after)
    elif head == "let" and len(form) == 4:
        _walk(form[2], scope, problems, where)
        _bind(_variables(form[1]), "a let pattern", scope, problems, where)
        _walk(form[3], scope, problems, where)
    elif head == "let*" and len(form) == 3:
        for binding in form[1]:
            if isinstance(binding, list) and len(binding) == 2:
                _walk(binding[1], scope, problems, where)
                _bind(_variables(binding[0]), "a let* pattern", scope, problems, where)
        _walk(form[2], scope, problems, where)
    else:
        for part in form:
            _walk(part, scope, problems, where)


# am[implements a-brs-k-scope-lint-1018@5831fe]
def rebound_variables(path: Path) -> list[tuple[str, str, str]]:
    """(equation head, variable, reason) for every pattern variable bound twice in one clause scope."""

    problems: list[tuple[str, str, str]] = []
    for form in _forms(_tokens(path.read_text())):
        if isinstance(form, list) and len(form) == 3 and form[0] == "=":
            head = form[1]
            where = head[0] if isinstance(head, list) and head else str(head)
            scope = {name: "the equation head" for name in _variables(head)}
            _walk(form[2], scope, problems, where)
    return problems
