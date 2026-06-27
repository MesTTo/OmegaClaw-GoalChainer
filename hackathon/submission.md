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

1. Represent individual and collective goals as weighted requirements.
2. Resolve obligations, permissions, prohibitions, and norm conflicts.
3. Ground the request as clear HyperBase-ready propositions and COLORE ontology
   context.
4. Project those propositions into native OmegaClaw NAL premises and run
   MeTTa/NAL deduction plus revision for action evidence.
5. Return a ranked action list with proof-oriented metadata and warnings.

The demo scenario is incident response. Publishing a raw log helps the collective
goal of coordination, but violates an individual privacy goal and a deontic
prohibition. Publishing a redacted summary satisfies the privacy goal, collective
repair goal, and coordination goal, and is therefore recommended.

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

- a Python scorer for goals, deontic statuses, and evidence projections,
- a native MeTTa/NAL evidence bridge over HyperBase-derived propositions,
- a COLORE ontology-context skill and HyperBase proposition renderer,
- a generated codebase repair demo with docs, tests, AST evidence, patch diff,
  and fail-to-pass verification,
- a runnable incident-response demo,
- tests for norm resolution, scoring, PeTTa STV parsing, native MeTTa/NAL
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

- Replace the small Python deontic resolver with direct `lib_deontic.metta`
  calls from the OmegaClaw deontic branch.
- Feed recommended actions into `lib_directive.metta` as claimable tasks.
- Add a browser or chat UI that shows which individual and collective goals each
  recommendation satisfies.
- Replace the placeholder video draft with the narrated final MP4 and submit the
  reviewed YouTube URL.
