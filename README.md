# OmegaClaw GoalChainer

GoalChainer turns a natural-language request into a ranked action with evidence,
proofs, goals, and a normative verdict. Native mode uses Mettabase SNARS as the
graded-belief system. The MeTTa programs run through PeTTa on SWI-Prolog.

The incident example distinguishes three cases:

- Private logs block raw publication.
- Explicitly public logs make raw publication permissible.
- Unverified facts add a required verification goal and rank holding first.

## Runtime layers

| Layer | Owner | Role |
| --- | --- | --- |
| Parsing | Mettabase AlphaBeta and HyperBase | Text to typed SH trees with source metadata |
| Belief | Mettabase SNARS | Evidence cells, opinions, receipts, proofs, trust, time, and counterfactuals |
| Norms | OmegaClaw-Core `lib_deontic` | Forbidden, obligated, and permitted verdicts |
| Preference | MetaMo | Individual and collective goal consensus |
| Scoring | `goalchainer_score.metta` | Native expectation, goal preference, obligation priority, stable order, and ties |
| Coordination | OmegaClaw-Core `lib_directive` | Dependencies, boards, assignment, lifecycle, validation, and analysis |
| Host | GoalChainer Python | Dependency resolution, typed transport, SQLite replay, process control, CLI, and skills |

PeTTa execution is authoritative. MeTTa LSP diagnostics can report syntax or type
problems that do not apply to PeTTa. The test suite confirms disputed diagnostics
with the pinned PeTTa runner.

PeTTaChainer remains available for the explicitly labelled offline path and the
older proof-audit demonstration. A PeTTaChainer STV is never presented as native
SNARS evidence.

## Set up

Fetch the pinned repositories:

```bash
git submodule update --init --recursive
```

Native execution resolves dependencies in this order:

```text
explicit constructor path
GOALCHAINER_METTABASE_DIR
external/mettabase
/home/user/Dev/mettabase
```

Configure PeTTa and SWI when they are outside the development defaults:

```bash
export GOALCHAINER_PETTA_DIR=/path/to/PeTTa
export GOALCHAINER_PETTA_SWIPL=/path/to/swipl
```

The AlphaBeta parser needs its NLP environment. If those packages are not
installed in the Python process that launches GoalChainer, set the parser
interpreter explicitly:

```bash
export GOALCHAINER_METTABASE_PYTHON=/path/to/mettabase/hyperbase/.venv/bin/python
```

GoalChainer sends request data to that process over standard input as JSON. It
does not place the request in command arguments or interpolate it into MeTTa
source.

## Make a decision

Native mode is the default:

```bash
PYTHONPATH=src python3 -m goal_chainer.cli demo \
  --request "Raw logs include customer emails. Engineering needs the incident room."
```

The JSON response retains the native opinion, raw evidence counts, receipts,
source trust, proof trees, conflict degree, deontic status, goal scores, final
formula, and counterfactual rollback digest:

```bash
PYTHONPATH=src python3 -m goal_chainer.cli demo --json
```

`solve` executes the selected action, checks the outgoing artifact for leaks, and
records the observed result through SNARS:

```bash
PYTHONPATH=src python3 -m goal_chainer.cli solve --json
```

Give `solve` a plan path to retain the claim, completion, or failure block as a
mode-0600 MeTTa audit log:

```bash
PYTHONPATH=src python3 -m goal_chainer.cli solve \
  --plan ./incident-plan.metta \
  --json
```

Use offline mode only when native dependencies are intentionally unavailable:

```bash
PYTHONPATH=src python3 -m goal_chainer.cli demo --mode offline --json
```

Offline output contains `"mode": "offline"` and
`"native_snars_ran": false`. Native failures do not switch to offline mode.
They return a structured error and a nonzero exit status.

## SNARS commands

`goalchainer snars` is the decision summary. The same command has focused
operations:

```bash
goalchainer snars assess --request "Logs are public."
goalchainer snars ask --request "" --statement '(sn p so "is" ((arg s (sn c "a")) (arg o $what)))'
goalchainer snars prove --request "" --statement '(sn p so "is" ((arg s (sn c "a")) (arg o (sn c "b"))))'
goalchainer snars explain --request "" --statement '(sn p so "is" ((arg s (sn c "a")) (arg o (sn c "b"))))'
goalchainer snars why-not --request "" --statement '(sn p so "is" ((arg s (sn c "a")) (arg o (sn c "b"))))'
goalchainer snars discover --request "" --statement '(sn p so "is" ((arg s $x) (arg o $y)))'
goalchainer snars goal --request "" --statement '(sn p so "goal" ((arg s (sn c "agent")) (arg o (sn c "safe"))))'
goalchainer snars subgoals --request "" --statement '(sn p so "goal" ((arg s (sn c "agent")) (arg o (sn c "safe"))))'
goalchainer snars what-if --request "" --hypothesis '(sn p so "is" ((arg s (sn c "logs")) (arg o (sn c "public"))))' --query '(sn p so "is" ((arg s (sn c "raw")) (arg o (sn c "acceptable"))))'
goalchainer snars temporal --request "" --statement '(sn p so "is" ((arg s (sn c "a")) (arg o (sn c "b"))))' --now 10
goalchainer snars trust --request ""
goalchainer snars mine --request "" --minimum-support 2
goalchainer snars inspect --request ""
goalchainer snars truth --request "" --statement '(sn p so "is" ((arg s (sn c "a")) (arg o (sn c "b"))))'
goalchainer snars control --request "" --budget 8
goalchainer snars structural --request ""
goalchainer snars transform --request "" --transform-kind marginal --statement '(sn p so "is" ((arg s (sn c "a")) (arg o (sn c "b"))))' --base-rate 0.7
goalchainer snars compiled-prove --request "" --statement '(sn p so "is" ((arg s (sn c "a")) (arg o (sn c "b"))))'
goalchainer snars guard --request "" --guard-rule 'safe(redacted).' --guard-goal 'safe(redacted)'
```

Pass `--database path/to/snars.sqlite3` to opt into persistent state. Without it,
the command uses an in-memory session.

## OmegaClaw

The MeTTa skill keeps PeTTa's two-part Python call restriction:

```metta
(goalchainer-decision "request")
(goalchainer-solve "request")
(goalchainer-directive "request")
(goalchainer-directive-dispatch
  "{\"operation\":\"status\",\"plan\":\"/path/to/incident.metta\"}")
(goalchainer-snars "request")
(goalchainer-snars-dispatch
  "{\"group\":\"trust-discovery\",\"operation\":\"inspect\"}")
```

The directive dispatcher supports snapshot, status, next, board, summary, info,
assignments, Markdown, validation, analysis, trace, task-state, claim, unclaim,
complete, block, unblock, and demo operations. Each mutation runs through
OmegaClaw's append-only MeTTa lifecycle.

Run the checked orchestration demo:

```bash
PYTHONPATH=src python3 -m goal_chainer.cli directive demo
```

The demo blocks a root task, checks the transitive `upstream-blocked` cascade,
unblocks it, then claims and completes all three tasks in dependency order. See
[directive orchestration](docs/directive-orchestration.md) for the exact output
and the differences from the earlier bridge.

The dispatcher accepts these groups:

- `decision`
- `evidence`
- `explanation`
- `counterfactual`
- `goal-temporal`
- `trust-discovery`

Unknown fields and group-operation mismatches are rejected before a PeTTa process
starts.

## Persistence and migration

[SNARS persistence and privacy](docs/snars-persistence.md) describes database
permissions, redaction, retention, replay, and deletion.

[SNARS migration and rollback](docs/snars-migration.md) describes the change from
projected PeTTaChainer STVs to native opinions, along with the explicit offline
rollback.

## Repository layout

- `integrations/snars/` contains the GoalChainer policy, protocol, and scorer in MeTTa.
- `integrations/directive/` contains the versioned PeTTa directive adapter in MeTTa.
- `src/goal_chainer/snars_*.py` contains typed host orchestration.
- `src/goal_chainer/directive*.py` contains the safe plan and transport boundary.
- `integrations/omegaclaw/` contains the two-part skill surface.
- `external/mettabase` pins the SNARS implementation.
- `tests/test_snars_native_integration.py` is the non-skipped PeTTa acceptance path.
- `docs/architecture.md` records component ownership and execution flow.
