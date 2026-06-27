# OmegaClaw GoalChainer Voiceover Script

Target length: about 3 minutes.

## 0:00 to 0:16

I am showing OmegaClaw GoalChainer, a decision layer for agents that need to
reason about individual and collective goals before they act.

The demo combines OmegaClaw, the Codex-auth provider branch, and PeTTaChainer.

## 0:16 to 0:42

The scenario is production incident response. A raw log may help the response
team coordinate, but it can expose identifiable user data. A cautious agent has
to balance privacy, service repair, coordination, and the norms that govern each
action.

GoalChainer makes those competing pressures explicit instead of hiding them in a
single prompt.

## 0:42 to 1:16

The Codex provider removes setup friction. OmegaClaw can use the logged-in Codex
subscription path instead of requiring a separate API key for this demo.

The self-test checks provider availability, gets a direct response, and verifies
multi-turn context by remembering the number 42. The recording hides credential
values and only shows whether the auth file contains the expected fields.

## 1:16 to 1:54

The decision layer ranks three actions.

Publishing a redacted summary is recommended because it satisfies the privacy
goal, the repair goal, and the coordination goal, and the deontic layer marks it
as obligated.

Holding the update protects privacy, but it misses the required collective goals.
Publishing the raw incident log helps coordination, but it is blocked by the
higher-priority privacy norm.

## 1:54 to 2:30

PeTTaChainer provides the proof-audit side. The incident proof loads facts,
rules, and distractor trust edges, then proves that CustomerDB should be
isolated and credentials should be rotated.

The important part is replayability. The output includes proof steps,
counterfactual checks, bundle verification, replay verification, and hashes for
the scenario and isolation proof.

## 2:30 to 2:50

This draft has placeholders for the live recordings. I can drop in a short
terminal clip showing the Codex self-test, a clip showing the GoalChainer or
PeTTaChainer run, and the final voiceover.

## 2:50 to 3:00

For the hackathon, the point is concrete: OmegaClaw becomes easier to start with,
and the agent's recommendation comes with inspectable goals, norms, evidence,
and a replayable proof trail.
