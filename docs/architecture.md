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

Everything runs on the PeTTa runtime (MeTTa compiled to SWI-Prolog), which is the
runtime OmegaClaw targets; there is no hyperon binary. `petta_runtime.py` drives
`PeTTa/src/main.pl` with `--silent`, so stdout carries only the result of each
`!(...)` form.

The deontic status comes from OmegaClaw Core's real `lib_deontic` on PeTTa, not
from a heuristic. `deontic_engine.py` projects the evidence into a defeasible
theory in pure MeTTa: facts (`(given (risky publish_raw_log))`), defeasible
`normally` rules, and deontic operators `must` / `may` / `forbidden`. It runs the
theory through `(library OmegaClaw-Core lib_deontic)` with `dl-run-deontic`, then
reads each action's forbidden / obligated / permitted status straight off the
tagged conclusion set (`(pd (lit pos F none publish_raw_log ()))`). Remove the
sensitive data and the risk fact leaves the theory, so the engine stops forbidding
the raw log. When facts are not ready, holding becomes obligated.

The graded belief comes from PeTTaChainer on the same runtime. `evidence_chainer.py`
projects the evidence into PLN statements (facts plus implication rules with truth
values), `compileadd`s them to a KB, and runs PeTTaChainer's contextual `query` for
`(Acceptable <action>)`. The answer is a PLN truth value with a proof term (a
`merge/revision` over the contributing rules); that strength feeds the score. So
the normative verdict (lib_deontic) and the graded belief (PeTTaChainer) are two of
the user's MeTTa systems combined, both on PeTTa, driven through the same wrapper.

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
| Defeasible/deontic norms | `OmegaClaw-Core lib_deontic` on PeTTa | Forbidden/obligated/permitted read from the real engine's tagged conclusions; the static policy table is display-only |
| Contextual evidence | PeTTaChainer PLN on PeTTa (`/home/user/Dev/PeTTaChainer`) | Contextual query grades each action's acceptability belief with a proof |
| Runtime | PeTTa (`PeTTa/src/main.pl`, swipl 9.3.x) | All MeTTa runs here; no hyperon binary |
| Proof audit | `external/PeTTaChainer` at `e4db5ca` | Reads sealed showcase artifacts and verifier output for the demo audit skill |
| Ontology and propositions | `/home/user/Dev/mettabase`, `/home/user/Dev/colore` | Read-only COLORE summary plus HyperBase-ready structured proposition facts |
| Codebase repair demo | Generated repo under `artifacts/codebase-demo/` | Reproducible fail-to-pass repair driven by docs, tests, AST evidence, and propositions |

The next step is to feed the ranked action back into the OmegaClaw directive layer
(`lib_directive`) as a task claim or completion, and to let Prolog-injected
primitives (`register_fun`) expose any custom scoring step as MeTTa.
