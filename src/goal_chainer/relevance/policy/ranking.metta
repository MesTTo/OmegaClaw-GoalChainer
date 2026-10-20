; Purpose: the relevance review's ranking policy, the five steps of the goal relevance governor
; paper's section 9.3 with a motivational step after the second for a domain that declares needs,
; its section 13.2 escalation triggers, the five dispositions and the licensed authority ceiling,
; over one compiled review.
;
; MeTTa owns this policy and Python only hands it typed data and renders what it answers
; (c-integrate-user-metta-policy-1016). Every name, band, kind and estimator class below is a
; string, as prelude.metta's data rule says; a MODE is one of lib_deontic's symbols F, O and P,
; which the shared status rule in policy/goalchainer_deontic.metta reads. The input is
;
;   (RankInput (Goals ((Goal ID KIND PRIORITY SOURCE) ...))      declaration order
;              (Dimensions (DIM ...))                            declaration order
;              (Tiers ((Tier ID RANK) ...))
;              (Ceilings ((Ceiling ESTIMATOR TIER) ...))
;              (Required (GOAL ...)) (Obligations (ACTION ...)) (OtherDilemmas (INDEX ...))
;              (Conflicted (SIGNAL ...))                          readset signals only
;              (Support ((Support SIGNAL (ESTIMATOR ...)) ...))   definite signals
;              (Candidates ((Candidate ID TIER (MODE ...) DILEMMA
;                                      ((Effect DIM BAND ESTIMATOR) ...)
;                                      ((Contrib GOAL BAND) ...)
;                                      (SIGNAL ...)) ...))        its readset
;              (Motivation None | (Regulation ((Regulates NEED GOAL) ...)
;                                             ((NeedState NEED STATE DISTANCE) ...)
;                                             ((Reduction ACTION NEED (Interval LOW HIGH)
;                                                         (CLASS ...) CLASS|None) ...))))
;
; and `(gc-relevance-rank INPUT)` answers one
;
;   (Ranking DISPOSITION SELECTED DECIDED-AT (Steps ...) (Escalations ...) (Contested ...)
;            (Blockers ...) TENSION (Unserved ...) (Appraisals ...) (Display ...)
;            (Standing ((For ID STATUS) ...))       every candidate's status, by the shared rule
;            NoHold | (Hold (Satisfied (NEED ...)) (Unreduced (NEED ...))))
;
; A goal a declared need regulates is valued by the need, not by its contribution band: its path is
; (NeedPath GOAL KIND PRIORITY SOURCE NEED VALUE), VALUE the goal's declared priority times the
; reduction of the need's urgency the action is expected to bring, an interval wherever the need's
; level or the action's change is unknown (motivation.metta). Every path's value, and so every
; aggregate and motive, is an (Interval LOW HIGH), a band path's a point, so a review of a domain
; without needs ranks as before; comparisons read a winner's low against a rival's high
; (c-v2m-interval-machinery-1019), which treats one unknown level shared by two candidates as two
; independent ones, a sound and conservative lead (c-v2m-lead-conservative-1019). Steps 1 and 2
; read no value, so no need can admit a forbidden action or cancel a duty
; (c-v2m-hard-steps-ignore-priority-1019). STATE is the snapshot's level state: "observed",
; "unobserved", "expired" or "conflicted", and DISTANCE an observed level's band distance x(n) or
; None for any other state.
;
; Reasons come back as typed constructors, never prose, so a host can branch on them.
; am[implements a-rel-ranking-1016@334372] am[rests-on c-integrate-user-metta-policy-1016@9eb3d0]
; am[rests-on c-rel-strings-inert-1016@947e27] am[implements a-rel-status-symbols-1016@0aaea4]
; am[implements a-v2m-drive-paths-1019@65a7d5] am[implements a-v2m-hold-1019@be4f47]
; am[rests-on c-v2m-interval-machinery-1019@cd9844] am[rests-on c-v2m-lead-conservative-1019@d314ac]
; am[rests-on c-v2m-hard-steps-ignore-priority-1019@3a77a5]

; ---- ordinal bands (section 8.2) ---------------------------------------------------------------
; A band's value is its position on the shared vocabulary's scale, (gc-bands), measured from the
; middle band and divided by the distance from the middle to an end, so the worst band is -1, the
; middle one 0 and the best 1, whatever the scale's odd length. An unknown effect spans that whole
; range.
; am[implements a-rel-nd-vocabulary-down-1018@6e6c8d]

(= (gc-relevance-position $items $item) (gc-relevance-position-from $items $item 0))
(= (gc-relevance-position-from $items $item $at)
   (if (== (car-atom $items) $item) $at (gc-relevance-position-from (cdr-atom $items) $item (+ $at 1))))
(= (gc-relevance-band-value $band)
   (gc-relevance-scaled (gc-relevance-position (gc-bands) $band)
                        (/ (- (size-atom (gc-bands)) 1) 2.0)))
(= (gc-relevance-scaled $position $middle) (/ (- $position $middle) $middle))
(= (gc-relevance-unknown-interval)
   (Interval (gc-relevance-band-value (car-atom (gc-bands)))
             (gc-relevance-band-value (car-atom (gc-relevance-reversed (gc-bands))))))
(= (gc-relevance-reversed $items) (foldl-atom $items () $acc $item (cons-atom $item $acc)))

; ---- reading the input -----------------------------------------------------------------------

(= (gc-relevance-goals (RankInput (Goals $x) $d $t $c $r $o $y $f $s $k $m)) $x)
(= (gc-relevance-dimensions (RankInput $g (Dimensions $x) $t $c $r $o $y $f $s $k $m)) $x)
(= (gc-relevance-tiers (RankInput $g $d (Tiers $x) $c $r $o $y $f $s $k $m)) $x)
(= (gc-relevance-ceilings (RankInput $g $d $t (Ceilings $x) $r $o $y $f $s $k $m)) $x)
(= (gc-relevance-required (RankInput $g $d $t $c (Required $x) $o $y $f $s $k $m)) $x)
(= (gc-relevance-obligations (RankInput $g $d $t $c $r (Obligations $x) $y $f $s $k $m)) $x)
(= (gc-relevance-other-dilemmas (RankInput $g $d $t $c $r $o (OtherDilemmas $x) $f $s $k $m)) $x)
(= (gc-relevance-conflicted (RankInput $g $d $t $c $r $o $y (Conflicted $x) $s $k $m)) $x)
(= (gc-relevance-support (RankInput $g $d $t $c $r $o $y $f (Support $x) $k $m)) $x)
(= (gc-relevance-candidates (RankInput $g $d $t $c $r $o $y $f $s (Candidates $x) $m)) $x)
(= (gc-relevance-motivation (RankInput $g $d $t $c $r $o $y $f $s $k (Motivation $x))) $x)

(= (gc-relevance-id (Candidate $id $tier $modes $dilemma $effects $contribs $readset)) $id)
(= (gc-relevance-tier (Candidate $id $tier $modes $dilemma $effects $contribs $readset)) $tier)
(= (gc-relevance-modes (Candidate $id $tier $modes $dilemma $effects $contribs $readset)) $modes)
(= (gc-relevance-dilemma (Candidate $id $tier $modes $dilemma $effects $contribs $readset)) $dilemma)
(= (gc-relevance-effects (Candidate $id $tier $modes $dilemma $effects $contribs $readset)) $effects)
(= (gc-relevance-contribs (Candidate $id $tier $modes $dilemma $effects $contribs $readset)) $contribs)
(= (gc-relevance-readset (Candidate $id $tier $modes $dilemma $effects $contribs $readset)) $readset)
(= (gc-relevance-ids $candidates) (map-atom $candidates $c (gc-relevance-id $c)))

(= (gc-relevance-goal-id (Goal $id $kind $priority $source)) $id)
(= (gc-relevance-goal-kind (Goal $id $kind $priority $source)) $kind)
(= (gc-relevance-goal-priority (Goal $id $kind $priority $source)) $priority)
(= (gc-relevance-goal-source (Goal $id $kind $priority $source)) $source)

(= (gc-relevance-effect-dimension (Effect $dimension $band $estimator)) $dimension)
(= (gc-relevance-effect-band (Effect $dimension $band $estimator)) $band)
(= (gc-relevance-effect-estimator (Effect $dimension $band $estimator)) $estimator)
(= (gc-relevance-contrib-goal (Contrib $goal $band)) $goal)
(= (gc-relevance-contrib-band (Contrib $goal $band)) $band)

(= (gc-relevance-kept (Split $kept $removed)) $kept)
(= (gc-relevance-removed (Split $kept $removed)) $removed)
(= (gc-relevance-elim-action (Elim $action $reason)) $action)
(= (gc-relevance-elim-reason (Elim $action $reason)) $reason)

; ---- the motivation --------------------------------------------------------------------------
; A domain with needs hands the snapshot's view the ranking reads: which need regulates which goal,
; each need's level state and band distance, and each action's reduction interval of each need's
; urgency with the estimator classes of the level and change it rests on. None for a domain
; without needs, whose review has no motivational step.
; am[implements a-v2m-drive-paths-1019@65a7d5] am[implements a-v2m-hold-1019@be4f47]

(= (gc-relevance-regulating? $input) (not (== (gc-relevance-motivation $input) None)))
(= (gc-relevance-regulated $input) (gc-relevance-regulated-of (gc-relevance-motivation $input)))
(= (gc-relevance-regulated-of None) ())
(= (gc-relevance-regulated-of (Regulation $regulated $states $reductions)) $regulated)
(= (gc-relevance-need-states $input) (gc-relevance-need-states-of (gc-relevance-motivation $input)))
(= (gc-relevance-need-states-of None) ())
(= (gc-relevance-need-states-of (Regulation $regulated $states $reductions)) $states)
(= (gc-relevance-reductions $input) (gc-relevance-reductions-of (gc-relevance-motivation $input)))
(= (gc-relevance-reductions-of None) ())
(= (gc-relevance-reductions-of (Regulation $regulated $states $reductions)) $reductions)

(= (gc-relevance-regulates-need (Regulates $need $goal)) $need)
(= (gc-relevance-regulates-goal (Regulates $need $goal)) $goal)
(= (gc-relevance-need-for $input $goal)
   (gc-relevance-first
     (map-atom (filter-atom (gc-relevance-regulated $input) $r (== (gc-relevance-regulates-goal $r) $goal)) $s
       (gc-relevance-regulates-need $s))))

(= (gc-relevance-state-need (NeedState $need $state $distance)) $need)
(= (gc-relevance-state-state (NeedState $need $state $distance)) $state)
(= (gc-relevance-state-distance (NeedState $need $state $distance)) $distance)
(= (gc-relevance-unknown-needs $input)
   (map-atom (filter-atom (gc-relevance-need-states $input) $s (not (== (gc-relevance-state-state $s) "observed"))) $t
     (gc-relevance-state-need $t)))
(= (gc-relevance-observed-needs $input)
   (filter-atom (gc-relevance-need-states $input) $s (== (gc-relevance-state-state $s) "observed")))

(= (gc-relevance-reduction-action (Reduction $action $need $interval $levels $changes)) $action)
(= (gc-relevance-reduction-need (Reduction $action $need $interval $levels $changes)) $need)
(= (gc-relevance-reduction-interval (Reduction $action $need $interval $levels $changes)) $interval)
(= (gc-relevance-reduction-of $input $c $need)
   (car-atom (filter-atom (gc-relevance-reductions $input) $r
               (and (== (gc-relevance-reduction-action $r) (gc-relevance-id $c)) (== (gc-relevance-reduction-need $r) $need)))))

; (Judged CANDIDATE None|(Some REASON)) ... -> (Split (KEPT ...) ((Elim ID REASON) ...)), in order.
(= (gc-relevance-judged-kept (Judged $c $verdict)) (== $verdict None))
(= (gc-relevance-judged-candidate (Judged $c $verdict)) $c)
(= (gc-relevance-judged-elim (Judged $c (Some $reason))) (Elim (gc-relevance-id $c) $reason))
(= (gc-relevance-partition $judged)
   (gc-relevance-split-of (partition (|-> ($j) (gc-relevance-judged-kept $j)) $judged)))
(= (gc-relevance-split-of ($kept $removed))
   (Split (map-atom $kept $k (gc-relevance-judged-candidate $k))
          (map-atom $removed $m (gc-relevance-judged-elim $m))))

; ---- deontic standing (step 1) ---------------------------------------------------------------
; An action is admissible only where the theory proves it permitted and its status in the shared
; order stays below forbidden, so a prohibition, a clash with one and a dilemma each remove it,
; and so does a defeater that withdraws a permission. The reason names what the theory proved.
; am[implements a-rel-admissibility-order-1017@baaefe]

; am[implements a-rel-member-once-1018@45ebae]
(= (gc-relevance-has-mode $c $mode) (gc-has (gc-relevance-modes $c) $mode))
(= (gc-relevance-inadmissibility $c)
   (if (gc-status-at-least forbidden (gc-relevance-status $c))
       (Some (gc-relevance-blocked-reason $c))
       (if (gc-relevance-has-mode $c P)
           None
           (if (gc-relevance-has-mode $c O) (Some PermissionWithdrawn) (Some NoPermission)))))
; What put the action at or above forbidden: F with O, F with P, F alone, or a dilemma.
(= (gc-relevance-blocked-reason $c)
   (if (gc-relevance-has-mode $c F)
       (if (gc-relevance-has-mode $c O)
           ObligedAndForbidden
           (if (gc-relevance-has-mode $c P) PermittedAndForbidden Forbidden))
       InDilemma))

(= (gc-relevance-obliged $c) (gc-relevance-has-mode $c O))

; An action's deontic status is the shared rule's, which the incident decision and the scorer
; read too: conflict for a dilemma or for F with O or P, then forbidden, obligated, permitted or
; unregulated. Its conflict is this review's conflicted standing, a section 13.2 trigger.
; am[implements a-rel-status-answer-1016@c302a1] am[implements a-rel-status-conflict-1016@abec85]
; am[rests-on c-ev-deontic-clash-semantics@dc6408]
(= (gc-relevance-status $c) (gc-deontic-status (gc-relevance-modes $c) (gc-relevance-dilemma $c)))
(= (gc-relevance-conflicted-standing $c) (== (gc-relevance-status $c) conflict))

; ---- goals and dimensions --------------------------------------------------------------------
; A goal with no derived contribution is no path, a point at zero; a dimension with no derived
; effect is unknown, the whole interval [-1, 1], and never neutral.

(= (gc-relevance-contribution $c $goal)
   (gc-relevance-first
     (map-atom (filter-atom (gc-relevance-contribs $c) $x (== (gc-relevance-contrib-goal $x) $goal)) $y
       (gc-relevance-contrib-band $y))))

(= (gc-relevance-effect-values $c $dimension)
   (map-atom (filter-atom (gc-relevance-effects $c) $e (== (gc-relevance-effect-dimension $e) $dimension)) $f
     (gc-relevance-band-value (gc-relevance-effect-band $f))))

(= (gc-relevance-known $c $dimension) (not (== (gc-relevance-effect-values $c $dimension) ())))

(= (gc-relevance-interval $c $dimension) (gc-relevance-interval-of (gc-relevance-effect-values $c $dimension)))
(= (gc-relevance-interval-of $values)
   (if (== $values ()) (gc-relevance-unknown-interval) (Interval (min-atom $values) (max-atom $values))))
(= (gc-relevance-low (Interval $low $high)) $low)
(= (gc-relevance-high (Interval $low $high)) $high)
; The midpoint, correctly rounded and finite for any finite ends, as libc++'s std::midpoint computes
; it (c-v2m-midpoint-libcxx-1020): (LOW + HIGH) / 2 while neither end exceeds half the largest
; double, so the sum cannot overflow; otherwise each end halved, except one below twice the least
; normal double, whose halving could round and which then joins unhalved. A path of priority 1e308
; is the point [1e308, 1e308], whose ends' sum overflows, and its midpoint is 1e308.
(= (gc-relevance-midpoint (Interval $low $high))
   (gc-relevance-midpoint-of (abs-math $low) (abs-math $high) $low $high))
(= (gc-relevance-midpoint-of $l $h $low $high)
   (if (and (<= $l 8.988465674311579e307) (<= $h 8.988465674311579e307))
       (/ (+ $low $high) 2.0)
       (if (< $l 4.450147717014403e-308)
           (+ $low (/ $high 2.0))
           (if (< $h 4.450147717014403e-308)
               (+ (/ $low 2.0) $high)
               (+ (/ $low 2.0) (/ $high 2.0))))))
(= (gc-relevance-wide (Interval $low $high)) (< $low $high))
(= (gc-relevance-point $value) (Interval $value $value))
; A nonnegative priority scales an interval without reordering its ends.
(= (gc-relevance-scaled-interval $weight (Interval $low $high)) (Interval (* $weight $low) (* $weight $high)))

; A goal a need regulates is always a need path, valued through the action's reduction of that
; need's urgency, unknown included; any other goal is a band path where the theory derived a
; contribution, and no path otherwise.
(= (gc-relevance-paths $input $goals $c)
   (if (== $goals ())
       ()
       (gc-relevance-path-step $input (car-atom $goals) $c
         (gc-relevance-need-for $input (gc-relevance-goal-id (car-atom $goals)))
         (gc-relevance-paths $input (cdr-atom $goals) $c))))
(= (gc-relevance-path-step $input $goal $c None $rest)
   (gc-relevance-band-step $goal (gc-relevance-contribution $c (gc-relevance-goal-id $goal)) $rest))
(= (gc-relevance-path-step $input $goal $c (Some $need) $rest)
   (cons-atom (NeedPath (gc-relevance-goal-id $goal) (gc-relevance-goal-kind $goal) (gc-relevance-goal-priority $goal)
                        (gc-relevance-goal-source $goal) $need
                        (gc-relevance-scaled-interval (gc-relevance-goal-priority $goal)
                          (gc-relevance-reduction-interval (gc-relevance-reduction-of $input $c $need))))
              $rest))
(= (gc-relevance-band-step $goal None $rest) $rest)
(= (gc-relevance-band-step $goal (Some $band) $rest)
   (cons-atom (Path (gc-relevance-goal-id $goal) (gc-relevance-goal-kind $goal) (gc-relevance-goal-priority $goal)
                    (gc-relevance-goal-source $goal) $band
                    (gc-relevance-point (* (gc-relevance-goal-priority $goal) (gc-relevance-band-value $band))))
              $rest))

(= (gc-relevance-path-kind (Path $goal $kind $priority $source $band $value)) $kind)
(= (gc-relevance-path-kind (NeedPath $goal $kind $priority $source $need $value)) $kind)
(= (gc-relevance-path-value (Path $goal $kind $priority $source $band $value)) $value)
(= (gc-relevance-path-value (NeedPath $goal $kind $priority $source $need $value)) $value)

; ---- aggregation rules (section 9.5) -----------------------------------------------------------
; Each rule folds an action's goal-path values, priority times band value, with its semiring's
; combine: sum-over-paths adds them, as pymetta's bag carrier does, and max-over-parents keeps
; the largest, as its ranked carrier does, on finite values up to the sign of a zero
; (c-rel-rules-are-carriers-finite-1017). A winner must win under every rule, so the appraisal,
; the motives and the selection all map over this one list.
; A path's value is an interval, and a rule folds its carrier's combine over the lows and over the
; highs apart, which is exact for sums and maxima of independent intervals, so a point folds as
; the number it is and the rule stays the carrier it names.
; am[implements a-rel-aggregation-rules-1017@b47aa6] am[rests-on c-rel-rules-are-carriers-finite-1017@48def8]
; am[implements a-v2m-drive-paths-1019@65a7d5]
(= (gc-relevance-rules)
   ((Aggregation "sum-over-paths" bag + (From 0.0)) (Aggregation "max-over-parents" ranked max FromFirst)))
(= (gc-relevance-rule-name (Aggregation $name $carrier $combine $start)) $name)
(= (gc-relevance-rule-named $name)
   (car-atom (filter-atom (gc-relevance-rules) $r (== (gc-relevance-rule-name $r) $name))))
; An action with no path is worth 0 under every rule by the review's point-at-zero convention,
; which no carrier supplies: pymetta answers nothing for it.
(= (gc-relevance-fold $rule $values) (if (== $values ()) 0.0 (gc-relevance-fold-from $rule $values)))
(= (gc-relevance-fold-interval $rule $values)
   (Interval (gc-relevance-fold $rule (map-atom $values $v (gc-relevance-low $v)))
             (gc-relevance-fold $rule (map-atom $values $w (gc-relevance-high $w)))))
; sum-over-paths starts from 0.0, as gc-relevance-sum does, so paths all worth -0.0 sum to 0.0.
; max-over-parents starts from its first value: 0 is no identity of max over signed values (a
; start at 0 would raise a maximum of -0.2 to 0), and pymetta reads no infinite literal. Each
; step is (COMBINE VALUE ACC), the order of max-atom's max_list, so the maximum is max-atom's.
; am[implements a-rel-fold-start-1017@1dacc6] am[rests-on c-rel-max-atom-is-max-list-1017@be494f]
(= (gc-relevance-fold-from (Aggregation $name $carrier $combine (From $start)) $values)
   (foldl-atom $values $start $acc $v ($combine $v $acc)))
(= (gc-relevance-fold-from (Aggregation $name $carrier $combine FromFirst) $values)
   (foldl-atom (cdr-atom $values) (car-atom $values) $acc $v ($combine $v $acc)))
(= (gc-relevance-aggregate $rule $paths) (gc-relevance-fold-interval $rule (map-atom $paths $p (gc-relevance-path-value $p))))
; Every rule's value for one set of paths, as (By RULE VALUE) in the rules' order.
(= (gc-relevance-by-rule $paths)
   (map-atom (gc-relevance-rules) $r (By (gc-relevance-rule-name $r) (gc-relevance-aggregate $r $paths))))
(= (gc-relevance-by-value $by $name)
   (car-atom (map-atom (filter-atom $by $b (== (gc-relevance-by-name $b) $name)) $x (gc-relevance-by-number $x))))
(= (gc-relevance-by-name (By $name $value)) $name)
(= (gc-relevance-by-number (By $name $value)) $value)
(= (gc-relevance-of-kind $paths $kind) (filter-atom $paths $p (== (gc-relevance-path-kind $p) $kind)))

; Section 9.4's motives: the local one reads the individual goals and the hive one the
; collective goals, the domain's two goal kinds.
(= (gc-relevance-motive-kinds) ((Motive "local" "individual") (Motive "hive" "collective")))
(= (gc-relevance-motive-of (Motive $name $kind) $paths) (Motive $name (gc-relevance-by-rule (gc-relevance-of-kind $paths $kind))))

; ---- authority (section 8.2) -----------------------------------------------------------------
; The action's rung lowered to what the weakest estimate it may rest on can license: its
; effects, and for each definite signal in its readset the strongest of the agreeing readings.

(= (gc-relevance-tier-id (Tier $id $rank)) $id)
(= (gc-relevance-tier-number (Tier $id $rank)) $rank)
(= (gc-relevance-tier-rank $input $tier)
   (gc-relevance-unwrap (gc-relevance-first
     (map-atom (filter-atom (gc-relevance-tiers $input) $t (== (gc-relevance-tier-id $t) $tier)) $u
       (gc-relevance-tier-number $u)))))

(= (gc-relevance-ceiling-estimator (Ceiling $estimator $tier)) $estimator)
(= (gc-relevance-ceiling-tier (Ceiling $estimator $tier)) $tier)
(= (gc-relevance-ceiling-of $input $estimator)
   (gc-relevance-unwrap (gc-relevance-first
     (map-atom (filter-atom (gc-relevance-ceilings $input) $x (== (gc-relevance-ceiling-estimator $x) $estimator)) $y
       (gc-relevance-ceiling-tier $y)))))
(= (gc-relevance-estimator-rank $input $estimator)
   (gc-relevance-tier-rank $input (gc-relevance-ceiling-of $input $estimator)))

(= (gc-relevance-strongest $input $estimators)
   (index-atom (gc-relevance-argmax (map-atom $estimators $e ((gc-relevance-estimator-rank $input $e) $e))) 1))

(= (gc-relevance-support-signal (Support $signal $estimators)) $signal)
(= (gc-relevance-support-estimators (Support $signal $estimators)) $estimators)
(= (gc-relevance-support-of $input $signal)
   (gc-relevance-first
     (map-atom (filter-atom (gc-relevance-support $input) $s (== (gc-relevance-support-signal $s) $signal)) $t
       (gc-relevance-support-estimators $t))))

(= (gc-relevance-bases $input $c)
   (union-atom
     (map-atom (gc-relevance-effects $c) $e
       (Basis "effect" (gc-relevance-effect-dimension $e) (gc-relevance-effect-estimator $e)))
     (union-atom (gc-relevance-reading-bases $input (gc-relevance-readset $c))
                 (gc-relevance-need-bases $input $c))))

; A need path rests on the need's observed level, at the strongest class of the observations
; agreeing on it, and on the action's known change of it, whatever value the reduction takes: on
; [0, 1] with band [0.4, 0.6] a change of +0.1 reduces nothing at 0.45 and worsens the need by
; 0.25 at 0.9, so a reduction of 0 still rests on the level and change it came from
; (c-v2m-zero-reduction-rests-1020).
; am[implements a-v2m-need-authority-1019@52deb8] am[rests-on c-v2m-receipt-calibrated-1019@210aaf]
; am[rests-on c-v2m-zero-reduction-rests-1020@0f4fab]
(= (gc-relevance-need-bases $input $c)
   (flatten-once (map-atom (gc-relevance-regulated $input) $r
     (gc-relevance-reduction-bases $input (gc-relevance-reduction-of $input $c (gc-relevance-regulates-need $r))))))
(= (gc-relevance-reduction-bases $input (Reduction $action $need $interval $levels $changes))
   (union-atom (if (== $levels ()) () ((Basis "need-level" $need (gc-relevance-strongest $input $levels))))
               (map-atom $changes $class (Basis "need-change" $need $class))))

(= (gc-relevance-reading-bases $input $signals)
   (if (== $signals ())
       ()
       (gc-relevance-reading-basis $input (car-atom $signals)
         (gc-relevance-support-of $input (car-atom $signals))
         (gc-relevance-reading-bases $input (cdr-atom $signals)))))
(= (gc-relevance-reading-basis $input $signal None $rest) $rest)
(= (gc-relevance-reading-basis $input $signal (Some $estimators) $rest)
   (cons-atom (Basis "reading" $signal (gc-relevance-strongest $input $estimators)) $rest))

(= (gc-relevance-basis-estimator (Basis $kind $name $estimator)) $estimator)
(= (gc-relevance-limit-of $input (Basis $kind $name $estimator))
   (Limit $kind $name $estimator (gc-relevance-ceiling-of $input $estimator)))
(= (gc-relevance-limit-tier (Limit $kind $name $estimator $tier)) $tier)

(= (gc-relevance-limits $input $c)
   (map-atom
     (filter-atom (gc-relevance-bases $input $c) $b
       (< (gc-relevance-estimator-rank $input (gc-relevance-basis-estimator $b))
          (gc-relevance-tier-rank $input (gc-relevance-tier $c))))
     $d (gc-relevance-limit-of $input $d)))

(= (gc-relevance-licensed $input $c $limits)
   (index-atom
     (foldl-atom $limits ((gc-relevance-tier-rank $input (gc-relevance-tier $c)) (gc-relevance-tier $c))
       $best $limit (gc-relevance-lower $input $best (gc-relevance-limit-tier $limit)))
     1))
(= (gc-relevance-lower $input $best $tier)
   (if (< (gc-relevance-tier-rank $input $tier) (car-atom $best))
       ((gc-relevance-tier-rank $input $tier) $tier)
       $best))

; ---- appraisal: everything about one candidate from that candidate alone -----------------------
; Nothing here reads another candidate, so adding one changes no other appraisal (11.10).

(= (gc-relevance-appraise $input $c)
   (gc-relevance-appraisal $input $c (gc-relevance-paths $input (gc-relevance-goals $input) $c)
     (gc-relevance-limits $input $c)))
; The projection adds the known dimensions' midpoints to the midpoint of the sum over paths.
(= (gc-relevance-appraisal $input $c $paths $limits)
   (Appraisal (gc-relevance-id $c) $paths
              (Aggregates (gc-relevance-by-rule $paths))
              (Motives (map-atom (gc-relevance-motive-kinds) $m (gc-relevance-motive-of $m $paths)))
              (+ (gc-relevance-midpoint (gc-relevance-aggregate (gc-relevance-rule-named "sum-over-paths") $paths))
                 (gc-relevance-sum (map-atom (filter-atom (gc-relevance-dimensions $input) $d (gc-relevance-known $c $d)) $e
                                     (gc-relevance-midpoint (gc-relevance-interval $c $e)))))
              (filter-atom (gc-relevance-dimensions $input) $f (not (gc-relevance-known $c $f)))
              (gc-relevance-tier $c)
              (gc-relevance-licensed $input $c $limits)
              $limits
              (gc-relevance-carrying $paths)))

; Section 9.5: the goal path whose priority carries most of the action's value, if any does, among
; the paths worth more than 0 whatever their unknowns are.
(= (gc-relevance-carrying $paths)
   (gc-relevance-carrying-of (filter-atom $paths $p (> (gc-relevance-low (gc-relevance-path-value $p)) 0))))
(= (gc-relevance-carrying-of $positive)
   (if (== $positive ())
       None
       (Some (index-atom (gc-relevance-argmax (map-atom $positive $p ((gc-relevance-low (gc-relevance-path-value $p)) $p))) 1))))

(= (gc-relevance-appraisal-of $appraisals $id)
   (car-atom (filter-atom $appraisals $a (== (gc-relevance-appraisal-id $a) $id))))
(= (gc-relevance-appraisal-id (Appraisal $id $p $g $m $v $u $t $l $limits $k)) $id)
(= (gc-relevance-appraisal-paths (Appraisal $id $p $g $m $v $u $t $l $limits $k)) $p)
(= (gc-relevance-aggregate-of (Appraisal $id $p (Aggregates $by) $m $v $u $t $l $limits $k) $rule)
   (gc-relevance-by-value $by $rule))
; Every motive's value under every rule, in a fixed order, for the pointwise comparison of step 4.
(= (gc-relevance-motives (Appraisal $id $p $g (Motives $motives) $v $u $t $l $limits $k))
   (flatten-once (map-atom $motives $m (gc-relevance-motive-numbers $m))))
(= (gc-relevance-motive-numbers (Motive $name $by)) (map-atom $by $b (gc-relevance-by-number $b)))
(= (gc-relevance-motive-value (Appraisal $id $p $g (Motives $motives) $v $u $t $l $limits $k) $motive $rule)
   (car-atom (map-atom (filter-atom $motives $m (== (gc-relevance-motive-name $m) $motive)) $x
               (gc-relevance-by-value (gc-relevance-motive-by $x) $rule))))
(= (gc-relevance-motive-name (Motive $name $by)) $name)
(= (gc-relevance-motive-by (Motive $name $by)) $by)
; The tension of step 4 compares what each motive prefers under sum-over-paths, at the midpoint of
; its interval, as the display order reads the projection.
(= (gc-relevance-local $a) (gc-relevance-midpoint (gc-relevance-motive-value $a "local" "sum-over-paths")))
(= (gc-relevance-hive $a) (gc-relevance-midpoint (gc-relevance-motive-value $a "hive" "sum-over-paths")))
(= (gc-relevance-projection (Appraisal $id $p $g $m $v $u $t $l $limits $k)) $v)

; ---- step 2: deterministic lifecycle -----------------------------------------------------------

(= (gc-relevance-harm $c $required)
   (gc-relevance-first (filter-atom (map-atom $required $goal (gc-relevance-harm-to $goal (gc-relevance-contribution $c $goal))) $h
     (not (== $h None)))))
(= (gc-relevance-harm-to $goal None) None)
(= (gc-relevance-harm-to $goal (Some $band))
   (if (< (gc-relevance-band-value $band) 0) (HarmsRequired $goal $band) None))

(= (gc-relevance-lifecycle $input $admissible)
   (gc-relevance-lifecycle-of $input $admissible (filter-atom $admissible $c (gc-relevance-obliged $c))))
(= (gc-relevance-lifecycle-of $input $admissible $obliged)
   (gc-relevance-lifecycle-harm $input
     (if (== $obliged ())
         ()
         (map-atom (filter-atom $admissible $c (not (gc-relevance-obliged $c))) $d
           (Elim (gc-relevance-id $d) (ObligationInForce (gc-relevance-ids $obliged)))))
     (if (== $obliged ()) $admissible $obliged)))
(= (gc-relevance-lifecycle-harm $input $removed $remaining)
   (gc-relevance-join-split $removed
     (gc-relevance-partition (map-atom $remaining $c (Judged $c (gc-relevance-harm $c (gc-relevance-required $input)))))))
(= (gc-relevance-join-split $removed (Split $kept $harmed)) (Split $kept (union-atom $removed $harmed)))

(= (gc-relevance-duty-escalations $admissible $survivors)
   (gc-relevance-duty-escalations-of (filter-atom $admissible $c (gc-relevance-obliged $c)) $survivors))
(= (gc-relevance-duty-escalations-of $obliged $survivors)
   (union-atom (if (> (size-atom $obliged) 1) ((SeveralDuties (gc-relevance-ids $obliged))) ())
               (if (and (not (== $obliged ())) (== $survivors ())) (AllDutiesHarm) ())))

; ---- step 3: Pareto elimination over every goal and dimension either candidate claims ------------
; A wins a coordinate only when its lowest possible value is at least B's highest, so an
; unknown effect can never make B look worse than it is (Borzsonyi et al., ICDE 2001, BNL).

(= (gc-relevance-coordinates $input $c)
   (union-atom
     (map-atom (gc-relevance-goals $input) $g
       (gc-relevance-goal-coordinate-of $input $c $g (gc-relevance-need-for $input (gc-relevance-goal-id $g))))
     (map-atom (gc-relevance-dimensions $input) $d
       (gc-relevance-dimension-coordinate $d (gc-relevance-interval $c $d) (gc-relevance-known $c $d)))))
; A regulated goal is compared on its need's reduction interval, which every candidate claims, since
; an unknown change of a need is never a change of zero.
(= (gc-relevance-goal-coordinate-of $input $c $g None)
   (gc-relevance-goal-coordinate (gc-relevance-goal-id $g) (gc-relevance-contribution $c (gc-relevance-goal-id $g))))
(= (gc-relevance-goal-coordinate-of $input $c $g (Some $need))
   (gc-relevance-need-coordinate $need (gc-relevance-reduction-interval (gc-relevance-reduction-of $input $c $need))))
(= (gc-relevance-need-coordinate $need (Interval $low $high)) (Coordinate (OnNeed $need) $low $high True))
(= (gc-relevance-goal-coordinate $goal None) (Coordinate (OnGoal $goal) 0.0 0.0 False))
(= (gc-relevance-goal-coordinate $goal (Some $band))
   (Coordinate (OnGoal $goal) (gc-relevance-band-value $band) (gc-relevance-band-value $band) True))
(= (gc-relevance-dimension-coordinate $dimension (Interval $low $high) $known)
   (Coordinate (OnDimension $dimension) $low $high $known))

(= (gc-relevance-coordinate-name (Coordinate $name $low $high $claimed)) $name)
(= (gc-relevance-coordinate-low (Coordinate $name $low $high $claimed)) $low)
(= (gc-relevance-coordinate-high (Coordinate $name $low $high $claimed)) $high)
(= (gc-relevance-coordinate-claimed (Coordinate $name $low $high $claimed)) $claimed)

; The coordinates where `better` robustly wins, (Some (NAME ...)), or None when it does not dominate.
(= (gc-relevance-dominates $better $worse) (gc-relevance-dominates-from $better $worse ()))
(= (gc-relevance-dominates-from $better $worse $strict)
   (if (== $better ())
       (if (== $strict ()) None (Some $strict))
       (gc-relevance-dominates-step (car-atom $better) (car-atom $worse) (cdr-atom $better) (cdr-atom $worse) $strict)))
(= (gc-relevance-dominates-step $mine $theirs $better $worse $strict)
   (if (or (gc-relevance-coordinate-claimed $mine) (gc-relevance-coordinate-claimed $theirs))
       (if (< (gc-relevance-coordinate-low $mine) (gc-relevance-coordinate-high $theirs))
           None
           (gc-relevance-dominates-from $better $worse
             (if (> (gc-relevance-coordinate-low $mine) (gc-relevance-coordinate-high $theirs))
                 (union-atom $strict ((gc-relevance-coordinate-name $mine)))
                 $strict)))
       (gc-relevance-dominates-from $better $worse $strict)))

(= (gc-relevance-dominator $input $c $others)
   (if (== $others ())
       None
       (if (== (gc-relevance-id (car-atom $others)) (gc-relevance-id $c))
           (gc-relevance-dominator $input $c (cdr-atom $others))
           (gc-relevance-dominator-step $input $c (car-atom $others) (cdr-atom $others)
             (gc-relevance-dominates (gc-relevance-coordinates $input (car-atom $others)) (gc-relevance-coordinates $input $c))))))
(= (gc-relevance-dominator-step $input $c $other $rest None) (gc-relevance-dominator $input $c $rest))
(= (gc-relevance-dominator-step $input $c $other $rest (Some $strict)) (Some (DominatedBy (gc-relevance-id $other) $strict)))

(= (gc-relevance-pareto $input $candidates)
   (gc-relevance-partition (map-atom $candidates $c (Judged $c (gc-relevance-dominator $input $c $candidates)))))

; ---- step 2b: motivational relevance, for a domain with needs (c-v2m-hard-steps-ignore-priority-1019) ----
; With no obligation in force, a candidate none of whose goal paths could be worth more than 0,
; whatever its unknowns are, has no motive: every need it touches is satisfied, made worse or
; regulates a goal of priority 0, whose paths are worth 0 whatever the reduction, and no
; unregulated goal gains, so it leaves (c-v2-satisfied-single-candidate-case-1019). An obliged
; candidate is never judged here, so a duty survives a satisfied agent, and a path whose high is
; above 0 keeps its candidate, so an unknown need never reads as satisfied.
; am[implements a-v2m-hold-1019@be4f47] am[rests-on c-v2-satisfied-single-candidate-case-1019@2461e5]
; am[addresses i-v2r-priority-zero-unserved-1020]
(= (gc-relevance-unmotivated $paths)
   (gc-relevance-all (map-atom $paths $p (<= (gc-relevance-high (gc-relevance-path-value $p)) 0))))
(= (gc-relevance-motive-verdict $appraisals $c)
   (if (gc-relevance-unmotivated (gc-relevance-appraisal-paths (gc-relevance-appraisal-of $appraisals (gc-relevance-id $c))))
       (Some Unmotivated)
       None))
(= (gc-relevance-motivated-step $input $appraisals $candidates)
   (if (and (gc-relevance-regulating? $input) (not (gc-relevance-any (map-atom $candidates $c (gc-relevance-obliged $c)))))
       (gc-relevance-partition (map-atom $candidates $d (Judged $d (gc-relevance-motive-verdict $appraisals $d))))
       (Split $candidates ())))
; A proposal of a domain with needs must be better than holding under every aggregation rule
; whatever its unknowns are, unless it discharges a duty; otherwise the review escalates, naming the
; needs whose unknown level or change could make it no better.
(= (gc-relevance-robustly-motivated $appraisals $c)
   (gc-relevance-all (map-atom (gc-relevance-rules) $r
     (> (gc-relevance-low (gc-relevance-aggregate-of (gc-relevance-appraisal-of $appraisals (gc-relevance-id $c))
                                                    (gc-relevance-rule-name $r)))
        0))))
(= (gc-relevance-motive-escalations $input $appraisals None) ())
(= (gc-relevance-motive-escalations $input $appraisals (Some $c))
   (if (or (not (gc-relevance-regulating? $input))
           (or (gc-relevance-obliged $c) (gc-relevance-robustly-motivated $appraisals $c)))
       ()
       ((NotRobustlyMotivated (gc-relevance-id $c) (gc-relevance-uncertain-needs $input ($c))))))
; The needs, in declaration order, whose unknown level or change leaves some of the candidates'
; reductions a range rather than a point: what an observation or a learned change could settle.
; am[implements a-v2r-undecided-need-named-1020]
(= (gc-relevance-uncertain-needs $input $candidates)
   (map-atom (filter-atom (gc-relevance-regulated $input) $r
               (gc-relevance-any (map-atom $candidates $c
                 (gc-relevance-wide (gc-relevance-reduction-interval (gc-relevance-reduction-of $input $c (gc-relevance-regulates-need $r)))))))
             $s (gc-relevance-regulates-need $s)))
; Step 2b removing every candidate holds, unless a need's level is unknown: what an unknown level
; needs is an observation, so the review escalates rather than call the agent settled
; (c-v2m-unknown-never-holds-1019).
; am[rests-on c-v2m-unknown-never-holds-1019@7b14f5]
(= (gc-relevance-hold-escalations $input $s2 $s2b)
   (if (and (gc-relevance-regulating? $input)
            (and (not (== $s2 ())) (and (== $s2b ()) (not (== (gc-relevance-unknown-needs $input) ())))))
       ((NeedsUnknown (gc-relevance-unknown-needs $input)))
       ()))
; A hold names every observed need inside its band as satisfied and every one outside it as
; unreduced: no remaining candidate's path through it is worth more than 0, since none reduces it or
; the goal it regulates has priority 0.
; am[implements a-v2m-hold-1019@be4f47] am[addresses i-v2r-priority-zero-unserved-1020]
(= (gc-relevance-hold $input $s2 $s2b)
   (if (and (gc-relevance-regulating? $input) (and (not (== $s2 ())) (== $s2b ())))
       (Hold (Satisfied (map-atom (filter-atom (gc-relevance-observed-needs $input) $s (<= (gc-relevance-state-distance $s) 0)) $t
                          (gc-relevance-state-need $t)))
             (Unreduced (map-atom (filter-atom (gc-relevance-observed-needs $input) $u (> (gc-relevance-state-distance $u) 0)) $v
                          (gc-relevance-state-need $v))))
       NoHold))
(= (gc-relevance-motive-steps $input $s2b $step2b)
   (if (gc-relevance-regulating? $input)
       ((Step "motivational relevance" (gc-relevance-ids $s2b) (gc-relevance-removed $step2b)))
       ()))

; ---- step 4: motivational reconciliation ---------------------------------------------------------
; Local and hive motives stay apart; a candidate leaves only when another is at least as good on
; both, under both aggregation rules, and better somewhere.

(= (gc-relevance-motive-dominator $appraisals $c $others)
   (if (== $others ())
       None
       (if (gc-relevance-motive-beats $appraisals (car-atom $others) $c)
           (Some (MotivesPrefer (gc-relevance-id (car-atom $others))))
           (gc-relevance-motive-dominator $appraisals $c (cdr-atom $others)))))
(= (gc-relevance-motive-beats $appraisals $other $c)
   (and (not (== (gc-relevance-id $other) (gc-relevance-id $c)))
        (gc-relevance-pointwise-beats
          (gc-relevance-motives (gc-relevance-appraisal-of $appraisals (gc-relevance-id $other)))
          (gc-relevance-motives (gc-relevance-appraisal-of $appraisals (gc-relevance-id $c))))))
(= (gc-relevance-pointwise-beats $theirs $mine)
   (and (gc-relevance-all (map-atom (zip $theirs $mine) $pair (gc-relevance-at-least $pair)))
        (gc-relevance-any (map-atom (zip $theirs $mine) $other (gc-relevance-above $other)))))
; Another candidate's motive is at least as good as this one's only when its low reaches this one's
; high, whatever either's unknowns are; for points that is the plain comparison.
(= (gc-relevance-at-least ($theirs $mine)) (>= (gc-relevance-low $theirs) (gc-relevance-high $mine)))
(= (gc-relevance-above ($theirs $mine)) (> (gc-relevance-low $theirs) (gc-relevance-high $mine)))

(= (gc-relevance-motive-front $appraisals $candidates)
   (gc-relevance-partition (map-atom $candidates $c (Judged $c (gc-relevance-motive-dominator $appraisals $c $candidates)))))

(= (gc-relevance-tension $appraisals $survivors)
   (if (> (size-atom $survivors) 1)
       (gc-relevance-tension-of
         (index-atom (gc-relevance-argmax (map-atom $survivors $c ((gc-relevance-local (gc-relevance-appraisal-of $appraisals (gc-relevance-id $c))) (gc-relevance-id $c)))) 1)
         (index-atom (gc-relevance-argmax (map-atom $survivors $d ((gc-relevance-hive (gc-relevance-appraisal-of $appraisals (gc-relevance-id $d))) (gc-relevance-id $d)))) 1))
       NoTension))
(= (gc-relevance-tension-of $local $hive) (if (== $local $hive) NoTension (Tension $local $hive)))

; ---- step 5: a projection no unknown can reverse ---------------------------------------------------

(= (gc-relevance-least-lead $input $appraisals $rule $winner $rival)
   (+ (- (gc-relevance-low (gc-relevance-aggregate-of (gc-relevance-appraisal-of $appraisals (gc-relevance-id $winner)) $rule))
         (gc-relevance-high (gc-relevance-aggregate-of (gc-relevance-appraisal-of $appraisals (gc-relevance-id $rival)) $rule)))
      (gc-relevance-sum
        (map-atom (filter-atom (gc-relevance-dimensions $input) $d
                    (or (gc-relevance-known $winner $d) (gc-relevance-known $rival $d)))
                  $e (- (gc-relevance-low (gc-relevance-interval $winner $e)) (gc-relevance-high (gc-relevance-interval $rival $e)))))))

(= (gc-relevance-decisive $input $appraisals $rule $candidates)
   (gc-relevance-first (filter-atom $candidates $w
     (gc-relevance-all (map-atom (filter-atom $candidates $s (not (== (gc-relevance-id $s) (gc-relevance-id $w)))) $t
                         (> (gc-relevance-least-lead $input $appraisals $rule $w $t) 0))))))

(= (gc-relevance-slack $input $candidates)
   (filter-atom (gc-relevance-dimensions $input) $d (gc-relevance-slack-on $candidates $d)))
(= (gc-relevance-slack-on $candidates $d)
   (or (and (gc-relevance-any (map-atom $candidates $c (gc-relevance-known $c $d)))
            (not (gc-relevance-all (map-atom $candidates $e (gc-relevance-known $e $d)))))
       (gc-relevance-any (map-atom (filter-atom $candidates $f (gc-relevance-known $f $d)) $g
                           (gc-relevance-wide (gc-relevance-interval $g $d))))))

; (Selection CHOICE ESCALATIONS REMOVED), CHOICE being (Some CANDIDATE) or None.
(= (gc-relevance-select $input $appraisals $survivors)
   (if (== (size-atom $survivors) 1)
       (Selection (Some (car-atom $survivors)) () ())
       (if (== $survivors ())
           (Selection None () ())
           (gc-relevance-select-by $input $survivors
             (map-atom (gc-relevance-rules) $r
               (Decided (gc-relevance-rule-name $r)
                        (gc-relevance-decisive $input $appraisals (gc-relevance-rule-name $r) $survivors)))))))
; Every rule must name one decisive winner and all must name the same one (section 9.5). A rule
; that names none leaves the projection open, and the reason names what could still reverse it: the
; dimensions with unknown or conflicting effects and the needs whose unknown level or change leaves
; a survivor's reduction a range; rules naming different winners disagree.
; am[implements a-v2r-undecided-need-named-1020]
(= (gc-relevance-select-by $input $survivors $decided)
   (gc-relevance-select-from $input $survivors $decided
     (map-atom (filter-atom $decided $d (== (gc-relevance-decided-choice $d) None)) $e (gc-relevance-decided-rule $e))))
(= (gc-relevance-select-from $input $survivors $decided $open)
   (if (not (== $open ()))
       (Selection None ((NotDecisive (gc-relevance-ids $survivors) $open (gc-relevance-slack $input $survivors)
                                     (gc-relevance-uncertain-needs $input $survivors)))
                  ())
       (gc-relevance-select-agreed $survivors $decided
         (unique-atom (map-atom $decided $f (gc-relevance-id (gc-relevance-unwrap (gc-relevance-decided-choice $f))))))))
(= (gc-relevance-select-agreed $survivors $decided $winners)
   (if (== (size-atom $winners) 1)
       (Selection (gc-relevance-decided-choice (car-atom $decided)) ()
         (map-atom (filter-atom $survivors $c (not (== (gc-relevance-id $c) (car-atom $winners)))) $d
           (Elim (gc-relevance-id $d) (ProjectionLead (car-atom $winners)))))
       (Selection None ((AggregationDisagree
                          (map-atom $decided $g
                            (Selects (gc-relevance-decided-rule $g) (gc-relevance-id (gc-relevance-unwrap (gc-relevance-decided-choice $g))))))) ())))
(= (gc-relevance-decided-rule (Decided $rule $choice)) $rule)
(= (gc-relevance-decided-choice (Decided $rule $choice)) $choice)

(= (gc-relevance-choice (Selection $choice $escalations $removed)) $choice)
(= (gc-relevance-selection-escalations (Selection $choice $escalations $removed)) $escalations)
(= (gc-relevance-selection-removed (Selection $choice $escalations $removed)) $removed)
(= (gc-relevance-final None $survivors) $survivors)
(= (gc-relevance-final (Some $c) $survivors) ($c))
(= (gc-relevance-choice-id None) None)
(= (gc-relevance-choice-id (Some $c)) (gc-relevance-id $c))

; ---- escalation triggers outside the ranking steps (section 13.2) -----------------------------------

(= (gc-relevance-reason-of $removed $id)
   (gc-relevance-reason-or-missing
     (gc-relevance-first (filter-atom $removed $e (== (gc-relevance-elim-action $e) $id)))))
(= (gc-relevance-reason-or-missing None) NotCandidate)
(= (gc-relevance-reason-or-missing (Some $elim)) (gc-relevance-elim-reason $elim))

(= (gc-relevance-conflict-claims $c $d)
   (map-atom (filter-atom (gc-relevance-effects $c) $e (== (gc-relevance-effect-dimension $e) $d)) $f
     (Claim (gc-relevance-effect-band $f) (gc-relevance-effect-estimator $f))))
(= (gc-relevance-claim-band (Claim $band $estimator)) $band)
(= (gc-relevance-estimator-conflicts $candidates)
   (flatten-once (map-atom $candidates $c
     (map-atom (filter-atom (unique-atom (map-atom (gc-relevance-effects $c) $e (gc-relevance-effect-dimension $e))) $d
                 (> (size-atom (unique-atom (map-atom (gc-relevance-conflict-claims $c $d) $claim (gc-relevance-claim-band $claim)))) 1))
               $f (EstimatorConflict (gc-relevance-id $c) $f (gc-relevance-conflict-claims $c $f))))))

; ---- the sequence ----------------------------------------------------------------------------------

(= (gc-relevance-step-name (Step $name $survivors $removed)) $name)
(= (gc-relevance-step-size (Step $name $survivors $removed)) (size-atom $survivors))
(= (gc-relevance-decided-at $steps)
   (gc-relevance-unwrap (gc-relevance-first
     (map-atom (filter-atom $steps $s (== (gc-relevance-step-size $s) 1)) $t (gc-relevance-step-name $t)))))

(= (gc-relevance-disposition $escalations $candidates $s2 $s2b $choice)
   (if (not (== $escalations ()))
       "escalate"
       (if (== $candidates ())
           "no-candidates"
           (if (== $s2 ())
               "blocked"
               (if (== $s2b ()) "hold" (if (== $choice None) "blocked" "propose"))))))

; Highest projection first; sort-by is stable, so equal projections keep declaration order.
(= (gc-relevance-display $appraisals $survivors)
   (map-atom (sort-by (|-> ($c) (gc-relevance-display-key $appraisals $c)) $survivors) $d
     (Shown (gc-relevance-id $d) (gc-relevance-projection (gc-relevance-appraisal-of $appraisals (gc-relevance-id $d))))))
(= (gc-relevance-display-key $appraisals $c)
   (- 0 (gc-relevance-projection (gc-relevance-appraisal-of $appraisals (gc-relevance-id $c)))))

; am[implements a-rel-mig-typed-entries-1018@c150af]
(: gc-relevance-rank (-> Atom Expression))
(= (gc-relevance-rank $input)
   (gc-relevance-rank-steps $input (gc-relevance-candidates $input)
     (map-atom (gc-relevance-candidates $input) $c (gc-relevance-appraise $input $c))))

; am[implements a-rel-member-once-1018@45ebae]
(= (gc-relevance-rank-steps $input $candidates $appraisals)
   (let* (($step1 (gc-relevance-partition (map-atom $candidates $c (Judged $c (gc-relevance-inadmissibility $c)))))
          ($s1 (gc-relevance-kept $step1))
          ($r1 (gc-relevance-removed $step1))
          ($step2 (gc-relevance-lifecycle $input $s1))
          ($s2 (gc-relevance-kept $step2))
          ($step2b (gc-relevance-motivated-step $input $appraisals $s2))
          ($s2b (gc-relevance-kept $step2b))
          ($step3 (gc-relevance-pareto $input $s2b))
          ($s3 (gc-relevance-kept $step3))
          ($step4 (gc-relevance-motive-front $appraisals $s3))
          ($s4 (gc-relevance-kept $step4))
          ($selection (gc-relevance-select $input $appraisals $s4))
          ($choice (gc-relevance-choice $selection))
          ($final (gc-relevance-final $choice $s4))
          ; The paper's section 9.3 names for the five steps, with the motivational step after the
          ; second for a domain with needs.
          ($steps (union-atom
                    ((Step "deontic admissibility" (gc-relevance-ids $s1) $r1)
                     (Step "deterministic lifecycle" (gc-relevance-ids $s2) (gc-relevance-removed $step2)))
                    (union-atom
                      (gc-relevance-motive-steps $input $s2b $step2b)
                      ((Step "Pareto elimination" (gc-relevance-ids $s3) (gc-relevance-removed $step3))
                       (Step "motivational reconciliation" (gc-relevance-ids $s4) (gc-relevance-removed $step4))
                       (Step "tie-breaking projection" (gc-relevance-ids $final) (gc-relevance-selection-removed $selection))))))
          ($escalations (unique-atom (flatten-once
             ((map-atom (gc-relevance-conflicted $input) $x (EvidenceConflict $x))
              (map-atom (gc-relevance-other-dilemmas $input) $y (OtherDilemma $y))
              (map-atom (filter-atom $candidates $z (gc-relevance-conflicted-standing $z)) $w
                (CandidateConflict (gc-relevance-id $w) (gc-relevance-reason-of $r1 (gc-relevance-id $w))))
              (map-atom (filter-atom (gc-relevance-obligations $input) $a (not (gc-has (gc-relevance-ids $s1) $a))) $b
                (UndischargedDuty $b (gc-relevance-reason-of $r1 $b)))
              (gc-relevance-duty-escalations $s1 $s2)
              (gc-relevance-estimator-conflicts $s4)
              (gc-relevance-selection-escalations $selection)
              (gc-relevance-hold-escalations $input $s2 $s2b)
              (gc-relevance-motive-escalations $input $appraisals $choice)))))
          ($disposition (gc-relevance-disposition $escalations $candidates $s2 $s2b $choice)))
     (Ranking $disposition
              (if (== $disposition "propose") (gc-relevance-choice-id $choice) None)
              (if (== $disposition "propose") (gc-relevance-decided-at $steps) None)
              (Steps $steps)
              (Escalations $escalations)
              (Contested (if (== $disposition "escalate") (gc-relevance-ids $s4) ()))
              (Blockers (if (== $disposition "blocked") (union-atom $r1 (gc-relevance-removed $step2)) ()))
              (gc-relevance-tension $appraisals $s4)
              (Unserved (filter-atom (gc-relevance-required $input) $g
                          (not (gc-relevance-any (map-atom $final $h (not (== (gc-relevance-contribution $h $g) None)))))))
              (Appraisals $appraisals)
              (Display (gc-relevance-display $appraisals $s4))
              (Standing (map-atom $candidates $c (For (gc-relevance-id $c) (gc-relevance-status $c))))
              (if (== $disposition "hold") (gc-relevance-hold $input $s2 $s2b) NoHold))))
