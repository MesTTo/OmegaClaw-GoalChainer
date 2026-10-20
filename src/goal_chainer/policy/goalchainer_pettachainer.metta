; Purpose: answer every PLN belief PeTTaChainer proves about each caller target from the caller's
; statements in one call, and warm the chainer once per process so a speculative grading finds its
; functions compiled.
; am[implements a-hh-pc-port-1018] am[implements a-hh-pc-warm-up-proof-1018] am[implements a-hh-gp-entry-1018]
;
; PeTTaChainer loads before this module, in the module group pettachainer (evidence_chainer.py).
; Each entry Python calls declares its type, as goal_chainer.runtime.evaluator requires: statements
; and targets are Atom so the hole data stays inert, the scalars their own types.

; One grading: every statement joins the knowledge base gc_grading, then (: $proof TARGET $tv) is
; queried for each target in order. The answer pairs each target with all its answers, an empty
; list where the chainer proved nothing, so the caller tells a missing belief from a false one.
; The call runs inside speculation (goal_chainer.runtime.evaluator.evaluate), so the knowledge base,
; the proof store and the cells it writes are discarded with it.
; Time: one compileadd per statement, then one query of at most $steps agenda steps per target.
; am[implements a-hh-pc-port-1018] am[implements a-hh-gp-entry-1018] am[rests-on c-hh-pc-speculation-rolls-back-1018]
(: gc-pettachainer-grade (-> Atom Atom Number Bool Expression))
(= (gc-pettachainer-grade $statements $targets $steps $prefilter)
   (let* (($_prefilter (set-backward-premise-prefilter gc_grading $prefilter))
          ($_added (collapse (compileadd gc_grading (superpose $statements)))))
      (Graded (gc-pettachainer-answers gc_grading $targets $steps))))

; am[implements a-hh-pc-port-1018] am[implements a-hh-gp-entry-1018]
(= (gc-pettachainer-answers $kb $targets $steps)
   (if (== $targets ())
      ()
      (let* (($target (car-atom $targets))
             ($found (collapse (query $steps $kb (: $proof $target $tv))))
             ($rest (gc-pettachainer-answers $kb (cdr-atom $targets) $steps)))
         (cons-atom ($target $found) $rest))))

; The warm-up compiles what a grading calls, outside any speculation, by grading a fixed example
; with the shapes a request uses: single-premise implications, facts, and a direct statement whose
; proof PLN revision merges with the rule proofs. chainer-reset! runs before it, so a warm-up
; stopped part way leaves nothing the next attempt sees, and after it, so what persists is the
; compiled functions and the engine's specializations of them. It answers True only when the
; example graded, so a chainer that cannot grade fails preparation rather than a request.
; am[implements a-hh-pc-warm-up-proof-1018] am[rests-on c-hh-pc-compile-survives-only-outside-1018]
(: gc-pettachainer-warm-up (-> Bool))
(= (gc-pettachainer-warm-up)
   (let* (($_clean (chainer-reset!))
          ((Graded (($_target $found)))
             (gc-pettachainer-grade
                ((: gc_warm_rule (Implication (Premises (GcWarmPremise $x)) (Conclusions (Acceptable $x))) (STV 0.9 0.9))
                 (: gc_warm_other (Implication (Premises (GcWarmOther $y)) (Conclusions (Acceptable $y))) (STV 0.8 0.9))
                 (: gc_warm_fact (GcWarmPremise gc_warm_action) (STV 1.0 0.9))
                 (: gc_warm_second (GcWarmOther gc_warm_action) (STV 0.7 0.9))
                 (: gc_warm_direct (Acceptable gc_warm_action) (STV 0.6 0.8)))
                ((Acceptable gc_warm_action))
                20
                True))
          ($_reset (chainer-reset!)))
      (not (== $found ()))))
