; GoalChainer skill extension for OmegaClaw.
;
; Load this module after the GoalChainer Python package is on PYTHONPATH.
; The skill definitions follow the same py-call pattern as technical-analysis.

(= (skill-doc)
   "- Get the GoalChainer system prompt. Keep user input natural, rewrite it internally as structured English propositions, send them to HyperBase, then require native MeTTa/NAL evidence: goalchainer-system-prompt")

(= (skill-doc)
   "- Decide an incident action by chaining individual goals, collective goals, norms, HyperBase propositions, and native MeTTa/NAL evidence: goalchainer-decision request")

(= (skill-doc)
   "- Inspect the PeTTaChainer proof packet and verifier output for a GoalChainer decision: goalchainer-proof-audit request")

(= (skill-doc)
   "- Build COLORE-backed ontology context and HyperBase-ready structured propositions: goalchainer-ontology-context request")

(= (skill-doc)
   "- Regenerate a broken checkout repo, reason over docs/tests/source, patch it, and return fail/pass evidence: goalchainer-codebase-demo request")

(= (skill-doc)
   "- Run GoalChainer verification tests and return collected test names plus pass/fail output: goalchainer-tests request")

(= (skill-doc)
   "- Feed the decision into OmegaClaw lib_directive as a claimable task (forbidden=blocked, obligated=ready), classified by an injected Prolog relation: goalchainer-directive request")

(= (skill-doc)
   "- Reconcile individual vs collective goals with MetaMo's OpenPsi motivation consensus (each owner a subsystem; disagreement-penalized): goalchainer-motivation request")

(= (skill-doc)
   "- Deduce the verdict with SNARS, grounded in the request, returning a Subjective-Logic opinion and proof: goalchainer-snars request")

(= (goalchainer-system-prompt)
   (py-call (goal_chainer.omegaclaw_skill.goalchainer_system_prompt)))

(= (goalchainer-decision $request)
   (py-call (goal_chainer.omegaclaw_skill.goalchainer_decision $request)))

(= (goalchainer-proof-audit $request)
   (py-call (goal_chainer.omegaclaw_skill.goalchainer_proof_audit $request)))

(= (goalchainer-ontology-context $request)
   (py-call (goal_chainer.omegaclaw_skill.goalchainer_ontology_context $request)))

(= (goalchainer-codebase-demo $request)
   (py-call (goal_chainer.omegaclaw_skill.goalchainer_codebase_demo $request)))

(= (goalchainer-tests $request)
   (py-call (goal_chainer.omegaclaw_skill.goalchainer_tests $request)))

(= (goalchainer-directive $request)
   (py-call (goal_chainer.omegaclaw_skill.goalchainer_directive $request)))

(= (goalchainer-motivation $request)
   (py-call (goal_chainer.omegaclaw_skill.goalchainer_motivation $request)))

(= (goalchainer-snars $request)
   (py-call (goal_chainer.omegaclaw_skill.goalchainer_snars $request)))
