# OmegaClaw GoalChainer orchestration research

## User requirements

- Implement `ai-handoff-full-snars-goalchainer.md`.
- Treat PeTTa execution as authoritative. MeTTa LSP results may contain false positives because the target is PeTTa rather than MeTTaScript.
- Keep the implementation mostly in MeTTa. Use Python for runtime boundaries and APIs only where needed.
- Read the supplied Markdown research files.
- Inspect `/home/user/Dev/oh-my-goals` for reusable goal and orchestration ideas.
- Inspect omegaclaw-deontic, especially its orchestration system.
- Determine whether GoalChainer takes full advantage of omegaclaw-deontic. Fix the integration where it does not.
- Provide live demos that show what GoalChainer can do after the change and how that differs from the prior behavior.
- Incorporate the MeTTa Markdown implementation already present in `/home/user/Dev/mettabase`. Do not create a competing format.
- Consider Kanban and other orchestration views backed by ASP and Clingo through its Python API.
- Compare that option with `/home/user/CalDar`.
- Inspect `/home/user/Dev/MeTTaLingo` and MettaLingua for mixed or multilingual reasoning ideas.
- Inspect the epilog system in `/home/user/Dev/MeTTaSpeak`, with attention to the TypeScript implementation.
- Update OmegaClaw to the latest upstream revision.
- Record ThreadKeeper as a later phase in which MeTTa Markdown becomes an orchestration specification language. Keep that work separate from the current implementation.

## Verified findings so far

- GoalChainer's old directive adapter made a disposable, flat incident plan.
- The old adapter used only `directive-status`, `directive-next`, and `directive-claim`.
- The OmegaClaw directive runtime also implements durable claim, unclaim, complete, block, unblock, dependency gating, boards, summaries, validation, traces, cycle analysis, and process mining.
- GoalChainer's OmegaClaw skill file did not advertise its existing directive bridge.
- The pinned omegaclaw-deontic payload and pinned OmegaClaw-Core directive source were identical before new changes.
- PeTTa is the execution authority. MeTTa LSP findings must be confirmed against PeTTa.
- The pinned deontic baseline passes 10 core suites. The pinned directive baseline passes the directive, inspect, analyze, and mining suites.
- The current directive propagation generator does not connect `blocked-X` to `upstream-blocked-Y`, despite the reference documentation saying `directive-block` cascades through the dependency graph. The existing integration tests do not cover the documented cascade.
- Official OmegaClaw Core main was at `a5d1599` when rechecked on
  2026-07-28. The clean Core pin now merges that fork head, upstream Core
  `b5d0586`, and the non-root propagation correction at `feed652`.
- The clean omegaclaw-deontic pin is `02d019e`, based on current public head
  `bb69eab`. Its directive suite passes all 36 assertions.
- The active `/home/user/Dev/OmegaClaw-Core` PeTTa deployment contains the same upstream merge and propagation fix at `90af295`.
- Mettabase already supplies `md-author-markdown` and the `(md ...)` authoring vocabulary in MeTTa. GoalChainer now invokes that implementation instead of defining another Markdown format.
- CalDar uses Clingo 5.8 with one `Control`, one grounding phase, complete guarded assumptions per solve, and exact literal mapping for multi-shot what-if queries.
- OmegaClaw should remain the task-state authority. A future Clingo layer should optimize capacity or schedules over a frozen Omega snapshot, not derive a second lifecycle board.
- MeTTaLingo uses a language-neutral typed abstract syntax with separate concrete grammars. Stable task IDs can follow that boundary, but its current grammar does not cover incident orchestration.
- MeTTaSpeak's EPILOG corpus targets TypeScript MeTTaScript. It is not a verified PeTTa library and is not directly imported here.
- oh-my-goals confirms the chosen ownership split: MeTTa owns goals, norms, rankings, and lifecycle; the host owns persistence, validated encoding, locks, and process bounds. Its generated lifecycle sequence tests motivated the new Hypothesis boundary tests.
- MeTTa LSP reports unresolved imports for PeTTa's `library OmegaClaw-Core` form and then marks imported directive names unknown. The same adapter passes live PeTTa classification, snapshot, mutation, Markdown, and demo tests.

## Implementation direction under test

- Keep task state, dependency reasoning, lifecycle transitions, boards, summaries, and analysis in MeTTa.
- Use one versioned S-expression protocol at the PeTTa boundary.
- Use Python for safe path handling, file locking, bounded process execution, typed decoding, CLI JSON, and OmegaClaw `py-call`.
- Persist a plan when the caller supplies a `.metta` path. Use a mode-0600 temporary plan otherwise.
- Wrap real action execution with directive claim and complete operations. Block the task when execution fails or produces an unsafe result.
- Add live dependency and lifecycle demos whose outputs are checked before they are presented as evidence.

## Decisions

- Do not add Clingo as a second board engine. Keep a documented optimizer seam for assignment and scheduling constraints.
- Do not claim multilingual orchestration until a controlled incident grammar is implemented and checked against stable MeTTa task meanings.
- Do not import TypeScript EPILOG code into the PeTTa package. Carry its proof identity and ownership ideas into the TypeScript port through a versioned protocol.
- Keep MeTTa LSP diagnostics advisory for PeTTa-only imports. Require a PeTTa execution test for acceptance.
- ThreadKeeper, first committed as `1456256`, was removed on 2026-10-18 with its
  Agent Orchestrator UI and MeTTaScript runtime: upstream GoalChainer never
  carried it, and the operator ruled it removed on that condition.

## Repository safety

- `/home/user/Dev/omegaclaw-deontic` contains widespread user-owned changes. Do not pull, reset, or edit it in place.
- Use clean pinned checkouts under `external/` for updates and implementation.
- The GoalChainer GitHub remote is public. Do not push without explicit approval.
