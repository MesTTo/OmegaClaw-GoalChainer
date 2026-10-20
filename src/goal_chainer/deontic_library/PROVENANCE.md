<!--
Purpose: say where GoalChainer's deontic library comes from, what was taken and left, and under
which licence, for the files beside this one.
-->

# Deontic library provenance

This directory is the defeasible deontic logic library GoalChainer reasons with: `lib_deontic`
for deontic reviews and `lib_directive` for directive orchestration. GoalChainer registers this
directory as the MeTTa library `deontic` on its in-process pymetta engine, so
`(library deontic X)` resolves to `X` here.

| | |
|---|---|
| Source | https://github.com/MesTTo/omegaclaw-deontic |
| Commit | `e5953fd3f908c8c439e1ffb6ca713571dbd0e32b` |
| Licence | MIT, `LICENSE` here, copied verbatim from the source's root |
| Taken | the source's `payload/` paths below, byte for byte, with `payload/` dropped |

Taken, the whole closure of `lib_deontic` and `lib_directive` and the library's core suites:

- `lib_deontic.metta`, `lib_directive.metta`
- `src/deontic/`: the nine reasoning modules and `platform/`, whose `platform.metta` loads the
  eight Prolog kernel files beside it
- `src/directive/`: the four directive modules
- `tests/deontic/`: the ten core suites and their fixtures, which GoalChainer's gate runs

Left in the source, because nothing GoalChainer runs loads them:

- `payload/deontic.metta`, `payload/src/skills_deontic.metta`, `payload/src/policy_guard.metta`:
  the OmegaClaw plugin's entry point and agent skills
- `payload/src/integration/`: bridges to OmegaClaw's `lib_nal` and to `faiss_ffi`
- `payload/tests/bootstrap.metta`, `payload/tests/integration/`, `payload/tests/deontic/run.sh`:
  the OmegaClaw plugin's registration and integration suites, and the PeTTa suite runner
- `payload/docs/`, `payload/examples/`, `payload/README.md`, and the installer, Docker files and
  design notes outside `payload/`

Every file was byte-identical to its source path when it was taken, and GoalChainer changed
these since:

- `explain` is `dl-explain` in `src/deontic/explain.metta`, `src/deontic/trust.metta`,
  `src/directive/cli.metta` and `tests/deontic/test_query.metta`. pymetta 0.9.4 has a builtin
  `explain/1` that answers before the library's definition, so on pymetta the query suite stopped
  after five checks and the trust suite, which folds over the proof tree, at its first. The new
  name runs the same on PeTTa.
- `tests/bootstrap.metta` is GoalChainer's: the source's registered the library on PeTTa from the
  host checkout's working directory, and GoalChainer's test harness registers it instead.

Later changes appear in this repository's history.
