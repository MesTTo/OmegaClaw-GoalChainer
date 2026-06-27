# Incorporating MetaMo as the motivation layer

MetaMo (iCog-Labs-Dev/MetaMo) is a MeTTa motivation system integrating MAGUS and
OpenPsi. This plans how GoalChainer adopts it to model individual and collective
goals as competing motivation subsystems, with `lib_deontic` as the hard gate and
SNARS supplying calibrated risk.

## It runs on PeTTa (proven)

- MetaMo's own CI is named **"Run MeTTa tests with PeTTa"** and installs PeTTa to
  run the `.metta` tests (`.github/workflows/metta-tests.yml`).
- Confirmed locally: running `core/tests/state_tests.metta` through
  `swipl -s PeTTa/src/main.pl` passes (`✅` on every `(test ...)`).

So MetaMo drives through the same `petta_runtime` path as `lib_deontic`,
PeTTaChainer, and SNARS. It ships an `openpsi/` module (appraisal, feeling) that
its states import.

## Why it fits: subsystems = goal owners

MetaMo's model:

- `MotivationalState = (motivation goals modulators)` — a goal-value vector plus
  OpenPsi modulators.
- `action = (action id goalCorrelations riskEstimate deltaG)` — an action's
  correlation with each goal, its risk, and the goal-satisfaction delta it yields.
- `dynamics/` evolves the state with damping, boundary-stabilization, and
  projection for stability (a category-theoretic pseudo-bimonad).

The research-assistant application runs **several subsystems at once** (Curiosity,
Ethics), each its own `(motivation …)` state proposing an action, then combines
them in `runMetaMoCycleDefault`. That is exactly the individual-vs-collective
structure GoalChainer needs: each goal owner is a subsystem.

| GoalChainer today | MetaMo mapping |
|---|---|
| `preserve_privacy` (owner ava, individual) | an **individual** subsystem; goals vector weights privacy |
| `restore_service` + `coordinate_team` (collective) | a **collective** subsystem; goals vector weights repair/coordination |
| an action's `satisfies` tuple | the action's `goalCorrelations` (per-goal correlation) |
| evidence strength / deontic risk | the action's `riskEstimate` |
| weighted goal coverage (static) | MetaMo's risk-aware selection over a dynamical state |

The static weighted-coverage score becomes a real motivation dynamics: each owner's
subsystem prefers the action that best advances its goals net of risk, and the
final choice balances the subsystems — with `lib_deontic` excluding any forbidden
action before motivation runs, and SNARS providing the risk/belief grounding.

## Phased plan

1. **Vendor + smoke-test.** Add MetaMo (and its `openpsi/`) under `external/MetaMo`
   (submodule). A GoalChainer driver imports `core/config` and runs one
   `runMetaMoCycleDefault` step on a toy state via `petta_runtime`, asserting it
   returns an action. Gate: green on PeTTa.

2. **`motivation.py` bridge.** From a `GoalScenario`, build:
   - one `MotivationalState` per goal owner (individual vs collective), goals
     vector from the owner's goal weights, modulators from incident posture
     (urgency from the outage, caution from privacy-at-stake);
   - each `CandidateAction` as `(action id goalCorrelations riskEstimate deltaG)`:
     `goalCorrelations` from `satisfies` (+1 advances, −1 harms, e.g. raw log
     harms privacy), `riskEstimate` from the SNARS/`lib_deontic` risk, `deltaG`
     from the net goal delta.
   Run the MetaMo cycle on PeTTa, parse each subsystem's proposed action and the
   combined selection.

3. **Fold into the decision.** Replace `_weighted_coverage` in `scoring.py` with the
   MetaMo motivation score (per-subsystem preference + combination), keeping the
   individual/collective split and the fairness floor as a cross-check. Order of
   precedence stays: `lib_deontic` hard gate → motivation preference → tie-breaks.
   Decision payload gains a `motivation` section: each owner-subsystem's wanted
   action and the combined choice, so "whose goal is served/harmed" is explicit.

4. **Surface + verify.** A `motivation` CLI/skill view ("the privacy subsystem
   wants hold; the repair subsystem wants raw log; the gated, balanced choice is
   redacted summary"). Guarded tests (skip without PeTTa). Differential check: the
   subsystem preferences and the combined choice change with the request, like the
   existing `validate` battery.

## Risks and open questions

- **Vector alignment.** MetaMo goals/modulators are positional vectors; GoalChainer
  must fix a stable goal ordering and modulator count (the state test used 4 goals,
  5 modulators). Encode this once in the bridge.
- **`riskEstimate` source.** Cleanest is the SNARS-derived forbidden expectation or
  the PeTTaChainer disbelief mass; pick one and document it.
- **Dynamics vs one-shot.** GoalChainer makes a single decision; MetaMo is a
  dynamical system. Start with a one-step cycle (appraise → evaluate → select); the
  multi-step urge dynamics (damping/stability across a session) is a later upgrade.
- **Deontic precedence.** MetaMo could, untamed, prefer a forbidden action on raw
  goal grounds. The gate must run first: filter forbidden actions out of the action
  set before the motivation cycle, never after.

## What this buys

It turns "individual and collective goals" from static weights into the user's own
OpenPsi motivation model: goal owners as subsystems with urges, risk-aware
selection, and stability — the deepest answer to the hackathon theme, on PeTTa,
composed with the deontic gate and SNARS that are already wired.
