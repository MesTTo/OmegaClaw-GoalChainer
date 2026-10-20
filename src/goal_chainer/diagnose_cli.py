"""Purpose: give goal_chainer.runtime.diagnostics a command-line surface, `goalchainer diagnose
profile|explain|match`, each run in a packaged module group named as module:attribute or in an ad
hoc group of module files, under the RunBudget the command's required limits build."""

from __future__ import annotations

import argparse
import hashlib
import pkgutil
from pathlib import Path
from typing import Any

from .errors import InvalidInputError, safe_repr
from .runtime import diagnostics
from .runtime.budget import RunBudget, caller_budget
from .runtime.evaluator import ModuleGroup


# Every diagnostic takes the group and both limits, after its own name, so each subcommand's
# options read in one place: `goalchainer diagnose profile --group ... --inference-budget N ...`.
# am[implements a-dg-cli-1019@996a1b]
def add_diagnose_arguments(parser: argparse.ArgumentParser) -> None:
    common = argparse.ArgumentParser(add_help=False)
    source = common.add_mutually_exclusive_group(required=True)
    source.add_argument("--group", metavar="MODULE:ATTRIBUTE",
                        help="a packaged ModuleGroup, such as goal_chainer.bigraph.kernel:GROUP")
    source.add_argument("--module", dest="modules", action="append", metavar="FILE",
                        help="a MeTTa or Python module of an ad hoc group; repeat it, in load order")
    common.add_argument("--inference-budget", type=int, required=True,
                        help="maximum engine inferences for this diagnostic")
    common.add_argument("--timeout-seconds", type=float, required=True,
                        help="wall-clock limit for this diagnostic, the group's preparation included")
    kinds = parser.add_subparsers(dest="diagnostic", required=True)
    profile = kinds.add_parser("profile", parents=[common],
                               help="run one expression once under the engine's statistical profiler")
    profile.add_argument("--top", type=int, default=20, help="predicate rows to report, most sampled first")
    profile.add_argument("expression", help="one MeTTa expression, such as '(bg-warm-up)'")
    explain = kinds.add_parser("explain", parents=[common],
                               help="the engine's plan for a match form, or an operation's declarations, "
                                    "without running it")
    explain.add_argument("expression", help="(match &self PATTERN TEMPLATE) or an operation call")
    match = kinds.add_parser("match", parents=[common],
                             help="which stage of a conjunctive match leaves it without answers")
    match.add_argument("--where", help="a guard over the patterns' variables, kept rows answering True")
    match.add_argument("patterns", nargs="+", help="one MeTTa pattern per argument, matched together")


# A packaged group is named the way an entry point names an object, module:attribute, and resolved
# by pkgutil.resolve_name; module files make a group named for the digest of their resolved paths,
# so one list of files is one group in a process and another list another. A path the engine could
# not take as text, one holding a surrogate escaping bytes that are no UTF-8, is refused here with
# the rest.
# am[implements a-dg-cli-1019@996a1b]
def _group(args: argparse.Namespace) -> ModuleGroup:
    if args.group is not None:
        try:
            group = pkgutil.resolve_name(args.group)
        except (ImportError, AttributeError, ValueError) as error:
            raise InvalidInputError(f"--group {args.group} names no importable object: {error}",
                                    details={"group": args.group}) from error
        if not isinstance(group, ModuleGroup):
            raise InvalidInputError(f"--group {args.group} names a {type(group).__name__}, not a ModuleGroup.",
                                    details={"group": args.group})
        return group
    try:
        modules = tuple(Path(module).expanduser().resolve() for module in args.modules)
        key = "\0".join(map(str, modules)).encode("utf-8")
    except (ValueError, RuntimeError, OSError) as error:
        raise InvalidInputError(f"--module names no usable path: {error}",
                                details={"modules": safe_repr(args.modules)}) from error
    return ModuleGroup(f"diagnose-{hashlib.sha256(key).hexdigest()[:16]}", modules)


# The budget is checked before the group is resolved, since resolving a packaged group imports its
# module and a used-up budget does no work at all.
# am[implements a-dg-cli-1019@996a1b]
def run_diagnose(args: argparse.Namespace, *, budget: RunBudget) -> dict[str, Any]:
    """The report of the diagnostic `args` names, under `budget`."""

    caller_budget(budget, "goalchainer diagnose").remaining()
    group = _group(args)
    if args.diagnostic == "profile":
        return diagnostics.profile(group, args.expression, top=args.top, budget=budget)
    if args.diagnostic == "explain":
        return diagnostics.explain(group, args.expression, budget=budget)
    return diagnostics.match(group, args.patterns, where=args.where, budget=budget)
