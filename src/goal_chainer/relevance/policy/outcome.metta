; Purpose: the relevance review's outcome policy: whether a stored review still has its support,
; whether a host's receipt for one attempt is coherent, and what it establishes about each of the
; proposal's predictions.
;
;   (gc-relevance-freshness (Moved READINGS DOMAIN REVIEW-POLICY ENGINE AUTHORITY MOTIVATION))
;     -> (Freshness STATUS SUPPORT)
;
; Each Moved field is a boolean: whether a readset reading, the domain digest, the review
; policy's digest, the engine identity, the review's authority rung or the motivation snapshot's
; identity changed since the review.
; A review is "stale" when anything it rests on moved, and its support is then "withdrawn"; it is
; "fresh" with its support "standing" otherwise. Stale is never a verdict against the review and
; never a reason to prefer an alternative, which is AgenticMind's distinction between an
; unsupported claim and a refuted one (claim.lp at 6df23ed2, lines 39, 69 and 94-95), and its rule
; that a summary goes stale when what it covered moves (state.lp, lines 720-734).
;
;   (gc-relevance-receipt-faults ATTEMPT ISSUED (OBSERVATION ...)) -> ((Fault REASON SUBJECT MESSAGE) ...)
;   (gc-relevance-assess ATTEMPT DECIDED WINDOW ((Prediction KIND TARGET) ...) (OBSERVATION ...))
;     -> (Assessment ((Status KIND TARGET STATUS ATTRIBUTION (INDEX ...)) ...)
;                    ((Uncounted INDEX REASON) ...))
;      | (Refused ((Fault REASON Receipt MESSAGE) ...))
;
; ATTEMPT is (Attempt "ID" (Applied MICROSECONDS)) or (Attempt "ID" NotApplied). ISSUED is when
; the host wrote the receipt and DECIDED when the decision the attempt applied was made, both in
; microseconds: a review's as_of, or the instant a planner dispatched the step it admitted, and
; never before a reading the decision rested on. WINDOW is (Until MICROSECONDS), when the same
; subject's next applied attempt was applied, or Forever. An OBSERVATION is (Observation INDEX
; KIND TARGET OUTCOME ESTIMATOR TIME PRODUCER): TIME is (At MICROSECONDS) or Untimed, and PRODUCER
; is (ProducedBy "ID"), the attempt the observation says produced what it saw, or Unstated. KIND
; is "effect", "contribution" or "achieves", TARGET a dimension, a goal or a literal a step
; achieves, OUTCOME "confirmed" or "contradicted", ESTIMATOR an estimator class, all strings. A
; fault's SUBJECT is Receipt or the INDEX of the observation it is in, and its MESSAGE says what is
; wrong with the host's values left as {where}, {attempt}, {applied}, {issued}, {observed},
; {producer}, {decision}, {decided} and {next} for the host to fill. A receipt is assessed only
; once gc-relevance-receipt-faults found no fault in it. Completed work is not a confirmed
; effect: an applied action leaves each prediction "predicted" until a counted observation checks
; it, "confirmed" or "missed", and counted observations that disagree leave it "conflicted"
; whatever their order (state.lp, lines 198-228 and 266-270). An action that was not applied
; attempted nothing, so its predictions are "not-attempted" and no observation counts. Goal
; achievement is never decided here.
; am[implements a-rel-review-contract-1016@d0bea9] am[rests-on c-integrate-agenticmind-effects-1016@7fdbf0]
; am[rests-on c-integrate-agenticmind-support-1016@b60619] am[rests-on c-integrate-user-metta-policy-1016@9eb3d0]
; am[implements a-rel-rcpt-v2-counting-1017@ae46fe] am[rests-on c-rel-rcpt-conflict-kept-1017@808ee5]
; am[implements a-rel-rcpt-v2-metta-rules-1018@c22bf6] am[rests-on c-user-metta-first-grounded-atoms-1018@b1803b]
; am[implements a-rel-assess-attempt-1018@20e6ca] am[rests-on c-rel-decided-at-follows-readings-1018@8c479a]

; am[implements a-rel-mig-typed-entries-1018@c150af]
(: gc-relevance-freshness (-> Atom Expression))
; am[implements a-v2m-snapshot-identity-1019@118a4b]
(= (gc-relevance-freshness (Moved $readings $domain $policy $engine $authority $motivation))
   (if (gc-relevance-any ($readings $domain $policy $engine $authority $motivation))
       (Freshness "stale" "withdrawn")
       (Freshness "fresh" "standing")))

(= (gc-relevance-observation-index (Observation $index $kind $target $outcome $estimator $time $producer)) $index)
(= (gc-relevance-observation-about (Observation $index $kind $target $outcome $estimator $time $producer)) (About $kind $target))
(= (gc-relevance-observation-outcome (Observation $index $kind $target $outcome $estimator $time $producer)) $outcome)
(= (gc-relevance-prediction-about (Prediction $kind $target)) (About $kind $target))

; Whether an observation follows the application: only a timed observation of an applied attempt
; can, and only strictly after it.
(= (gc-relevance-follows NotApplied $time) False)
(= (gc-relevance-follows (Applied $applied) Untimed) False)
(= (gc-relevance-follows (Applied $applied) (At $observed)) (< $applied $observed))

; Every table here is a list of rows (Row REASON HOLDS ...) that the shared reader
; (policy/goalchainer_fault_tables.metta) reads in order, the First reading: a later row reads
; what the rows before it established, so only a subject's first failing row is its fault.
; am[implements a-rel-nd-shared-table-reader-1018@24e3dd]

; What a receipt states about its own instants and about production must cohere before anything
; it observed can count: the receipt table is read once and the observation table once per
; observation. A receipt reports what happened up to when it was written, and a product follows
; the start of what produced it (PROV-CONSTRAINTS Constraint 34), which an attempt that applied
; nothing gives no time to follow. The order of times is all such a statement is checked against;
; it never makes the statement. Each row ends with its fault's message.
; am[implements a-rel-rcpt-v2-metta-rules-1018@c22bf6] am[addresses i-rel-rcpt-rules-in-python-1018@707110]
; am[rests-on c-rel-rcpt-produced-needs-application-1017@8afb25] am[rests-on c-rel-rcpt-prov-ordering-necessary-1017@04778d]
(= (gc-relevance-receipt-table)
   ((Row "applied-after-issue" gc-relevance-row-applied-by-issue
         "receipt.applied_at {applied} is after the receipt was issued at {issued}")))
(= (gc-relevance-observation-table)
   ((Row "observed-after-issue" gc-relevance-row-observed-by-issue
         "{where} was observed at {observed}, after the receipt was issued at {issued}")
    (Row "producer-not-attempt" gc-relevance-row-producer-is-attempt
         "{where} names {producer} as its producer, but the receipt is for attempt {attempt}")
    (Row "produced-without-application" gc-relevance-row-producer-applied
         "{where} says attempt {attempt} produced it, but the receipt applied nothing")
    (Row "produced-before-application" gc-relevance-row-producer-preceded
         "{where} says attempt {attempt} produced it, so it must be observed after the application at {applied}")))

(= (gc-relevance-row-applied-by-issue (Written (Attempt $id $application) $issued) $receipt)
   (gc-relevance-applied-by $application $issued))
(= (gc-relevance-applied-by NotApplied $moment) True)
(= (gc-relevance-applied-by (Applied $applied) $moment) (<= $applied $moment))
(= (gc-relevance-row-observed-by-issue (Written $attempt $issued)
                                       (Observation $i $kind $target $outcome $estimator $time $producer))
   (gc-relevance-observed-by $time $issued))
(= (gc-relevance-observed-by Untimed $moment) True)
(= (gc-relevance-observed-by (At $observed) $moment) (<= $observed $moment))
(= (gc-relevance-row-producer-is-attempt (Written (Attempt $id $application) $issued)
                                         (Observation $i $kind $target $outcome $estimator $time $producer))
   (if (== $producer Unstated) True (== $producer (ProducedBy $id))))
(= (gc-relevance-row-producer-applied (Written (Attempt $id $application) $issued)
                                      (Observation $i $kind $target $outcome $estimator $time $producer))
   (if (== $producer Unstated) True (not (== $application NotApplied))))
(= (gc-relevance-row-producer-preceded (Written (Attempt $id $application) $issued)
                                       (Observation $i $kind $target $outcome $estimator $time $producer))
   (if (== $producer Unstated) True (gc-relevance-follows $application $time)))

; The receipt against the decision and the window it is assessed in: no application precedes the
; decision it applied, which the counting table's before-application row relies on, and the same
; subject's next attempt follows this one.
; am[implements a-rel-rcpt-v2-metta-rules-1018@c22bf6] am[addresses i-rel-rcpt-rules-in-python-1018@707110]
; am[rests-on c-rel-rcpt-readings-precede-as-of-1017@54e66d] am[rests-on c-rel-next-attempt-at-final-1017@a3d73f]
; am[implements a-rel-assess-attempt-1018@20e6ca] am[rests-on c-rel-assessment-table-names-decision-1018@738b65]
(= (gc-relevance-assessment-table)
   ((Row "applied-before-decision" gc-relevance-row-applied-after-decision
         "attempt {attempt} was applied at {applied}, before decision {decision} was made at {decided}")
    (Row "next-attempt-not-after-application" gc-relevance-row-window-after-application
         "next_attempt_at {next} is not after attempt {attempt}'s application at {applied}")))

(= (gc-relevance-row-applied-after-decision (Assessing (Attempt $id $application) $decided $window) $assessing)
   (gc-relevance-not-before $application $decided))
(= (gc-relevance-not-before NotApplied $moment) True)
(= (gc-relevance-not-before (Applied $applied) $moment) (>= $applied $moment))
(= (gc-relevance-row-window-after-application (Assessing (Attempt $id $application) $decided $window) $assessing)
   (gc-relevance-closes-after $application $window))
(= (gc-relevance-closes-after NotApplied $window) True)
(= (gc-relevance-closes-after (Applied $applied) Forever) True)
(= (gc-relevance-closes-after (Applied $applied) (Until $next)) (> $next $applied))

; The receipt is one subject, named Receipt, and each observation another, named by its index.
; Time: one row check for the receipt and at most 4 for each of its o observations.
; am[implements a-rel-mig-typed-entries-1018@c150af]
(: gc-relevance-receipt-faults (-> Atom Atom Atom Expression))
(= (gc-relevance-receipt-faults $attempt $issued $observations)
   (let* (($written (Written $attempt $issued))
          ($observed (map-atom $observations $o (Subject (gc-relevance-observation-index $o) $o))))
     (append (gc-table-faults First (gc-relevance-receipt-table) $written ((Subject Receipt $written)))
             (gc-table-faults First (gc-relevance-observation-table) $written $observed))))

; The counting table. An observation counts toward the predictions about its target only when
; every row holds, and the first row that fails is the reason it is listed uncounted. A later row
; reads what the rows before it established: an application time and an observation time. Every
; reading the decision rested on was made at or before DECIDED, which no application precedes, so
; the fourth row keeps the decision's own evidence from coming back as its outcome. The fifth
; reads the window as reading validity is read, so an observation made exactly when the next
; attempt was applied belongs to this attempt.
; am[implements a-rel-rcpt-v2-counting-1017@ae46fe] am[rests-on c-rel-rcpt-readings-precede-as-of-1017@54e66d]
; am[rests-on c-rel-rcpt-untimed-loophole-1017@cf7c9c] am[addresses i-ev-pl-stale-observation-credits-1017@4583b7]
; am[rests-on c-rel-decided-at-follows-readings-1018@8c479a]
(= (gc-relevance-counting-table)
   ((Row "cannot-establish" gc-relevance-row-establishing)
    (Row "not-applied" gc-relevance-row-applied)
    (Row "untimed" gc-relevance-row-timed)
    (Row "before-application" gc-relevance-row-after-application)
    (Row "after-next-attempt" gc-relevance-row-within-window)
    (Row "unpredicted" gc-relevance-row-predicted)))

; Only an observation of a class that can establish what happened counts; an estimate is listed
; and changes nothing. The shared vocabulary says which classes establish.
; am[rests-on c-rel-establishing-classes-1016@72edbb] am[implements a-rel-rr-shared-module-1018@13aee9]
(= (gc-relevance-row-establishing $context (Observation $i $kind $target $outcome $estimator $time $producer))
   (gc-establishes $estimator))
(= (gc-relevance-row-applied (Context (Attempt $id $application) $window $about) $observation)
   (not (== $application NotApplied)))
(= (gc-relevance-row-timed $context (Observation $i $kind $target $outcome $estimator $time $producer))
   (not (== $time Untimed)))
(= (gc-relevance-row-after-application (Context (Attempt $id $application) $window $about)
                                       (Observation $i $kind $target $outcome $estimator $time $producer))
   (gc-relevance-follows $application $time))
(= (gc-relevance-row-within-window (Context $attempt $window $about)
                                   (Observation $i $kind $target $outcome $estimator (At $observed) $producer))
   (not (gc-reading-expired $observed $window)))
; Membership answers once however often a target occurs in $about, so a target two predictions
; share never answers the whole assessment twice (c-rel-rcpt-member-needs-unique-1017).
; am[related c-rel-rcpt-member-needs-unique-1017@222657] am[implements a-rel-member-once-1018@45ebae]
(= (gc-relevance-row-predicted (Context $attempt $window $about)
                               (Observation $i $kind $target $outcome $estimator $time $producer))
   (gc-has $about (About $kind $target)))

; Time: at most 6 row checks, each with at most p comparisons, p = predicted targets.
(= (gc-relevance-reason $context $observation)
   (gc-relevance-row-reason (gc-table-first-failing (gc-relevance-counting-table) $context $observation)))
; A row whose predicate answered neither True nor False is the reader's Defect, passed on whole so
; the host's shape check reports the policy's own mistake rather than a reason.
(= (gc-relevance-row-reason Holds) Holds)
(= (gc-relevance-row-reason (Row $reason $holds)) $reason)
(= (gc-relevance-row-reason (Defect $reason $term $answers)) (Defect $reason $term $answers))

; An outcome is credited to the attempt only when a counted observation agreeing with the status
; names this attempt as its producer. When the time order makes that statement credible is the
; observation table's to check (PROV-CONSTRAINTS Constraint 34); the order alone never makes it,
; and a human-asserted statement keeps its establishing class.
; am[implements a-rel-rcpt-v2-counting-1017@ae46fe] am[rests-on c-rel-rcpt-ordering-blind-to-cause-1017@83239a]
; am[rests-on c-rel-rcpt-prov-ordering-necessary-1017@04778d] am[rests-on c-integrate-human-attribution-existing-policy-1017@f0de63]
; am[addresses i-rel-rcpt-confirmation-not-attribution-1017@de2720]
(= (gc-relevance-attribution $id $status $seen)
   (if (== $status "confirmed")
       (gc-relevance-attributed $id "confirmed" $seen)
       (if (== $status "missed") (gc-relevance-attributed $id "contradicted" $seen) "unestablished")))
(= (gc-relevance-attributed $id $agreeing $seen)
   (if (== (filter-atom $seen $o (gc-relevance-produced $o $id $agreeing)) ()) "unestablished" "asserted"))
(= (gc-relevance-produced (Observation $i $kind $target $outcome $estimator $time $producer) $id $agreeing)
   (and (== $producer (ProducedBy $id)) (== $outcome $agreeing)))

(= (gc-relevance-status (Attempt $id $application) (About $kind $target) $seen)
   (let $status (if (== $application NotApplied)
                    "not-attempted"
                    (gc-relevance-verdict (unique-atom (map-atom $seen $o (gc-relevance-observation-outcome $o)))))
     (Status $kind $target $status (gc-relevance-attribution $id $status $seen)
             (map-atom $seen $s (gc-relevance-observation-index $s)))))

(= (gc-relevance-verdict $outcomes)
   (if (== $outcomes ())
       "predicted"
       (if (== (size-atom $outcomes) 1)
           (if (== (car-atom $outcomes) "confirmed") "confirmed" "missed")
           "conflicted")))

(= (gc-relevance-reasoned-counted (Reasoned $observation $reason)) (== $reason Holds))
(= (gc-relevance-reasoned-observation (Reasoned $observation $reason)) $observation)
(= (gc-relevance-reasoned-uncounted (Reasoned $observation $reason))
   (Uncounted (gc-relevance-observation-index $observation) $reason))

; Time: 2 assessment rows, then o reasons of at most 6 rows each, then p * o comparisons,
; p = predictions, o = observations.
; am[implements a-rel-mig-typed-entries-1018@c150af] am[implements a-rel-assess-attempt-1018@20e6ca]
(: gc-relevance-assess (-> Atom Atom Atom Atom Atom Expression))
(= (gc-relevance-assess $attempt $decided $window $predictions $observations)
   (let $assessing (Assessing $attempt $decided $window)
     (let $faults (gc-table-faults First (gc-relevance-assessment-table) $assessing ((Subject Receipt $assessing)))
       (if (== $faults ())
           (gc-relevance-count $attempt $window $predictions $observations)
           (Refused $faults)))))

(= (gc-relevance-count $attempt $window $predictions $observations)
   (let $context (Context $attempt $window (unique-atom (map-atom $predictions $q (gc-relevance-prediction-about $q))))
     (let $reasoned (map-atom $observations $o (Reasoned $o (gc-relevance-reason $context $o)))
       (let $counted (map-atom (filter-atom $reasoned $r (gc-relevance-reasoned-counted $r)) $c
                               (gc-relevance-reasoned-observation $c))
         (Assessment
           (map-atom $predictions $p
             (gc-relevance-status $attempt (gc-relevance-prediction-about $p)
               (filter-atom $counted $w (== (gc-relevance-observation-about $w) (gc-relevance-prediction-about $p)))))
           (map-atom (filter-atom $reasoned $r (not (gc-relevance-reasoned-counted $r))) $u
                     (gc-relevance-reasoned-uncounted $u)))))))
