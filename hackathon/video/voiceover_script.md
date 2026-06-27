# OmegaClaw GoalChainer Voiceover Script

Target length: about 3 minutes.

## 0:00 to 0:16

I am showing OmegaClaw GoalChainer, a decision layer for agents that need to
reason about individual and collective goals before they act.

The demo combines OmegaClaw, the Codex-auth provider branch, PeTTaChainer,
COLORE, and HyperBase-style propositions.

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

The terminal first checks the Codex-auth branch and then starts the decision
loop. The user speaks once in ordinary incident language. After that, Codex
emits OmegaClaw skill commands.

## 1:16 to 1:54

The first skill call is `goalchainer-ontology-context`. It rewrites the incident
as clear structured propositions, emits HyperBase-ready `(hb ...)` facts, and
shows the COLORE ontology slice that can license ordering and relation
composition.

The next call is `goalchainer-decision`. It is the same kind of agent tool
surface as OmegaClaw's other skills: Codex emits a command, the MeTTa skill
delegates to Python through `py-call`, and the result is returned as
`LAST_SKILL_USE_RESULTS`.

Publishing a redacted summary is recommended because it satisfies the privacy
goal, the repair goal, and the coordination goal, and the deontic layer marks it
as obligated.

Holding the update protects privacy, but it misses the required collective goals.
Publishing the raw incident log helps coordination, but it is blocked by the
higher-priority privacy norm.

## 1:54 to 2:30

PeTTaChainer provides the proof-audit side. The decision skill uses
PeTTaChainer contextual evidence, and the audit skill checks the saved forensic
packet.

The important part is replayability. The output shows verifier checks passing,
red-team rejection checks passing, sealed evidence sources, and the portable
audit capsule verification.

## 2:30 to 2:50

The final skill call runs the GoalChainer tests. The tests check deontic
priority handling, conflict reporting, the OmegaClaw skill wrapper, PeTTa STV
parsing, and the incident ranking behavior.

## 2:50 to 3:00

For the hackathon, the point is concrete: the user does not need to know the
formal terms. They ask a normal operational question, and the agent answers with
inspectable goals, norms, evidence, tests, and a replayable proof trail.
