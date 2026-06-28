# OmegaClaw GoalChainer

GoalChainer is a goal-aware decision layer for agents. It takes a messy
natural-language request, reasons about who the action helps, who it harms, which
norms apply, and how strongly each option is believed acceptable, and returns a
ranked decision with a proof and a claimable task.

Everything runs on **PeTTa** (MeTTa compiled to SWI-Prolog). The reasoning is not
Python heuristics; it composes real OmegaClaw and mettabase systems, each running
as MeTTa or Prolog on PeTTa:

| Layer | System | What it does |
|---|---|---|
| Perception | mettabase HyperBase parser + Ollama embeddings | natural language to Semantic-Hypergraph propositions; concept detection with TNF polarity |
| Norms | OmegaClaw-Core `lib_deontic` | forbidden / obligated / permitted, by defeasible logic + Standard Deontic Logic |
| Belief | PeTTaChainer | PLN contextual query for how acceptable each action is, with a proof |
| Reasoning | SNARS | Subjective-Logic NARS deduction of the verdict, grounded in the request, with provenance |
| Motivation | MetaMo (OpenPsi/MAGUS) | individual and collective goals as competing motivation subsystems, reconciled by a disagreement-penalized consensus |
| Coordination | OmegaClaw-Core `lib_directive` | the chosen action becomes a claimable task; a Prolog relation maps the deontic status to the task state |
| Decision | `gc_score.pl` on PeTTa | the combined score is a Prolog relation, gated by the deontic verdict |

The demo scenario is incident response. A service is down. Engineers want to share
raw logs that may contain customer emails, order IDs, or payloads. The decision is
to publish a redacted summary, not raw logs, and to hold external updates while the
facts are not ready. The point is that GoalChainer derives that, input by input,
rather than replaying a fixed answer: change the request and the verdict changes.

## What it produces

```
$ goalchainer demo
recommended  0.987  Publish redacted summary
   blocked  -1.000  Publish raw incident log

individual vs collective goals (MetaMo motivation consensus)
  individual goals pull toward: publish_redacted_summary
  collective goals pull toward: publish_raw_log
  reconciled consensus:         publish_redacted_summary

why
Recommended: Publish redacted summary (score 0.987).
  lib_deontic derived this action obligated. PeTTaChainer belief b=0.91, d=0.06, u=0.02.
Blocked: Publish raw incident log (score -1.000).
  lib_deontic derived this action forbidden, so the score is forced negative.
```

## Use it

As a CLI:

```bash
PYTHONPATH=src python3 -m goal_chainer.cli demo            # full decision + why + motivation
PYTHONPATH=src python3 -m goal_chainer.cli solve           # decide AND execute: the safe deliverable, leak-checked
PYTHONPATH=src python3 -m goal_chainer.cli motivation      # individual vs collective consensus (MetaMo)
PYTHONPATH=src python3 -m goal_chainer.cli snars           # deduce the verdict with SNARS (opinion + proof)
PYTHONPATH=src python3 -m goal_chainer.cli directive       # turn the decision into a claimable task
PYTHONPATH=src python3 -m goal_chainer.cli validate        # differential battery: the decision depends on the input
```

`solve` goes past the recommendation. It takes the actual raw incident log (customer
emails, order IDs, tokens, traces), runs the recommended action, and returns the
artifact you would really send, with a leak check proving every sensitive value is
gone:

```
$ goalchainer solve
decided: Publish redacted summary (recommended)
channel: external
safe deliverable:
  diagnostics: { customer_email: [redacted], order_id: [redacted],
                 access_token: [redacted], stack_trace: [redacted],
                 error_code: PAYMENT_TIMEOUT }
leak check: safe=True leaked=[]
```

As an OmegaClaw skill (the agent tool surface, `integrations/omegaclaw/goalchainer_skill.metta`):

```
(goalchainer-decision   "request")   ; ranked decision + English why + motivation summary + release plan
(goalchainer-motivation "request")   ; MetaMo individual/collective consensus
(goalchainer-snars      "request")   ; SNARS deduction grounded in the request
(goalchainer-directive  "request")   ; lib_directive task (obligated=ready, forbidden=blocked)
(goalchainer-system-prompt)          ; the structured-English pipeline contract
```

The semantic perception path (real SH parse + Ollama embeddings) is opt-in with
`GOALCHAINER_SEMANTIC=1`; the default is keyword matching so the test suite runs
offline. The reasoning layers need the PeTTa runtime and the vendored systems under
`external/`:

```bash
git submodule update --init --recursive
```

Runtime paths are configurable by environment variable (`GOALCHAINER_PETTA_DIR`,
`GOALCHAINER_PETTA_SWIPL`, `GOALCHAINER_METABASE_DIR`, `GOALCHAINER_METAMO_DIR`,
`GOALCHAINER_OLLAMA_URL`).

## Repo layout

- `src/goal_chainer/` the orchestration: evidence, the PeTTa runtime bridge, the
  deontic engine, PeTTaChainer belief, SNARS query, MetaMo motivation, the directive
  hookup, scoring, and the OmegaClaw skill bridge.
- `integrations/prolog/` the Prolog files loaded into PeTTa.
- `integrations/omegaclaw/` the `.metta` skill surface.
- `external/` the vendored systems (OmegaClaw-Core, PeTTaChainer, omegaclaw-deontic,
  MetaMo) as submodules.
- `docs/architecture.md` how the layers fit together.
- `hackathon/` the submission copy and pitch-video package.
- `tests/` offline unit tests plus guarded integration tests that exercise the live
  PeTTa/Ollama/SNARS/MetaMo path when the runtime is present.

## Links

- OmegaClaw-Core fork: <https://github.com/MesTTo/OmegaClaw-Core>
- PeTTaChainer fork: <https://github.com/MesTTo/PeTTaChainer>
- Standalone deontic package: <https://github.com/MesTTo/omegaclaw-deontic>
- Hackathon page: <https://deep-projects.ai/hackathon/ai-agents-that-understand-our-individual-and-collective-goals/>
