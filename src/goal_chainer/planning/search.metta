; Purpose: the planning projection's search over bigraph states (ai-planning-projection.md proposal 3,
; sections 5 and 6): the least plan under the scheduling cost, else the cheapest inquiry some
; investigator can answer, else NoPlan with what blocks each goal literal and, as explanation only,
; the least plan that rests on unchecked literals; and whether some world at rest fits the snapshot at all.
;
;   (gc-pk-respond SIG GOAL RULES LIBRARY TRACKS LITERALS INVESTIGATORS BUILT POSSIBLE MOVED)
;     -> (Plan ((Taken NAME OCC) ...) CLASS ((Assumes LIT VALUE) ...))
;      | (Inquire LIT "INVESTIGATOR" (True ANSWER) (False ANSWER))
;      | (NoPlan ((Unsolved LIT VALUE REASON) ...) ALTERNATIVE)
;      | (Unadmitted ((Holds LIT VALUE) ...))
;   (gc-pk-answer ...) -> the same, an Unadmitted snapshot answered NoPlan with every goal literal Contradicted
;
; GOAL is (Goal (Holds LIT VALUE) ...). RULES are compiled rules (projection.metta's gc-pk-rules); the
; kernel's priority classes apply Finish and Derive before any other rule, so effects arrive with each
; procedure's last executed step. BUILT is gc-pk-build's (Built STATE ASSUMABLE). TRACKS are
; ((Track "PROCEDURE" LITERAL HOLDS) ...), HOLDS True when the procedure's record establishes that it
; brings LITERAL about. LITERALS is (Literals LIT ...), every declared literal instance, and
; INVESTIGATORS (Investigators (Investigator "NAME" (LIT ...)) ...), both anchored by gc-pk-lit like
; the goal. CLASS is (Class established|unestablished ready|pending), and a plan's assumptions are
; empty except in NoPlan's explanatory alternative. REASON is NoWay, Blocked, (Unknowable (LIT ...)) or
; Contradicted. A snapshot no world at rest fits answers Unadmitted, naming what it knows of the literals
; Finishes and Derives touch: projection.metta refuses the plan's own, and an inquiry branch answers it as
; a dead NoPlan (a-ev-pc-c1-admission-1019).
; The cost is a scheduling policy: which plan to pursue first, not a probability that it succeeds
; and not a utility (c-integrate-projection3-implementation-1018).
; am[implements a-ev-pk-search-1018@f96ce8] am[rests-on c-ev-pk-probe-acceptance-1018@3ed4ce]
; am[implements a-ev-pc-c1-admission-1019@92a093]

!(import! &self (library lib_functional))

; Two subcalls are inherent where an inquiry answers both of its branches, so the functions that
; recurse through both decline pymetta's automatic memoization, which would key each call by its whole
; arguments and keep every answer (c-brs-k-auto-memo-1018), and so do the walks over a closure, which
; call themselves once per successor.
; am[implements a-ev-pk-no-auto-memo-1018@7bf95a] am[rests-on c-brs-k-auto-memo-1018@9c39b3]
!(add-atom &metta (cache gc-pk-answer refuse))
!(add-atom &metta (cache gc-pk-respond refuse))
!(add-atom &metta (cache gc-pk-inquire refuse))
!(add-atom &metta (cache gc-pk-inquiry-tree refuse))
!(add-atom &metta (cache gc-pk-tree-cost refuse))
!(add-atom &metta (cache gc-pk-closure-visit refuse))
!(add-atom &metta (cache gc-pk-world-visit refuse))

; --- cost --------------------------------------------------------------------------------------------------
; (Cost U A E M ORDER): procedure applications whose record is not Holds for every Achieves literal,
; assumptions, executed steps, model steps (Start, Finish, Derive) and the steps' declared indices.
; U accrues once per application the plan touches, where the plan commits to it: at Start for an
; application the plan creates, at Derive for one with no executed step, and at the first step the
; plan takes of an instance the executor's journal started. So a plan that reaches its goal before
; an application's Finish, an act's merged reaction having established the literal, still counts it
; (c-integrate-plan-prefix-underpriced-1018). CHARGED lists the started instances already counted.
; Within a class it prefers fewer unestablished applications, then fewer executed steps, then
; earlier-declared procedures, where the composer took the first declared way per literal.
; A journal Finish, a variant matching a (Completed "P" KIND) instance, touches it without committing to
; anything when its control is (Completed "P" Silent): no Achieves of its was entailed, so no plan rests on its
; procedure's record, and it charges no U (a-ev-pc-completion-u-1019); (Completed "P" Wrote) entailed one,
; which the plan's start rests on, so it charges U as a first touch (a-jk-pc-r3-exact-amend-1019). Declaration order
; only ranks orders of one closure that rest alike, since
; a root whose closure rests two ways is refused (gc-pk-pop), so it never decides what a world does.
; am[implements a-ev-pk-commitment-cost-1018@c9673e] am[addresses i-ev-pk-prefix-underpriced-1018@7fdbf7]
(= (gc-pk-unestablished $name (Library $procedures $investigators) $tracks)
   (let $procedure (car-atom (filter-atom $procedures $p (== (index-atom $p 1) $name)))
     (if (gc-pk-all (map-atom (index-atom $procedure 2) $l
           (gc-pk-any (map-atom $tracks $t (case $t (((Track $n $tl $holds) (and (== $n $name) (and (== $tl $l) $holds)))))))))
         0 1)))
; am[implements a-ev-pk-membership-gc-has-1018@f2f7e4]
; am[implements a-ev-pc-completion-u-1019@9471f3] am[rests-on c-ev-pc-completion-commits-nothing-1019@15c580]
(= (gc-pk-add-cost (Cost $u $a $e $m $order) $charged (Step $index $name $part) $occ $library $tracks $state)
   (let* (($commits (gc-has (Start Derive) $part))
          ($model (gc-has (Start Finish Derive) $part))
          ($instance (if $commits None (bg-image $occ Inst)))
          ($first-touch (if (gc-pk-started-instance? $instance)
                            (and (not (gc-has $charged $instance)) (not (gc-pk-completed? $state $instance)))
                            False))
          ($du (if (or $commits $first-touch) (gc-pk-unestablished $name $library $tracks) 0)))
     (Costed (Cost (+ $u $du) $a (+ $e (if $model 0 1)) (+ $m (if $model 1 0)) (append $order ($index)))
             (if $first-touch (cons-atom $instance $charged) $charged))))
; A started instance is the executor's (Inst "ID"); every instance the plan starts has a fresh
; (new ...) id from the kernel, and a Start or Derive has no instance to read.
(= (gc-pk-started-instance? $id) (case $id (((Inst $i) True) ($other False))))
(= (gc-pk-completed? $state $id) (case (bg-control $state $id) (((Completed $p Silent) True) ($other False))))
(= (gc-pk-class (Cost $u $a $e $m $order)) (Class (if (== $u 0) established unestablished) (if (== $a 0) ready pending)))

; --- uniform-cost search ---------------------------------------------------------------------------------------
; Over (Fringe COST STATE STEPS ASSUMED CHARGED CHANGED), keyed by the state, the assumptions, the started
; instances already charged, which decide every later step's cost, and the literals some world may hold
; otherwise than the snapshot observed, which decide every later cancellation. Every step adds a non-negative
; cost, so the first time a key is popped its cost is least and the first goal state popped is a
; least plan; equal keys are found by bucket, then bg-iso. ASSUMABLE is () except when collecting the
; explanatory alternative, and an assumption is taken only before the first step: it is about the
; evidence now. Each pop answers (Found PLAN) or (Continue FRONTIER CLOSED), so the loop calls itself
; once and pymetta never memoizes it (c-brs-k-auto-memo-1018). MOVING is (Moving POSSIBLE INFLIGHT
; LITERALS WORLDS): what knowledge.metta's gc-pk-settle cancels by, and gc-pk-admitted's worlds at rest, by
; which an assumption set is admitted. Every state entering the frontier is settled.
; Time: each pop sorts the frontier, f log f for frontier size f, times the states popped; each
; pop also compares its key with the closed keys of its bucket by bg-iso, and each open key's state,
; the goal state's included, has its successors found once, each successor diffed over the declared and
; Done literals and settled; each closure root whose priority class steps also walks its closure once.
; am[implements a-ev-pk-search-1018@f96ce8] am[implements a-ev-pk-no-auto-memo-1018@7bf95a]
; am[implements a-ev-pk-maybe-enabled-k0-1018@287f15]
(= (gc-pk-search $sig $goal $rules $library $tracks $assumable $moving $frontier $closed)
   (if (== $frontier ())
       NoPlan
       (case (gc-pk-pop $sig $goal $rules $library $tracks $assumable $moving (msort $frontier) $closed)
         (((Found $plan) $plan)
          ((Continue $next-frontier $next-closed)
           (gc-pk-search $sig $goal $rules $library $tracks $assumable $moving $next-frontier $next-closed))))))
; The least entry is skipped when its key is closed, answered when it satisfies the goal in a settled
; state, and otherwise expanded by every rule's successors and, before any step, every assumption. A
; state is settled when only the lowest priority class steps in it, or nothing does: Finish and Derive
; apply before any other rule, as the world applies a procedure's effects when its last step completes,
; so a goal holding while one of them still steps holds only until it applies
; (i-ev-pk-goal-before-settled-1018).
; A world, not the plan, picks the order of Finishes and Derives enabled together, so a closure root, the
; start, an assumption's state or the state after an ordinary step, keeps its rule successors only when
; every run of its priority moves ends, without revisiting a key, in one rest key, CHANGED included
; (a-jk-pc-r1-closure-1019): forks between are free to differ, as Newman's lemma lets a terminating and
; joinable closure (c-integrate-confluence-transfer-1019), and the search goes on exploring their orders
; for the least cost. An assumption set no admitted world agrees with is no root at all.
; am[implements a-ev-pk-goal-settled-1018@797476] am[addresses i-ev-pk-goal-before-settled-1018@408d3c]
; am[implements a-ev-pc-r1-guard-1019@c59bcf] am[implements a-jk-pc-r1-closure-1019@f9b888] am[implements a-ev-pc-c1-admission-1019@92a093]
(= (gc-pk-pop $sig $goal $rules $library $tracks $assumable $moving $sorted $closed)
   (let* ((($head $rest) (decons-atom $sorted))
          ((Fringe $cost $state $steps $assumed $charged $changed) $head)
          ($key (gc-pk-fringe-key $head)))
     (if (gc-pk-closed? $key $closed)
         (Continue $rest $closed)
         (if (not (gc-pk-assumed-admitted? $assumed $moving))
             (Continue $rest (cons-atom $key $closed))
             (let $stepping (bg-successors $sig $rules $state)
               (if (and (gc-pk-settled? $stepping $rules) (gc-pk-satisfies? $goal $state))
                   (Found (Plan (gc-pk-reversed $steps) (gc-pk-class $cost) $assumed))
                   (let* (($by-rules (if (gc-pk-refused-root? $sig $rules $library $tracks $moving $head $stepping)
                                         ()
                                         (gc-pk-successors $stepping $library $tracks $moving $head)))
                          ($by-assumption (if (== $steps ()) (gc-pk-assume-moves $cost $assumable $moving $head) ())))
                     (Continue (append $rest (append $by-rules $by-assumption)) (cons-atom $key $closed)))))))))
(= (gc-pk-fringe-key (Fringe $cost $state $steps $assumed $charged $changed))
   (Key (bg-bucket $state) $state (msort $assumed) (msort $charged) (msort $changed)))
; The kernel answers the steps of one priority class, so the first step's rule decides; Start and the
; executed steps are class 0 (compile.metta).
; am[implements a-ev-pk-goal-settled-1018@797476]
(= (gc-pk-settled? $stepping $rules)
   (if (== $stepping ())
       True
       (case (car-atom $stepping)
         (((Step $name $occ $next)
           (gc-pk-ordinary-rule? $name $rules))))))
(= (gc-pk-ordinary-rule? $name $rules)
   (case (car-atom (filter-atom $rules $r (== (index-atom $r 1) $name)))
     (((Rule $n $redex $reactum $eta $conds (Priority $p)) (== $p 0)))))

; --- closure roots ------------------------------------------------------------------------------------------------
; A fringe is a closure root when it has taken no step, or its last step was an ordinary one; one whose priority
; class steps is refused when its closure revisits a key or rests in two.
; am[implements a-ev-pc-r1-guard-1019@c59bcf]
(= (gc-pk-refused-root? $sig $rules $library $tracks $moving (Fringe $cost $state $steps $assumed $charged $changed) $stepping)
   (and (gc-pk-root? $steps $rules)
        (and (not (gc-pk-settled? $stepping $rules))
             (case (gc-pk-closure-visit $sig $rules $library $tracks $moving (Fringe $cost $state $steps $assumed $charged $changed) () (Visited () ()))
               ((Revisits True)
                ((Visited $done $rests) (> (size-atom $rests) 1)))))))
(= (gc-pk-root? $steps $rules)
   (if (== $steps ()) True (case (car-atom $steps) (((Taken $name $occ) (gc-pk-ordinary-rule? $name $rules))))))
; A depth-first walk of the closure from FRINGE: (Visited DONE RESTS), the keys whose closure is walked and the
; distinct rest keys found, or Revisits once a run reaches a key on its own path.
; Time: each key of the closure expanded once, its successors found and settled as gc-pk-successors does, and
; each compared by bucket and bg-iso with the keys on its path, the keys done and the rests.
; am[implements a-ev-pc-r1-guard-1019@c59bcf] am[implements a-jk-pc-r1-closure-1019@f9b888]
(= (gc-pk-closure-visit $sig $rules $library $tracks $moving $fringe $path $visited)
   (case $visited
     ((Revisits Revisits)
      ((Visited $done $rests)
       (let $key (gc-pk-fringe-key $fringe)
         (if (gc-pk-closed? $key $path)
             Revisits
             (if (gc-pk-closed? $key $done)
                 $visited
                 (case $fringe
                   (((Fringe $cost $state $steps $assumed $charged $changed)
                     (let $stepping (bg-successors $sig $rules $state)
                       (if (gc-pk-settled? $stepping $rules)
                           (Visited (cons-atom $key $done) (if (gc-pk-closed? $key $rests) $rests (cons-atom $key $rests)))
                           (case (foldl-atom (gc-pk-successors $stepping $library $tracks $moving $fringe) $visited $acc $next
                                   (gc-pk-closure-visit $sig $rules $library $tracks $moving $next (cons-atom $key $path) $acc))
                             ((Revisits Revisits)
                              ((Visited $walked $found) (Visited (cons-atom $key $walked) $found))))))))))))))))
; Each successor is settled from CHANGED and every literal the step moved.
; am[implements a-ev-pk-maybe-enabled-k0-1018@287f15]
(= (gc-pk-successors $stepping $library $tracks (Moving $possible $inflight $literals $worlds)
                     (Fringe $cost $state $steps $assumed $charged $changed))
   (map-atom $stepping $s
     (case $s (((Step $name $occ $next)
                (case (gc-pk-add-cost $cost $charged $name $occ $library $tracks $state)
                  (((Costed $next-cost $next-charged)
                    (case (gc-pk-settle $next (unique-atom (append $changed (gc-pk-moved $state $next $literals $library)))
                                        $possible $inflight)
                      (((Settled $settled $moved)
                        (Fringe $next-cost $settled (cons-atom (Taken $name $occ) $steps) $assumed $next-charged $moved))))))))))))
; The literals whose knowledge differs between two states: the declared ones and each Done of either's instances.
; Time: 2 knowledge reads per candidate, l declared literals and d Done literals.
; am[implements a-ev-pk-maybe-enabled-k0-1018@287f15]
(= (gc-pk-moved $state $next $literals $library)
   (filter-atom (unique-atom (append (cdr-atom $literals) (append (gc-pk-done-literals $state $library) (gc-pk-done-literals $next $library))))
                $lit (not (== (gc-pk-knowledge $lit $state) (gc-pk-knowledge $lit $next)))))
(= (gc-pk-done-literals $state (Library $procedures $investigators))
   (gc-pk-flatten (map-atom (bg-nodes $state) $row
     (case $row (((N $i (Instance $name)) (map-atom (gc-pk-executed-ids $name $procedures) $s (Lit (Done $s) $i (Via))))
                 ($other ()))))))
(= (gc-pk-closed? (Key $bucket $state $assumed $charged $changed) $closed)
   (gc-pk-any (map-atom $closed $k
     (case $k (((Key $b $s $a $c $m)
                (if (and (== $b $bucket) (and (== $a $assumed) (and (== $c $charged) (== $m $changed)))) (bg-iso $s $state) False)))))))
(= (gc-pk-reversed $steps) (foldl-atom $steps () $acc $s (cons-atom $s $acc)))
(= (gc-pk-satisfies? $goal $state)
   (gc-pk-all (map-atom (cdr-atom $goal) $g (case $g (((Holds $lit $value) (== (gc-pk-knowledge $lit $state) (Known $value))))))))
; An assumption, like a checked reading, describes the settled world, so it moves no literal, and the state
; it extends is settled again.
; am[implements a-ev-pk-maybe-enabled-k0-1018@287f15]
(= (gc-pk-assume-moves (Cost $u $a $e $m $order) $assumable (Moving $possible $inflight $literals $worlds)
                       (Fringe $cost $state $steps $assumed $charged $changed))
   (gc-pk-flatten (map-atom $assumable $x
     (case $x (((Assumable $lit $value)
       (if (== (gc-pk-knowledge $lit $state) Unknown)
           (case (gc-pk-settle (gc-pk-add-knowledge $state $lit $value assume) $changed $possible $inflight)
             (((Settled $settled $moved)
               ((Fringe (Cost $u (+ $a 1) $e $m $order) $settled () (cons-atom (Assumes $lit $value) $assumed) $charged $moved)))))
           ())))))))

; --- the answer -----------------------------------------------------------------------------------------------------
; Unadmitted when no world at rest fits the snapshot; else a model-valid plan; else the cheapest inquiry tree
; over literals an investigator covers; else NoPlan with the least assumption-dependent plan as an explanatory
; alternative, never actionable. projection.metta's gc-pk-plan-worker reaches gc-pk-respond, and the inquiry
; reaches gc-pk-answer with each branch's computed snapshot.
; POSSIBLE is compile.metta's gc-pk-possible, and MOVED is (Moved INFLIGHT CHANGED), the items of the acts in
; flight and the literals that have moved: the built state's done journal instances are classified
; (knowledge.metta's gc-pk-classify) and it is settled from them before anything is searched, inquired or
; explained. An inquiry's candidates are the settled state's unknown literals, and its branches observe on the
; built state, before the classification and the settle, and do both again from MOVED.
; am[implements a-ev-pk-maybe-enabled-k0-1018@287f15] am[implements a-ev-pk-inquiry-branch-as-reading-1018@9c2431]
; am[implements a-ev-pc-r3-classify-1019@314db6] am[implements a-ev-pc-c1-admission-1019@92a093]
(= (gc-pk-respond $sig $goal $rules $library $tracks $literals $investigators $built $possible $moved)
   (let* (((Built $root $assumable) $built)
          ($worlds (gc-pk-admitted $sig $rules $possible $literals $root)))
     (if (gc-pk-no-world? $worlds)
         (Unadmitted (gc-pk-touched-known $worlds $root))
         (let* (((Moved $inflight $changed0) $moved)
                ((Classified $classified $changed1) (gc-pk-classify $root $changed0 $worlds))
                ((Settled $state $changed) (gc-pk-settle $classified $changed1 $possible $inflight))
                ($moving (Moving $possible $inflight $literals $worlds))
                ($start ((Fringe (Cost 0 0 0 0 ()) $state () () () $changed)))
                ($valid (gc-pk-search $sig $goal $rules $library $tracks () $moving $start ())))
           (if (gc-pk-plan? $valid)
               $valid
               (let $inquiry (gc-pk-inquire $sig $goal $rules $library $tracks $literals $investigators $state $assumable
                                            $root $possible $moved)
                 (if (gc-pk-tree? $inquiry)
                     $inquiry
                     (let $alternative (gc-pk-search $sig $goal $rules $library $tracks $assumable $moving $start ())
                       (NoPlan (gc-pk-unsolved $goal $rules $literals $investigators $state)
                               (if (gc-pk-plan? $alternative) (Alternative $alternative) NoAlternative))))))))))
; An inquiry branch's snapshot no world fits is an answer no investigator can give: a NoPlan naming every goal
; literal Contradicted, with no alternative, dead in the inquiry metric (a-jk-pc-c1-admitted-1019).
; am[implements a-ev-pc-c1-admission-1019@92a093]
(= (gc-pk-answer $sig $goal $rules $library $tracks $literals $investigators $built $possible $moved)
   (case (gc-pk-respond $sig $goal $rules $library $tracks $literals $investigators $built $possible $moved)
     (((Unadmitted $known)
       (NoPlan (map-atom (cdr-atom $goal) $g (case $g (((Holds $lit $value) (Unsolved $lit $value Contradicted)))))
               NoAlternative))
      ($answer $answer))))
(= (gc-pk-plan? $answer) (case $answer (((Plan $steps $class $assumed) True) ($other False))))
(= (gc-pk-tree? $answer) (case $answer (((Plan $steps $class $assumed) True) ((Inquire $l $i $y $n) True) ($other False))))

; --- admission: some world at rest fits the snapshot -------------------------------------------------------------
; The readings observe the world at rest, after it settled from the journal and before any act in flight
; landed, and every reading still valid holds at the plan's time (c-ev-pc-valid-readings-simultaneous-1019).
; So the snapshot is admitted when some world, settled to rest from any valuation, holds every literal ROOT
; knows (a-jk-pc-c1-admitted-1019). Only Derives and the Finishes of the journal's done instances move
; anything in that settling, so only the literals they read or write, TOUCHED, need both values, observed ones
; included, since a reading observes only the rest; every other literal keeps what ROOT knows, and an act in
; flight never lands, its Done staying unknown. Deciding admission is NP-hard, each Derive a clause, but only
; in the touched literals (c-jk-pc-admission-np-1019). Answers (Worlds TOUCHED FINISHING (REST ...)): FINISHING
; the journal's done instances, (Finishing ID "P" (STEP ...) READS WRITES) each, and each REST
; (World ((Holds LIT VALUE) ...) (ID ...)) the touched values at a rest that fits with the done instances
; still open there, each distinct once; an inquiry's branch or an assumption set is admitted when some REST
; agrees with what it adds, and knowledge.metta's gc-pk-classify reads each done instance's status off them.
; Time: 2^t valuations, t = the touched literals, each a depth-first walk of its priority closure with every
; state compared by bucket and bg-iso with those already walked, and k knowledge reads per rest, k = the
; literals ROOT knows; all under the request's RunBudget, whose exhaustion raises as every budget does.
; am[implements a-ev-pc-c1-admission-1019@92a093] am[implements a-jk-pc-c1-admitted-1019@321a3b]
; am[rests-on c-ev-pc-valid-readings-simultaneous-1019@f12136]
(= (gc-pk-admitted $sig $rules (Possible $mays $acts $finishes) $literals $root)
   (let* (($finishing (gc-pk-finishing $finishes $root))
          ($touched (gc-pk-touched $mays $finishing))
          ($known (filter-atom (cdr-atom $literals) $l (not (== (gc-pk-knowledge $l $root) Unknown))))
          ($rests (gc-pk-flatten (map-atom (gc-pk-valuations $touched) $v
                    (gc-pk-valuation-rests $sig $rules $root $known $touched $finishing $v)))))
     (Worlds $touched $finishing (unique-atom $rests))))
(= (gc-pk-no-world? (Worlds $touched $finishing $rests)) (== $rests ()))
; What ROOT knows of the touched literals, which a refusal names.
(= (gc-pk-touched-known (Worlds $touched $finishing $rests) $root)
   (gc-pk-flatten (map-atom $touched $l (case (gc-pk-knowledge $l $root) (((Known $v) ((Holds $l $v))) (Unknown ()))))))
; The journal's instances in ROOT whose executed steps all have receipts, each with its Finish's reads and writes.
; am[implements a-ev-pc-c1-admission-1019@92a093] am[implements a-jk-pc-r3-exact-amend-1019@9a3391]
(= (gc-pk-finishing $finishes $root)
   (gc-pk-flatten (map-atom $finishes $f (case $f (((Finish $name $ids $fr $fw)
     (gc-pk-flatten (map-atom (gc-pk-instances-of $name $root) $i
       (if (gc-pk-all (map-atom $ids $d (== (gc-pk-knowledge (Lit (Done $d) $i (Via)) $root) (Known True))))
           ((Finishing $i $name $ids $fr $fw))
           ())))))))))
; am[implements a-ev-pc-c1-admission-1019@92a093]
(= (gc-pk-touched $mays $finishing)
   (unique-atom (gc-pk-flatten (append
     (map-atom $mays $m (case $m (((May Derive $dr $dw) (gc-pk-holds-literals (append $dr $dw))) ($other ()))))
     (map-atom $finishing $f (case $f (((Finishing $i $name $ids $fr $fw) (gc-pk-holds-literals (append $fr $fw))))))))))
(= (gc-pk-holds-literals $holds) (map-atom $holds $h (case $h (((Holds $lit $value) $lit)))))
; Every valuation of LITS, each a list of (Holds LIT VALUE).
(= (gc-pk-valuations $lits)
   (if (== $lits ())
       (())
       (let* ((($first $others) (decons-atom $lits))
              ($tails (gc-pk-valuations $others)))
         (append (map-atom $tails $t (cons-atom (Holds $first True) $t))
                 (map-atom $tails $u (cons-atom (Holds $first False) $u))))))
; The touched values at each rest of VALUATION's closure that holds every literal ROOT knows, with the done
; instances still open there.
; am[implements a-ev-pc-c1-admission-1019@92a093] am[implements a-jk-pc-r3-exact-amend-1019@9a3391]
(= (gc-pk-valuation-rests $sig $rules $root $known $touched $finishing $valuation)
   (let $world (foldl-atom $valuation $root $w $h
                 (case $h (((Holds $lit $value) (gc-pk-add-knowledge (gc-pk-forget $w $lit) $lit $value build)))))
     (case (gc-pk-world-visit $sig $rules $world () (Rested () ()))
       ((Revisits ())
        ((Rested $done $rests)
         (map-atom (filter-atom $rests $r (gc-pk-all (map-atom $known $k (== (gc-pk-knowledge $k $r) (gc-pk-knowledge $k $root))))) $kept
           (World (map-atom $touched $l (case (gc-pk-knowledge $l $kept) (((Known $v) (Holds $l $v)) (Unknown (Holds $l Unknown)))))
                  (gc-pk-flatten (map-atom $finishing $f (case $f (((Finishing $i $name $ids $fr $fw)
                    (if (gc-has (gc-pk-instances-of $name $kept) $i) ($i) ())))))))))))))
; A depth-first walk of a world's priority closure as the kernel steps it, no settle and no cost:
; (Rested DONE RESTS), or Revisits once a run reaches a state on its own path, a world that never rests,
; which R2 rules out and which is no world anything observed.
; am[implements a-ev-pc-c1-admission-1019@92a093]
(= (gc-pk-world-visit $sig $rules $state $path $walked)
   (case $walked
     ((Revisits Revisits)
      ((Rested $done $rests)
       (if (gc-pk-state-among? $state $path)
           Revisits
           (if (gc-pk-state-among? $state $done)
               $walked
               (let $stepping (bg-successors $sig $rules $state)
                 (if (gc-pk-settled? $stepping $rules)
                     (Rested (cons-atom $state $done) (cons-atom $state $rests))
                     (case (foldl-atom $stepping $walked $acc $s
                             (case $s (((Step $name $occ $next) (gc-pk-world-visit $sig $rules $next (cons-atom $state $path) $acc)))))
                       ((Revisits Revisits)
                        ((Rested $seen $found) (Rested (cons-atom $state $seen) $found))))))))))))
(= (gc-pk-state-among? $state $states)
   (let $bucket (bg-bucket $state)
     (gc-pk-any (map-atom $states $s (if (== (bg-bucket $s) $bucket) (bg-iso $s $state) False)))))
; An assumption set is admitted when some admitted world agrees with each assumption on a touched literal;
; an untouched literal no closure moves, and an assumption is only ever taken on a literal the state leaves
; unknown.
; am[implements a-ev-pc-c1-admission-1019@92a093]
(= (gc-pk-assumed-admitted? $assumed (Moving $possible $inflight $literals (Worlds $touched $finishing $rests)))
   (if (== $assumed ())
       True
       (gc-pk-any (map-atom $rests $w (case $w (((World $values $open)
         (gc-pk-all (map-atom $assumed $a (case $a (((Assumes $lit $value)
           (if (gc-has $touched $lit) (gc-has $values (Holds $lit $value)) True)))))))))))))

; --- inquiry -------------------------------------------------------------------------------------------------------
; Only a literal some investigator covers can be inquired; an inquiry is usable when either branch
; opens a plan. Trees are compared by (DEAD DEPTH STEPS): branches ending without a plan, nested
; inquiries and executed steps on the worst path.
; The settle cancels what a Finish, Derive or attempt in flight may overwrite, so an observation's branch can
; forget it: with an attempt in flight setting sensitive-data, observing it false settles back to the state that
; asked. A literal is therefore a candidate only when some branch keeps its observation, a branch that forgets
; it searches from the state that asked, and neither branch's investigators cover it again: every inquiry
; precedes the plan's first step, so a second observation would answer what the first did, and asked again it
; would repeat until the budget ran out (cortez-pereira's a-jk-po-inquiry-progress-1018 rule).
; An investigator's answer is a reading: it replaces the literal's knowledge in ROOT, the state before the
; settle, which a reading may hold, and the branch settles from the snapshot's CHANGED, so what the settle
; cancelled for want of the answer comes back where the answer decides it. Observed on the settled state
; instead, a journal's instance whose Finish reads the unknown literal stays uncertain after the answer
; makes its Finish enabled, as cortez-pereira's OBSERVATION_ENABLES_FINISH measured
; (c-jk-po-inquiry-branch-disagrees-replanning-a44aeba-1018).
; Time: with k inquirable unknown literals, each level tries every literal its path has not inquired, so a path
; inquires at most k literals: k!·2^k searches at worst, each after two settles of its observations.
; am[implements a-integrate-k0-inquiry-termination-1018@e862f7] am[addresses i-ev-pk-inquiry-repeats-cancelled-1018@f783c5]
; am[implements a-ev-pk-inquiry-branch-as-reading-1018@9c2431]
(= (gc-pk-inquire $sig $goal $rules $library $tracks $literals $investigators $state $assumable $root $possible $moved)
   (let* (($open (filter-atom (gc-pk-unknown-literals $literals $state) $l (not (== (gc-pk-investigator $l $investigators) None))))
          ($trees (collapse (gc-pk-inquiry-tree (superpose $open) $sig $goal $rules $library $tracks $literals $investigators $root
                                                $assumable $possible $moved))))
     (if (== $trees ()) NoInquiry (index-atom (car-atom (msort (map-atom $trees $t (Ranked (gc-pk-tree-cost $t) $t)))) 2))))
(= (gc-pk-inquiry-tree $lit $sig $goal $rules $library $tracks $literals $investigators $root $assumable $possible $moved)
   (let* (($left (filter-atom $assumable $a (case $a (((Assumable $l $v) (not (== $l $lit)))))))
          ($asked (gc-pk-asked $investigators $lit))
          ((Observed $kept-true $built-true $moved-true) (gc-pk-observe $sig $rules $literals $root $lit True $left $possible $moved))
          ((Observed $kept-false $built-false $moved-false) (gc-pk-observe $sig $rules $literals $root $lit False $left $possible $moved)))
     (if (or $kept-true $kept-false)
         (let* (($yes (gc-pk-answer $sig $goal $rules $library $tracks $literals $asked $built-true $possible $moved-true))
                ($no (gc-pk-answer $sig $goal $rules $library $tracks $literals $asked $built-false $possible $moved-false)))
           (if (or (gc-pk-tree? $yes) (gc-pk-tree? $no))
               (Inquire $lit (gc-pk-investigator $lit $investigators) (True $yes) (False $no))
               (empty)))
         (empty))))
; One observation's branch, (Observed KEPT BUILT MOVED): ROOT with LIT's knowledge replaced by VALUE, its BUILT
; and MOVED those of the snapshot, KEPT True when classifying its done journal instances and settling it under
; the attempts in flight and the snapshot's CHANGED leaves the observation standing, as the branch's own
; answer will classify and settle it.
; am[implements a-integrate-k0-inquiry-termination-1018@e862f7] am[implements a-ev-pk-inquiry-branch-as-reading-1018@9c2431]
; am[implements a-ev-pc-r3-classify-1019@314db6]
(= (gc-pk-observe $sig $rules $literals $root $lit $value $left $possible (Moved $inflight $changed))
   (let $observed (gc-pk-add-knowledge (gc-pk-forget $root $lit) $lit $value inquire)
     (case (gc-pk-classify $observed $changed (gc-pk-admitted $sig $rules $possible $literals $observed))
       (((Classified $classified $more)
         (case (gc-pk-settle $classified $more $possible $inflight)
           (((Settled $settled $moved)
             (Observed (== (gc-pk-knowledge $lit $settled) (Known $value)) (Built $observed $left) (Moved $inflight $changed))))))))))
; INVESTIGATORS once LIT has been inquired: none covers it.
; am[implements a-integrate-k0-inquiry-termination-1018@e862f7]
(= (gc-pk-asked $investigators $lit)
   (cons-atom Investigators
     (map-atom (cdr-atom $investigators) $i
       (case $i (((Investigator $name $observes) (Investigator $name (filter-atom $observes $o (not (== $o $lit))))))))))
(= (gc-pk-tree-cost $tree)
   (case $tree
     (((Plan $steps $class $assumed) (TreeCost 0 0 (size-atom (filter-atom $steps $s (gc-pk-executed-taken? $s)))))
      ((Inquire $lit $investigator (True $yes) (False $no))
       (case (Pair (gc-pk-tree-cost $yes) (gc-pk-tree-cost $no))
         (((Pair (TreeCost $xy $dy $sy) (TreeCost $xn $dn $sn))
           (TreeCost (+ $xy $xn) (+ 1 (gc-pk-larger $dy $dn)) (gc-pk-larger $sy $sn))))))
      ($dead (TreeCost 1 0 0)))))
; am[implements a-ev-pk-membership-gc-has-1018@f2f7e4]
(= (gc-pk-executed-taken? (Taken (Step $index $name $part) $occ)) (not (gc-has (Start Finish Derive) $part)))
(= (gc-pk-larger $a $b) (if (> $a $b) $a $b))

; The declared literals STATE leaves unknown, in standard order.
(= (gc-pk-unknown-literals $literals $state)
   (msort (filter-atom (cdr-atom $literals) $lit (== (gc-pk-knowledge $lit $state) Unknown))))
; The investigator observing LIT, or None.
; am[implements a-ev-pk-membership-gc-has-1018@f2f7e4]
(= (gc-pk-investigator $lit $investigators)
   (let $covering (filter-atom (cdr-atom $investigators) $i (case $i (((Investigator $name $observes) (gc-has $observes $lit)))))
     (if (== $covering ()) None (index-atom (car-atom $covering) 1))))

; --- no plan ---------------------------------------------------------------------------------------------------------
; Per goal literal STATE does not establish, with the value the goal wants: NoWay when no rule writes
; it with that value, Unknowable when every rule writing it reads a literal unknown here that no
; investigator covers, naming those literals, Blocked otherwise. A rule reads a literal when its redex
; holds the literal's subject or witness, so an unknown literal no writer reads never makes a goal
; unknowable.
; am[implements a-ev-pk-search-1018@f96ce8]
(= (gc-pk-unsolved $goal $rules $literals $investigators $state)
   (gc-pk-flatten (map-atom (cdr-atom $goal) $g
     (case $g (((Holds $lit $value)
       (if (== (gc-pk-knowledge $lit $state) (Known $value))
           ()
           ((Unsolved $lit $value (gc-pk-reason $lit $value $rules $literals $investigators $state))))))))))
(= (gc-pk-reason $lit $value $rules $literals $investigators $state)
   (let* (($writers (filter-atom $rules $r (gc-pk-writes? $r $lit $value)))
          ($uncovered (filter-atom (gc-pk-unknown-literals $literals $state) $l (== (gc-pk-investigator $l $investigators) None)))
          ($stuck (map-atom $writers $w (filter-atom $uncovered $l (gc-pk-reads? $w $l)))))
     (if (== $writers ())
         NoWay
         (if (gc-pk-all (map-atom $stuck $s (not (== $s ()))))
             (Unknowable (unique-atom (gc-pk-flatten $stuck)))
             Blocked))))
; am[implements a-ev-pk-membership-gc-has-1018@f2f7e4]
(= (gc-pk-reads? (Rule $name $redex $reactum $eta $conds $priority) (Lit $subject $entity $via))
   (let $controls (map-atom (bg-nodes $redex) $n (index-atom $n 2))
     (or (gc-has $controls $subject) (gc-has $controls (Not $subject)))))
; A rule writes LIT with VALUE when its reactum places that polarity, under any node, where the redex did not.
(= (gc-pk-writes? (Rule $name $redex $reactum $eta $conds $priority) (Lit $subject $entity $via) $value)
   (let $control (gc-pk-polarity $subject $value)
     (> (size-atom (filter-atom (bg-nodes $reactum) $n (== (index-atom $n 2) $control)))
        (size-atom (filter-atom (bg-nodes $redex) $n (== (index-atom $n 2) $control))))))
