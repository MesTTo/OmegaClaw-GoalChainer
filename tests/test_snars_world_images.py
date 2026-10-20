"""Purpose: verify that a process starting SNARS worlds from images starts each world from the
fast image an earlier compile of the same identity saved, in a relocated copy of the package too,
and, once it has planned every function the world defines, answers and charges each batch as the
compiled world did; that a world is published only after its plan, which changes no atom and no
store outside pymetta's own, and that a plan that raises or that the deadline stops leaves the
world unpublished for the next call to start again; that an image starts only the identity it
names, so a changed world module or an image whose bytes are not those its sidecar names is
compiled afresh and saved again; that a cache the process cannot write, or a default cache with no
home to find, leaves the world compiled and says so; that opting in changes no batch's budget; and
that the commands' main functions, run in their caller's process, leave it compiling. Each process
that opts in is a fresh interpreter on its own copy of the package."""

from __future__ import annotations

import json
from pathlib import Path

from copied_package import copy_package, run_fresh
from request_support import CLI_LIMITS, LIMITS
from snars_differential import clock_fields, equal, records

from goal_chainer import cli, omegaclaw_skill, snars_engine
from goal_chainer.snars_program import PROTOCOL_PATH

CLOCKS = clock_fields(PROTOCOL_PATH.read_text(encoding="utf-8"))
EDGE_AB = '(sn p so "is" ((arg s (sn c "a")) (arg o (sn c "b"))))'
EDGE_BC = '(sn p so "is" ((arg s (sn c "b")) (arg o (sn c "c"))))'
EDGE_AC = '(sn p so "is" ((arg s (sn c "a")) (arg o (sn c "c"))))'
PATTERN = '(sn p so "is" ((arg s (sn c "a")) (arg o $what)))'

# What planning a world may not change, as a sorted list of rows: every dynamic predicate whose
# source lies outside pymetta's package, with the variant hash of its clauses, and every global
# variable not named with '$'. A predicate's source is the file source_file/2 names, which for the
# SNARS kernel's stores is kernel.pl, the one declaring them, else the file defining it, else its
# module's file; a predicate with none, as pymetta's own handle leases are, belongs to no
# application file. The predicates pymetta's files define hold its compilation, which planning
# moves. `Root` is pymetta's package directory.
# am[verifies a-rt-iw-effect-plan-1019@fc18bf]
APPLICATION_STATE = (
    "findall(_S, (current_module(_M), \\+ module_property(_M, class(system)), current_predicate(_M:_N/_A), "
    "functor(_H, _N, _A), predicate_property(_M:_H, dynamic), \\+ predicate_property(_M:_H, imported_from(_)), "
    "once(( source_file(_M:_H, _F) ; predicate_property(_M:_H, file(_F)) ; module_property(_M, file(_F)) )), "
    "\\+ sub_atom(_F, 0, _, _, Root), "
    "findall(_H-_B, clause(_M:_H, _B), _Clauses), variant_sha1(_Clauses, _Sha), "
    "format(string(_S), '~q:~q/~q ~w', [_M, _N, _A, _Sha])), _Predicates), "
    "findall(_S, (nb_current(_K, _V), atom(_K), \\+ sub_atom(_K, 0, _, _, '$'), variant_sha1(_V, _Sha), "
    "format(string(_S), 'global ~q ~w', [_K, _Sha])), _Globals), "
    "append(_Predicates, _Globals, _All), msort(_All, Census)"
)


# An inspect batch in the plain world, after two beliefs and the ask, prove, obligations and
# what-if batches on them with `operations`, and with `guard` a guard batch in the guard world, all
# started from images in `cache`: each world's origin and identity, what each batch printed and the
# inferences it was charged, the warnings the engine logged and the kinds of file the cache holds
# afterwards.
# am[verifies a-rt-image-identity-1017@94d06b] am[verifies a-rt-image-cache-1017@66d7ae]
# am[verifies a-rt-iw-effect-plan-1019@fc18bf]
def _script(cache: Path, *, guard: bool = True, operations: bool = False) -> str:
    return f"""
import json, logging
from goal_chainer import snars_engine
from goal_chainer.runtime.budget import RunBudget
from goal_chainer.semantic_reader import default_reader
from goal_chainer.snars_models import Evidence
from goal_chainer.snars_reasoner import SnarsSession
warnings = []
logging.getLogger("goal_chainer.snars_engine").addHandler(type("Keep", (logging.Handler,), {{"emit": lambda self, record: warnings.append(record.getMessage())}})())
cache = Path({str(cache)!r})
snars_engine.start_worlds_from_images(cache)
outputs, charges = [], []
def recording(batch, budget):
    run = snars_engine.run_snars_batch(batch, budget=budget)
    outputs.append("\\n".join(run.output_lines))
    charges.append(run.inferences)
    return run.output_lines
budget = RunBudget(inference_budget=None, timeout_seconds=900)
with SnarsSession.ephemeral(budget=budget, include_goalchainer_policy=False, execute=recording,
                            reader=default_reader(budget=budget)) as session:
    if {operations!r}:
        for index, statement in enumerate({(EDGE_AB, EDGE_BC)!r}):
            session.believe(statement, evidence=Evidence(8, 0), source=f"source-{{index}}")
        session.ask({PATTERN!r})
        session.prove({EDGE_AC!r})
        session.obligations({EDGE_AC!r})
        session.what_if({EDGE_AB!r}, {EDGE_AC!r})
    session.inspect()
    if {guard!r}:
        # am[verifies a-integrate-guard-metta-gate-1019@1bf9e1]
        session.guard("(safe redacted)", rules=("(safe redacted)",))
worlds = [{{"includes": list(world.includes), "origin": world.origin, "identity": world.snars_identity,
           "modules": [list(module) for module in world.modules], "runtime": world.runtime_digest}}
          for world in snars_engine.compiled_worlds()]
files = sorted(path.suffix for path in cache.iterdir()) if cache.is_dir() else []
print(json.dumps({{"worlds": worlds, "outputs": outputs, "charges": charges, "warnings": warnings, "files": files}}))
"""


# am[verifies a-rt-image-identity-1017@94d06b]
def _origins(report: dict) -> list[str]:
    return [world["origin"] for world in report["worlds"]]


# am[verifies a-rt-image-identity-1017@94d06b]
def _identities(report: dict) -> list[dict]:
    return [{key: value for key, value in world.items() if key != "origin"} for world in report["worlds"]]


# The first process compiles both worlds and saves them; a second, importing another copy of the
# package from another directory, starts both from those images, rehydrated, with the same
# identities, and each batch prints what the compiled world printed, up to the wall clock. Each
# batch is charged within 1% of what the compiled world charged it: the planned world compiled
# before it was published what a batch calls, where an unplanned one compiled it inside every
# batch's speculation, at about 14 million inferences a batch (c-rt-iw-effect-plan-compiles-1019).
# am[verifies a-rt-image-identity-1017@94d06b] am[verifies a-rt-image-relocation-rehydration-1017@bb9fc4]
# am[verifies a-rt-image-cache-1017@66d7ae] am[verifies a-rt-image-entry-point-optin-1017@f47b3e]
# am[verifies a-rt-iw-effect-plan-1019@fc18bf]
def test_a_later_process_starts_each_world_from_the_image_an_earlier_compile_saved(tmp_path) -> None:
    cache = tmp_path / "cache"
    first = run_fresh(copy_package(tmp_path / "first"), _script(cache, operations=True))
    second = run_fresh(copy_package(tmp_path / "relocated"), _script(cache, operations=True))

    assert _origins(first) == ["compiled", "compiled"] and _origins(second) == ["image", "image"]
    assert [world["includes"] for world in first["worlds"]] == [[], ["guard"]]
    assert _identities(second) == _identities(first)
    assert len(first["outputs"]) == len(second["outputs"]) == 8
    for compiled, started in zip(first["outputs"], second["outputs"]):
        assert equal(records(compiled), records(started), CLOCKS)
    for compiled, started in zip(first["charges"], second["charges"]):
        assert abs(started - compiled) <= compiled // 100, (compiled, started)
    assert first["files"] == second["files"] == [".img", ".img", ".json", ".json"]
    assert first["warnings"] == second["warnings"] == []


# A world started from its image is published only once its plan has compiled it. A plan that
# raises, or one whose request's deadline passes before it starts, leaves the world unpublished,
# and the next call starts it from its image again; no plan, finished or not, changes the world's
# atoms or any store pymetta's files do not define, and starting the world again leaves both as the
# first start left them, so the world a retry publishes holds the atoms one started cleanly in
# another process holds.
# am[verifies a-rt-iw-effect-plan-1019@fc18bf] am[verifies a-rt-image-warm-up-1018@da80c2]
def test_an_image_world_is_published_only_after_a_plan_that_changes_nothing_but_compilation(tmp_path) -> None:
    cache = tmp_path / "cache"
    site = copy_package(tmp_path / "site")
    assert _origins(run_fresh(site, _script(cache, guard=False))) == ["compiled"]
    state = f"""
import json, time
import metta
from goal_chainer import snars_engine
from goal_chainer.runtime.budget import ReviewTimeout, RunBudget
from goal_chainer.runtime.engine import metta_engine
snars_engine.start_worlds_from_images(Path({str(cache)!r}))
root = str(Path(metta.__file__).resolve().parent)
def state(space):
    return {{"digest": space.digest(), "census": space.runtime.once({APPLICATION_STATE!r}, Root=root)["Census"]}}
def published():
    return [world.space for world in snars_engine.compiled_worlds()]
"""
    report = run_fresh(site, state + """
plan, functions = snars_engine._plan, snars_engine._functions
plans = []
def observed(space, budget):
    before, seen = state(space), published()
    try:
        plan(space, budget)
    finally:
        plans.append({"published": str(space.name) in seen, "unchanged": state(space) == before, **before})
snars_engine._plan = observed
outcomes = []
def failing(space):
    raise RuntimeError("a fault injected into the plan")
snars_engine._functions = failing
try:
    snars_engine.prepare_snars_world(())
except RuntimeError as error:
    outcomes.append([str(error), published()])
budget = RunBudget(inference_budget=None, timeout_seconds=15)
def late(space):
    try:
        while True:
            time.sleep(min(0.05, budget.remaining()[1]))
    except ReviewTimeout:
        pass
    return functions(space)
snars_engine._functions = late
try:
    snars_engine.prepare_snars_world((), budget=budget)
except ReviewTimeout as error:
    outcomes.append([type(error).__name__, published()])
snars_engine._functions = functions
world = snars_engine.prepare_snars_world(())
with metta_engine(None) as engine:
    final = state(engine.space(world.space))
print(json.dumps({"outcomes": outcomes, "plans": plans, "origin": world.origin, "published": published(),
                  "space": world.space, "state": final}))
""")
    clean = run_fresh(site, state + """
world = snars_engine.prepare_snars_world(())
with metta_engine(None) as engine:
    print(json.dumps({"origin": world.origin, "state": state(engine.space(world.space))}))
""")

    assert report["outcomes"] == [["a fault injected into the plan", []], ["ReviewTimeout", []]]
    assert [plan["published"] for plan in report["plans"]] == [False, False, False]
    assert all(plan["unchanged"] for plan in report["plans"])
    assert any(row.startswith("user:sn_ev/4 ") for row in report["plans"][0]["census"])
    first, retried = report["plans"][0], report["plans"][-1]
    assert (first["digest"], first["census"]) == (retried["digest"], retried["census"])
    assert report["origin"] == clean["origin"] == "image" and report["published"] == [report["space"]]
    assert report["state"]["digest"] == clean["state"]["digest"]


# A world module changed after the image was saved gives the world another identity, so no image
# starts it and its compile is saved beside the old one; an image whose bytes are not the ones its
# sidecar names starts nothing either, and the compile that replaces it starts the next process.
# am[verifies a-rt-image-identity-1017@94d06b] am[verifies a-rt-image-cache-1017@66d7ae]
# am[verifies a-ie-s2c-scalar-tests-proofs-1018@5a0031]
def test_an_image_starts_only_the_identity_and_bytes_its_sidecar_names(tmp_path) -> None:
    cache = tmp_path / "cache"
    site = copy_package(tmp_path / "site")
    saved = run_fresh(site, _script(cache, guard=False))
    protocol = site / "goal_chainer" / "policy" / "goalchainer_protocol.metta"
    protocol.write_text(protocol.read_text(encoding="utf-8") + "\n; changed after the images were saved\n",
                        encoding="utf-8")

    changed = run_fresh(site, _script(cache, guard=False))
    assert _origins(saved) == _origins(changed) == ["compiled"]
    assert changed["worlds"][0]["modules"] != saved["worlds"][0]["modules"]
    assert changed["files"] == [".img", ".img", ".json", ".json"]

    for image in cache.glob("*.img"):
        image.write_bytes(image.read_bytes() + b"\0")
    assert _origins(run_fresh(site, _script(cache, guard=False))) == ["compiled"]
    assert _origins(run_fresh(site, _script(cache, guard=False))) == ["image"]


# A cache path the process cannot make into a directory leaves the world compiled, its batch
# answered and a warning naming the world not saved.
# am[verifies a-rt-image-cache-1017@66d7ae]
def test_a_cache_the_process_cannot_write_leaves_the_world_compiled(tmp_path) -> None:
    cache = tmp_path / "cache"
    cache.write_text("a file where the cache directory would go", encoding="utf-8")
    report = run_fresh(copy_package(tmp_path / "site"), _script(cache, guard=False))

    assert _origins(report) == ["compiled"] and len(report["outputs"]) == 1
    assert len(report["warnings"]) == 1
    assert all("was not saved as an image" in warning for warning in report["warnings"])


# A world module the process cannot read gets no image, and the compile names it as the missing
# dependency it is, as a process that never starts from images would.
# am[verifies a-rt-image-identity-1017@94d06b]
# am[verifies a-ie-s2c-scalar-tests-proofs-1018@5a0031]
def test_a_world_module_missing_is_a_named_dependency_with_images_on(tmp_path) -> None:
    site = copy_package(tmp_path / "site")
    (site / "goal_chainer" / "policy" / "goalchainer_protocol.metta").unlink()
    report = run_fresh(site, f"""
import json
from goal_chainer import snars_engine
from goal_chainer.errors import DependencyUnavailableError
snars_engine.start_worlds_from_images(Path({str(tmp_path / "cache")!r}))
try:
    snars_engine.prepare_snars_world(())
except DependencyUnavailableError as error:
    print(json.dumps({{"refused": str(error), "worlds": len(snars_engine.compiled_worlds())}}))
""")
    assert "goalchainer_protocol.metta" in report["refused"] and report["worlds"] == 0


# Opting in records the choice and nothing else: with no XDG_CACHE_HOME and a home directory that
# cannot be found, as for a uid with no passwd entry, start_worlds_from_images returns, and the
# first world the process prepares compiles, answers its batch and says once why it has no image.
# am[verifies a-rt-image-console-main-1017@87159d] am[verifies c-rel-optin-resolves-cache-eagerly-1017@c12616]
def test_an_opt_in_with_no_home_to_find_leaves_worlds_compiled_and_says_so(tmp_path) -> None:
    report = run_fresh(copy_package(tmp_path / "site"), """
import json, logging, os, pathlib
from goal_chainer import snars_engine
from goal_chainer.runtime.budget import RunBudget
from goal_chainer.semantic_reader import default_reader
from goal_chainer.snars_reasoner import SnarsSession
warnings = []
logging.getLogger("goal_chainer.snars_engine").addHandler(type("Keep", (logging.Handler,), {"emit": lambda self, record: warnings.append(record.getMessage())})())
os.environ.pop("XDG_CACHE_HOME", None)
os.environ.pop("HOME", None)
def no_home(cls):
    raise RuntimeError("Could not determine home directory.")
pathlib.Path.home = classmethod(no_home)
snars_engine.start_worlds_from_images()
budget = RunBudget(inference_budget=None, timeout_seconds=900)
with SnarsSession.ephemeral(budget=budget, include_goalchainer_policy=False,
                            reader=default_reader(budget=budget)) as session:
    session.inspect()
    session.inspect()
print(json.dumps({"origins": [world.origin for world in snars_engine.compiled_worlds()], "warnings": warnings}))
""")
    assert report["origins"] == ["compiled"]
    assert len(report["warnings"]) == 1 and "has no home" in report["warnings"][0]


# A batch runs under its session's budget whether or not its process starts worlds from images, so
# starting from images changes no bound a request set.
# am[verifies a-rt-image-console-main-1017@87159d] am[verifies a-rt-rbs-session-budget-1018@8c3da2]
def test_starting_from_images_leaves_every_batch_budget_as_it_was(tmp_path) -> None:
    report = run_fresh(copy_package(tmp_path / "site"), f"""
import json
from goal_chainer import snars_engine
from goal_chainer.runtime.budget import RunBudget
from goal_chainer.semantic_reader import default_reader
from goal_chainer.snars_reasoner import SnarsSession, execute_in_process
budgets = []
def inspect():
    opened = RunBudget(inference_budget=10**9, timeout_seconds=600)
    def recording(batch, budget):
        budgets.append([budget is opened, budget.inference_budget, budget.timeout_seconds])
        return execute_in_process(batch, budget)
    with SnarsSession.ephemeral(budget=opened, include_goalchainer_policy=False, execute=recording,
                                reader=default_reader(budget=opened)) as session:
        session.inspect()
inspect()
snars_engine.start_worlds_from_images(Path({str(tmp_path / "cache")!r}))
inspect()
print(json.dumps({{"budgets": budgets}}))
""")
    assert report["budgets"] == [[True, 10**9, 600.0], [True, 10**9, 600.0]]


# main is the reusable entry: the goalchainer and skill mains, run in their caller's process as
# tests run them, leave that process compiling its worlds, so only console_main opts a process in.
# am[verifies a-rt-image-console-main-1017@87159d] am[verifies c-rt-main-called-in-process-1017@fe5086]
# am[verifies a-integrate-request-budget-surface-1018@d6882c]
def test_the_commands_main_leaves_its_caller_compiling(capsys) -> None:
    assert snars_engine._IMAGES == {}
    assert cli.main(["snars", *CLI_LIMITS, "ask", "--statement", '(sn p so "is" ((arg s (sn c "a")) (arg o $what)))', "--json"]) == 0
    request = {"group": "evidence", "operation": "ask", "statement": '(sn p so "is" ((arg s (sn c "a")) (arg o $what)))', **LIMITS}
    assert omegaclaw_skill.main(["goalchainer-snars-dispatch", "--request", json.dumps(request)]) == 0
    capsys.readouterr()
    assert snars_engine._IMAGES == {}
