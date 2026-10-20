; Purpose: the bench-booking domain's procedures, a caller's declaration of how a blocked bench can be
; freed and what the host can observe; the planner composes them, and no step list is written here.
; am[implements a-dd-examples-1018@dfa4b9]

(gc-procedures bench-v1)

; Moving the run frees the booked bench, once a spare bench is free and the coordinator confirmed it.
(gc-procedure free-the-bench
  (Achieves (Not (Signal bench_blocked)))
  (When (Signal bench_blocked) (Signal spare_bench_free))
  (Steps (Step confirm achieve (Signal coordinator_confirmed) (After))
         (Step move act rebook (After confirm))))

; Asking the coordinator gets the confirmation while a spare bench is free.
(gc-procedure get-confirmation
  (Achieves (Signal coordinator_confirmed))
  (When (Signal spare_bench_free))
  (Steps (Step ask act ask_coordinator (After))))

; The booking calendar shows whether a spare bench is free.
(gc-investigator bench-calendar (Signal spare_bench_free))
