; Purpose: a caller's task-control procedure library that keeps track records: the packaged library's
; forms in the same order, then a promotion rule, so the receipts of earlier attempts can establish a
; procedure's record.
; am[implements a-dd-receipt-variation-1018@655fcb]

(gc-procedures task-control-v1)

; Releasing a shared resource by pausing needs a reachable safe point first: section 8.10 of the
; governor paper says a pause delivered mid-transaction is not recoverable, it is damage.
; It also rests on the checkpoint store restoring task state, a fact about the store that a
; restore drill establishes and that holds for every task, so it is a SNARS statement.
(gc-procedure release-by-pause
  (Achieves (Not (Signal resource_contention)))
  (When (Signal resource_contention) (Signal state_preservation_route)
        (Statement (sn p so "restores" ((arg s (sn c "checkpoint-store")) (arg o (sn c "task-state"))))))
  (Steps (Step reach achieve (Signal safe_point_reachable) (After))
         (Step pause act pause_recoverably (After reach))))

; Running on to the next checkpoint-and-release point reaches a safe point, where the task can
; preserve its state at all.
(gc-procedure reach-safe-point
  (Achieves (Signal safe_point_reachable))
  (When (Signal state_preservation_route))
  (Steps (Step run act continue_task (After))))

; Handing the work to the owner it belongs with releases the resource, once that owner accepts. The
; hand step is the domain's handoff reaction, which moves the task from the seat that owns it to the
; receiving seat, so it names each of the reaction's nodes: an unbound one would leave the matcher to
; choose the seat (c-ev-pk-unbound-node-wrong-target-1018).
; am[implements a-ev-pk-bind-table-1018@761a0f]
(gc-procedure release-by-handoff
  (Achieves (Not (Signal resource_contention)))
  (When (Signal resource_contention) (Signal owner_mismatch))
  (Steps (Step accept achieve (Signal receiving_owner_accepts) (After))
         (Step hand act handoff (After accept) (Bind (T task) (A seat) (B receiving_seat)))))

(gc-procedure ask-receiving-owner
  (Achieves (Signal receiving_owner_accepts))
  (When (Signal owner_mismatch))
  (Steps (Step ask act escalate (After))))

; Releasing contention would also free a safe point, but releasing by pause needs the safe point
; first: this support cycle has no founded entry, so it is never chosen on its own.
(gc-procedure reach-by-release
  (Achieves (Signal safe_point_reachable))
  (When (Signal state_preservation_route))
  (Steps (Step free achieve (Not (Signal resource_contention)) (After))))

(gc-investigator scheduler-probe (Signal safe_point_reachable))
(gc-investigator owner-registry (Signal owner_mismatch) (Signal receiving_owner_accepts))
(gc-investigator restore-drill
  (Statement (sn p so "restores" ((arg s (sn c "checkpoint-store")) (arg o (sn c "task-state"))))))

; A procedure's record holds once at least three of its applied attempts are attributed trials and
; SNARS's track-record cut at 0.5 holds on their counts (planning/feedback.metta counts the trials and
; planning/projection.py asks SNARS); with no such rule no record holds.
(gc-track-promotion (Trials 3) (Threshold 0.5))
