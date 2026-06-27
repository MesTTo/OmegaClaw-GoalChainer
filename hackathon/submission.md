# DEEP Projects Hackathon Draft

Project name: OmegaClaw GoalChainer

Team email: metta.mestto@gmail.com

Repository:

- Planned primary repo: `https://github.com/MesTTo/OmegaClaw-GoalChainer`
- Existing deontic package: `https://github.com/MesTTo/omegaclaw-deontic`
- Existing OmegaClaw deontic branches: `https://github.com/MesTTo/OmegaClaw-Core`
- Existing PeTTaChainer fork: `https://github.com/MesTTo/PeTTaChainer`
- Pitch video source: `hackathon/video/`

## Short Description

OmegaClaw GoalChainer is a goal-aware agent decision layer. It ranks actions by
checking individual goals, collective goals, deontic norms, and contextual
evidence before the agent acts.

## Problem

Agents often optimize a task instruction without tracking whose goal is being
served, whose goal is being harmed, and which norms block an otherwise useful
action. The result can look competent while still violating privacy, consent,
dependency order, or collective coordination constraints.

## Solution

GoalChainer adds an explicit decision layer:

1. Read the request into evidence signals (sensitive-data categories present,
   data declared public, facts ready, coordination needed).
2. Project the evidence into a defeasible-deontic theory in pure MeTTa (facts,
   `normally` rules, `must`/`may`/`forbidden`) and run it through OmegaClaw Core's
   `lib_deontic` on PeTTa, reading each action's forbidden / obligated / permitted
   status from the engine's tagged conclusions.
3. Grade how strongly each action is acceptable with a PeTTaChainer PLN contextual
   query on the same runtime, which returns a truth value and a proof.
4. Combine the engine's deontic status with weighted individual and collective
   goal coverage and a fairness floor.
5. Return a ranked action list with the deontic status, the graded belief, and
   warnings.

The decision depends on the request. The same code blocks publishing the raw log
when the logs carry customer emails and order IDs, and recommends publishing it
when the request says the data is public and safe to share, because the risk
grounding drops and the native forbidden expectation falls below the threshold.
When the facts are not ready, holding outranks publishing. `goalchainer validate`
runs this as a differential battery and checks each outcome, so the reasoning is
demonstrably a function of the input rather than a fixed answer.

The demo scenario is incident response. With sensitive data present, publishing a
raw log helps collective coordination but is derived as forbidden and blocked, so
the redacted summary, which covers every required goal, is recommended.

The semantic showcase uses a request with no trigger words at all — "Engineering
wants to dump everything we know about each affected shopper, who they are and how
to reach them, into the public status page." A keyword matcher sees nothing; the
mettabase SH parser plus Ollama-embedding concept matching reads the meaning,
`lib_deontic` forbids the raw log, PeTTaChainer grades the redacted summary, and
the `why` section explains the decision in plain English. A key claim can be
assessed directly with the user's SNARS reasoner (`goalchainer snars`), which
returns a Subjective-Logic opinion `(b,d,u,a)` with a provenance receipt.

The separate codebase demo turns the same idea into an engineering task. It
regenerates a checkout-status repo with a seeded customer-data leak, runs failing
tests, reads the repo policy docs and source code, emits structured propositions
for the conflict, patches the implementation, reruns the tests, and commits the
repair in the generated repo. That gives the video a concrete fail-to-pass
workflow instead of only a decision table.

## Why It Fits The Hackathon

The project is directly about agents understanding individual and collective
goals. It does not treat goals as a single prompt string. It keeps personal,
team, and policy constraints inspectable, then combines them with contextual
evidence.

## Current Prototype

The repo contains:

- a Python scorer for goals, derived deontic status, and evidence projections,
- an evidence layer that reads decision-relevant signals from the request,
- a PeTTa runtime wrapper plus a deontic engine that runs OmegaClaw's real
  `lib_deontic` on PeTTa for the forbidden/obligated/permitted verdict, and
  PeTTaChainer's PLN contextual query for the graded belief with a proof; no
  hyperon binary,
- a directive hookup that feeds the decision into OmegaClaw's `lib_directive` as a
  claimable task (obligated=ready, forbidden=blocked), with the deontic-to-task
  mapping done by a Prolog relation injected into PeTTa and called as MeTTa,
- a `validate` command and test: a differential battery proving the decision
  changes with the input (raw log blocked with PII, recommended when public),
- a COLORE ontology-context skill and HyperBase proposition renderer,
- a generated codebase repair demo with docs, tests, AST evidence, patch diff,
  and fail-to-pass verification,
- a runnable incident-response demo,
- tests for scoring math, evidence extraction, input sensitivity, native MeTTa/NAL
  reasoning, COLORE loading, and HyperBase facts,
- architecture notes and links to the existing OmegaClaw and PeTTaChainer work,
- submodule pins for OmegaClaw-Core, omegaclaw-deontic, and PeTTaChainer.
- a TypeScript pitch-video package with a 3-minute draft, narration script, and
  recording placeholders.

## Pitch Video

The pitch video is prepared under `hackathon/video/`.

The current generated draft is 2:00 and shows:

- the Codex auth path as an OmegaClaw setup improvement,
- the COLORE and HyperBase proposition layer,
- the incident-response goal conflict,
- the ranked GoalChainer action list,
- the PeTTaChainer proof-audit and replay checks,
- a separate codebase repair clip where the agent fixes a regenerated checkout
  status repo from docs, tests, and source evidence,
- placeholders for Ahmad Mesto's voiceover and optional live clips.

The remaining local steps are to review the video, record the voiceover, and
render the clean MP4. Do not upload the video, paste a URL, or click `Update
Deliverables` until Ahmad explicitly approves publishing.

## Next Milestones

- Drive `directive-complete` after the action runs, and recover a plan from
  observed event logs with `lib_directive`'s process-mining.
- Feed recommended actions into `lib_directive.metta` as claimable tasks.
- Add a browser or chat UI that shows which individual and collective goals each
  recommendation satisfies.
- Replace the placeholder video draft with the narrated final MP4 and submit the
  reviewed YouTube URL.
