; Purpose: the planner's feedback rules, which turn the executor's journal and the receipt-v2 documents its
; caller holds into the attempts relevance's assess_attempt grades and, from those grades, the trial counts a
; library's promotion rule reads (a-ev-pk-feedback-1018): each typed entry is a wrapper over an untyped worker.
;
;   (gc-pk-run-feedback-attempts LIBRARY EVENTS DOCUMENTS)
;     -> (Attempts ((Assess "RECEIPT" "PROCEDURE" K NEXT) ...) ("PROCEDURE" ...)) | (Refused (Problem KIND DETAIL) ...)
;   (gc-pk-run-feedback-counts PROMOTION COMPLETE TRIALS)
;     -> (Counts ((Count "PROCEDURE" K SUCCESSES FAILURES) ...))
;
; LIBRARY is goal_chainer.planning's library term. EVENTS are the journal's, projection.metta's: (Started "I"
; "P" "J"), (Dispatched "I" "S" "A" "DECISION" AT), (Receipt "R" "I" "S" "A" APPLIED), (Superseded "R"
; "LATEST") and (Finished "I"). DOCUMENTS are ((Document "R" "ATTEMPT" "ACTION" "FINGERPRINT" APPLIED ISSUED)
; ...), the receipt-v2 document the caller holds for journal Receipt R: APPLIED (At MICROS) or NotApplied,
; ISSUED microseconds, as every AT here is. An Assess asks for one grade of receipt R's attempt against the
; K-th Achieves literal of its procedure, from 0, its window closing at NEXT, (Until "R2") when receipt R2's
; attempt is applied next on that literal's subject, or Forever; the caller reads the decision instant from
; R's Dispatched and the window's end from R2's document. The second answer lists each procedure whose record is complete. A
; Trial is (Trial "P" K STATUS ATTRIBUTION), assess_attempt's status and attribution, PROMOTION (Promotion N)
; or NoPromotion, and COMPLETE that list.
; am[implements a-ev-pk-feedback-1018@84fec1] am[rests-on c-ev-pk-typed-entry-wrapper-1018@ef5a23]

!(import! &self (library lib_functional))

; --- the attempts ---------------------------------------------------------------------------------------------
; A journal and documents that do not cohere are refused (c-ev-fb-refusals-1018); else every applied attempt
; whose current receipt the caller documented is graded once per Achieves literal (c-ev-fb-window-per-target-1018),
; and a procedure whose every dispatched attempt has a documented current receipt is complete
; (c-ev-fb-complete-record-1018).
; Time: for e events and d documents, each document and receipt scans the events once, and each graded
; literal scans the current receipts for its window: O((e + d)·e + g·r) for g grades and r receipts.
; am[implements a-ev-fb-request-receipts-1018@4c8f23] am[implements a-ev-fb-trials-1018@775554]
(: gc-pk-run-feedback-attempts (-> Atom Atom Atom Expression))
(= (gc-pk-run-feedback-attempts $library $events $documents) (gc-pk-feedback-attempts $library $events $documents))
(= (gc-pk-feedback-attempts (Library $procedures $investigators) $events $documents)
   (let* (($receipts (filter-atom $events $e (gc-pk-headed? Receipt $e)))
          ($superseded (gc-pk-flatten (map-atom $events $e (case $e (((Superseded $old $latest) ($old)) ($other ()))))))
          ($current (filter-atom $receipts $r (not (gc-has $superseded (index-atom $r 1)))))
          ($problems (append (gc-pk-document-problems $events $receipts $documents $procedures)
                             (append (gc-pk-current-problems $current) (gc-pk-supersession-problems $events $receipts $documents)))))
     (if (== $problems ())
         (Attempts (gc-pk-flatten (map-atom $current $c (gc-pk-assessments $c $current $events $documents $procedures)))
                   (filter-atom (map-atom $procedures $p (index-atom $p 1)) $name
                     (gc-pk-complete? $name $events $current $documents)))
         (cons-atom Refused $problems))))
(= (gc-pk-headed? $head $atom) (if (== (get-metatype $atom) Expression) (== (car-atom $atom) $head) False))

; Every document names a journal Receipt of a dispatched attempt of a started instance, and agrees with them:
; the same attempt, applied exactly when the journal says, under the dispatched step's decision digest, and
; for an act the act's action.
(= (gc-pk-document-problems $events $receipts $documents $procedures)
   (append (gc-pk-flatten (map-atom $documents $d (gc-pk-document-faults $d $events $receipts $procedures)))
           (gc-pk-flatten (map-atom $receipts $r (gc-pk-receipt-faults $r $events)))))
(= (gc-pk-receipt-faults (Receipt $id $i $s $a $applied) $events)
   (append (if (== (gc-pk-dispatch-of $i $s $a $events) ()) ((Problem UndispatchedReceipt $id)) ())
           (if (== (gc-pk-procedure-of $i $events) ()) ((Problem UnstartedInstance $i)) ())))
(= (gc-pk-document-faults (Document $id $attempt $action $fingerprint $applied-at $issued) $events $receipts $procedures)
   (let $found (filter-atom $receipts $r (== (index-atom $r 1) $id))
     (if (== $found ())
         ((Problem UnknownReceipt $id))
         (case (car-atom $found)
           (((Receipt $rid $i $s $a $applied)
             (let* (($dispatch (gc-pk-dispatch-of $i $s $a $events))
                    ($expected (gc-pk-step-action (gc-pk-procedure-of $i $events) $s $procedures)))
               (gc-pk-flatten
                 ((if (== $attempt $a) () ((Problem AttemptMismatch $id)))
                  (if (== $applied (not (== $applied-at NotApplied))) () ((Problem ApplicationMismatch $id)))
                  (case $dispatch
                    ((() ())
                     ((Dispatched $di $ds $da $decision $at) (if (== $fingerprint $decision) () ((Problem DecisionMismatch $id))))))
                  (if (or (== $expected None) (== $expected $action)) () ((Problem ActionMismatch $id))))))))))))
; The Dispatched of an attempt, or ().
(= (gc-pk-dispatch-of $i $s $a $events)
   (let $found (filter-atom $events $e (case $e (((Dispatched $di $ds $da $decision $at) (and (== $di $i) (and (== $ds $s) (== $da $a))))
                                                ($other False))))
     (if (== $found ()) () (car-atom $found))))
; The procedure the journal started instance I of, or ().
(= (gc-pk-procedure-of $i $events)
   (let $found (filter-atom $events $e (case $e (((Started $si $p $j) (== $si $i)) ($other False))))
     (if (== $found ()) () (index-atom (car-atom $found) 2))))
; The action of step S of procedure P when it is an act, else None.
(= (gc-pk-step-action $name $s $procedures)
   (let $acts (gc-pk-flatten (map-atom (filter-atom $procedures $p (== (index-atom $p 1) $name)) $q
                (filter-atom (index-atom $q 4) $t (case $t (((Act $id $action $after $binds) (== $id $s)) ($other False))))))
     (if (== $acts ()) None (index-atom (car-atom $acts) 2))))

; One current receipt per attempt.
(= (gc-pk-current-problems $current)
   (let $attempts (map-atom $current $c (case $c (((Receipt $id $i $s $a $applied) (Attempt $i $s $a)))))
     (map-atom (unique-atom (filter-atom $attempts $x (> (size-atom (filter-atom $attempts $y (== $y $x))) 1))) $twice
               (Problem AmbiguousReceipt $twice))))
; A Superseded's later receipt is the same attempt's and, where both are documented, issued after the earlier.
(= (gc-pk-supersession-problems $events $receipts $documents)
   (gc-pk-flatten (map-atom $events $e
     (case $e
       (((Superseded $old $latest)
         (let* (($o (filter-atom $receipts $r (== (index-atom $r 1) $old)))
                ($l (filter-atom $receipts $r (== (index-atom $r 1) $latest))))
           (if (or (== $o ()) (== $l ()))
               ((Problem SupersessionMismatch $old))
               (if (and (== (gc-pk-attempt-of (car-atom $o)) (gc-pk-attempt-of (car-atom $l)))
                        (gc-pk-issued-after? $latest $old $documents))
                   ()
                   ((Problem SupersessionMismatch $old))))))
        ($other ()))))))
(= (gc-pk-attempt-of (Receipt $id $i $s $a $applied)) (Attempt $i $s $a))
(= (gc-pk-issued-after? $later $earlier $documents)
   (let* (($l (gc-pk-issued $later $documents))
          ($e (gc-pk-issued $earlier $documents)))
     (if (or (== $l None) (== $e None)) True (> $l $e))))
(= (gc-pk-issued $id $documents)
   (let $found (filter-atom $documents $d (== (index-atom $d 1) $id))
     (if (== $found ()) None (index-atom (car-atom $found) 6))))

; The grades of one current receipt: none unless its attempt was applied and the caller documented it, else one
; per Achieves literal of its procedure.
(= (gc-pk-assessments (Receipt $id $i $s $a $applied) $current $events $documents $procedures)
   (let $doc (filter-atom $documents $d (== (index-atom $d 1) $id))
     (if (or (== $doc ()) (not $applied))
         ()
         (let* (($name (gc-pk-procedure-of $i $events))
                ($achieves (gc-pk-achieves-of $name $procedures))
                ($applied-at (gc-pk-applied-micros (car-atom $doc))))
           (map-atom (gc-pk-indexed $achieves 0) $k
             (case $k (((Indexed $n $lit)
                        (Assess $id $name $n (gc-pk-window $lit $id $applied-at $current $events $documents $procedures))))))))))
(= (gc-pk-achieves-of $name $procedures)
   (index-atom (car-atom (filter-atom $procedures $p (== (index-atom $p 1) $name))) 2))
(= (gc-pk-applied-micros (Document $id $attempt $action $fingerprint (At $micros) $issued)) $micros)
(= (gc-pk-indexed $items $k)
   (if (== $items ()) () (cons-atom (Indexed $k (car-atom $items)) (gc-pk-indexed (cdr-atom $items) (+ $k 1)))))
; The window of a grade of LIT: the earliest application after AT of another current receipt's applied attempt
; whose procedure achieves LIT or its negation, else Forever; equal instants close nothing
; (c-ev-fb-window-per-target-1018).
(= (gc-pk-window $lit $id $at $current $events $documents $procedures)
   (let $later (gc-pk-flatten (map-atom $current $c
                 (case $c (((Receipt $other $i $s $a True)
                            (let $doc (filter-atom $documents $d (== (index-atom $d 1) $other))
                              (if (or (== $other $id) (== $doc ()))
                                  ()
                                  (let $y (gc-pk-applied-micros (car-atom $doc))
                                    (if (and (> $y $at) (gc-pk-achieves-subject? (gc-pk-procedure-of $i $events) $lit $procedures))
                                        ((Later $y $other))
                                        ())))))
                           ($unapplied ())))))
     (if (== $later ()) Forever (Until (index-atom (car-atom (msort $later)) 2)))))
(= (gc-pk-achieves-subject? $name $lit $procedures)
   (let $subject (gc-pk-subject-of $lit)
     (gc-pk-any (map-atom (gc-pk-achieves-of $name $procedures) $l (== (gc-pk-subject-of $l) $subject)))))

; Complete: every dispatched attempt of the procedure's instances has a documented current receipt.
(= (gc-pk-complete? $name $events $current $documents)
   (gc-pk-all (map-atom (filter-atom $events $e (case $e (((Dispatched $i $s $a $decision $at) (== (gc-pk-procedure-of $i $events) $name))
                                                       ($other False))))
                        $d (case $d (((Dispatched $i $s $a $decision $at)
                                      (gc-pk-any (map-atom $current $c
                                        (case $c (((Receipt $id $ci $cs $ca $applied)
                                                   (and (and (== $ci $i) (and (== $cs $s) (== $ca $a)))
                                                        (not (== (filter-atom $documents $doc (== (index-atom $doc 1) $id)) ()))))))))))))))

; --- the counts ---------------------------------------------------------------------------------------------------
; A grade is a success when the receipt confirmed the literal and named the attempt its producer, a failure when
; it missed it so attributed, and no trial otherwise: only an attributed grading moves a procedure's record
; (a-rel-rcpt-causal-credit-split-1017). A procedure's literal is counted only under a declared promotion, with
; its record complete and at least N trials (a-ev-fb-promotion-1018).
; Time: one pass over the trials per (procedure, literal) they name.
; am[implements a-ev-fb-trials-1018@775554] am[implements a-ev-fb-promotion-1018@2ae86c]
(: gc-pk-run-feedback-counts (-> Atom Atom Atom Expression))
(= (gc-pk-run-feedback-counts $promotion $complete $trials) (gc-pk-feedback-counts $promotion $complete $trials))
(= (gc-pk-feedback-counts $promotion $complete $trials)
   (case $promotion
     ((NoPromotion (Counts ()))
      ((Promotion $least)
       (Counts (gc-pk-flatten (map-atom (unique-atom (map-atom $trials $t (case $t (((Trial $p $k $status $by) (Target $p $k))))))
                                        $target (gc-pk-count-of $target $least $complete $trials))))))))
(= (gc-pk-count-of (Target $name $k) $least $complete $trials)
   (let* (($mine (filter-atom $trials $t (case $t (((Trial $p $n $status $by) (and (== $p $name) (== $n $k)))))))
          ($successes (size-atom (filter-atom $mine $t (case $t (((Trial $p $n $status $by) (and (== $status "confirmed") (== $by "asserted"))))))))
          ($failures (size-atom (filter-atom $mine $t (case $t (((Trial $p $n $status $by) (and (== $status "missed") (== $by "asserted")))))))))
     (if (and (gc-has $complete $name) (>= (+ $successes $failures) $least))
         ((Count $name $k $successes $failures))
         ())))
