;; Purpose: expose structured MeTTa guard programs and existential s(CASP) queries.
;; am[implements a-integrate-guard-metta-build-1019@e688cb]
(@doc (sn guard-rule!)
  (@desc "Add a held MeTTa fact or rule to the s(CASP) guard. Expressions use the solver's functors: (:- HEAD BODY), (, A B), (not GOAL), (- GOAL) and unary (:- BODY) for an integrity constraint. Variables and nested terms retain their identity.")
  (@params ((@param "Quoted clause, e.g. (quote (:- (flies $x) (, (isa $x bird) (not (ab $x)))))")))
  (@return "True"))

(@doc (sn guard?)
  (@desc "Run a held goal under s(CASP). Return the first supporting model as text, or \"no\" if there is none. Solver errors propagate. Support in one model does not mean truth in every model. GoalChainer batches isolate their guard rules through speculation.")
  (@params ((@param "Quoted goal, e.g. (quote (flies tweety))")))
  (@return "Model text or \"no\""))

(@doc (sn guard-proves?)
  (@desc "Boolean view of guard?: does a stable model support the goal? Solver errors propagate.")
  (@params ((@param "Quoted goal expression")))
  (@return "True or False"))

(@doc (sn guard-project!)
  (@desc "Project the crisp slice of the world model into the guard: every copula statement with both arguments atomic and projected probability above the threshold becomes pred(subject-label, object-label). SNARS keeps probability; the guard receives possibility.")
  (@params ((@param "Guard predicate symbol")
            (@param "Projection threshold")))
  (@return "Projected guard facts"))

(sn (function guard-rule!))
(sn (function guard?))
(sn (function guard-proves?))
(sn (function guard-project!))

;; requires snars.metta (loaded first) for the sn layer. The guard's sCASP
;; program is snars/guard.pl, imported the way kernel.metta imports kernel.pl.
!(import_prolog_functions_from_file (library snars snars/guard.pl)
  (sn_guard_assert sn_guard_fact2 sn_guard_check))

;; Quote protects data at compound sn heads; Atom protects the foreign call.
;; am[implements a-integrate-guard-metta-build-1019@e688cb]
(: sn_guard_assert (-> Atom Bool))
(: sn_guard_check (-> Atom String))
(: (sn guard-rule!) (-> %Undefined% Bool))
(= (sn guard-rule! $clause)
   (sn_guard_assert $clause))

;; am[implements a-integrate-guard-metta-build-1019@e688cb]
(: (sn guard?) (-> %Undefined% String))
(= (sn guard? $goal)
   (sn_guard_check $goal))

;; am[implements a-integrate-guard-metta-build-1019@e688cb]
(: (sn guard-proves?) (-> %Undefined% Bool))
(= (sn guard-proves? $goal)
   (not (== (sn_guard_check $goal) "no")))

(: (sn guard-project!) (-> %Undefined% Number Expression))
(= (sn guard-project! $pred $threshold)
   (collapse
     (match &self (sn stmt $sid (sh (tag P d so $amr) $cop (args ((arg s (sh-atom $t1 $x)) (arg o (sh-atom $t2 $y))))))
       (if (sn above $sid $threshold)
           (sn_guard_fact2 $pred $x $y)
           (empty)))))
