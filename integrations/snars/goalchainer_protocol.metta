;;; Versioned machine protocol for GoalChainer's PeTTa SNARS adapter.
;;;
;;; Each public function returns one `(goalchainer-snars-v1 ...)` record.
;;; Python selects that tagged record and parses it with Mettabase's shared
;;; S-expression parser. Human renderers such as why! stay outside this
;;; protocol because their wording is not a stable machine interface.

(= (gc receipts $sid)
   (collapse
     (match &self (sn receipt $sid $source $hash)
       (receipt $hash $source $sid
                (sn_tr_p src $source (sn config trust-prior-src))))))

(= (gc occurrences $sid)
   (collapse (match &self (sn occ $sid $tick) (occurrence $sid $tick))))

(= (gc supporting-receipts $statement $depth)
   (msort
     (collapse
       (let (: $opinion $proof $conclusion) (sn prove $statement $depth)
         (let* (($leaves (sn ax-leaves $proof))
                ($stamp (superpose $leaves)))
           (match &self (sn receipt $stamp $source $hash)
             (receipt $hash $source $stamp
                      (sn_tr_p src $source
                               (sn config trust-prior-src)))))))))

(= (gc proof-rows $statement $depth)
   (collapse
     (let (: $opinion $proof $conclusion) (sn prove $statement $depth)
       (proof $opinion $proof $conclusion
              (stamps (sn ax-leaves $proof))))))

(= (gc sized-proof-rows $statement $max-size)
   (collapse
     (let (: $opinion $proof $conclusion) (sn prove-sized $statement $max-size)
       (proof $opinion $proof $conclusion
              (stamps (sn ax-leaves $proof))))))

(= (gc direct-belief $statement $depth)
   (let* (($canon (sn canon $statement))
          ($sid (sn sid $canon))
          ($proofs (gc proof-rows $statement $depth))
          ($opinion
            (if (== $proofs ())
                (sn opinion $sid)
                (sn prove-fused $statement $depth)))
          ((Opinion $b $d $u $oa) $opinion)
          ((Ev $r $s $a) (sn op-to-ev $opinion)))
     (belief $sid $canon
             (opinion $b $d $u $oa)
             (evidence $r $s $a)
             (receipts (gc supporting-receipts $statement $depth))
             (proofs $proofs)
             (occurrences (gc occurrences $sid)))))

(= (gc belief-record $operation $statement $depth)
   (goalchainer-snars-v1 $operation ok
     (gc direct-belief $statement $depth)))

(= (gc action-assessment $action)
   (let* (($acceptable (gc action-property $action "acceptable"))
          ($forbidden (gc action-property $action "forbidden")))
     (action $action
       (acceptable (gc direct-belief $acceptable 4))
       (risky
         (gc direct-belief (gc action-property $action "risky") 4))
       (forbidden (gc direct-belief $forbidden 4))
       (conflict
         (sn dc (sn sid (sn canon $acceptable))
                (sn sid (sn canon $forbidden)))))))

(= (gc assess-record)
   (goalchainer-snars-v1 assess ok
     (assessment
       (gc action-assessment "publish_raw_log")
       (gc action-assessment "publish_redacted_summary")
       (gc action-assessment "hold_external_update"))))

(= (gc context-record)
   (goalchainer-snars-v1 context ok
     (context
       (sensitive
         (gc direct-belief
           (gc action-property "request" "sensitive-data") 4))
       (public
         (gc direct-belief
           (gc action-property "request" "public-data") 4))
       (unverified
         (gc direct-belief
           (gc action-property "request" "unverified") 4))
       (coordination
         (gc direct-belief
           (gc action-property "request" "coordination-needed") 4)))))

(= (gc ask-record $pattern)
   (goalchainer-snars-v1 ask ok
     (answers (collapse (ask! $pattern)))))

(= (gc prove-record $statement $depth $max-size)
   (goalchainer-snars-v1 prove ok
     (proof-result
       (statement $statement)
       (fused (sn prove-fused $statement $depth))
       (depth-bounded (gc proof-rows $statement $depth))
       (size-bounded (gc sized-proof-rows $statement $max-size)))))

(= (gc explain-record $statement $depth)
   (let $sid (sn sid (sn canon $statement))
     (goalchainer-snars-v1 explain ok
       (explanation
         (belief (gc direct-belief $statement $depth))
         (why (collapse (why! $statement)))
         (proof-trees (collapse (sn proof-dag $sid)))
         (why-not (collapse (why-not! $statement)))))))

(= (gc discover-record $pattern)
   (goalchainer-snars-v1 discover ok
     (discoveries (collapse (discover! $pattern)))))

(= (gc goal-record $statement $owner $kind $desire $required $source)
   (let* (($goal-id (sn sid (Goal (sn canon $statement))))
          ($subgoals (collapse (sn subgoals! $goal-id))))
     (goalchainer-snars-v1 goal ok
       (goal $goal-id (sn canon $statement) $owner $kind
             (sn desire $goal-id) $required $source
             (subgoals $subgoals)))))

(= (gc subgoals-record $statement)
   (let* (($goal-id (sn sid (Goal (sn canon $statement))))
          ($generated (collapse (sn subgoals! $goal-id)))
          ($rows (collapse
                   (match &self (sn goal $sid $tree)
                     (goal $sid $tree (sn desire $sid))))))
     (goalchainer-snars-v1 subgoals ok
       (subgoals $goal-id $generated $rows))))

;;; A deterministic structural fingerprint. Python hashes the emitted tree.
;;; Counterfactual tests compare the exact before and after trees as well as
;;; their SHA-256 digests.
(= (gc state-fingerprint)
   (state
     (statements
       (msort (collapse
         (match &self (sn stmt $sid $tree)
           (statement $sid $tree (sn evidence $sid))))))
     (receipts
       (msort (collapse
         (match &self (sn receipt $sid $source $hash)
           (receipt $sid $source $hash)))))
     (goals
       (msort (collapse
         (match &self (sn goal $sid $tree)
           (goal $sid $tree (sn desire $sid))))))
     (occurrences
       (msort (collapse
         (match &self (sn occ $sid $tick)
           (occurrence $sid $tick)))))
     (trust
       (msort (collapse
         (match &self (sn tstamp $kind $key1 $key2 $sid)
           (trust-stamp $kind $key1 $key2 $sid)))))))

(= (gc what-if-record $hypothesis $options $query $depth)
   (let* (($before (gc state-fingerprint))
          ($proofs
            (collapse
              (let (: $opinion $proof $conclusion)
                   (sn what-if! $hypothesis $options $query $depth)
                (proof $opinion $proof $conclusion
                       (stamps (sn ax-leaves $proof))))))
          ($opinion (sn would?! $hypothesis $query $depth))
          ($after (gc state-fingerprint)))
     (goalchainer-snars-v1 what-if ok
       (counterfactual
         (hypothesis $hypothesis)
         (query $query)
         (opinion $opinion)
         (proofs $proofs)
         (state-before $before)
         (state-after $after)))))

(= (gc temporal-record $statement $budget $now)
   (let* (($sid (sn sid (sn canon $statement)))
          ($processed (collapse (sn temporal! $budget $now)))
          ($intervals (collapse
                        (match &self (sn interval $sid $from $to)
                          (interval $sid $from $to))))
          ($occurrences (gc occurrences $sid)))
     (goalchainer-snars-v1 temporal ok
       (temporal $sid $now $processed $occurrences $intervals
                 (event-opinion (sn opinion $sid))
                 (eternal-opinion (sn view $sid))))))

(= (gc trust-record)
   (goalchainer-snars-v1 trust ok
     (trust
       (sources
         (msort (collapse
           (match &self (sn receipt $sid $source $hash)
             (source $source
                     (sn_tr_p src $source (sn config trust-prior-src)))))))
       (rule-stamps
         (msort (collapse
           (match &self (sn tstamp $kind $key1 $key2 $sid)
             (trust-stamp $kind $key1 $key2 $sid))))))))

(= (gc mine-record $minimum-support)
   (let* (($mined (collapse (sn mine! $minimum-support)))
          ($proposals (collapse (sn proposals))))
     (goalchainer-snars-v1 mine ok
       (mining $mined (proposals $proposals) (activated False)))))

(= (gc inspect-record)
   (goalchainer-snars-v1 inspect ok
     (inspection
       (state (gc state-fingerprint))
       (clock (sn clock))
       (cells (collapse (sn cells)))
       (metadata (collapse (sn meta-view $sid))))))

(= (gc truth-record $statement $threshold)
   (let $sid (sn sid (sn canon $statement))
     (goalchainer-snars-v1 truth ok
       (truth $sid (sn canon $statement)
              (evidence (sn evidence $sid))
              (opinion (sn opinion $sid))
              (view (sn view $sid))
              (expectation (sn expect $sid))
              (above (sn above $sid $threshold))
              (marginal (sn marginal (sn canon $statement)))
              (surprise (sn surprise $sid))))))

(= (gc control-record $budget)
   (let* (($compiled (collapse (sn compile-rules!)))
          ($step (collapse (sn step!)))
          ($focused (sn focus! $budget))
          ($forgotten (sn forget! $budget)))
     (goalchainer-snars-v1 control ok
       (control
         (compiled-now $compiled)
         (compiled (collapse (sn compiled)))
         (step $step)
         (frontier (get-state &sn-frontier))
         (forget-enabled (sn forget-enabled?))
         (forgotten $forgotten)))))

(= (gc structural-record)
   (goalchainer-snars-v1 structural ok
     (structural
       (rewrite-names (collapse (sn rw-list)))
       (rewrite-types (collapse (sn rw-typed)))
       (compiled (collapse (sn compiled)))
       (proposals (collapse (sn proposals))))))

(= (gc transform-record $kind $first $second $value)
   (let $result
     (case $kind
       ((marginal
          (sn marginal! (sn canon $first) $value))
        (similarity
          (sn sim2inh! (sn sid (sn canon $first))))
        (symmetric
          (sn sym-edges! (sn sid (sn canon $first))))
        (disjunction
          (sn or-view
            (sn sid (sn canon $first))
            (sn sid (sn canon $second))))))
     (goalchainer-snars-v1 transform ok
       (transform $kind $result))))

(= (gc compiled-prove-record $statement)
   (let* (($compiled (collapse (sn compile-rules!)))
          ($answers (collapse (sn cfire! $statement))))
     (goalchainer-snars-v1 compiled-prove ok
       (compiled-proof
         (compiled-now $compiled)
         (answers $answers)))))

(= (gc guard-record $goal)
   (goalchainer-snars-v1 guard ok
     (guard
       (goal $goal)
       (proves (sn guard-proves? $goal))
       (model (sn guard? $goal)))))

(= (gc outcome-record $statement $r $s $a $source $trust)
   (let* (($sid (sn sid (sn canon $statement)))
          ($before (sn_tr_p src $source (sn config trust-prior-src)))
          ($outcome (sn outcome! $sid $r $s $a $source $trust))
          ($after (sn_tr_p src $source (sn config trust-prior-src))))
     (goalchainer-snars-v1 outcome ok
       (outcome-audit $outcome
                      (source $source)
                      (trust-before $before)
                      (trust-after $after)))))

(= (gc error-record $operation $code $message)
   (goalchainer-snars-v1 $operation error
     (error $code $message)))
