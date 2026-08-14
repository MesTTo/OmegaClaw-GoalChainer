; GoalChainer plugin — goal-aware decision support as OmegaClaw skills.
;
; GoalChainer parses a request into Semantic-Hypergraph propositions, ingests
; them as SNARS evidence, gates the candidate actions through lib_deontic, ranks
; what survives with MetaMo's motivation consensus, and can then execute the
; winner and leak-check the result. This file is the seam: the engine is the
; omegaclaw-goalchainer Python package, reached through py-call, and every
; command below is registered with add-skill so the loop will dispatch it.
;
; Registration is what makes a skill callable. src/loop.metta prechecks each
; parsed command with (HandleError UNKNOWN_SKILL_CALL $s $s), and
; balance_parentheses in src/helper.py raises that for any command whose head is
; not in LLM_COMMANDS -- a set extended only by helper.add_llm_command, which
; add-skill calls. Advertising a command without registering it produces a skill
; the agent is told to use and is then refused when it does.
;
; Requires the deontic plugin (lib_deontic gates the actions) and the
; omegaclaw-goalchainer package on the agent's PYTHONPATH.

(= (loadOmegaClawPlugin)
   (progn
     (log INFO "goalchainer-plugin" "Adding the GoalChainer skills")
     (add-skill goalchainer-decision
        "Decide what to send in an incident using parsed SH evidence, SNARS beliefs and proofs, lib_deontic, and MetaMo"
        (request))
     (add-skill goalchainer-solve
        "Decide AND execute: run the recommended action on the incident data and return the safe, leak-checked deliverable"
        (request))
     (add-skill goalchainer-motivation
        "Reconcile individual vs collective goals with MetaMo's motivation consensus"
        (request))
     (add-skill goalchainer-directive
        "Create and claim an OmegaClaw directive plan from an incident decision"
        (request))
     (add-skill goalchainer-directive-dispatch
        "Inspect or mutate a durable directive plan, or run the dependency demo, from typed JSON"
        (json_request))
     (add-skill goalchainer-snars
        "Run the native SNARS decision summary"
        (request))
     (add-skill goalchainer-snars-dispatch
        "Dispatch evidence, explanation, counterfactual, goal-temporal, or trust-discovery operations from typed JSON"
        (json_request))
     (add-skill goalchainer-thread-dispatch
        "Compile, inspect, route, run, render, or demonstrate MeTTa Markdown thread orchestration from typed JSON"
        (json_request))
     ; The pipeline GoalChainer expects the agent to follow is context, not a
     ; skill the agent has to remember to call for itself.
     (add-prompt-extension goalchainer (goalchainer-system-prompt))
     ()))

; py-call resolves exactly one dot, so the callable surface is the single
; top-level gcskill module rather than goal_chainer.omegaclaw_skill directly.
; Each function returns a short plain string, which the loop feeds back to the
; agent as LAST_SKILL_USE_RESULTS.
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
