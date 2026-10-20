; Purpose: a two-action domain whose duty and prohibition about one action can both apply,
; so the relevance review can be checked against an unresolved deontic dilemma.
; am[verifies i-rel-dilemma-silent-1016@8b9179]

(gc-domain "Dilemma probe")
(gc-policy-version dilemma-v1)
(gc-authority advisory 1 "A recommendation delivered to a human.")
(gc-estimator-ceiling measured advisory)
(gc-estimator-ceiling deterministic advisory)
(gc-estimator-ceiling receipt-calibrated advisory)
(gc-estimator-ceiling model-proposed advisory)
(gc-estimator-ceiling human-asserted advisory)

(gc-action act "Act" "Do the contested thing." (authority advisory))
(gc-action wait "Wait" "Hold off." (authority advisory))
(gc-goal served owner individual 0.5 "The work is served." (priority-source human:test))
(gc-dimension cost cost "What the action costs.")
(gc-signal open "a review is open")
(gc-signal urgent "acting is urgent")
(gc-signal risky "acting is risky")

(normally rCandAct (signal open) (candidate act))
(normally rCandWait (signal open) (candidate wait))
(normally rPermit (candidate ?a) (may (do ?a)))
(normally rMust (and (candidate act) (signal urgent)) (must (do act)))
(normally rForbid (and (candidate act) (signal risky)) (forbidden (do act)))
(normally rServe (candidate ?a) (contributes ?a served slightly-positive))
(normally rCost (candidate ?a) (effect ?a cost neutral deterministic))
