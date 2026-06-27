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

Two extractors produce those signals. The default is keyword matching (offline,
fast). With `GOALCHAINER_SEMANTIC=1`, `semantic_evidence.py` instead parses the
request into Semantic-Hypergraph propositions with the mettabase HyperBase parser,
detects the concepts by embedding similarity against the local Ollama model
(`qwen3-embedding`), and — the part that makes it more than fuzzy keywords — reads
polarity structurally from mettabase's TNF `peel`. Concepts are stated positively,
so a sentence that matches "sensitive" but peels to `negated` ("contains no private
data") votes *public*, and "the facts are not ready" votes *not-ready*. Votes are
tallied across sentences with a privacy-protective tie-break.

This handles the negation that defeats raw-text embeddings, but it is still a
heuristic, not solved: the AlphaBeta parser's own verdict is "treat the edge as
evidence," and its negation detection degrades on long/compound sentences, so ties
and missed negations resolve privacy-protective by design. The robust endpoint is
reasoning over the SH structure with SLN truth and provenance (mettabase's
`sh-rich-reasoning` / SNARS, the LLM-as-System-1, SNARS-as-System-2 design); the
SL opinion `(b,d,u,a)` already attached to each action's evidence is the first
step onto that calculus.

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

The decision then feeds OmegaClaw Core's directive layer. `directive.py` turns the
ranked decision into a `lib_directive` plan: the obligated action is a ready task,
the forbidden action is blocked, a permitted alternative sits in the backlog. It
runs `directive-status` / `directive-next` to schedule the work and
`directive-claim` to claim the recommended task, so the loop closes from a
natural-language request through to a claimed task in OmegaClaw's coordinator.

The deontic-status to task-state mapping is a Prolog relation injected into PeTTa
and used as MeTTa. PeTTa exposes `assertzPredicate` / `Predicate` /
`import_prolog_function`, so `gc_task_state/2` is asserted as Prolog clauses,
registered, and then `(gc_task_state obligated)` returns `ready` from MeTTa. That
is the "inject Prolog, use it as MeTTa" path, doing real work in the pipeline.

A claim can also be reasoned about with SNARS, the user's Subjective-Logic NARS
reasoner in mettabase. `snars_query.py` does two things. `assess` asserts a claim
with `believe!`, queries it with `ask!`, and explains it with `why!`. `derive`
goes further: it believes a two-step inheritance chain (e.g. "publish_raw_log is
risky_action" from the request and "risky_action is forbidden_action" as the norm),
runs SNARS forward deduction (`sn derive!`), and reads back the deduced conclusion
("publish_raw_log is forbidden_action") with a Subjective-Logic opinion `(b,d,u,a)`
and the full proof — both premises with their own opinions. That is calibrated,
provenance-tracked, multi-hop reasoning, the System-2 the architecture aims at,
where a scalar score carries none of it. SNARS runs through mettabase on PeTTa with
cwd at the mettabase root (the kernel resolves data relative to it). Exposed as the
`snars` command. The next step is to feed the request's own parsed SH propositions
in as the premises, so the chain is grounded in what the user actually said.

The further steps are `directive-complete` once the action is executed, plan
recovery from event logs via `lib_directive`'s process-mining, and feeding the
parsed SH propositions into SNARS so the belief layer reasons over the request's
own statements with polarity and provenance.
