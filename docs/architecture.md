# Architecture

GoalChainer is a small orchestration repo rather than a fork of any one runtime.
The prototype has three layers.

The goal layer models individual and collective goals as weighted requirements.
Each action lists the goals it satisfies. The scorer keeps individual and
collective coverage separate, then uses the lower of the two as a fairness floor.
An action cannot hide poor individual-goal support behind a strong collective
score, or the reverse.

The decision depends on the request. An evidence layer (`evidence.py`) reads the
request into four signals: which sensitive-data categories are present, whether
the request declares the data public, whether the facts are ready, and whether
responders need coordination. Everything downstream is a function of those
signals, so a different request produces different premises and a different
ranking. The `validate` command runs a battery of contrasting requests and checks
this: the same code blocks the raw log when sensitive data is present and
recommends it when the request declares the data public.

The deontic status is derived, not declared. The evidence layer fixes the
*grounding* truth (does an action have a property such as `privacy_risky_action`,
and how strongly), while three constant norm rules carry the standing policy
(`risky -> forbidden`, `protecting -> acceptable`, `supporting -> acceptable`).
GoalChainer inlines OmegaClaw Core's `lib_nal.metta`, runs `|-nal` deduction and
same-term revision over the grounded premises, then reads `Truth_Expectation` of
each conclusion. An action is forbidden when its forbidden-conclusion expectation
crosses a threshold (0.6); otherwise it is acceptable or merely permitted. So
removing the sensitive data lowers the risk grounding, drops the forbidden
expectation below the threshold, and the prohibition disappears, all through the
native engine. The runner defines the small `min` and `max` functions that
`Truth_Revision` expects before loading the NAL library. Missing native runtime
files are command failures, not substituted scores.

The standing `oblige`/`permit`/`forbid` table is still kept (`policy_norms`) and
shown next to the derived status as the declared policy, but it no longer decides
the outcome. That keeps the policy inspectable while the decision follows the
evidence.

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
| Defeasible/deontic norms | `external/OmegaClaw-Core`, `external/omegaclaw-deontic` at `bb69eab` | Deontic status derived from native `Truth_Expectation`; the static policy table is display-only |
| Contextual evidence | `/home/user/Dev/OmegaClaw-Core/lib_nal.metta`, `/home/user/Dev/mettabase/hyperbase/.venv/bin/metta` | Native NAL deduction, revision, and `Truth_Expectation` over evidence-grounded premises |
| Proof audit | `external/PeTTaChainer` at `e4db5ca` | Reads sealed showcase artifacts and verifier output for the demo audit skill |
| Ontology and propositions | `/home/user/Dev/mettabase`, `/home/user/Dev/colore` | Read-only COLORE summary plus HyperBase-ready structured proposition facts |
| Codebase repair demo | Generated repo under `artifacts/codebase-demo/` | Reproducible fail-to-pass repair driven by docs, tests, AST evidence, and propositions |

The intended next step is to move the forbidden/obligated/permitted classification
into OmegaClaw Core's `lib_deontic.metta` instead of the `Truth_Expectation`
threshold. That is not wired yet because `lib_deontic.metta` imports
`(library OmegaClaw-Core ...)` modules that the plain hyperon `metta` binary does
not resolve (it reports "import! expects a destination &space and a module name"),
so using it needs OmegaClaw Core's module-catalog runtime. After that, feed the
ranked action back into the OmegaClaw directive layer as a task claim or completion.
