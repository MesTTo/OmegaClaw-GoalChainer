# Re-architecture: make the GoalChainer decision a function of the input

## Problem (verified)
The incident decision is input-insensitive. Running `demo` with "bake a cake" or
"publish everything publicly, no sensitive data" yields byte-identical output to
the incident default. Causes, all hardcoded:
1. `scenarios.py` fixes goals/norms/actions + engineered `default_strength`.
2. `metta_reasoner.py` maps propositions to premises with fixed truth `(stv 1.0 .9x)`,
   fixed rule truths, and a *predetermined* conclusion term (raises otherwise).
3. `scoring.py` reads a static `Norm` table; `forbidden -> -1.0` dominates.
The native NAL engine is real (verified: Truth_Deduction math, different inputs ->
different stv), but it computes over constants, so the answer never changes.

## Native deontic engine: blocked this round
`lib_deontic.metta` uses `(library OmegaClaw-Core ...)` imports that the plain
hyperon `metta` binary rejects ("import! expects a destination &space and a module
name"). Using it needs OmegaClaw-Core's module-catalog runtime. Out of scope now;
derive deontic status from native `Truth_Expectation` over NAL conclusions instead
(same binary, still real OmegaClaw NAL). Document the blocker.

## Plan
- [x] 1. `evidence.py`: extract `IncidentEvidence` from request
      (sensitive_categories, public_declared, facts_ready, coordination_needed).
- [x] 2. NAL grounding truth derived from evidence (the variable part); norm rules
      stay constant + inspectable (risky->forbidden, protecting->acceptable).
- [x] 3. Reasoner: parse the engine's own conclusion; classify per-action deontic
      status via native `Truth_Expectation` threshold (forbidden/acceptable/permitted).
- [x] 4. `scoring.py`: consume derived deontic status, not the static Norm table.
- [x] 5. `validation.py` + CLI `validate` subcommand + test: differential battery
      proving contrasting inputs -> different decisions (the track's "evidence").
- [x] 6. Update existing tests to the derived behavior; add differential tests.
- [x] 7. Docs + submission: state exactly what is derived vs. constant.
- [x] 8. Verify: pytest (26 passed), jscpd (0 clones), git diff --check (clean),
      validate battery PASS, demo correct on 3 contrasting inputs.

## Acceptance criteria (must hold)
- PII present  -> publish_raw_log blocked (derived forbidden), redacted recommended.
- Public declared, no sensitive data -> raw_log NOT forbidden (permitted/candidate).
- Facts not ready -> hold rises above redacted.
- All three flow through the native NAL engine (real stv in raw_outputs).
- No clones (jscpd 0), full pytest green.
