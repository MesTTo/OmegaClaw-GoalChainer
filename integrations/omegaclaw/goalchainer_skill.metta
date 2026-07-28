; GoalChainer as an OmegaClaw Core skill.
;
; OmegaClaw dispatches a skill by (eval $command) over the command the agent emits,
; which py-calls a TWO-part module.function (the same shape as agentverse's
; technical-analysis in src/skills.metta). PeTTa cannot resolve a three-part path, so
; the callable surface is the single top-level `gcskill` module. Load this file into
; OmegaClaw (or via run_in_omegaclaw.metta) so the loop can eval these commands.

(= (goalchainer-decision $request)
   (py-call (gcskill.decision $request)))

(= (goalchainer-solve $request)
   (py-call (gcskill.solve $request)))

(= (goalchainer-motivation $request)
   (py-call (gcskill.motivation $request)))

(= (goalchainer-directive $request)
   (py-call (gcskill.directive $request)))

(= (goalchainer-directive-dispatch $request)
   (py-call (gcskill.directive_dispatch $request)))

(= (goalchainer-snars $request)
   (py-call (gcskill.snars $request)))

(= (goalchainer-snars-dispatch $request)
   (py-call (gcskill.dispatch $request)))

(= (goalchainer-thread-dispatch $request)
   (py-call (gcskill.thread_dispatch $request)))

(= (goalchainer-system-prompt)
   (py-call (gcskill.system_prompt)))

; The skill descriptions to add to OmegaClaw's getSkills, so the agent (the LLM /
; Codex provider) is told these commands exist. Same one-line "- description: name arg"
; form OmegaClaw uses. Typed SH ingestion and native SNARS evidence stay part of
; the contract via goalchainer-system-prompt.
(= (goalchainer-skill-docs)
   ("- Decide what to send in an incident using parsed SH evidence, SNARS beliefs and proofs, lib_deontic, and MetaMo: goalchainer-decision request"
    "- Decide AND execute: run the recommended action on the incident data and return the safe, leak-checked deliverable: goalchainer-solve request"
    "- Reconcile individual vs collective goals with MetaMo's motivation consensus: goalchainer-motivation request"
    "- Create and claim an OmegaClaw directive plan from an incident decision: goalchainer-directive request"
    "- Inspect or mutate a durable directive plan, or run the dependency demo, from typed JSON: goalchainer-directive-dispatch json_request"
    "- Run the native SNARS decision summary: goalchainer-snars request"
    "- Dispatch evidence, explanation, counterfactual, goal-temporal, or trust-discovery operations from typed JSON: goalchainer-snars-dispatch json_request"
    "- Compile, inspect, route, run, render, or demonstrate MeTTa Markdown thread orchestration from typed JSON: goalchainer-thread-dispatch json_request"))
