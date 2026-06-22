# DEEP Projects Hackathon Draft

Project name: OmegaClaw GoalChainer

Team email: metta.mestto@gmail.com

Repository:

- Planned primary repo: `https://github.com/MesTTo/OmegaClaw-GoalChainer`
- Existing deontic package: `https://github.com/MesTTo/omegaclaw-deontic`
- Existing OmegaClaw deontic branches: `https://github.com/MesTTo/OmegaClaw-Core`
- Existing PeTTaChainer fork: `https://github.com/MesTTo/PeTTaChainer`

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
3. Score evidence with PeTTaChainer generated-context reasoning when the runtime
   is available.
4. Return a ranked action list with proof-oriented metadata and warnings.

The demo scenario is incident response. Publishing a raw log helps the collective
goal of coordination, but violates an individual privacy goal and a deontic
prohibition. Publishing a redacted summary satisfies the privacy goal, collective
repair goal, and coordination goal, and is therefore recommended.

## Why It Fits The Hackathon

The project is directly about agents understanding individual and collective
goals. It does not treat goals as a single prompt string. It keeps personal,
team, and policy constraints inspectable, then combines them with contextual
evidence.

## Current Prototype

The repo contains:

- a Python scorer for goals, deontic statuses, and evidence projections,
- an optional PeTTaChainer bridge through `contextual_query`,
- a runnable incident-response demo,
- tests for norm resolution, scoring, and PeTTa STV parsing,
- architecture notes and links to the existing OmegaClaw and PeTTaChainer work,
- submodule pins for OmegaClaw-Core, omegaclaw-deontic, and PeTTaChainer.

## Next Milestones

- Replace the small Python deontic resolver with direct `lib_deontic.metta`
  calls from the OmegaClaw deontic branch.
- Feed recommended actions into `lib_directive.metta` as claimable tasks.
- Add a browser or chat UI that shows which individual and collective goals each
  recommendation satisfies.
- Package a short demo video and a reproducible artifact bundle.
