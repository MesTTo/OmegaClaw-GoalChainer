; Purpose: compile every relevance policy module once per process by calling each entry point on
; a small input, as fixed work no review's inference budget is charged for;
; `(gc-relevance-warm-up)` answers True.
;
; The first evaluation in a process compiles what was imported, about 4.4 million inferences for
; the policy (c-rel-inference-history-1016); this runs it where no review's inferences pay for it,
; at a host's startup or inside the deadline of the first request that needs it. The inputs
; reach the main branches: decay, a conflict of one tier and a contrary overruled by a higher one
; in the evidence policy, a variable binding in the cones, a forbidden candidate, an obliged
; candidate in a dilemma, a Pareto comparison and a motive elimination in the ranking, both
; freshness outcomes, a receipt's faults for an observation after its issue and another attempt's
; product, an assessment refused for an application before its decision, and in the receipt
; assessment an observation that passes every row of the counting table and is attributed, one
; made before the application, and one whose estimator cannot establish an outcome. The policy's
; module group runs the justification kernel's own warm-up before this one, so the kernel the
; evidence policy calls is compiled already.
; The motivation policy's snapshot is called on a stream with an observed, an expired and an
; unobserved need, a sample with its residual against a declared change, a sample refused for an
; unestablished baseline and an excluded observation, so every reduction case runs; the ranking is
; called twice more with needs, once removing every candidate as unmotivated and holding and once
; proposing a candidate whose unknown change leaves it no better than holding.
; am[implements a-rel-metta-policy-1016@fdaa20] am[rests-on c-rel-inference-history-1016@b4779a]
; am[rests-on c-rel-one-deadline-1016@75de2a] am[implements a-rel-rcpt-v2-counting-1017@ae46fe]
; am[implements a-rel-rcpt-v2-metta-rules-1018@c22bf6] am[implements a-rel-rr-projection-1018@a05ccf]
; am[implements a-rel-mig-group-1018@28c337] am[implements a-rel-mig-typed-entries-1018@c150af]
; am[related a-rel-assess-attempt-1018@20e6ca] am[implements a-v2m-levels-1019@387e68] am[implements a-v2m-hold-1019@be4f47]

(: gc-relevance-warm-up (-> Bool))
(= (gc-relevance-warm-up)
   (let* (($effective
             (gc-relevance-effective 10
               ((Reading "s" "detected" "measured" Forever 0) (Reading "s" "refuted" "deterministic" (Until 20) 1)
                (Reading "t" "refuted" "measured" (Until 5) 2) (Reading "u" "unknown" None Forever 3)
                (Reading "v" "detected" "measured" Forever 4) (Reading "v" "refuted" "model-proposed" Forever 5))
               ("s" "t" "u" "v")))
          ($cones
             (gc-relevance-cones
               (ConeInput ("s" "t")
                          ("a" "b")
                          ((Rule ((Lit "signal" ((Const "s")))) ((Lit "candidate" ((Const "a")))))
                           (Rule ((Lit "candidate" ((Var "x"))) (Lit "signal" ((Const "t")))) ((Lit "do" ((Var "x"))))))
                          ((Lit "do" ((Var "y")))))))
          ($readsets (gc-relevance-review-readset $cones ("a")))
          ($ranking
             (gc-relevance-rank
               (RankInput (Goals ((Goal "g" "collective" 0.9 "human:owner") (Goal "h" "individual" 0.5 "")))
                          (Dimensions ("d" "e"))
                          (Tiers ((Tier "advisory" 1) (Tier "preauthorized" 5)))
                          (Ceilings ((Ceiling "measured" "preauthorized") (Ceiling "model-proposed" "advisory")))
                          (Required ("g")) (Obligations ("x")) (OtherDilemmas ()) (Conflicted ())
                          (Support ((Support "s" ("measured" "model-proposed"))))
                          (Candidates
                            ((Candidate "a" "preauthorized" (P) False
                                        ((Effect "d" "positive" "measured") (Effect "e" "negative" "model-proposed"))
                                        ((Contrib "g" "positive") (Contrib "h" "slightly-positive")) ("s"))
                             (Candidate "b" "advisory" (P) False
                                        ((Effect "d" "slightly-negative" "measured"))
                                        ((Contrib "g" "slightly-positive")) ("s"))
                             (Candidate "c" "advisory" (P) False () () ())
                             (Candidate "f" "advisory" (F) False () () ())
                             (Candidate "x" "advisory" (O) True () () ())))
                          (Motivation None))))
          ($snapshot
             (gc-motivation-snapshot
               (MotivationInput (AsOf 100)
                 (Needs ((Need "n" "g" 0.0 1.0 0.4 0.6 2.0) (Need "m" "h" 0.0 1.0 0.0 1.0 1.0) (Need "q" "h" 0.0 1.0 0.2 0.3 1.5)))
                 (Declared ((Expectation "a" "n" 0.3 "human-asserted")))
                 (Actions ("a" "b"))
                 (Observations ((Obs "o1" "n" 0.9 0.0 1.0 "measured" 10 Forever Unstated)
                                (Obs "o2" "n" 0.5 0.0 1.0 "measured" 30 Forever (ProducedBy "t1"))
                                (Obs "o3" "m" 0.5 0.0 1.0 "model-proposed" 10 (Until 50) Unstated)
                                (Obs "o4" "m" 0.7 0.0 1.0 "measured" 60 Forever (ProducedBy "t2"))
                                (Obs "o5" "x" 0.5 0.0 1.0 "measured" 10 Forever Unstated)))
                 (Attempts ((Attempt "t1" "a" (Applied 20)) (Attempt "t2" "b" (Applied 55)) (Attempt "t3" "b" NotApplied))))))
          ($held
             (gc-relevance-rank
               (RankInput (Goals ((Goal "g" "individual" 0.9 "human:owner"))) (Dimensions ()) (Tiers ((Tier "advisory" 1)))
                          (Ceilings ((Ceiling "measured" "advisory"))) (Required ()) (Obligations ()) (OtherDilemmas ())
                          (Conflicted ()) (Support ())
                          (Candidates ((Candidate "a" "advisory" (P) False () () ())))
                          (Motivation (Regulation ((Regulates "n" "g")) ((NeedState "n" "observed" 0.0))
                                                  ((Reduction "a" "n" (Interval -0.25 -0.25) ("measured") ("measured"))))))))
          ($unsettled
             (gc-relevance-rank
               (RankInput (Goals ((Goal "g" "individual" 0.9 "human:owner") (Goal "h" "collective" 0.4 "human:owner")))
                          (Dimensions ()) (Tiers ((Tier "advisory" 1)))
                          (Ceilings ((Ceiling "measured" "advisory") (Ceiling "receipt-calibrated" "advisory")))
                          (Required ()) (Obligations ()) (OtherDilemmas ()) (Conflicted ()) (Support ())
                          (Candidates ((Candidate "a" "advisory" (P) False () ((Contrib "h" "positive")) ())
                                       (Candidate "b" "advisory" (P) False () () ())))
                          (Motivation (Regulation ((Regulates "n" "g")) ((NeedState "n" "unobserved" None))
                                                  ((Reduction "a" "n" (Interval -0.5 0.75) () ("receipt-calibrated"))
                                                   (Reduction "b" "n" (Interval -0.5 -0.5) () ("measured"))))))))
          ($fresh (gc-relevance-freshness (Moved False False False False False False)))
          ($stale (gc-relevance-freshness (Moved True False False False False False)))
          ($faults
             (gc-relevance-receipt-faults (Attempt "a" (Applied 10)) 40
               ((Observation 0 "effect" "d" "confirmed" "measured" (At 20) (ProducedBy "a"))
                (Observation 1 "effect" "d" "contradicted" "deterministic" (At 50) Unstated)
                (Observation 2 "effect" "d" "confirmed" "measured" (At 20) (ProducedBy "b")))))
          ($refused (gc-relevance-assess (Attempt "a" (Applied 10)) 20 Forever () ()))
          ($assessment
             (gc-relevance-assess (Attempt "a" (Applied 10)) 0 (Until 30)
               ((Prediction "effect" "d") (Prediction "contribution" "g"))
               ((Observation 0 "effect" "d" "confirmed" "measured" (At 20) (ProducedBy "a"))
                (Observation 1 "effect" "d" "contradicted" "deterministic" (At 5) Unstated)
                (Observation 2 "contribution" "g" "confirmed" "model-proposed" Untimed Unstated)))))
     True))
