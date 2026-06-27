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

(= (goalchainer-snars $request)
   (py-call (gcskill.snars $request)))

(= (goalchainer-system-prompt)
   (py-call (gcskill.system_prompt)))

; The skill descriptions to add to OmegaClaw's getSkills, so the agent (the LLM /
; Codex provider) is told these commands exist. Same one-line "- description: name arg"
; form OmegaClaw uses. The structured English propositions and native MeTTa/NAL
; evidence path stay part of the contract via goalchainer-system-prompt.
(= (goalchainer-skill-docs)
   ("- Decide what to send in an incident, weighing individual and collective goals, norms (lib_deontic), belief (PeTTaChainer), and motivation (MetaMo); returns a ranked decision with a proof: goalchainer-decision request"
    "- Decide AND execute: run the recommended action on the incident data and return the safe, leak-checked deliverable: goalchainer-solve request"
    "- Reconcile individual vs collective goals with MetaMo's motivation consensus: goalchainer-motivation request"
    "- Deduce the verdict with SNARS, returning a Subjective-Logic opinion with provenance: goalchainer-snars request"))
