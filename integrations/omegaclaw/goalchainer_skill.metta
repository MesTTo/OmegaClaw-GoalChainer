; GoalChainer skill extension for OmegaClaw.
;
; Load this module after the GoalChainer Python package is on PYTHONPATH.
; The skill definitions follow the same py-call pattern as technical-analysis.

(= (skill-doc)
   "- Decide an incident action by chaining individual goals, collective goals, norms, and PeTTa evidence: goalchainer-decision request")

(= (skill-doc)
   "- Inspect the PeTTaChainer proof packet and verifier output for a GoalChainer decision: goalchainer-proof-audit request")

(= (skill-doc)
   "- Build COLORE-backed ontology context and HyperBase-ready structured propositions: goalchainer-ontology-context request")

(= (skill-doc)
   "- Regenerate a broken checkout repo, reason over docs/tests/source, patch it, and return fail/pass evidence: goalchainer-codebase-demo request")

(= (skill-doc)
   "- Run GoalChainer verification tests and return collected test names plus pass/fail output: goalchainer-tests request")

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
