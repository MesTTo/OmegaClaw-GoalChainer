; Purpose: a caller's own domain for docs/planning.md: a laboratory run holding a bench another group
; booked, with its own signals, actions and one-entity world, which GoalChainer has never seen and
; which no code names. bench-booking.procedures.metta declares how it can be freed, and the
; bench-booking requests plan with both through the same request command as the packaged domains.
; am[implements a-dd-examples-1018@dfa4b9]

(gc-domain "Bench booking for a shared laboratory")
(gc-policy-version bench-v1)

; One rung: everything here is a recommendation to the lab coordinator.
(gc-authority advisory 0 "A recommendation to the lab coordinator.")
(gc-estimator-ceiling deterministic advisory)
(gc-estimator-ceiling measured advisory)
(gc-estimator-ceiling human-asserted advisory)
(gc-estimator-ceiling model-proposed advisory)
(gc-estimator-ceiling receipt-calibrated advisory)

(gc-action rebook "Rebook" "Move the run to another bench." (authority advisory))
(gc-action ask_coordinator "Ask the coordinator" "Ask the lab coordinator to confirm a free bench." (authority advisory))

(gc-goal shared_use owner collective 0.8 "Keep shared benches available to the groups that booked them."
  (priority-source human:lab-coordinator))

(gc-signal bench_blocked "the run holds a bench another group has booked")
(gc-signal spare_bench_free "another bench is free for the run")
(gc-signal coordinator_confirmed "the coordinator has confirmed the spare bench")

; The review proposes rebooking whenever the bench is blocked; nothing forbids it.
(normally rRebookCand (signal bench_blocked) (candidate rebook))
(normally rPermit (candidate ?a) (may (do ?a)))

; The world the procedures act on: the bench the run occupies, which every signal describes.
(gc-brs-control Bench (Ports) active)
(gc-brs-entity bench Bench "the bench the run occupies")
(gc-brs-in bench (Root 0))
(gc-brs-literal (Signal bench_blocked) (On bench))
(gc-brs-literal (Signal spare_bench_free) (On bench))
(gc-brs-literal (Signal coordinator_confirmed) (On bench))
