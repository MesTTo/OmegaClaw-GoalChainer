#!/usr/bin/env python3
"""Purpose: install or remove the GoalChainer plugin on an Omega clone, recording the
interpreter its skills run in.

Three operations, kept separate so the result is reversible:

  copy   plugins/goalchainer into <target>/plugins/goalchainer. Every path is
         new on a clean clone, so nothing existing is touched.
  record write <target>/plugins/goalchainer/goalchainer_host.py naming the
         interpreter given with --python, after one skill has run in it, so the
         plugin's skills run GoalChainer as a child of that exact interpreter,
         and the defaults of the plugin's reader settings given with
         --model-cache, --jev-cache, --jev-offline and --jev-url, which Omega's
         configuration overrides at run time.
  patch  register it by appending one record to config/plugins.yaml, as a
         managed block delimited by sentinel comments, so a re-run replaces it
         in place and uninstall strips it out.

An install writes a receipt (.goalchainer-plugin-receipt.json) listing every
file copied or generated and every patch applied, so uninstall reverts exactly what was done,
restoring the YAML from the snapshot it took rather than un-substituting the
block: stripping text back out cannot know whether the blank line around it was
ours or the file's, and the receipt exists to make the revert byte-exact.

No core file is edited. The plugin registers its skills with add-skill at load
time, which is what puts them among the tools the agent's loop offers the LLM
and evaluates when the LLM calls one.

The engine itself is the omegaclaw-goalchainer package in the recorded
interpreter's environment. The agent's own Python only needs the small gcskill
module, which starts that interpreter for each skill.
"""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCE = REPO / "plugins" / "goalchainer"
# The plugin's py-calls reach gcskill, which Omega's MeTTa loader finds because it appends the
# plugin's own directory to sys.path; installed beside goalchainer.metta it lets a stock Omega agent
# start GoalChainer's child with nothing added to the agent's environment. It imports only the
# standard library.
# am[implements a-oc-plugin-ships-gcskill-1018@01ac9e] am[rests-on c-oc-plugin-api-1018@14ec52]
TRANSPORT = REPO / "src" / "gcskill.py"
RECEIPT_NAME = ".goalchainer-plugin-receipt.json"
BAK_SUFFIX = ".goalchainer-plugin.bak"
# A Python module because Omega's loader puts the plugin's directory on sys.path, which reaches it on
# PeTTa and pymetta alike; its name is GoalChainer's own, since every plugin directory shares sys.path.
# am[implements a-oc-plugin-host-module-1018@180dc9] am[rests-on c-oc-petta-import-working-dir-1018@cec2fd]
HOST_FILE = "goalchainer_host.py"

PLUGIN_NAME = "goalchainer"
PLUGIN_DIR = Path("plugins") / PLUGIN_NAME
PLUGINS_YAML = "config/plugins.yaml"
# lib_omega.metta is what Omega's run.metta imports; upstream renamed it from lib_omegaclaw.metta.
# am[implements a-oc-plugin-entry-1018@3f1f44] am[rests-on c-oc-upstream-moved-1018@5d3f58]
MARKERS = ("lib_omega.metta", PLUGINS_YAML)

BEGIN = "# >>> goalchainer (managed; do not edit by hand) >>>"
END = "# <<< goalchainer <<<"
BLOCK_RE = re.compile(r"\n?# >>> goalchainer.*?# <<< goalchainer <<<\n?", re.DOTALL)
PLUGIN_RECORD = (
    f"- name: {PLUGIN_NAME}\n"
    f"  loader: metta\n"
    f'  location: "{{REPO}}/{PLUGIN_DIR.as_posix()}"\n'
)


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def strip_block(text):
    return BLOCK_RE.sub("\n", text)


def patch_plugins_yaml(text):
    """Append the managed plugin record. None if this is not the list of records
    the loader expects."""
    stripped = strip_block(text)
    if not re.search(r"^\s*-\s+name:", stripped, re.MULTILINE):
        return None
    return stripped.rstrip("\n") + f"\n\n{BEGIN}\n{PLUGIN_RECORD}{END}\n"


# am[implements a-oc-plugin-ships-gcskill-1018@01ac9e]
def payload_files():
    """Every file the install copies, as (path under the plugin directory, source): the plugin's own
    files, bytecode caches left by running its suite excepted, then gcskill.py at the plugin
    directory's root."""
    for src in sorted(p for p in SOURCE.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        yield src.relative_to(SOURCE).as_posix(), src
    yield TRANSPORT.name, TRANSPORT


def load_receipt(target):
    p = target / RECEIPT_NAME
    return json.loads(p.read_text()) if p.exists() else None


# One skill runs through the same transport the plugin uses, so an interpreter that cannot run
# GoalChainer, pymetta included, is refused before anything is recorded.
# am[implements a-rt-skill-process-boundary-1016@a36729]
def verified_interpreter(python):
    sys.path.insert(0, str(REPO / "src"))
    import gcskill  # noqa: PLC0415 (the transport lives beside the package it starts)

    resolved = Path(python).expanduser()
    if not resolved.is_absolute() or not resolved.is_file():
        die(f"--python must name an existing interpreter by absolute path, not {python}")
    try:
        gcskill.call(str(resolved), "goalchainer-system-prompt")
    except gcskill.GoalChainerSkillError as error:
        die(f"{resolved} cannot run GoalChainer's skills: {error}")
    return str(resolved)


# The interpreter is a Python string literal the plugin's (goalchainer-python) answers to every skill
# call, and READER the defaults its loadOmegaPlugin configures the reader settings from; repr writes
# literals Python reads back as the same values.
# am[implements a-rt-skill-process-boundary-1016@a36729] am[implements a-oc-plugin-host-module-1018@180dc9]
# am[implements a-irp-reader-keys-1018@14bc18] am[rests-on c-irp-contract-1018@3ed0b0]
def host_source(python, reader):
    return (
        '"""Purpose: name the interpreter GoalChainer\'s skills run in and the defaults of the plugin\'s\n'
        'reader settings, recorded by scripts/install_plugin.py; reinstall the plugin to change them."""\n'
        "\n"
        f"PYTHON = {python!r}\n"
        f"READER = {dict(sorted(reader.items()))!r}\n"
        "\n"
        "\n"
        "def python():\n"
        '    """The recorded interpreter\'s absolute path."""\n'
        "    return PYTHON\n"
        "\n"
        "\n"
        "def reader_default(key):\n"
        '    """The install\'s default for the reader setting `key`, empty when it chose none."""\n'
        '    return READER.get(key, "")\n'
    )


# am[implements a-rt-skill-process-boundary-1016@a36729]
def do_install(target, python, reader, force, dry):
    for marker in MARKERS:
        if not (target / marker).exists():
            die(f"{target} does not look like an Omega clone (missing {marker}).")
    if not SOURCE.is_dir():
        die(f"plugin source missing: {SOURCE}")
    if (SOURCE / HOST_FILE).exists():
        die(f"{SOURCE / HOST_FILE} is generated at install and must not be in the plugin source")

    prior = load_receipt(target)
    prior_files = set(prior["copied_files"]) | set(prior.get("generated_files", [])) if prior else set()
    files = list(payload_files())

    yaml_text = (target / PLUGINS_YAML).read_text()
    if patch_plugins_yaml(yaml_text) is None:
        die(f"{PLUGINS_YAML}: expected a YAML list of plugin records to append to.")
    for rel in [rel for rel, _ in files] + [HOST_FILE]:
        dst = target / PLUGIN_DIR / rel
        if dst.exists() and rel not in prior_files and not force:
            die(f"refusing to overwrite a file not from a prior install: {PLUGIN_DIR / rel}\n"
                f"  (re-run with --force to overwrite)")

    print(f"goalchainer plugin -> {target}")
    print(f"  copy {len(files)} files into {PLUGIN_DIR}; register in {PLUGINS_YAML}")
    print(f"  skills run in {python}")
    for key, value in sorted(reader.items()):
        print(f"  {key} defaults to {value}")
    if dry:
        print("  (dry run: nothing written)")
        return
    python = verified_interpreter(python)

    receipt = {
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "target": str(target),
        "python": python,
        "reader": reader,
        "copied_files": [],
        "generated_files": [],
        "patched_files": [],
        "backups": [],
    }
    for rel, src in files:
        dst = target / PLUGIN_DIR / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        receipt["copied_files"].append(rel)
    (target / PLUGIN_DIR / HOST_FILE).write_text(host_source(python, reader))
    receipt["generated_files"].append(HOST_FILE)

    bak = target / (PLUGINS_YAML + BAK_SUFFIX)
    if not bak.exists():
        shutil.copy2(target / PLUGINS_YAML, bak)
    receipt["backups"].append(PLUGINS_YAML + BAK_SUFFIX)
    (target / PLUGINS_YAML).write_text(patch_plugins_yaml(yaml_text))
    receipt["patched_files"].append({"path": PLUGINS_YAML, "kind": "plugin-record"})

    (target / RECEIPT_NAME).write_text(json.dumps(receipt, indent=2))
    print(f"  done. receipt: {target / RECEIPT_NAME}")


# am[implements a-rt-skill-process-boundary-1016@a36729]
def do_uninstall(target, dry):
    receipt = load_receipt(target)
    if not receipt:
        print(f"no receipt at {target}; stripping the managed block best-effort.")
        if not dry:
            fy = target / PLUGINS_YAML
            if fy.exists():
                fy.write_text(strip_block(fy.read_text()))
            shutil.rmtree(target / PLUGIN_DIR, ignore_errors=True)
        return

    print(f"removing the goalchainer plugin from {target}")
    if dry:
        print(f"  would remove {len(receipt['copied_files'])} files and "
              f"un-patch {len(receipt['patched_files'])} files")
        return

    for entry in receipt["patched_files"]:
        f = target / entry["path"]
        bak = target / (entry["path"] + BAK_SUFFIX)
        if not f.exists():
            continue
        f.write_text(bak.read_text() if bak.exists() else strip_block(f.read_text()))

    installed = receipt["copied_files"] + receipt.get("generated_files", [])
    for rel in installed:
        f = target / PLUGIN_DIR / rel
        if f.exists():
            f.unlink()
    root = target / PLUGIN_DIR
    for d in sorted({(root / rel).parent for rel in installed},
                    key=lambda p: len(p.parts), reverse=True):
        try:
            while d != target and d.is_dir() and not any(d.iterdir()):
                d.rmdir()
                d = d.parent
        except OSError:
            pass

    for name in receipt["backups"]:
        b = target / name
        if b.exists():
            b.unlink()
    (target / RECEIPT_NAME).unlink(missing_ok=True)
    print("  done. clone restored to its pre-install state.")


# am[implements a-rt-skill-process-boundary-1016@a36729]
def main():
    ap = argparse.ArgumentParser(
        description="Install/remove the GoalChainer plugin on an Omega clone.")
    ap.add_argument("target", type=Path,
                    help="path to the Omega clone (the dir with lib_omega.metta)")
    ap.add_argument("--uninstall", action="store_true", help="revert a previous install")
    ap.add_argument("--python",
                    help="absolute path of the interpreter whose environment holds GoalChainer; "
                         "required to install")
    # One flag per reader setting, named for its Omega configuration key; a deployment such as the
    # image records its paths here, and a checkout install records none.
    # am[implements a-irp-reader-keys-1018@14bc18]
    for flag, key, meaning in (("--model-cache", "goalchainerModelCache", "the provisioned cross-encoder's model cache"),
                               ("--jev-cache", "goalchainerJevCache", "the Jev answer cache"),
                               ("--jev-offline", "goalchainerJevOffline", "1 to answer from the Jev cache alone, 0 to ask Jev"),
                               ("--jev-url", "goalchainerJevUrl", "the Jev endpoint, such as a gateway route")):
        ap.add_argument(flag, dest=key, metavar="VALUE", help=f"default of {key}: {meaning}")
    ap.add_argument("--force", action="store_true", help="overwrite existing files")
    ap.add_argument("--dry-run", action="store_true", help="show the plan, write nothing")
    args = ap.parse_args()

    target = args.target.resolve()
    if not target.is_dir():
        die(f"target not a directory: {target}")
    if args.uninstall:
        do_uninstall(target, args.dry_run)
    else:
        if not args.python:
            die("--python is required to install: the interpreter GoalChainer's skills run in")
        do_install(target, args.python, reader_defaults(args), args.force, args.dry_run)


# Each given setting, checked as the plugin will check it at load, so a malformed default is refused
# before anything is written.
# am[implements a-irp-reader-keys-1018@14bc18]
def reader_defaults(args):
    sys.path.insert(0, str(REPO / "src"))
    import gcskill  # noqa: PLC0415 (the transport lives beside the package it starts)

    reader = {key: getattr(args, key) for key, _ in gcskill.READER_VARIABLES if getattr(args, key) is not None}
    try:
        return {key: gcskill.reader_setting(key, value) for key, value in reader.items()}
    except ValueError as error:
        die(str(error))


if __name__ == "__main__":
    main()
