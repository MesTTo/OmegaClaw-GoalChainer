"""Purpose: verify installed policy resources, adopted libraries and actual native decisions, a public
plan request and the admission of the step it returned included."""
# am[verifies a-integrate-verify-package-1016@a6700c]

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from zipfile import ZipFile

from goal_chainer.planning.group import MODULES
from goal_chainer.planning.projection import Admitted, Answer, Plan, Verdict
from goal_chainer.planning.transport import decode
from request_support import CLI_LIMITS, LIMITS


# am[verifies a-integrate-verify-package-1016@a6700c]
def test_wheel_only_domain_command(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    env = {
        key: value for key, value in os.environ.items()
        if key not in {"PYTHONPATH", "PYTHONHOME", "SWI_HOME_DIR"} and not key.startswith("GOALCHAINER_")
    }
    env["TMPDIR"] = str(tmp_path)
    env["XDG_CACHE_HOME"] = str(tmp_path / "user-cache")

    # am[verifies a-integrate-verify-package-1016@a6700c]
    def run(command, cwd):
        result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout

    # uv builds the sdist, then the wheel from the unpacked sdist, from a copy of the checkout's files
    # that git does not ignore. A wheel built in the checkout would also carry whatever an earlier
    # build left there, which a battery tree reused across revisions holds: setuptools' build/lib with
    # deleted modules, and an egg-info SOURCES.txt whose every listed file reaches the sdist, so a
    # file the package data now excludes would still ship. The two submodule checkouts are directories
    # the build does not read.
    # Time and space: one copy of the unignored files, about 1300 files and 8 MB.
    # am[addresses i-tk-wheel-test-builds-in-tree-1018@793e7a] am[rests-on c-tk-stale-build-lib-ships-1018@abe860]
    # am[verifies a-tk-wheel-from-sdist-1018@730308]
    # am[addresses i-ip-stale-egg-info-ships-1018@d9bbeb] am[rests-on c-ip-stale-sources-keep-excluded-files-1018@81fd70]
    # am[implements a-ip-clean-source-build-1018@514ef0]
    source = tmp_path / "source"
    for name in filter(None, run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], repo).split("\0")):
        if (repo / name).is_file():
            (source / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo / name, source / name)
    # git ignores native-wheels/, and uv reads the find-links entry naming it before it builds
    # anything, so the copy reaches the checkout's verified directories through one link.
    # am[implements a-rt-n2ic-wheel-test-1018@7cb39a] am[rests-on c-rt-n2ic-find-links-needs-placement-1018@e71866]
    (source / "native-wheels").symlink_to(repo / "native-wheels")
    dist = tmp_path / "dist"
    run(["uv", "build", "--out-dir", str(dist)], source)
    wheel, = dist.glob("*.whl")
    # Check the complete adopted tree, including its Prolog kernel and source notices, and every
    # policy module and the directive adapter the package loads, so a wheel missing one fails here
    # rather than on its first decision.
    # Time: two reads of B total bytes. Space: F paths and two largest-file buffers.
    # am[verifies a-rt-incorporate-deontic-1016@6ea255] am[verifies a-ev-wheel-policy-files-1017@737255]
    # am[verifies a-rt-snars-wheel-execution-1017@cb7db2]
    package_root = repo / "src" / "goal_chainer"
    library = package_root / "deontic_library"
    source_files = sorted(path for path in library.rglob("*") if path.is_file())
    assert source_files, "the adopted deontic library is absent"
    policy_files = sorted((package_root / "policy").glob("*.metta"))
    assert policy_files, "the policy modules are absent"
    source_files += [*policy_files, package_root / "goalchainer_directive.metta"]
    # SNARS ships whole with its sCASP copy, and its Python half is the snars_python package
    # beside it and the top-level py-call module, so no vendored tree carries a bytecode cache.
    snars = sorted(path for path in (package_root / "snars_library").rglob("*") if path.is_file())
    assert snars, "the adopted SNARS library is absent"
    source_files += [*snars, *sorted((package_root / "snars_python").glob("*.py"))]
    # Markdown ships the same way: its MeTTa library whole, its Python half the markdown_python
    # package beside it and the top-level py-call module goalchainer_markdown.
    # am[verifies a-rt-p3-markdown-vendored-1017@88745b]
    markdown = sorted(path for path in (package_root / "markdown_library").rglob("*") if path.is_file())
    assert markdown, "the adopted Markdown library is absent"
    source_files += [*markdown, *sorted((package_root / "markdown_python").glob("*.py"))]
    # The bigraph kernel's MeTTa module, which goal_chainer.bigraph.kernel loads from beside itself.
    # am[verifies a-brs-k-wheel-kernel-check-1018@619ea3]
    source_files.append(package_root / "bigraph" / "kernel.metta")
    # The planner's module group and the packaged procedure libraries and domains it plans over, each
    # loaded from beside the module that names it.
    # am[verifies a-integrate-installed-planner-contract-1018@a2c34a]
    source_files += [path for path in MODULES if path not in source_files]
    source_files += [*sorted((package_root / "planning" / "library").glob("*.metta")),
                     *sorted((package_root / "domains" / "data").glob("*.metta"))]
    with ZipFile(wheel) as archive:
        # The wheel holds the goal_chainer package, the three top-level py-call modules and its
        # metadata; nothing installs under the environment's prefix as a data file.
        # am[verifies a-tk-packaging-1018@7cd2e8]
        top = {name.split("/", 1)[0] for name in archive.namelist()}
        assert {name for name in top if not name.endswith(".dist-info")} == {
            "goal_chainer", "gcskill.py", "goalchainer_snars.py", "goalchainer_markdown.py"}, top
        for path in source_files:
            member = "goal_chainer/" + path.relative_to(package_root).as_posix()
            assert archive.read(member) == path.read_bytes(), member
        for module in ("goalchainer_snars.py", "goalchainer_markdown.py"):
            assert archive.read(module) == (repo / "src" / module).read_bytes(), module
        cached = [name for name in archive.namelist()
                  if name.startswith(("goal_chainer/deontic_library/", "goal_chainer/snars_library/",
                                      "goal_chainer/markdown_library/"))
                  and ("__pycache__" in name or name.endswith((".pyc", ".qlf")))]
        assert cached == [], cached
        # The wheel declares GoalChainer's MIT and the licence of every LICENSE file the package
        # ships, read from the file's title, and lists each of those files as a License-File.
        # am[verifies a-rt-wheel-licence-declared-1017@c31ef6]
        # am[verifies a-v2-review-package-1020@940ccf]
        metadata = archive.read(next(name for name in archive.namelist() if name.endswith(".dist-info/METADATA")))
        fields = [line.split(": ", 1) for line in metadata.decode("utf-8").splitlines() if ": " in line]
        licences = [repo / "LICENSE", *sorted(package_root.rglob("LICENSE"))]
        assert sorted(value for key, value in fields if key == "License-File") == [
            path.relative_to(repo).as_posix() for path in licences]
        dist_info = next(name for name in top if name.endswith(".dist-info"))
        for path in licences:
            member = f"{dist_info}/licenses/{path.relative_to(repo).as_posix()}"
            assert archive.read(member) == path.read_bytes(), member
        # am[verifies a-ie-ontology-retirement-1018@8ce5ff]
        # am[verifies a-v2-public-license-notice-1020@fedb58]
        spdx = {"MIT License": "MIT", "Apache License": "Apache-2.0",
                "GNU GENERAL PUBLIC LICENSE": "GPL-3.0-only"}
        titles = {spdx[path.read_text(encoding="utf-8").strip().splitlines()[0].strip()] for path in licences}
        expression, = (value for key, value in fields if key == "License-Expression")
        assert set(expression.split(" AND ")) == {"MIT", *titles}
    installation = tmp_path / "installed"
    run(["uv", "venv", "--python", sys.executable, str(installation)], tmp_path)
    python = installation / "bin" / "python"
    # A wheel carries no tool.uv settings, so its exact pymetta pin finds the local build only in the
    # verified directories given here, as for anyone installing the wheel alone, and check then holds
    # the installation to the published wheel.
    # am[verifies a-rt-n2ic-wheel-test-1018@7cb39a] am[rests-on c-rt-n2ic-exact-pin-fails-loud-1018@4bebfe]
    links = [part for directory in sorted((repo / "native-wheels").iterdir()) for part in ("--find-links", str(directory))]
    run(["uv", "pip", "install", "--python", str(python), *links, str(wheel)], tmp_path)
    run([str(python), str(repo / "scripts" / "native-wheels.py"), "check"], tmp_path)
    domain = json.loads(run([
        str(installation / "bin" / "goalchainer"), "relevance", "domain", "--json",
        "--inference-budget", "5000000", "--timeout-seconds", "60",
    ], tmp_path))
    assert domain["actions"] and domain["signals"] and domain["goals"]
    assert domain["source"] == "goal_chainer/domains/data/task_control.metta"
    assert len(domain["digest"]) >= 64
    location = run([str(python), "-c", "import goal_chainer; print(goal_chainer.__file__)"], tmp_path)
    assert Path(location.strip()).is_relative_to(installation)

    # The installed request command plans from the caller's copy of the public planning example, then
    # admits the first step it returned, passed back unchanged with the same evidence. Each run takes
    # the caller's limits and starts in the scratch directory with no variable naming a checkout. The
    # packaged domain, its procedure library and every planner module load from the installation, and
    # each step names a procedure that library declares.
    # am[verifies a-integrate-installed-planner-contract-1018@a2c34a]
    goalchainer = str(installation / "bin" / "goalchainer")
    request = json.loads((repo / "examples" / "planning" / "task-control.request.json").read_text(encoding="utf-8"))
    (tmp_path / "plan.json").write_text(json.dumps(request), encoding="utf-8")
    planned = json.loads(run([goalchainer, "request", "--input", "plan.json", *CLI_LIMITS], tmp_path))
    answer = decode(planned["planning"], Answer)
    assert isinstance(answer, Plan) and answer.steps and not answer.assumptions, planned["planning"]
    assert answer.steps[0].kind == "start"
    admission = {key: value for key, value in request.items() if key != "goal"}
    admission.update(operation="admit", step=planned["planning"]["steps"][0], instance_id=None)
    (tmp_path / "admission.json").write_text(json.dumps(admission), encoding="utf-8")
    checked = json.loads(run([goalchainer, "request", "--input", "admission.json", *CLI_LIMITS], tmp_path))
    verdict = decode(checked["admission"], Verdict)
    assert isinstance(verdict, Admitted) and f'"{answer.steps[0].procedure}"' in verdict.occurrence, checked["admission"]
    for result in (planned, checked):
        assert result["authorization"] == "unresolved" and result["applies_effects"] is False
        assert result["review"]["domain"]["source"] == "goal_chainer/domains/data/task_control.metta"
        assert 0 < result["inferences"] <= LIMITS["inference_budget"]
    planner = json.loads(run([str(python), "-c", '''
import json
from goal_chainer.domains.loader import packaged_domain
from goal_chainer.planning.group import MODULES
from goal_chainer.planning.procedures import packaged_procedures
from goal_chainer.runtime.budget import RunBudget

budget = RunBudget(inference_budget=1_000_000_000, timeout_seconds=600)
library = packaged_procedures(packaged_domain("task-control", budget=budget), budget=budget)
print(json.dumps({"modules": [str(path) for path in MODULES], "library": library.source,
                  "procedures": [procedure.name for procedure in library.procedures]}))
'''], tmp_path))
    assert all(Path(path).is_relative_to(installation) and Path(path).is_file() for path in planner["modules"])
    assert [Path(path).name for path in planner["modules"]] == [path.name for path in MODULES]
    assert planner["library"] == "goal_chainer/planning/library/task_control.metta"
    assert {step.procedure for step in answer.steps} <= set(planner["procedures"])

    # The domain assertion above runs without native overrides. Core evaluation below names
    # only the pinned dependencies provisioned in this battery, never an editing checkout, and no
    # Mettabase: the directive program renders Markdown through the installation's own library.
    # am[verifies a-core-policy-verification-1016@1996a0] am[verifies a-rt-p3-callers-1017@69a49e]
    # am[verifies a-ie-s2c-scalar-tests-proofs-1018@5a0031]
    env["GOALCHAINER_OMEGACLAW_DIR"] = str(tmp_path / "no-omegaclaw-checkout")
    env["GOALCHAINER_TEST_PLAN"] = str(tmp_path / "installed-plan.metta")
    result = json.loads(run([str(python), "-c", '''
import json
import os
from pathlib import Path
import goal_chainer
from goal_chainer import evidence_policy
from goal_chainer.memory_evidence import consumed_slots
from goal_chainer.semantic_models import model_cache
from goal_chainer.deontic_engine import DEONTIC_DIRECTORY, DEONTIC_STATUSES, run_deontic_theory
from goal_chainer.directive import ADAPTER_PATH, create_plan, run_directive_request
from goal_chainer.runtime.budget import RunBudget

package = Path(goal_chainer.__file__).parent
# One evaluation loads the evidence policy's modules from the installed package: the memory policy
# answers the slots it reads, each with its encoding.
assert evidence_policy.POLICY_DIRECTORY.is_relative_to(package)
slots = consumed_slots(budget=RunBudget(inference_budget=None, timeout_seconds=120.0))
assert slots and set(slots.values()) <= {'stv', 'ec'}, dict(slots)
assert 'unregulated' in DEONTIC_STATUSES
cache = model_cache()
assert cache == Path(os.environ['XDG_CACHE_HOME']) / 'goalchainer' / 'models'
assert not cache.is_relative_to(package)
# am[verifies a-rt-incorporate-deontic-1016@6ea255]
assert DEONTIC_DIRECTORY.is_relative_to(package)
assert ADAPTER_PATH.is_relative_to(package) and ADAPTER_PATH.is_file()
assert (DEONTIC_DIRECTORY / 'LICENSE').read_text().startswith('MIT License')
review = run_deontic_theory(
    """(given (risky publish_raw_log))
(normally rRawForbid (risky publish_raw_log) (forbidden publish_raw_log))
""",
    budget=RunBudget(inference_budget=10_000_000, timeout_seconds=120.0),
)
assert review.engine.runtime.startswith('pymetta ')
assert any(row.literal.mode == 'F' and row.literal.functor == 'publish_raw_log'
           for row in review.conclusions)
# The installed directive adapter reads a caller-written plan.
plan = create_plan(os.environ['GOALCHAINER_TEST_PLAN'],
    '(meta plan (id "WHEEL") (title "Installed check") (version "1.0.0") (status "active")'
    ' (created "2026-10-18") (author "agent:test"))\\n'
    '(given task-check)\\n(given no-deps-check)\\n'
    '(normally r-check (and task-check no-deps-check) ready-check)\\n')
board = run_directive_request({'operation': 'board', 'plan': str(plan)},
    budget=RunBudget(inference_budget=None, timeout_seconds=120.0))
assert board['result']['ready'] == ['check'], board
# The audit's authored tree renders through the Markdown library the installation carries, loaded
# in-process into the directive's space from the installation.
from goal_chainer.directive import DirectiveRuntime
markdown = DirectiveRuntime().bounded(RunBudget(inference_budget=None, timeout_seconds=120.0)).render_markdown(
    '(md d1 (h1 "Audit") (p "Ready."))').value
assert markdown == '# Audit\\n\\nReady.', markdown
print(json.dumps({'package': str(package), 'cache': str(cache)}))
'''], tmp_path))
    assert Path(result["package"]).is_relative_to(installation)
    assert Path(result["cache"]) == tmp_path / "user-cache" / "goalchainer" / "models"

    # The installed package runs SNARS in-process from its own files, the guard on its sCASP copy,
    # with no GOALCHAINER_* variable naming a checkout and HOME an empty directory, so SWI-Prolog
    # finds no pack of the user's. Guard and attention batches load their modules from the
    # installation. Each world's identity is the one a
    # session checks a store against, and names the installed helper files' bytes.
    # am[verifies a-rt-snars-wheel-execution-1017@cb7db2] am[verifies a-rt-scasp-vendor-1017@5bec02]
    # am[verifies a-rt-snars-identity-resident-1017@3c837e]
    # am[verifies a-integrate-ecan-forward-query-interface-1017@2afce8]
    snars_env = {key: value for key, value in env.items() if not key.startswith("GOALCHAINER_")}
    snars_env["HOME"] = str(tmp_path / "empty-home")
    (tmp_path / "empty-home").mkdir()
    snars_result = subprocess.run([str(python), "-c", '''
import json
from pathlib import Path
import goal_chainer, goalchainer_snars
from goal_chainer import snars_python
from goal_chainer.runtime.budget import RunBudget
from goal_chainer.snars_engine import compiled_worlds, run_snars_batch, snars_identity
from goal_chainer.snars_program import SNARS_DIRECTORY, SnarsProgramBuilder, parse_statement, world_modules
from goal_chainer.semantic_reader import default_reader
from goal_chainer.snars_reasoner import SnarsSession

package = Path(goal_chainer.__file__).parent
budget = RunBudget(inference_budget=None, timeout_seconds=900)
with SnarsSession.ephemeral(budget=budget, reader=default_reader(budget=budget)) as session:
    # am[verifies a-integrate-guard-metta-gate-1019@1bf9e1]
    guard = session.guard("(safe redacted)", rules=("(safe redacted)",))
builder = SnarsProgramBuilder()
codec = builder.codec
effects = [builder.belief_effect(
    parse_statement(f'(sn p so "is" ((arg s (sn c "{left}")) (arg o (sn c "{right}"))))'),
    positive=8, negative=0, base_rate=None, source=f"edge-{index}", trust=1,
) for index, (left, right) in enumerate((("a", "b"), ("b", "c")))]
query = codec.parse('(gc forward-query-record (sn p so "is" ((arg s (sn c "a")) (arg o (sn c "c")))))')
attention = run_snars_batch(builder.batch(query, effects=effects, includes={"attention"}),
                           budget=RunBudget(inference_budget=None, timeout_seconds=900))
worlds = compiled_worlds()
print(json.dumps({
    "proves": guard.payload[2],
    "attention": attention.output_lines,
    "includes": [list(world.includes) for world in worlds],
    "loaded": [path.is_relative_to(package) for world in worlds
               for path in (SNARS_DIRECTORY, *world_modules(frozenset(world.includes)))],
    "helpers": [[str(path), digest] for path, digest in snars_python.loaded()],
    "same_identity": all(world.snars_identity == snars_identity() for world in worlds),
}))
'''], cwd=tmp_path, env=snars_env, text=True, capture_output=True)
    assert snars_result.returncode == 0, snars_result.stdout + snars_result.stderr
    snars_run = json.loads(snars_result.stdout)
    assert snars_run["proves"] == ["proves", "True"]
    assert snars_run["includes"] == [["policy", "guard"], ["attention"]] and all(snars_run["loaded"])
    assert len(snars_run["attention"]) == 1 and "(status Witness)" in snars_run["attention"][0]
    # The S-expression syntax helper is goal_chainer.sexpr.syntax, which SNARS's helpers share.
    # am[verifies a-rt-rb-codec-1018@e3e552]
    assert [Path(path).name for path, _ in snars_run["helpers"]] == [
        "goalchainer_snars.py", "english.py", "syntax.py", "tnf.py"]
    for path, digest in snars_run["helpers"]:
        assert Path(path).is_relative_to(installation) and hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
    assert snars_run["same_identity"]

    # The installed package parses Markdown and renders authored source from its own copy, run from
    # the installation with no variable naming a Mettabase checkout.
    # am[verifies a-rt-p3-markdown-vendored-1017@88745b]
    markdown_result = subprocess.run([str(python), "-c", '''
import json
from pathlib import Path
import goal_chainer, goalchainer_markdown
from goal_chainer.markdown_python import bridge
print(json.dumps({
    "rendered": goalchainer_markdown.md_author_markdown('(md d1 (h1 "Title") (p "Body."))'),
    "facts": bridge.markdown_to_facts("# Title", doc_id="d1"),
    "modules": [module.__file__ for module in (goal_chainer, goalchainer_markdown, bridge)],
}))
'''], cwd=tmp_path, env=snars_env, text=True, capture_output=True)
    assert markdown_result.returncode == 0, markdown_result.stdout + markdown_result.stderr
    markdown_run = json.loads(markdown_result.stdout)
    assert markdown_run["rendered"] == "# Title\n\nBody."
    assert '(md-text d1-h1 "Title")' in markdown_run["facts"]
    assert all(Path(module).is_relative_to(installation) for module in markdown_run["modules"])

    # The installed goalchainer script and the skill as gcskill starts it, python -I -m
    # goal_chainer.omegaclaw_skill, start their worlds from images in the user cache. A process that
    # opted in saves each world it compiles, so a run that leaves the cache as it found it started
    # from an image there: the skill's first run saves the policy world, the script then starts from
    # that image and answers as the skill did, a world module edited in the installation names
    # another identity, which the script compiles and saves beside the first, and the skill then
    # starts from the new image.
    # am[verifies a-rt-image-console-main-1017@87159d]
    # Each entry passes the request's limits, which both entry points require.
    # am[verifies a-rt-wheel-image-limits-1018@5e612a]
    question = '(sn p so "is" ((arg s (sn c "a")) (arg o $what)))'
    entries = {
        "script": [str(installation / "bin" / "goalchainer"), "snars", *CLI_LIMITS, "ask", "--statement", question,
                   "--json"],
        "skill": [str(python), "-I", "-m", "goal_chainer.omegaclaw_skill", "goalchainer-snars-dispatch",
                  "--request", json.dumps({**LIMITS, "group": "evidence", "operation": "ask", "statement": question})],
    }
    image_env = {**snars_env, "XDG_CACHE_HOME": str(tmp_path / "image-cache")}
    worlds = tmp_path / "image-cache" / "goalchainer" / "snars-worlds"

    # am[verifies a-rt-image-console-main-1017@87159d]
    def entry(name):
        completed = subprocess.run(entries[name], cwd=tmp_path, env=image_env, text=True, capture_output=True)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        cache = sorted((path.name, path.stat().st_mtime_ns) for path in worlds.iterdir())
        return json.loads(completed.stdout)["result"], cache

    compiled, saved = entry("skill")
    assert sorted(Path(name).suffix for name, _ in saved) == [".img", ".json"]
    started, unchanged = entry("script")
    assert unchanged == saved and started == compiled
    protocol = Path(location.strip()).parent / "policy" / "goalchainer_protocol.metta"
    protocol.write_text(protocol.read_text(encoding="utf-8") + "\n; edited in the installation\n", encoding="utf-8")
    _, resaved = entry("script")
    assert set(saved) < set(resaved) and sorted(Path(name).suffix for name, _ in resaved) == [".img", ".img", ".json", ".json"]
    _, last = entry("skill")
    assert last == resaved
