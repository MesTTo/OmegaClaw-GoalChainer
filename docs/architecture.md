# Architecture

GoalChainer is a small orchestration repo rather than a fork of any one runtime.
The prototype has three layers.

The goal layer models individual and collective goals as weighted requirements.
Each action lists the goals it satisfies. The scorer keeps individual and
collective coverage separate, then uses the lower of the two as a fairness floor.
An action cannot hide poor individual-goal support behind a strong collective
score, or the reverse.

The deontic layer mirrors the vocabulary used by the OmegaClaw deontic branch:
`oblige`, `permit`, and `forbid`, each with a priority. A higher-priority
prohibition blocks an action. Equal-priority permit/forbid disagreement is
reported as a conflict instead of being silently averaged away.

The evidence layer uses the native MeTTa runtime. GoalChainer projects
HyperBase propositions into NAL premises, inlines OmegaClaw Core's
`lib_nal.metta`, and calls `|-nal` for deduction and same-term revision. The
runner defines the small `min` and `max` functions that `Truth_Revision` expects
before loading the NAL library. Missing native runtime files are command
failures, not substituted scores.

The ontology and proposition layer sits before the decision payload. It reads the
local mettabase COLORE fixture when present and exposes selected axioms as named
projection licenses. The first useful slice is `timepoints/lp_ordering/a1`,
which licenses transitive `before` ordering, plus kinship composition examples
that show COLORE definitions can become goal-directed relation rules. The same
payload renders incident facts as HyperBase-style `(hb ...)` facts and typed
`(sh ...)` trees. Those propositions are then projected into the native NAL
premises that drive action evidence.

The generated codebase demo adds a repair loop around those pieces. It creates a
fresh local checkout-status repo, commits the seeded bug, runs the repo's tests,
extracts the policy contract from Markdown, inspects `build_customer_update`
with Python AST, and turns the docs/test/source conflict into structured
propositions. The repair is synthesized from the extracted contract: restricted
fields are redacted before the external update, and only allowed diagnostics are
kept. The demo then reruns tests and commits the fix in the generated repo, so a
screen recording can show a concrete fail-to-pass engineering task rather than a
static explanation.

This is how the pieces line up with the existing repos:

| Concern | Source repo | Current use |
| --- | --- | --- |
| Agent loop and long-term memory | `external/OmegaClaw-Core` at `fb5afb6` | Target integration point after the prototype is stable |
| Defeasible/deontic norms | `external/OmegaClaw-Core`, `external/omegaclaw-deontic` at `bb69eab` | Mirrored in the Python resolver, with branch links in the submission |
| Contextual evidence | `/home/user/Dev/OmegaClaw-Core/lib_nal.metta`, `/home/user/Dev/mettabase/hyperbase/.venv/bin/metta` | Required native NAL deduction and revision over HyperBase-derived premises |
| Proof audit | `external/PeTTaChainer` at `e4db5ca` | Reads sealed showcase artifacts and verifier output for the demo audit skill |
| Ontology and propositions | `/home/user/Dev/mettabase`, `/home/user/Dev/colore` | Read-only COLORE summary plus HyperBase-ready structured proposition facts |
| Codebase repair demo | Generated repo under `artifacts/codebase-demo/` | Reproducible fail-to-pass repair driven by docs, tests, AST evidence, and propositions |

The intended next step is to replace the small Python norm resolver with calls
into `lib_deontic.metta` and to feed the ranked action back into the OmegaClaw
directive layer as a task claim or completion.
