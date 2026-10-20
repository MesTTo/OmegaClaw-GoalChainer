; Purpose: the task-control domain, the relevance governor's own decision problem over
; lifecycle interventions on one focal task.
;
; The candidate actions are lifecycle interventions on a focal task, and the
; goals are the standing desiderata a review weighs. Both come from the goal
; relevance governor paper (Goertzel, goal_relevance_governor_v3.pdf): the
; verdicts and their authority postures are Appendix C, the preconditions are
; §11.4, the deterministic pre-pass is §10.3, the goal set is §11.7, and the
; dimensions are §A.4.
;
; This file is the test that GoalChainer is general. It is a domain the engine
; has never seen, in a field with no incidents and no privacy, and it needs no
; Python change to run.

(gc-domain "Task control for a persistent agent's own work")
(gc-policy-version task-control-v1)

; --- the authority ladder ---------------------------------------------------
; §16.7's promotion gates, as rungs. Nothing is applied above the rung its
; weakest supporting estimator can license.

(gc-authority shadow 0 "Recorded for later comparison; nothing acts on it.")
(gc-authority advisory 1 "A recommendation delivered to a human or the scheduler.")
(gc-authority owner-confirmation 2 "Applied only after the task's owner accepts it.")
(gc-authority deliberation-room 3 "Applied only after a bounded deliberation commits a conclusion.")
(gc-authority scheduling-gate 4 "The scheduler may block a new start, with override and a graph-quality minimum.")
(gc-authority preauthorized 5 "Applied inside a declared low-risk envelope, with a receipt.")

; §8.2: the gate conditions authority on the estimator class, not the
; magnitude. A model-proposed reversibility of 0.97 licenses at most an
; advisory recommendation; the same number receipt-calibrated may license a
; preauthorized pause.
(gc-estimator-ceiling model-proposed advisory)
(gc-estimator-ceiling receipt-calibrated preauthorized)
(gc-estimator-ceiling measured preauthorized)
(gc-estimator-ceiling deterministic preauthorized)
(gc-estimator-ceiling human-asserted preauthorized)

; --- the candidate actions (Appendix C) -------------------------------------
; Twelve lifecycle interventions on a focal task. The authority clause is the
; rung this action may be applied at once every other check has passed; the
; estimator ceiling can lower it further but never raise it.
;
; There is no strength number here. What an action is worth is derived per
; review as typed effects with estimator provenance, because a constant
; attached to an action is a value judgment wearing numeric clothing.

(gc-action continue_task "Continue"
  "The current task and plan remain proportionate; carry on."
  (authority advisory))
(gc-action accelerate "Accelerate"
  "Allocate more authorized resources to the task."
  (authority advisory))
(gc-action streamline "Streamline"
  "Reduce review cadence, reporting, or other governance overhead."
  (authority advisory))
(gc-action pause_recoverably "Pause recoverably"
  "Preserve state and release a resource with a resume condition, delivered at a safe point."
  (authority preauthorized))
(gc-action stop_stale "Stop as stale"
  "No active parent-goal path remains, so stop the task."
  (authority scheduling-gate))
(gc-action retarget "Retarget"
  "Point still-useful worker machinery at a different active goal path."
  (authority owner-confirmation))
(gc-action replan "Replan"
  "A superior route or an invalidated assumption changes the decomposition."
  (authority deliberation-room))
(gc-action descope "Descope"
  "Narrow contracted scope to the current stage's needs, preserving the rest as an option."
  (authority owner-confirmation))
(gc-action defer "Defer"
  "Useful later, but not for the current result stage."
  (authority owner-confirmation))
(gc-action handoff "Hand off"
  "The task remains valuable but belongs with a different owner or seat."
  (authority owner-confirmation))
(gc-action escalate "Escalate"
  "The judgment or authority required exceeds the evaluator."
  (authority advisory))
(gc-action declare_blocked "Declare blocked"
  "No safe authorized step is available."
  (authority advisory))

; --- the goals (§11.7) ------------------------------------------------------
; Relatively stable desiderata, not context-sensitive modulators. Each carries
; the source that declared its priority, so no derived score can quietly
; replace a human judgment with its own.

(gc-goal project_outcome owner collective 0.95
  "Deliver the result the project actually commissioned."
  (priority-source human:project-owner))
(gc-goal decision_relevant_speed owner collective 0.80
  "Reach the next decision-relevant result quickly."
  (priority-source human:project-owner))
(gc-goal epistemic_integrity reviewer individual 0.90
  "Report only what the evidence supports, and keep the record true."
  (priority-source policy:standing-ethical-goal))
(gc-goal least_commitment planner individual 0.70
  "Keep options open; prefer the reversible route until evidence closes it."
  (priority-source policy:planning-doctrine))
(gc-goal mature_result_efficiency planner collective 0.65
  "Spend hardening effort only where the result's stage warrants it."
  (priority-source policy:result-contract))
(gc-goal commitment_fulfilment owner collective 0.85
  "Honour what was promised to other seats and to people."
  (priority-source human:project-owner))

; --- the dimensions actions are compared on (§A.4) --------------------------
; Polarity is what makes Pareto domination well defined without a weight.
; These stay separate on purpose: §9.2 forbids collapsing contribution,
; priority, evidential support and operational risk into one number.

(gc-dimension expected-goal-delta benefit "Predicted magnitude and direction of change in goal progress.")
(gc-dimension contribution-belief benefit "Estimated truth of the causal link from this action to the goal.")
(gc-dimension contribution-confidence benefit "Amount and quality of evidence supporting that estimate.")
(gc-dimension urgency benefit "Time-sensitive importance, deadline pressure, or cost of delay.")
(gc-dimension option-value benefit "Future choices retained by a reversible action.")
(gc-dimension recoverability benefit "Availability and expected quality of checkpoint, rollback, or resume.")
(gc-dimension direct-cost cost "Compute, money, storage, latency, or human effort directly consumed.")
(gc-dimension opportunity-cost cost "Value of higher-priority paths delayed or blocked.")
(gc-dimension hazard-probability cost "Probability of a specified harmful outcome.")
(gc-dimension hazard-severity cost "Magnitude or blast radius if the hazard occurs.")
(gc-dimension irreversibility cost "Difficulty and cost of returning to the prior state.")
(gc-dimension governance-cost cost "Coordination, review, reporting, and policy overhead.")

; --- the signals a review packet can carry ----------------------------------
; §9.9's triggers and §11.4's preconditions, as things the compiler either
; observes in the committed graph or reads from the review packet.

(gc-signal review_open "a review is in progress for this task")
(gc-signal stale_parent_goal "every parent goal is achieved or superseded and no other active path remains")
(gc-signal active_parent_path "at least one parent goal is active and reachable through this task")
(gc-signal completion_proximate "little remains between here and the finished result")
(gc-signal safe_point_reachable "a checkpoint-and-release point is reachable inside the review's time bound")
(gc-signal state_preservation_route "the task has a checkpoint or state-preservation route at all")
(gc-signal resource_contention "the task holds a resource an urgent higher-priority claimant is waiting on")
(gc-signal authorized_resource_named "the review names the authorized resource an acceleration would consume")
(gc-signal governance_overhead_named "the review names the specific overhead a streamlining would remove")
(gc-signal simpler_route_available "a simpler, faster, cheaper, safer, or more reversible route now exists")
(gc-signal assumption_invalidated "an assumption the decomposition rests on no longer holds")
(gc-signal cost_variance_material "observed cost has diverged materially from the estimate")
(gc-signal scope_exceeds_stage "contracted scope is wider than the current result stage needs")
(gc-signal owner_mismatch "the work belongs with a different owner or seat")
(gc-signal receiving_owner_accepts "the receiving owner has accepted the handoff")
(gc-signal authority_unavailable "the effect this action needs is outside the evaluator's authority")
(gc-signal judgment_exceeds_evaluator "the judgment required exceeds what the evaluator may decide alone")
(gc-signal no_safe_step "no safe authorized step is available at all")
(gc-signal low_graph_quality "the decision-relevant slice is stale or poorly evidenced")
(gc-signal ethics_consilience_broken "the task has fallen out of consilience with a standing ethical goal")
(gc-signal sunk_cost_argument "the case for continuing rests on investment already made")

; ===========================================================================
; The theory. Everything conditional lives here, where superiority, defeaters
; and contrary-to-duty chains can act on it.
; ===========================================================================

; --- candidacy (§11.4) ------------------------------------------------------
; "Only contextually meaningful candidates should be generated." An action
; whose precondition fails is not a low-ranked option, it is not an option.

(normally rContinueCand (signal review_open) (candidate continue_task))
(normally rEscalateCand (signal review_open) (candidate escalate))

; PAUSE_RECOVERABLY needs both a route and a reachable safe point. §8.10: a
; pause delivered mid-transaction is not recoverable, it is damage.
(normally rPauseCand (and (signal state_preservation_route) (signal safe_point_reachable))
   (candidate pause_recoverably))

; ACCELERATE must name the authorized resource it would consume.
(normally rAccelCand (and (signal review_open) (signal authorized_resource_named))
   (candidate accelerate))

; STREAMLINE must name the specific overhead it would remove.
(normally rStreamCand (and (signal review_open) (signal governance_overhead_named))
   (candidate streamline))

; STOP_STALE requires a stale active-goal path, not merely weak recent progress.
(normally rStopCand (signal stale_parent_goal) (candidate stop_stale))

(normally rRetargetCand (and (signal stale_parent_goal) (signal active_parent_path))
   (candidate retarget))
(normally rReplanCand (signal simpler_route_available) (candidate replan))
(normally rReplanCand2 (signal assumption_invalidated) (candidate replan))
; §9.8 question 6 and §9.9: a material divergence between observed and estimated
; cost is a changed assumption, so it makes a replan worth considering, and
; continuing as planned now carries the observed overrun.
; am[implements a-rel-taskcontrol-1016@a7e7e4] am[addresses i-rel-deadsignal-1016@c0cf3b]
(normally rReplanCand3 (signal cost_variance_material) (candidate replan))
(normally rDescopeCand (signal scope_exceeds_stage) (candidate descope))
(normally rDeferCand (signal scope_exceeds_stage) (candidate defer))
(normally rHandoffCand (signal owner_mismatch) (candidate handoff))
(normally rBlockedCand (signal no_safe_step) (candidate declare_blocked))
(normally rBlockedCand2 (signal authority_unavailable) (candidate declare_blocked))

; --- deontic admissibility (§9.1, §9.3 step 1) ------------------------------
; Permission is the default for a candidate; prohibitions defeat it.

(normally rPermitCandidates (candidate ?a) (may (do ?a)))

; §10.3: an effect needing unavailable authority is not merely unwise.
(normally rNoAuthority (and (candidate ?a) (signal authority_unavailable))
   (forbidden (do ?a)))
(prefer rNoAuthority rPermitCandidates)

; §8.10: pausing without a reachable safe point is damage, so the absence of
; the precondition forbids the action rather than only failing to propose it.
(normally rNoSafePoint (and (candidate pause_recoverably) (not (signal safe_point_reachable)))
   (forbidden (do pause_recoverably)))
(prefer rNoSafePoint rPermitCandidates)

; §8.3: STOP_STALE from an exact query over a wrong graph is a confident false
; positive with real cost, so a poorly evidenced slice withdraws the stop.
(except rStopNeedsGraphQuality (signal low_graph_quality) (not (may (do stop_stale))))

; §7.6 via §9.1: a broken ethical consilience is a reason to review and never a
; licence to continue, so continuing is forbidden until the review lands.
(normally rEthicsHalt (and (candidate continue_task) (signal ethics_consilience_broken))
   (forbidden (do continue_task)))
(prefer rEthicsHalt rPermitCandidates)

; Escalation is the one action that stays permitted when judgment runs out.
(always rEscalateAlways (signal judgment_exceeds_evaluator) (must (do escalate)))

; --- obligations from the deterministic pre-pass (§10.3, §9.3 step 2) -------

(normally rStopObliged (and (signal stale_parent_goal) (not (signal active_parent_path)))
   (must (do stop_stale)))
(normally rBlockedObliged (signal no_safe_step) (must (do declare_blocked)))

; §8.10 again, as a contrary-to-duty chain: the primary duty when an urgent
; claimant is blocked is to release the resource by pausing; if that is
; violated, the reparation is to escalate rather than to do nothing.
(normally rContention (and (signal resource_contention) (signal safe_point_reachable))
   (otherwise (must (do pause_recoverably)) (must (do escalate))))

; --- what each action does for each goal ------------------------------------
; Contribution is per goal path and stays uncollapsed (§9.5).

(normally rContinueOutcome (candidate continue_task)
   (contributes continue_task project_outcome positive))
(normally rContinueSpeed (and (candidate continue_task) (signal completion_proximate))
   (contributes continue_task decision_relevant_speed strongly-positive))
(normally rContinueCommit (candidate continue_task)
   (contributes continue_task commitment_fulfilment slightly-positive))

; §9.6: completion proximity legitimately favours finishing; prior investment
; never does. The sunk-cost signal withdraws the continuation contribution
; rather than adding a term against it, so no argument for continuing can
; reduce to what was already spent.
(except rNoSunkCost (signal sunk_cost_argument)
   (not (contributes continue_task project_outcome positive)))

(normally rAccelSpeed (candidate accelerate)
   (contributes accelerate decision_relevant_speed strongly-positive))
(normally rStreamSpeed (candidate streamline)
   (contributes streamline decision_relevant_speed positive))
(normally rStreamMature (candidate streamline)
   (contributes streamline mature_result_efficiency positive))

(normally rPauseOption (candidate pause_recoverably)
   (contributes pause_recoverably least_commitment strongly-positive))
(normally rPauseOutcome (and (candidate pause_recoverably) (signal resource_contention))
   (contributes pause_recoverably project_outcome positive))

(normally rStopMature (candidate stop_stale)
   (contributes stop_stale mature_result_efficiency strongly-positive))
(normally rStopIntegrity (candidate stop_stale)
   (contributes stop_stale epistemic_integrity positive))

(normally rRetargetOutcome (candidate retarget)
   (contributes retarget project_outcome positive))
(normally rReplanOutcome (candidate replan)
   (contributes replan project_outcome positive))
(normally rReplanCommit (and (candidate replan) (signal assumption_invalidated))
   (contributes replan commitment_fulfilment slightly-negative))
(normally rDescopeMature (candidate descope)
   (contributes descope mature_result_efficiency positive))
(normally rDescopeCommit (candidate descope)
   (contributes descope commitment_fulfilment slightly-negative))
(normally rDeferSpeed (candidate defer)
   (contributes defer decision_relevant_speed slightly-positive))
(normally rHandoffOutcome (and (candidate handoff) (signal receiving_owner_accepts))
   (contributes handoff project_outcome positive))
(normally rEscalateIntegrity (candidate escalate)
   (contributes escalate epistemic_integrity strongly-positive))
(normally rBlockedIntegrity (candidate declare_blocked)
   (contributes declare_blocked epistemic_integrity positive))

; --- typed predicted effects (§8.6, §A.4) -----------------------------------
; Each carries its estimator class, so the policy gate can see how the number
; was produced and cap the authority accordingly.

; Every candidate costs something to govern; that is deterministic, not guessed.
; Two rules assigning different bands to one (action, dimension) do not attack
; each other in DL(d) — the band is an argument, so both would simply derive and
; the action would carry two contradictory costs. Where a specific rule
; overrides this default it must withdraw it explicitly.
(normally rGovAll (candidate ?a)
   (effect ?a governance-cost slightly-negative deterministic))
(except rGovNotEscalate (candidate escalate)
   (not (effect escalate governance-cost slightly-negative deterministic)))
; Streamlining removes overhead and a handoff adds coordination, so each has its
; own governance-cost estimate, and the default has to step aside for both.
; am[implements a-rel-taskcontrol-1016@a7e7e4] am[addresses i-rel-govcost-1016@e950e5]
(except rGovNotStreamline (candidate streamline)
   (not (effect streamline governance-cost slightly-negative deterministic)))
(except rGovNotHandoff (candidate handoff)
   (not (effect handoff governance-cost slightly-negative deterministic)))

(normally rContinueRev (candidate continue_task)
   (effect continue_task irreversibility neutral deterministic))
(normally rContinueOpp (and (candidate continue_task) (signal resource_contention))
   (effect continue_task opportunity-cost strongly-negative measured))
(normally rContinueOption (candidate continue_task)
   (effect continue_task option-value slightly-negative model-proposed))
; am[implements a-rel-taskcontrol-1016@a7e7e4] am[addresses i-rel-deadsignal-1016@c0cf3b]
(normally rContinueCostVariance (and (candidate continue_task) (signal cost_variance_material))
   (effect continue_task direct-cost negative measured))

(normally rAccelCost (candidate accelerate)
   (effect accelerate direct-cost negative measured))
(normally rAccelOpp (candidate accelerate)
   (effect accelerate opportunity-cost negative model-proposed))

(normally rStreamGov (candidate streamline)
   (effect streamline governance-cost positive measured))
(normally rStreamHazard (candidate streamline)
   (effect streamline hazard-probability slightly-negative model-proposed))

(normally rPauseRecover (and (candidate pause_recoverably) (signal safe_point_reachable))
   (effect pause_recoverably recoverability strongly-positive deterministic))
(normally rPauseRev (candidate pause_recoverably)
   (effect pause_recoverably irreversibility slightly-negative model-proposed))
(normally rPauseOptionValue (candidate pause_recoverably)
   (effect pause_recoverably option-value strongly-positive model-proposed))
(normally rPauseCost (candidate pause_recoverably)
   (effect pause_recoverably direct-cost slightly-negative measured))

(normally rStopRev (candidate stop_stale)
   (effect stop_stale irreversibility negative model-proposed))
(normally rStopOpp (candidate stop_stale)
   (effect stop_stale opportunity-cost strongly-positive deterministic))
(normally rStopOption (candidate stop_stale)
   (effect stop_stale option-value negative model-proposed))

(normally rRetargetRev (candidate retarget)
   (effect retarget irreversibility slightly-negative model-proposed))
(normally rReplanCost (candidate replan)
   (effect replan direct-cost negative model-proposed))
(normally rReplanOption (candidate replan)
   (effect replan option-value positive model-proposed))
(normally rDescopeOption (candidate descope)
   (effect descope option-value slightly-positive model-proposed))
(normally rDeferOption (candidate defer)
   (effect defer option-value positive model-proposed))
(normally rHandoffGov (candidate handoff)
   (effect handoff governance-cost negative model-proposed))
(normally rEscalateGov (candidate escalate)
   (effect escalate governance-cost strongly-negative deterministic))
(normally rEscalateRev (candidate escalate)
   (effect escalate irreversibility neutral deterministic))
(normally rBlockedGov (candidate declare_blocked)
   (effect declare_blocked governance-cost slightly-negative deterministic))

; --- which goals this review must satisfy -----------------------------------
; Requiredness is derived like everything else conditional.

(always rIntegrityAlways (signal review_open) (required epistemic_integrity))
(normally rOutcomeRequired (signal active_parent_path) (required project_outcome))
(normally rSpeedRequired (signal resource_contention) (required decision_relevant_speed))
(normally rCommitRequired (signal owner_mismatch) (required commitment_fulfilment))

; --- the world the procedures act on: the paper's typed graph ---------------
; §8.1.1's node types are the bigraph's controls, with §3.4's seats, the durable roles whose
; memory persists while no process is resident. A seat holds the tasks it owns; a task occupies a
; resource, contributes to its parent goals and is reviewed by a review; and a checkpoint is the
; §8.1.1 result the checkpoint store keeps. Each port is named for the §8.1.2 edge type it
; carries, and each signal is anchored on the entity it describes. The review reads none of this
; section; the planner reads it with the procedure library, so the packaged procedures plan on
; the packaged domain without a caller's topology.
; am[implements a-rel-tc-topology-1018@c19624]

(gc-brs-control Seat (Ports) active)
(gc-brs-control Task (Ports occupies contributes-to reviewed-by) active)
(gc-brs-control Goal (Ports contributes-to) passive)
(gc-brs-control Resource (Ports occupies) passive)
(gc-brs-control Checkpoint (Ports) passive)
(gc-brs-control Review (Ports reviewed-by) passive)

(gc-brs-entity seat Seat "the seat that owns the focal task")
(gc-brs-entity receiving_seat Seat "the seat the work belongs with")
(gc-brs-entity task Task "the focal task under review")
(gc-brs-entity parent_goal Goal "the parent goals the task contributes to")
(gc-brs-entity resource Resource "the shared resource the task holds")
(gc-brs-entity checkpoint Checkpoint "the task state the checkpoint store keeps")
(gc-brs-entity review Review "the review in progress")

(gc-brs-in seat (Root 0))
(gc-brs-in receiving_seat (Root 0))
(gc-brs-in task seat)
(gc-brs-in parent_goal (Root 0))
(gc-brs-in resource (Root 0))
(gc-brs-in checkpoint (Root 0))
(gc-brs-in review (Root 0))

(gc-brs-link task occupies (Edge occupancy))
(gc-brs-link resource occupies (Edge occupancy))
(gc-brs-link task contributes-to (Edge contribution))
(gc-brs-link parent_goal contributes-to (Edge contribution))
(gc-brs-link task reviewed-by (Edge reviewing))
(gc-brs-link review reviewed-by (Edge reviewing))

; The task holds the contended resource through its occupancy, and whether its parent goals still
; want it is a fact about its contribution.
(gc-brs-literal (Signal resource_contention) (On task) (Via occupancy))
(gc-brs-literal (Signal stale_parent_goal) (On task) (Via contribution))
(gc-brs-literal (Signal active_parent_path) (On task) (Via contribution))
; What the review names, and what it may decide.
(gc-brs-literal (Signal authorized_resource_named) (On review))
(gc-brs-literal (Signal governance_overhead_named) (On review))
(gc-brs-literal (Signal low_graph_quality) (On review))
(gc-brs-literal (Signal judgment_exceeds_evaluator) (On review))
(gc-brs-literal (Signal authority_unavailable) (On review))
; The receiving owner's acceptance belongs to the receiving seat.
(gc-brs-literal (Signal receiving_owner_accepts) (On receiving_seat))
; Every other signal describes the task itself.
(gc-brs-literal (Signal review_open) (On task))
(gc-brs-literal (Signal completion_proximate) (On task))
(gc-brs-literal (Signal safe_point_reachable) (On task))
(gc-brs-literal (Signal state_preservation_route) (On task))
(gc-brs-literal (Signal simpler_route_available) (On task))
(gc-brs-literal (Signal assumption_invalidated) (On task))
(gc-brs-literal (Signal cost_variance_material) (On task))
(gc-brs-literal (Signal scope_exceeds_stage) (On task))
(gc-brs-literal (Signal owner_mismatch) (On task))
(gc-brs-literal (Signal no_safe_step) (On task))
(gc-brs-literal (Signal ethics_consilience_broken) (On task))
(gc-brs-literal (Signal sunk_cost_argument) (On task))
; The checkpoint store restoring task state is a fact about the checkpoint, which a restore drill
; establishes and a reading can never settle.
(gc-brs-literal (Statement (sn p so "restores" ((arg s (sn c "checkpoint-store")) (arg o (sn c "task-state"))))) (On checkpoint))

; A handoff moves the focal task from the seat that owns it to the receiving seat, keeping its
; occupancy, contribution and review links: §3.4's seat holds the tasks it owns, so the work
; changing hands is the task changing seats. The procedure library's hand step binds T, A and B to
; task, seat and receiving_seat.
; am[implements a-rel-tc-topology-1018@c19624] am[implements a-ev-pk-bind-table-1018@761a0f]
(gc-brs-reaction handoff
  (Redex (Bigraph (Inner 3 ()) (Outer 2 (occ con rev)) (Nodes (N A Seat) (N B Seat) (N T Task))
                  (Place (In A (Root 0)) (In B (Root 1)) (In T A) (In (Site 0) A) (In (Site 1) B) (In (Site 2) T))
                  (Link (P T 0 (Name occ)) (P T 1 (Name con)) (P T 2 (Name rev)))))
  (Reactum (Bigraph (Inner 3 ()) (Outer 2 (occ con rev)) (Nodes (N A Seat) (N B Seat) (N T Task))
                    (Place (In A (Root 0)) (In B (Root 1)) (In T B) (In (Site 0) A) (In (Site 1) B) (In (Site 2) T))
                    (Link (P T 0 (Name occ)) (P T 1 (Name con)) (P T 2 (Name rev)))))
  (Eta (0 0) (1 1) (2 2))
  (Conditions))
