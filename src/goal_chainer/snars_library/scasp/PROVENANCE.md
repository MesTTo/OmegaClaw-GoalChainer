<!--
Purpose: say where the sCASP copy SNARS's guard runs on comes from, what was taken and left, and
under which licence, for the files beside this one.
-->

# sCASP provenance

This directory is s(CASP), the goal-directed answer set programming solver for SWI-Prolog that
the SNARS guard (`../snars/guard.pl`) runs its programs on. The guard loads `prolog/scasp.pl` by a
path relative to itself, and sCASP loads its own modules by paths relative to that file, so
neither engine needs an SWI-Prolog pack.

| | |
|---|---|
| Source | https://github.com/SWI-Prolog/sCASP |
| Commit | `2dfbdb9cb41f8b9198f19289bab73dd72efad46a`, version 1.1.4 |
| Licence | Apache License 2.0, `LICENSE` here, copied verbatim from the source's root |

Taken: the source's `prolog/` directory, `scasp.pl` and `scasp/` with every module they load.

Left in the source: its `main.qlf`, a quick-load file compiled for one SWI-Prolog version, its
command-line program, documentation, examples and tests.

No file here differs from the source. Later changes appear in this repository's history.
