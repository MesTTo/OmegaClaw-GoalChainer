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
          ((Ev $r $s $a) (sn evidence $sid))
          ((Opinion $b $d $u $oa) (sn opinion $sid))
          ($proofs (gc proof-rows $statement $depth)))
     (belief $sid $canon
             (opinion $b $d $u $oa)
             (evidence $r $s $a)
             (receipts (gc receipts $sid))
             (proofs $proofs)
             (occurrences (gc occurrences $sid)))))

(= (gc belief-record $operation $statement $depth)
   (goalchainer-snars-v1 $operation ok
     (gc direct-belief $statement $depth)))

(= (gc action-assessment $action)
   (action $action
     (acceptable
       (gc direct-belief (gc action-property $action "acceptable") 4))
     (risky
       (gc direct-belief (gc action-property $action "risky") 4))
     (forbidden
       (gc direct-belief (gc action-property $action "forbidden") 4))))

(= (gc assess-record)
   (goalchainer-snars-v1 assess ok
     (assessment
       (gc action-assessment "publish_raw_log")
       (gc action-assessment "publish_redacted_summary")
       (gc action-assessment "hold_external_update"))))

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
   (goalchainer-snars-v1 explain ok
     (explanation
       (belief (gc direct-belief $statement $depth))
       (why-not (collapse (why-not! $statement))))))

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
          ($proofs (collapse (sn what-if! $hypothesis $options $query $depth)))
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
