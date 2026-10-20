"""Purpose: run GoalChainer's SNARS batches in-process on the process's pymetta engine, each in the
world compiled once per process for the optional features it includes, inside that world's
speculation under the caller's RunBudget, answering the lines the batch printed and answered, the
inferences it spent and the world it ran in.

A world is a named space holding the packaged SNARS library and the modules
snars_program.WORLD_MODULES lists for its features, in that order. Worlds are kept apart because
the protocol's own functions reduce the policy's wherever the policy is loaded: a batch without the
policy runs in a world that never loaded it. A named space compiles into a function namespace of its own and sees nothing the
process's self space defines, so the deontic, evidence and relevance modules other callers load
there stay out of every world. A world compiles the first time a batch needs it, within that
batch's deadline, and one a deadline stopped compiles again on the next call; prepare_snars_world
compiles one ahead of any request. A world is published whole once its compilation succeeds, so
compiled_worlds, which a command's report reads, answers at once whatever holds the engine.

A batch's facts and directive run as one call inside the world's speculate scope, which runs the
call on an SWI snapshot and discards every write it made, to the world's atoms and to the SNARS
kernel's Prolog stores alike. Every batch therefore starts from its world as compiled, whatever ran
before it, and a batch its budget stopped or that raised leaves nothing behind. Speculation also
discards what the batch compiled, so each batch pays the first-call compilation of what it
evaluates. Its answers come back as their printed text split into lines, which the protocol reader
decodes.

A world names what it runs: the SNARS library bytes it imported and the bytes snars_python
compiled the Python helpers from. A process runs one SNARS: its first world import or
snars_identity() call pins the library digest, and every later world must import the same bytes.
Compiling a world and snars_identity() raise ModuleChanged once a library or helper file on disk
differs from what the process holds, since only a fresh process loads the new bytes; a world
already compiled keeps running what it holds, which its identity names.

A process that calls start_worlds_from_images starts each world, when it can, from the pymetta
fast image an earlier compile of the same identity saved in the user cache, and saves the worlds
it compiles there: the image loads in well under a second where a compile takes 20 to 30 s. An
image holds no compiled clauses, so before the world is published every function it defines is
planned, which compiles the function without running it, and its batches then cost what a compiled
world's do.

Measured on pymetta 0.9.4: compiling SNARS into a world takes about 18 s and 138 million
inferences, and the policy world's other modules 35 to 50 s more; a warm batch takes a median
0.75 s and 4.1 million inferences, an action assessment about 6.5 s, and a control or
compiled-prove batch about 24 s, most of it compiling rules inside the speculation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, replace
from functools import partial
from pathlib import Path
from types import MappingProxyType
from typing import Any

from . import snars_python
from .sexpr import syntax
from .sexpr.forms import top_level_forms
from .errors import ModuleChanged
from .runtime.budget import ReviewTimeout, RunBudget, run_bounded
from .runtime.modules import (
    file_digest,
    initialize_once,
    load_metta_module,
    register_metta_library,
    tree_digest,
)
from .runtime.engine import pymetta_identity, shared_evaluation
from .semantic_models import cache_home
from .sexpr.protocol import nonempty_output_lines
from .errors import DependencyUnavailableError, InvalidInputError, MettaEngineError
from .snars_program import (
    FEATURES,
    SNARS_DIRECTORY,
    SNARS_LIBRARY,
    SnarsBatch,
    feature_set,
    world_modules,
)

# The files of the Python SNARS's py-calls run, goalchainer_snars.py first, each compiled by
# snars_python from the one read its digest names.
# am[implements a-rt-snars-identity-resident-1017@3c837e]
SNARS_HELPERS = tuple(path for path, _ in snars_python.loaded())

__all__ = [
    "SNARS_HELPERS",
    "SnarsBatchRun",
    "SnarsWorld",
    "compiled_worlds",
    "prepare_snars_world",
    "run_snars_batch",
    "snars_identity",
    "start_worlds_from_images",
    "world_image_cache",
]

logger = logging.getLogger(__name__)

# The layout of an image's sidecar; a sidecar of any other layout is not read.
IMAGE_FORMAT = 1


# am[implements a-rt-snars-worlds-by-includes-1017@54c05f]
@dataclass(frozen=True, slots=True)
class SnarsWorld:
    """What one world was compiled from, so a run's identity changes whenever its world does.

    `includes` are its optional features in FEATURES order and `space` the named space holding it.
    `runtime`, `runtime_digest` and `swipl_version` identify the engine, as PymettaIdentity does.
    `library_digest` is the loader's digest of the SNARS library tree it imported and
    `helpers_digest` SHA-256 over the bytes the process compiled the Python its py-calls run from;
    `snars_identity` combines the two as snars_identity() does. `modules` pairs each world
    module's file name with the digest of the bytes imported from it, in load order. `origin` says
    how this process got the world: "compiled", or "image" from the fast image a compile of the
    same identity saved; it is not part of the identity.
    """

    includes: tuple[str, ...]
    space: str
    runtime: str
    runtime_digest: str
    swipl_version: str
    library_digest: str
    helpers_digest: str
    modules: tuple[tuple[str, str], ...]
    origin: str = "compiled"

    @property
    def snars_identity(self) -> str:
        return _combined(self.library_digest, self.helpers_digest)


# Each world this process compiled or started from an image, by its included features, published
# once its setup succeeds. A publication replaces the whole mapping and no published mapping ever
# changes, so a reader that loads _WORLDS once holds every world published before that load and no
# world half-made, without holding the engine.
# am[implements a-integrate-snars-report-deadline-1018@5ba321] am[rests-on c-rt-global-rebind-atomic-1018@d0b92c]
_WORLDS: Mapping[frozenset[str], SnarsWorld] = MappingProxyType({})

# The digest of the SNARS library this process runs, under "library", set by the first world's
# import or snars_identity()'s first read, whichever comes first.
_PINNED: dict[str, str] = {}

# Whether this process starts worlds from images: "cache" is present once start_worlds_from_images
# has been called, holding the directory it named or None for the default, which _image_cache finds
# when the first world needs it.
_IMAGES: dict[str, Path | None] = {}


# am[implements a-rt-snars-batch-speculative-1017@451056]
@dataclass(frozen=True, slots=True)
class SnarsBatchRun:
    """One in-process batch: the nonempty lines of what it printed and answered; the inferences it
    alone spent, charged to the caller's RunBudget; and the world it ran in."""

    output_lines: tuple[str, ...]
    inferences: int
    world: SnarsWorld


# The batch is one call, facts and directive together, because each call inside a speculate block
# is its own what-if: a second call would not see the facts the first added.
# Time: one engine run inside a snapshot, bounded by what is left of the budget, plus printing the
# answers; the first batch of a world also pays the world's compilation.
# am[implements a-rt-snars-batch-speculative-1017@451056] am[implements a-rt-snars-inprocess-executor-1016@2569f0]
# am[rests-on c-rt-speculative-scope-process-wide-1017@008e5b] am[rests-on c-rt-space-face-runs-bounded-1017@00d15c]
# am[rests-on c-rt-snars-stack-prints-nothing-1017@7f820a]
# am[implements a-rt-rbr-read-before-engine-1018@b0a647] am[rests-on c-rt-boot-inside-deadline-1018@e9a118]
# am[implements a-dr-sr-snars-batch-declaration-1018@5c965d]
# am[implements a-integrate-pymetta-public-errors-1019@05202a]
def run_snars_batch(batch: SnarsBatch, *, budget: RunBudget) -> SnarsBatchRun:
    """Run one batch in its world under what is left of `budget`, charging its inferences there.

    Raises InferenceBudgetExceeded or ReviewTimeout, naming the whole bound, when a bound stops
    the world's compilation or the batch, or was used up before them; MettaEngineError
    when the engine fails on the batch; and DependencyUnavailableError when pymetta, the
    packaged SNARS library or a world module is missing. A batch's writes never outlast it.
    """

    from metta.errors import MettaError  # noqa: PLC0415 (pymetta is imported only once an engine exists)

    if not isinstance(batch, SnarsBatch):
        raise InvalidInputError("run_snars_batch takes a SnarsBatch.")
    # Read before taking the engine, whose first boot nothing can interrupt, so a request whose
    # bounds are used up never boots it; every wait for the engine ends at the budget's deadline.
    budget.remaining()
    world = _prepared_world(batch.includes, budget=budget)
    # The batch's declaration rows go in with its facts, so the speculation discards both.
    source = "\n".join((*batch.rows, *batch.facts, f"!{batch.directive}"))

    # The world's first batch compiles it holding the engine alone, and a later one takes no hold
    # (c-rt-kernel-per-call-exclusive-1018); the batch writes only inside its own speculation and
    # captures only its own printing, both task-local, so it shares the engine with other batches
    # and evaluations on its own pool worker (a-rt-cc-rw-pool-1018).
    def run(engine: Any) -> tuple[str, list[list[Any]], int]:
        space = engine.space(world.space)
        try:
            with space.speculative(), space.capture() as printed:
                answers, used = run_bounded(space, source, budget=budget)
        except MettaError as error:
            raise MettaEngineError(
                f"SNARS failed on the batch: {error}",
                details={"engine": world.runtime, "world": world.space, "error": type(error).__name__},
            ) from error
        return printed.text, answers, used

    printed, answers, used = shared_evaluation(run, budget=budget)
    text = printed + "".join(f"{atom}\n" for group in answers for atom in group)
    return SnarsBatchRun(output_lines=nonempty_output_lines(text), inferences=used, world=world)


# am[implements a-rt-snars-worlds-by-includes-1017@54c05f] am[implements a-rt-bounded-preparation-1016@e7eb12]
def prepare_snars_world(includes: Iterable[str] = (), *, budget: RunBudget | None = None) -> SnarsWorld:
    """Compile the world for these optional features, once per process, and answer its identity.

    Inside a request, pass the request's budget: the compilation then runs inside its deadline,
    and a deadline that stops it raises ReviewTimeout and leaves the rest to the next call. Without
    one it is the host's startup compilation, outside any request. run_snars_batch compiles the
    world it needs itself, and a call after the first compilation does nothing.
    """

    included = feature_set(includes)
    return _prepared_world(included, budget=budget)


# A command reports the worlds it ran in after its batches answered, so the report reads the
# published mapping and takes no hold: a load or another world's compilation holding the engine
# alone never delays it, and it never boots the engine.
# am[implements a-rt-snars-worlds-by-includes-1017@54c05f] am[implements a-integrate-snars-report-deadline-1018@5ba321]
# am[rests-on c-rt-global-rebind-atomic-1018@d0b92c]
def compiled_worlds() -> tuple[SnarsWorld, ...]:
    """Every world this process has published, compiled or started from an image, in the order it
    got them. It waits for nothing, so a world still compiling is not among them."""

    return tuple(_WORLDS.values())


# The user cache's directory of SNARS world images, beside the model cache.
# am[implements a-rt-image-cache-1017@66d7ae]
def world_image_cache() -> Path:
    """cache_home()/snars-worlds, where start_worlds_from_images keeps images by default."""

    return cache_home() / "snars-worlds"


# A process that runs few batches calls this: an image-started world loads and rehydrates in 0.1 to
# 0.4 s and plans in 0.3 to 0.4 s, against 20 to 30 s for a compile, and then answers every batch
# as its compiled twin does and is charged within 0.07% of it (c-rt-iw-plan-all-worlds-1019).
# am[implements a-rt-image-entry-point-optin-1017@f47b3e] am[implements a-rt-image-cache-1017@66d7ae]
# am[rests-on c-rt-image-corpus-equal-dearer-1017@52448d] am[rests-on c-rel-optin-resolves-cache-eagerly-1017@c12616]
# am[rests-on c-rt-iw-plan-all-worlds-1019@7c56f6] am[rests-on c-rt-iw-plan-once-cheaper-1019@22b504]
def start_worlds_from_images(cache: Path | None = None) -> None:
    """From now on, each world this process prepares starts from the fast image in `cache`, by
    default world_image_cache(), that a compile of the same identity saved, and a world compiled
    for want of one is saved there for later processes. It only records the choice: the default
    cache is found when the first world is prepared, inside whatever command prepares it."""

    _IMAGES["cache"] = cache


# The cache this process opted into, the default found at the first world that needs it, so the
# opt-in at a process's entry does no fallible work before the command's own error handling. A home
# directory that cannot be found, as for a uid with no passwd entry and no HOME, leaves this and
# every later world compiled and says why once, as a cache that cannot be written does; cache_home
# names that case as its DependencyUnavailableError.
# am[implements a-rt-image-console-main-1017@87159d] am[rests-on c-rel-optin-resolves-cache-eagerly-1017@c12616]
# am[related a-dr-cache-home-typed-1018@63015f]
def _image_cache() -> Path | None:
    if "cache" not in _IMAGES:
        return None
    cache = _IMAGES["cache"]
    if cache is None:
        try:
            cache = _IMAGES["cache"] = world_image_cache()
        except DependencyUnavailableError as error:
            logger.warning("SNARS worlds start without images: the image cache has no home: %s", error)
            _IMAGES.clear()
            return None
    return cache


# Time: a tree digest of the SNARS library, about 620 KB in 72 files of which its sCASP copy is
# 420 KB, about 2 ms, and a read of the four helper files, about 40 KB.
# am[implements a-rt-snars-store-identity-1017@deb59d] am[implements a-rt-snars-identity-resident-1017@3c837e]
def snars_identity() -> str:
    """SHA-256 naming the SNARS this process runs: the library digest its worlds import, pinned
    by the first world or the first call, combined with the digest of the bytes it compiled the
    Python helpers from, as each world's snars_identity combines them. Raises ModuleChanged once
    the library or a helper on disk differs from what the process holds."""

    return _combined(_pinned_library(tree_digest(_snars_directory())), _helpers_digest())


# A world is compiled holding the engine alone the first time it is asked for; afterwards this
# reads two records and takes no hold.
# am[implements a-rt-snars-worlds-by-includes-1017@54c05f] am[implements a-rt-cc-rw-pool-1018]
def _prepared_world(includes: frozenset[str], *, budget: RunBudget | None) -> SnarsWorld:
    initialize_once(f"snars-world:{_space_name(includes)}", partial(_compile_world, includes=includes, budget=budget),
                    budget=budget)
    return _WORLDS[includes]


# The one way a world enters _WORLDS: a new mapping holding every published world and this one.
# Only _compile_world calls it, inside initialize_once's setup, which holds the engine alone, so no
# two publications interleave and none is lost.
# Time: one copy of the mapping, which holds at most one world per feature set the process runs.
# am[implements a-integrate-snars-report-deadline-1018@5ba321]
# am[rests-on c-rt-worlds-written-only-holding-engine-1018@64dd5b]
def _publish(includes: frozenset[str], world: SnarsWorld) -> None:
    global _WORLDS
    _WORLDS = MappingProxyType({**_WORLDS, includes: world})


# The world's identity is taken from what is imported, at import: each digest is the loader's, read
# on each side of that module's import into this world's space, and the helpers' is the digest of
# the bytes the process compiled them from, checked before any import so a world never compiles
# beside helpers that changed on disk.
# Time: one import of the SNARS library, about 18 s on pymetta 0.9.4, and one of each world module,
# about 35 to 50 s for the policy world's, plus the digests on each side of every import.
# am[implements a-rt-snars-worlds-by-includes-1017@54c05f] am[implements a-rt-load-module-per-space-1017@309625]
# am[rests-on c-rt-named-spaces-separate-worlds-1017@92b148] am[rests-on c-rt-world-blind-to-home-1017@c1b6ea]
# am[rests-on c-rt-world-load-order-neutral-1017@d30cd1]
# am[rests-on c-rt-preloaded-definitions-reach-other-batches-v2-1017@f05590]
# am[implements a-rt-bounded-preparation-1016@e7eb12] am[rests-on c-rt-stopped-import-retry-safe-1016@cba696]
# am[implements a-rt-snars-identity-resident-1017@3c837e]
# am[implements a-rt-image-identity-1017@94d06b]
# am[implements a-integrate-snars-report-deadline-1018@5ba321]
# am[implements a-integrate-pymetta-public-errors-1019@05202a]
def _compile_world(engine: Any, *, includes: frozenset[str], budget: RunBudget | None) -> None:
    from metta.errors import MettaError  # noqa: PLC0415 (pymetta is imported only once an engine exists)

    helpers_digest = _helpers_digest()
    engine_identity = pymetta_identity(engine)
    space = engine.space(_space_name(includes))
    register_metta_library(SNARS_LIBRARY.name, _snars_directory(), budget=budget)
    cache = _image_cache()
    if cache is not None:
        # A world module that cannot be read gets no image; the compile below names it as a
        # missing dependency.
        try:
            expected = SnarsWorld(
                includes=tuple(feature for feature in FEATURES if feature in includes),
                space=str(space.name),
                runtime=engine_identity.runtime,
                runtime_digest=engine_identity.runtime_digest,
                swipl_version=engine_identity.swipl_version,
                library_digest=_pinned_library(tree_digest(_snars_directory())),
                helpers_digest=helpers_digest,
                modules=tuple((path.name, file_digest(path.resolve())) for path in world_modules(includes)),
            )
        except OSError:
            expected = None
        if expected is not None and _start_from_image(space, expected, cache, budget):
            _publish(includes, replace(expected, origin="image"))
            return
    started = time.monotonic()
    try:
        with space.stats() as spent:
            library_digest = _pinned_library(load_metta_module(engine, SNARS_LIBRARY, budget=budget, space=space))
            modules = tuple(
                (path.name, load_metta_module(engine, path, budget=budget, space=space))
                for path in world_modules(includes)
            )
    except MettaError as error:
        raise MettaEngineError(
            f"The SNARS world {space.name} failed to compile: {error}",
            details={"engine": engine_identity.runtime, "world": str(space.name), "error": type(error).__name__},
        ) from error
    world = SnarsWorld(
        includes=tuple(feature for feature in FEATURES if feature in includes),
        space=str(space.name),
        runtime=engine_identity.runtime,
        runtime_digest=engine_identity.runtime_digest,
        swipl_version=engine_identity.swipl_version,
        library_digest=library_digest,
        helpers_digest=helpers_digest,
        modules=modules,
    )
    _publish(includes, world)
    if cache is not None:
        _save_image(space, world, cache, inferences=spent.inferences, seconds=time.monotonic() - started)


# A world's identity as its image's sidecar records it: every field but the space, which its
# features name, and its origin.
# am[implements a-rt-image-identity-1017@94d06b]
def _identity(world: SnarsWorld) -> dict[str, Any]:
    fields = asdict(world)
    del fields["space"], fields["origin"]
    return json.loads(json.dumps(fields))


# The sidecar's name: SHA-256 over the identity, so a process looks only at the image of the
# world it would compile.
# am[implements a-rt-image-cache-1017@66d7ae]
def _image_key(world: SnarsWorld) -> str:
    return hashlib.sha256(json.dumps(_identity(world), sort_keys=True).encode()).hexdigest()


# The image is loaded only when its sidecar records this exact identity and the image file holds
# the bytes the sidecar names; anything else, a missing or unreadable file included, is no image.
# An image file is written once under a name of its own and never rewritten, so the bytes checked
# are the bytes loaded. A world started from its image is planned before this answers, so the
# caller publishes it only once every function it defines has compiled. A load is all or nothing,
# the rehydration's directives leave the world and the process's stores as they found them when
# they run again (c-rt-iw-rehydrate-twice-1019), and a plan changes nothing a batch reads, so
# whatever stops this, a retry starts the world again from the image.
# Time: a read of the sidecar and the image, about 140 KB, a load of 0.02 to 0.05 s, the
# rehydration's seven directives, 0.06 to 0.35 s, and the world's plan.
# am[implements a-rt-image-identity-1017@94d06b] am[implements a-rt-image-relocation-rehydration-1017@bb9fc4]
# am[rests-on c-rt-image-relocates-1017@9a01d4] am[implements a-rt-iw-effect-plan-1019@fc18bf]
# am[rests-on c-rt-iw-rehydrate-twice-1019@943a22]
# am[implements a-integrate-pymetta-public-errors-1019@05202a]
def _start_from_image(space: Any, world: SnarsWorld, cache: Path, budget: RunBudget | None) -> bool:
    from metta.errors import MettaError, TimeLimitError  # noqa: PLC0415 (pymetta is imported only once an engine exists)

    try:
        recorded = json.loads((cache / f"{_image_key(world)}.json").read_text(encoding="utf-8"))
        image = cache / Path(recorded["image"]).name
        held = image.read_bytes()
    except (OSError, ValueError, KeyError, TypeError):
        return False
    if (
        recorded.get("format") != IMAGE_FORMAT
        or recorded.get("world") != _identity(world)
        or hashlib.sha256(held).hexdigest() != recorded.get("image_sha256")
    ):
        return False
    try:
        space.load(image, timeout=None if budget is None else budget.remaining()[1])
        space.run(_rehydration(frozenset(world.includes)), timeout=None if budget is None else budget.remaining()[1])
        _plan(space, budget)
    except TimeLimitError as error:
        raise ReviewTimeout(budget.timeout_seconds) from error
    except MettaError as error:
        raise MettaEngineError(
            f"The SNARS world image {image} failed to start: {error}",
            details={"engine": world.runtime, "world": world.space, "image": str(image), "error": type(error).__name__},
        ) from error
    return True


# An image holds a world's atoms but none of its compiled clauses
# (c-rt-iw-no-compile-primitive-native2-1019), so each function would compile at its first call
# inside a batch's speculation, which discards what it compiled, and so again in every batch. One
# plan of a call to every function the world defines compiles them all once, outside every batch,
# and runs none of them: Space.effect_plan translates its target and follows the compiled calls it
# reaches without executing it (c-rt-iw-effect-plan-compiles-1019), so the world's atoms and the
# process's stores stay as the rehydration left them, and each batch then prints what a compiled
# world's batch prints and is charged within 0.07% of it (c-rt-iw-plan-all-worlds-1019). The calls
# share one plan because a plan walks every compiled call it reaches, so a plan per function would
# walk the shared ones again for each (c-rt-iw-plan-once-cheaper-1019). A plan takes no timeout and
# pymetta's scoped limits do not reach it (c-rt-iw-limits-miss-plan-1019), so the deadline is read
# before it and the plan runs to its end.
# Time: one translation of every function the image left uncompiled and one walk of the compiled
# calls they reach: 0.28 to 0.39 s and 2.1 to 2.3 million inferences for each of the six worlds the
# sessions use, on pymetta 0.9.4+goalchainer.native.2.
# am[implements a-rt-iw-effect-plan-1019@fc18bf] am[rests-on c-rt-iw-effect-plan-compiles-1019@3e89ed]
# am[rests-on c-rt-iw-no-compile-primitive-native2-1019@769e0d]
# am[addresses i-rt-image-start-multiplies-request-spend-1018@56abe3]
# am[rests-on c-rt-iw-plan-all-worlds-1019@7c56f6] am[rests-on c-rt-iw-plan-once-cheaper-1019@22b504]
# am[rests-on c-rt-iw-limits-miss-plan-1019@6dbff2] am[implements a-rt-image-warm-up-1018@da80c2]
def _plan(space: Any, budget: RunBudget | None) -> None:
    calls = [
        f"($f{index} ({' '.join([name, *(f'$f{index}x{argument}' for argument in range(arity))])}))"
        for index, (name, arity) in enumerate(_functions(space))
    ]
    if budget is not None:
        budget.remaining()
    if calls:
        space.effect_plan(f"(let* ({' '.join(calls)}) ())")


# Each function the world's equations define, by name and arity, once for each arity it is defined
# at: a call to it with a fresh variable for each argument compiles every equation it has at that
# arity, whatever its arguments are. Sorted, so every process plans a world in one order.
# Time: one pass over the world's atoms, about 750.
# am[implements a-rt-iw-effect-plan-1019@fc18bf] am[rests-on c-rt-iw-plan-all-worlds-1019@7c56f6]
def _functions(space: Any) -> list[tuple[str, int]]:
    from metta import Expression, Symbol  # noqa: PLC0415 (pymetta is imported once an engine exists)

    heads: set[tuple[str, int]] = set()
    for atom in space.atoms():
        equation = atom.children if isinstance(atom, Expression) else ()
        if len(equation) == 3 and isinstance(equation[0], Symbol) and equation[0].name == "=":
            head = equation[1].children if isinstance(equation[1], Expression) else ()
            if head and isinstance(head[0], Symbol):
                heads.add((head[0].name, len(head) - 1))
    return sorted(heads)


# Each writer saves its image under a name of its own, since two saves of one world differ in
# their bytes, and then replaces the sidecar in one step, so a reader finds either no sidecar or
# one naming a whole image. A save that fails leaves the world compiled and costs only the next
# process's compile, so it is logged rather than raised.
# Time: a fast save of about 0.15 s and a read of the image to digest it, about 140 KB.
# am[implements a-rt-image-cache-1017@66d7ae] am[rests-on c-rt-image-bytes-vary-1017@e21896]
# am[implements a-integrate-pymetta-public-errors-1019@05202a]
def _save_image(space: Any, world: SnarsWorld, cache: Path, *, inferences: int, seconds: float) -> None:
    from metta.errors import MettaError  # noqa: PLC0415 (pymetta is imported only once an engine exists)

    key = _image_key(world)
    nonce = f"{os.getpid()}.{time.time_ns()}"
    try:
        cache.mkdir(parents=True, exist_ok=True)
        image = cache / f"{key}.{nonce}.img"
        space.save(image, format="fast")
        sidecar = {
            "format": IMAGE_FORMAT,
            "world": _identity(world),
            "image": image.name,
            "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
            "compile_inferences": inferences,
            "compile_seconds": round(seconds, 3),
        }
        staged = cache / f"{key}.{nonce}.json.tmp"
        staged.write_text(json.dumps(sidecar, sort_keys=True), encoding="utf-8")
        os.replace(staged, cache / f"{key}.json")
    except (OSError, MettaError) as error:
        logger.warning("The SNARS world %s was not saved as an image in %s: %s", world.space, cache, error)


# The load-time directives a world's image does not carry, in load order: the library
# aggregator's own, with each of its imports of a library module replaced by that module's
# directives, since the image holds the module's atoms but not what its directives did outside
# them, then each world module's. Reading them from the modules keeps the list the modules' own.
# Time: one read of the library's modules and the world's, about 260 KB of MeTTa.
# am[implements a-rt-image-relocation-rehydration-1017@bb9fc4] am[implements a-rt-metta-forms-shared-1017@db105c]
# am[rests-on e122fefb@292e61]
def _rehydration(includes: frozenset[str]) -> str:
    directory = _snars_directory()
    directives: list[str] = []
    for form in top_level_forms((directory / "snars.metta").read_text(encoding="utf-8")):
        if not form.directive:
            continue
        (body,) = top_level_forms(form.text[1:])
        parsed = syntax.parse(body.text)
        if [getattr(atom, "text", None) for atom in parsed[:2]] == ["import!", "&self"] and hasattr(parsed[2], "text"):
            module = (directory / f"{parsed[2].text}.metta").read_text(encoding="utf-8")
            directives += [inner.text for inner in top_level_forms(module) if inner.directive]
        else:
            directives.append(form.text)
    for path in world_modules(includes):
        directives += [form.text for form in top_level_forms(path.read_text(encoding="utf-8")) if form.directive]
    return "\n".join(directives) + "\n"


# &goalchainer-snars for a world without optional features, &goalchainer-snars-policy-guard for one
# with both, the features in FEATURES order.
# am[implements a-rt-snars-worlds-by-includes-1017@54c05f]
def _space_name(includes: frozenset[str]) -> str:
    return "&goalchainer-snars" + "".join(f"-{feature}" for feature in FEATURES if feature in includes)


# am[implements a-rt-snars-adopt-library-1017@1231db]
def _snars_directory() -> Path:
    if not (SNARS_DIRECTORY / "snars.metta").is_file():
        raise DependencyUnavailableError(
            f"GoalChainer's SNARS library is missing from its package at {SNARS_DIRECTORY}; "
            "reinstall GoalChainer.",
            details={"dependency": "SNARS library", "path": str(SNARS_DIRECTORY)},
        )
    return SNARS_DIRECTORY


# The process's library digest: the first one asked for pins it, and any other is bytes the
# process does not run.
# am[implements a-rt-snars-identity-resident-1017@3c837e]
def _pinned_library(digest: str) -> str:
    pinned = _PINNED.setdefault("library", digest)
    if digest != pinned:
        raise ModuleChanged(SNARS_DIRECTORY, pinned, digest)
    return digest


# Each helper file by name and the digest of the bytes the process compiled it from, composed
# from snars_python's digests and never from a read of the files; each file is read only to
# refuse one whose bytes are no longer those the process runs, and a module put in a helper's
# place in sys.modules is refused as a helper the process never compiled.
# Time: one read of each helper file, about 40 KB in all.
# am[implements a-rt-snars-store-identity-1017@deb59d] am[implements a-rt-snars-python-helpers-1017@e0faec]
# am[implements a-rt-snars-identity-resident-1017@3c837e] am[rests-on c-rt-pycall-runs-resident-module-1017@a14440]
def _helpers_digest() -> str:
    try:
        helpers = snars_python.loaded()
    except ImportError as error:
        raise DependencyUnavailableError(
            str(error), details={"dependency": "SNARS helper", "module": str(error.name)}
        ) from error
    digest = hashlib.sha256()
    for path, compiled in helpers:
        try:
            current = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as error:
            raise DependencyUnavailableError(
                f"Cannot read the SNARS helper at {path}: {error}",
                details={"dependency": "SNARS helper", "path": str(path), "error": str(error)},
            ) from error
        if current != compiled:
            raise ModuleChanged(path, compiled, current)
        digest.update(f"{path.name}\0{compiled}\0".encode())
    return digest.hexdigest()


# am[implements a-rt-snars-store-identity-1017@deb59d]
def _combined(library_digest: str, helpers_digest: str) -> str:
    return hashlib.sha256(f"snars\0{library_digest}\0{helpers_digest}".encode()).hexdigest()
