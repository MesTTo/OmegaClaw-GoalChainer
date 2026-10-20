; Purpose: a caller's task-control procedure library for a host that can pause and probe but cannot
; hand work to another owner: the packaged library's pause route and its investigators, without the
; handoff procedures or the owner registry. task-control-pause-only.request.json plans the shipped
; example's evidence against it, so docs/planning.md shows what removing a capability does.
; am[implements a-dd-examples-1018@dfa4b9]

(gc-procedures task-control-v1)

; Releasing a shared resource by pausing needs a reachable safe point first, and rests on the
; checkpoint store restoring task state, which a restore drill establishes.
(gc-procedure release-by-pause
  (Achieves (Not (Signal resource_contention)))
  (When (Signal resource_contention) (Signal state_preservation_route)
        (Statement (sn p so "restores" ((arg s (sn c "checkpoint-store")) (arg o (sn c "task-state"))))))
  (Steps (Step reach achieve (Signal safe_point_reachable) (After))
         (Step pause act pause_recoverably (After reach))))

; Running on to the next checkpoint-and-release point reaches a safe point.
(gc-procedure reach-safe-point
  (Achieves (Signal safe_point_reachable))
  (When (Signal state_preservation_route))
  (Steps (Step run act continue_task (After))))

(gc-investigator scheduler-probe (Signal safe_point_reachable))
(gc-investigator restore-drill
  (Statement (sn p so "restores" ((arg s (sn c "checkpoint-store")) (arg o (sn c "task-state"))))))
