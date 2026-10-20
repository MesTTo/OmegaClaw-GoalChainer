"""Purpose: evaluate GoalChainer's one-answer MeTTa policies on the process's pymetta engine. A
ModuleGroup names MeTTa modules loaded once per process, in order, into a named space of their own,
so groups never share a function namespace; `prepare` loads a group under a caller's deadline and
answers its identity, holding the engine alone; `evaluate` runs one typed entry of a group inside
that space's speculative scope under the caller's RunBudget, on a worker of the engine's pool while
other evaluations run on theirs, and answers its one answer atom; `plain_value` reads an answer atom
as plain Python."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import InvalidInputError, MettaEngineError, ProtocolError, safe_repr
from .budget import RunBudget, caller_budget, run_bounded
from .engine import shared_evaluation
from .modules import MettaLibrary, initialize_once, load_metta_module

# A MeTTa symbol: what a group's name, an entry and a warm-up name must each be, since they enter
# program text and a space's name as written.
_SYMBOL = re.compile(r"[^\s()\";]+")
# The groups this process was asked to prepare, by name, so one name stands for one group, and the
# identity of each one prepare finished.
_GROUPS: dict[str, ModuleGroup] = {}
_IDENTITIES: dict[str, str] = {}
# The group each Python module was loaded for. pymetta registers a Python module's operations by
# name for the whole process, so a second group loading it would register them again.
# am[rests-on c-rt-py-ops-process-global-1018@ddf81f]
_PYTHON_MODULES: dict[Path, str] = {}
# Each entry's parameter count once its declared type was read, by group name and entry.
_ARITIES: dict[tuple[str, str], int] = {}


# am[implements a-rt-rb-evaluator-api-1018@9374f4] am[implements a-rt-rb-evaluate-answers-atom-1018@0aeca3]
# am[implements a-rel-nd-section-warm-ups-1018@df1a66] am[implements a-rt-rr-safe-repr-1018@ec9700]
@dataclass(frozen=True, slots=True)
class ModuleGroup:
    """MeTTa modules evaluated together: `modules`, Paths or MettaLibrary values, load in order into
    the named space `space`, and `warm_ups` names entries taking no argument that the group must
    each answer True to once loaded, in order and outside any speculation, so what they compile
    stays compiled. A group composed of several owners' modules names each owner's warm-up once.
    A MeTTa module may belong to any number of groups, each importing its own copy from the same
    pinned bytes; a Python module belongs to one."""

    name: str
    modules: tuple[Path | MettaLibrary, ...]
    warm_ups: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _symbol(self.name):
            raise InvalidInputError("A module group's name must be a MeTTa symbol.", details={"name": safe_repr(self.name)})
        if not isinstance(self.warm_ups, tuple):
            raise InvalidInputError("A module group's warm-ups must be a tuple of entry names.",
                                    details={"group": self.name, "warm_ups": safe_repr(self.warm_ups)})
        for warm_up in self.warm_ups:
            if not _symbol(warm_up):
                raise InvalidInputError("A module group's warm-up must name an entry, a MeTTa symbol.",
                                        details={"group": self.name, "warm_up": safe_repr(warm_up)})
        if len(set(self.warm_ups)) != len(self.warm_ups):
            raise InvalidInputError("A module group names each warm-up once.",
                                    details={"group": self.name, "warm_ups": list(self.warm_ups)})
        if not isinstance(self.modules, tuple) or not self.modules or not all(
                isinstance(module, (Path, MettaLibrary)) for module in self.modules):
            raise InvalidInputError("A module group's modules must be a nonempty tuple of Paths and MettaLibrary values.",
                                    details={"group": self.name, "modules": safe_repr(self.modules)})

    # The engine recognizes a space by an &-prefixed name or as a registered operand (catalog.pl's
    # metta_space_name), and it did not recognize a space engine.space made under a plain name:
    # there an empty conjunctive match answered an Error atom saying match expects a space, and
    # explain described a match form as the match operation, with no plan. So a group's freshly
    # named space carries the prefix, as the SNARS worlds' &goalchainer-snars... names do.
    # am[implements a-dg-amp-group-spaces-1019@9b4cf8] am[rests-on c-dg-unrecognized-space-defects-1019@e59ed6]
    @property
    def space(self) -> str:
        """The named space the group's modules load into, &gc-group-NAME, which a test may run a
        call in directly."""

        return f"&gc-group-{self.name}"


# A prepared group's call reads two records and the clock and takes no hold, so an evaluation of a
# prepared group never waits for running ones (c-rt-kernel-per-call-exclusive-1018); only the first
# call per group takes the engine alone, inside initialize_once.
# Time: on a process's first call per group, one import per module, each a read and SHA-256 of its
# bytes on both sides, and each warm-up's inferences; on every later call, one read of the clock.
# am[implements a-rt-rb-evaluator-api-1018@9374f4] am[implements a-rt-rb-py-module-one-group-1018@64026b]
# am[implements a-rt-rb-one-budget-1018@550ffd] am[rests-on c-rel-one-deadline-1016@75de2a]
# am[implements a-rt-cc-rw-pool-1018]
def prepare(group: ModuleGroup, *, budget: RunBudget) -> str:
    """Load the group into its space once per process and answer its identity, 'sha256:' and the
    SHA-256 over its name and each module's loader digest in order. The loads and the warm-ups run
    inside what is left of `budget`'s deadline and are charged no inferences, being fixed
    per-process work; a budget already used up is stopped here even in a prepared process. A load
    or warm-up that fails leaves the group unprepared, and the next call starts it again, each
    module it already imported answering its recorded digest and every warm-up running again from
    the first.

    Raises InvalidInputError for a budget that is not a RunBudget, for another group under a
    prepared group's name, or for a Python module another group loaded; DependencyUnavailableError
    and ModuleChanged from the loader;
    ReviewTimeout when the deadline stops the preparation; ProtocolError for a warm-up answering
    anything but True once; MettaEngineError when the engine refuses a module or a warm-up."""

    deadline = caller_budget(budget, f"Module group {group.name}").deadline_only()
    registered = _GROUPS.setdefault(group.name, group)
    if registered != group:
        raise InvalidInputError(
            f"Module group {group.name} is already prepared with other modules in this process.",
            details={"group": group.name},
        )
    initialize_once(group.space, lambda engine: _load(engine, group, deadline), budget=deadline)
    return _IDENTITIES[group.name]


# am[implements a-rt-rb-evaluator-api-1018@9374f4] am[implements a-rt-rb-py-module-one-group-1018@64026b]
# am[implements a-rel-nd-section-warm-ups-1018@df1a66]
def _load(engine: Any, group: ModuleGroup, deadline: RunBudget) -> None:
    from metta import MettaError  # noqa: PLC0415 (pymetta is imported only once an engine exists)

    space = engine.space(group.space)
    identity = hashlib.sha256(group.name.encode("utf-8") + b"\0")
    for module in group.modules:
        if isinstance(module, Path) and module.suffix == ".py":
            owner = _PYTHON_MODULES.setdefault(module.resolve(), group.name)
            if owner != group.name:
                raise InvalidInputError(
                    f"{module} registers Python operations for the whole process and already belongs "
                    f"to module group {owner}.",
                    details={"group": group.name, "module": str(module), "owner": owner},
                )
        try:
            loaded = load_metta_module(engine, module, budget=deadline, space=space)
        except MettaError as error:
            raise MettaEngineError(
                f"The engine refused module {module} of module group {group.name}: {error}",
                details={"group": group.name, "module": str(module), "error": str(error)},
            ) from error
        label = module.name if isinstance(module, Path) else module.spec
        identity.update(label.encode("utf-8") + b"\0" + loaded.encode("ascii") + b"\0")
    for warm_up in group.warm_ups:
        try:
            answers, _ = run_bounded(space, f"!({warm_up})", budget=deadline)
        except MettaError as error:
            raise MettaEngineError(
                f"Module group {group.name}'s warm-up {warm_up} failed: {error}",
                details={"group": group.name, "warm_up": warm_up, "error": str(error)},
            ) from error
        if [[plain_value(answer) for answer in answered] for answered in answers] != [[True]]:
            raise ProtocolError(
                f"Module group {group.name}'s warm-up {warm_up} must answer True once.",
                details={"group": group.name, "warm_up": warm_up,
                         "answers": [[str(answer) for answer in answered] for answered in answers]},
            )
    _IDENTITIES[group.name] = "sha256:" + identity.hexdigest()


# The group's first call prepares it holding the engine alone; the call itself only reads what
# preparation loaded and writes nothing that outlives its speculation, so it shares the engine with
# other evaluations, each on its own pool worker (a-rt-cc-rw-pool-1018).
# Time: one prepare, then one engine run bounded by what is left of the budget; the entry's type is
# read once per group and entry.
# am[implements a-rt-rb-evaluator-api-1018@9374f4] am[implements a-rt-rb-evaluate-answers-atom-1018@0aeca3]
# am[implements a-rt-rb-one-budget-1018@550ffd] am[rests-on c-jk-atom-entry-inert-1018@63e37f]
# am[rests-on c-rt-speculative-scope-process-wide-1017@008e5b] am[implements a-rt-cc-rw-pool-1018]
# am[implements a-rt-rr-safe-repr-1018@ec9700]
def evaluate(group: ModuleGroup, function: str, *arguments: Any, budget: RunBudget) -> Any:
    """The one answer atom of `(FUNCTION ARGUMENT ...)` in the group's space.

    Each argument enters as a hole, so a str is one String atom and an atom enters as itself. The
    call runs inside the space's speculative scope, so nothing it writes outlives it, through
    run_bounded under what is left of `budget`, which is charged its inferences: composed calls
    sharing one budget share one deadline and one allowance. The call runs on a worker of the
    engine's pool, so calls from different threads run at once; a caller already holding the
    engine runs it on its own thread. The entry must declare its type, `(: FUNCTION (-> ...))`,
    with no undefined parameter and one parameter per argument, because an untyped entry evaluates
    hole data whose head names a function. A caller wanting Python values applies plain_value to
    the answer.

    Raises InvalidInputError for an entry that is not a symbol, is untyped or takes another number
    of arguments; ProtocolError unless the call answers exactly once; InferenceBudgetExceeded or
    ReviewTimeout when the budget stops it; MettaEngineError when the engine refuses the call; and
    whatever prepare raises."""

    from metta import MettaError, Symbol  # noqa: PLC0415 (pymetta is imported only once an engine exists)

    if not _symbol(function):
        raise InvalidInputError("A module group's entry must be a MeTTa symbol.", details={"function": safe_repr(function)})
    prepare(group, budget=budget)
    holes = {f"argument{index}": argument for index, argument in enumerate(arguments)}
    source = "!(" + " ".join([function, *("{" + name + "}" for name in holes)]) + ")"

    def call(engine: Any) -> list[list[Any]]:
        space = engine.space(group.space)
        arity = _ARITIES.get((group.name, function))
        if arity is None:
            arity = _ARITIES[(group.name, function)] = _declared_arity(space.type(Symbol(function)), group, function)
        if arity != len(arguments):
            raise InvalidInputError(
                f"{function} in module group {group.name} takes {arity} arguments, not {len(arguments)}.",
                details={"group": group.name, "function": function, "arity": arity, "arguments": len(arguments)},
            )
        try:
            with space.speculative():
                answers, _ = run_bounded(space, source, budget=budget, **holes)
        except MettaError as error:
            raise MettaEngineError(
                f"The engine refused {function} in module group {group.name}: {error}",
                details={"group": group.name, "function": function, "error": str(error)},
            ) from error
        return answers

    answers = shared_evaluation(call, budget=budget)
    if len(answers) != 1 or len(answers[0]) != 1:
        raise ProtocolError(
            f"{function} in module group {group.name} answered "
            f"{sum(len(answered) for answered in answers)} results where one was required.",
            details={"group": group.name, "function": function,
                     "answers": [[str(answer) for answer in answered] for answered in answers]},
        )
    return answers[0][0]


# The parameter count of an entry's declared arrow type, refusing an entry with no declared type or
# an undefined parameter, either of which would let the engine evaluate hole data on the way in.
# am[implements a-rt-rb-evaluator-api-1018@9374f4] am[rests-on c-jk-atom-entry-inert-1018@63e37f]
def _declared_arity(declared: Any, group: ModuleGroup, function: str) -> int:
    from metta import Expression  # noqa: PLC0415 (pymetta is imported only once an engine exists)

    shape = declared.children if isinstance(declared, Expression) else ()
    if not shape or str(shape[0]) != "->" or any(str(parameter) == "%Undefined%" for parameter in shape[1:-1]):
        raise InvalidInputError(
            f"{function} in module group {group.name} must declare an arrow type with every "
            f"parameter typed, (: {function} (-> ...)), before evaluate calls it; its type is {declared}.",
            details={"group": group.name, "function": function, "type": str(declared)},
        )
    return len(shape) - 2


# am[implements a-rt-rb-evaluator-api-1018@9374f4]
def _symbol(value: object) -> bool:
    return isinstance(value, str) and _SYMBOL.fullmatch(value) is not None


# A leaf atom raises TypeError for `.children`, so the type is checked before the children are.
# Symbols stay atoms because a domain may name an action None: read as text, the policy's own
# None symbol and the String "None" would be one value.
# Time: linear in the number of atoms in the answer.
# am[implements a-rt-pymetta-engine-1016@296784]
def plain_value(atom: Any) -> Any:
    """An answer atom as plain Python: an expression as the tuple of its children's values, a
    grounded atom as its Python value, and a symbol or variable as itself, the pymetta atom, so
    `(f "s" 1 2.5 True $x (g))` reads (S.f, "s", 1, 2.5, True, V.x, (S.g,)) and a String can
    never pass for a symbol: a reader compares a symbol position against S.name."""

    from metta import Expression, Grounded  # noqa: PLC0415 (a dependency only in-process callers load)

    if isinstance(atom, Expression):
        return tuple(plain_value(child) for child in atom.children)
    if isinstance(atom, Grounded):
        return atom.value
    return atom
