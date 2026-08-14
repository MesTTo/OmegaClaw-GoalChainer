#!/usr/bin/env python3
"""Install or remove the GoalChainer plugin on an OmegaClaw-Core clone.

Two operations, kept separate so the result is reversible:

  copy   plugins/goalchainer into <target>/plugins/goalchainer. Every path is
         new on a clean clone, so nothing existing is touched.
  patch  register it by appending one record to config/plugins.yaml, as a
         managed block delimited by sentinel comments, so a re-run replaces it
         in place and uninstall strips it out.

An install writes a receipt (.goalchainer-plugin-receipt.json) listing every
file copied and every patch applied, so uninstall reverts exactly what was done,
restoring the YAML from the snapshot it took rather than un-substituting the
block: stripping text back out cannot know whether the blank line around it was
ours or the file's, and the receipt exists to make the revert byte-exact.

No core file is edited. The plugin registers its skills with add-skill at load
time, which is what puts them in helper.LLM_COMMANDS and so what makes the loop
willing to dispatch them.

The engine itself is the omegaclaw-goalchainer package, which has to be
importable by the agent's Python; this only installs the MeTTa seam.
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
RECEIPT_NAME = ".goalchainer-plugin-receipt.json"
BAK_SUFFIX = ".goalchainer-plugin.bak"

PLUGIN_NAME = "goalchainer"
PLUGIN_DIR = Path("plugins") / PLUGIN_NAME
PLUGINS_YAML = "config/plugins.yaml"
MARKERS = ("lib_omegaclaw.metta", PLUGINS_YAML)

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


def payload_files():
    for src in sorted(p for p in SOURCE.rglob("*") if p.is_file()):
        yield src.relative_to(SOURCE).as_posix(), src


def load_receipt(target):
    p = target / RECEIPT_NAME
    return json.loads(p.read_text()) if p.exists() else None


def do_install(target, force, dry):
    for marker in MARKERS:
        if not (target / marker).exists():
            die(f"{target} does not look like an OmegaClaw-Core clone (missing {marker}).")
    if not SOURCE.is_dir():
        die(f"plugin source missing: {SOURCE}")

    prior = load_receipt(target)
    prior_files = set(prior["copied_files"]) if prior else set()
    files = list(payload_files())

    yaml_text = (target / PLUGINS_YAML).read_text()
    if patch_plugins_yaml(yaml_text) is None:
        die(f"{PLUGINS_YAML}: expected a YAML list of plugin records to append to.")
    for rel, _ in files:
        dst = target / PLUGIN_DIR / rel
        if dst.exists() and rel not in prior_files and not force:
            die(f"refusing to overwrite a file not from a prior install: {PLUGIN_DIR / rel}\n"
                f"  (re-run with --force to overwrite)")

    print(f"goalchainer plugin -> {target}")
    print(f"  copy {len(files)} files into {PLUGIN_DIR}; register in {PLUGINS_YAML}")
    if dry:
        print("  (dry run: nothing written)")
        return

    receipt = {
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "target": str(target),
        "copied_files": [],
        "patched_files": [],
        "backups": [],
    }
    for rel, src in files:
        dst = target / PLUGIN_DIR / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        receipt["copied_files"].append(rel)

    bak = target / (PLUGINS_YAML + BAK_SUFFIX)
    if not bak.exists():
        shutil.copy2(target / PLUGINS_YAML, bak)
    receipt["backups"].append(PLUGINS_YAML + BAK_SUFFIX)
    (target / PLUGINS_YAML).write_text(patch_plugins_yaml(yaml_text))
    receipt["patched_files"].append({"path": PLUGINS_YAML, "kind": "plugin-record"})

    (target / RECEIPT_NAME).write_text(json.dumps(receipt, indent=2))
    print(f"  done. receipt: {target / RECEIPT_NAME}")
    print("  the engine is the omegaclaw-goalchainer package; put it on the agent's PYTHONPATH")


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

    for rel in receipt["copied_files"]:
        f = target / PLUGIN_DIR / rel
        if f.exists():
            f.unlink()
    root = target / PLUGIN_DIR
    for d in sorted({(root / rel).parent for rel in receipt["copied_files"]},
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


def main():
    ap = argparse.ArgumentParser(
        description="Install/remove the GoalChainer plugin on an OmegaClaw-Core clone.")
    ap.add_argument("target", type=Path,
                    help="path to the OmegaClaw-Core clone (the dir with lib_omegaclaw.metta)")
    ap.add_argument("--uninstall", action="store_true", help="revert a previous install")
    ap.add_argument("--force", action="store_true", help="overwrite existing files")
    ap.add_argument("--dry-run", action="store_true", help="show the plan, write nothing")
    args = ap.parse_args()

    target = args.target.resolve()
    if not target.is_dir():
        die(f"target not a directory: {target}")
    if args.uninstall:
        do_uninstall(target, args.dry_run)
    else:
        do_install(target, args.force, args.dry_run)


if __name__ == "__main__":
    main()
