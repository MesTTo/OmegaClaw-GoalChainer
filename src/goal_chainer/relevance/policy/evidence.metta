; Purpose: the relevance review's evidence policy: what a review believes about each declared
; signal at its reference time, which fact that belief gives the theory, and whether the
; signal's readings are in dispute, read off the justification kernel's labels for the review's
; readings.
;
;   (gc-relevance-effective AS-OF ((Reading SIGNAL STATE ESTIMATOR VALIDITY ID) ...) (SIGNAL ...))
;     -> ((Effective SIGNAL STATE FACT DISPUTED (SUPPORT-ID ...) (CONTESTED-ID ...)
;                    (DECAYED-ID ...) (UNKNOWN-ID ...)) ...)
;      | (Refused (Problem KIND DETAIL) ...)
;
; SIGNAL is a string; a reading's STATE is "detected", "refuted" or "unknown", its ESTIMATOR the
; estimator class that produced it, and its VALIDITY Forever or (Until MICROSECONDS). An
; effective STATE may also be "conflicted", and DISPUTED is True or False. AS-OF is integer
; microseconds since the epoch, and ID is the reading's observation id, the one name the planner
; gives its row too, so Python can name the observations behind each belief. A Refused answer is
; the kernel's, for rows it cannot read, which validated readings never make.
;
; The kernel decides (planning/justification.metta). Each detected or refuted reading is one row,
; built by the shared vocabulary's gc-reading-row: (From (Signal SIGNAL) SOURCE) or (From (Not
; (Signal SIGNAL)) SOURCE), whose SOURCE (Observation (Reading ID ESTIMATOR VALIDITY)) carries
; the reading's class and validity; the kernel's answer names each claim (Claim C) and each row
; (Row R), so no spelling of a signal can be read as another category. A reading past its
; validity is undercut and decays toward unknown, never toward refuted (the paper's section 8.3:
; an unreviewed edge decays toward unknown, not toward its last value). Of two current contrary
; readings the one whose class has the higher tier in the shared vocabulary is preferred, an
; adopted, defeasible preference between sources and never a proof that a measurement is true;
; two of one tier leave both undecided, a conflict rather than a majority vote. AgenticMind keeps
; the same line between an unsupported claim and a refuted one (claim.lp at 6df23ed2, lines 39
; and 69).
;
; The belief projects the kernel's labels. A claim of either polarity that is Accepted, whatever
; its check, gives the state detected or refuted and its fact; an Undecided claim gives conflicted
; and no fact; anything else gives unknown. Each reading is listed once: a current row the
; preference defeated as contested, any other current row as support, an undercut row as decayed,
; and an unknown reading, which makes no row, as unknown. A signal is in dispute when it is
; conflicted or one of its readings is contested: the disagreement is live, and the ranking
; escalates it when the signal can affect the review, while the theory runs on the preferred
; polarity and the authority ceilings read the support's classes unchanged, since acceptance
; grants no authority. An expired or withdrawn contrary is no live disagreement.
;
; FACT is (Some (Fact SIGNAL True)) for a detected signal, (Some (Fact SIGNAL False)) for a refuted
; one and None otherwise. Defeasible logic is not negation as failure: a rule body (not (signal X))
; needs the negative literal proved, so a refuted signal asserts its negation, and an unknown or
; conflicted one asserts nothing, which leaves the theory open-world exactly where evidence is
; missing. Python renders FACT as (given (signal X)) or (given (not (signal X))).
; am[implements a-rel-signals-1016@16b33a] am[rests-on c-integrate-agenticmind-support-1016@b60619]
; am[rests-on c-integrate-user-metta-policy-1016@9eb3d0] am[implements a-rel-rr-projection-1018@a05ccf]
; am[rests-on c-integrate-reading-owner-rule-1018@9de720] am[rests-on c-rel-projection-accepted-any-check-1018@fc3e2d]
; am[rests-on c6bd00cd@8dffaf] am[rests-on c-rel-agrees-jk-typed-boundary-1018@e7ee48]
; am[implements a-rel-rr-p-typed-refs-1018@4eb60a]

(= (gc-relevance-reading-signal (Reading $signal $state $estimator $validity $index)) $signal)
(= (gc-relevance-reading-observation (Reading $signal $state $estimator $validity $id)) $id)

; The rows are the shared vocabulary's, one per definite reading, and they are bound before the
; kernel's entry takes them: its parameters are typed Atom, so a call written in its argument
; would reach it unevaluated.
; Time: one kernel call over the r readings' rows, then for each of s signals one scan of the
; kernel's a answer atoms per claim and per reading, s * (2 + r) * a comparisons at most.
; am[rests-on c-jk-atom-entry-inert-1018@63e37f] am[rests-on c-rel-typed-entry-let-bound-1018@bda6c4]
; am[implements a-rel-rr-p-rows-1018@14fc36] am[rests-on c-rel-rr-definite-readings-have-class-1018@20cb5d]
; am[implements a-rel-pj-reading-row-1018@03ad71] am[implements a-rel-mig-typed-entries-1018@c150af]
(: gc-relevance-effective (-> Atom Atom Atom Expression))
(= (gc-relevance-effective $as-of $readings $signals)
   (let* (($rows (gc-reading-rows $readings))
          ($answer (gc-justify (At $as-of) $rows)))
     (if (== (car-atom $answer) Justification)
         (gc-relevance-beliefs (cdr-atom $answer) $readings $signals)
         $answer)))

(= (gc-relevance-beliefs $labelled $readings $signals)
   (map-atom $signals $signal
     (gc-relevance-belief $labelled $signal (filter-atom $readings $r (== (gc-relevance-reading-signal $r) $signal)))))

; am[implements a-rel-rr-p-effective-1018@2a0968] am[implements a-rel-rr-p-escalation-1018@86a7bb]
(= (gc-relevance-belief $labelled $signal $readings)
   (let* (($state (gc-relevance-state (gc-relevance-status-of $labelled (Claim (Signal $signal)))
                                      (gc-relevance-status-of $labelled (Claim (Not (Signal $signal))))))
          ($standings (map-atom $readings $reading
                        (Standing (gc-relevance-standing $labelled $reading) (gc-relevance-reading-observation $reading))))
          ($contested (gc-relevance-observations Contested $standings)))
     (Effective $signal $state (gc-relevance-fact $signal $state)
                (or (== $state "conflicted") (not (== $contested ())))
                (gc-relevance-observations Support $standings) $contested
                (gc-relevance-observations Decayed $standings) (gc-relevance-observations Unknown $standings))))

(= (gc-relevance-state $positive $negative)
   (if (== $positive Accepted)
       "detected"
       (if (== $negative Accepted)
           "refuted"
           (if (or (== $positive Undecided) (== $negative Undecided)) "conflicted" "unknown"))))

; An argument's label; a claim no row speaks for has none, which is silence: unknown, never refuted.
(= (gc-relevance-status-of $labelled $argument)
   (let $found (filter-atom $labelled $item (gc-relevance-labels $item $argument))
     (if (== $found ()) Unsupported (gc-relevance-label-status (car-atom $found)))))

; Every cell of a row's label and link decides its standing: an undercut link decays the row
; whatever its label; a current row that lost to a preferred contrary is contested; any other
; current row, Accepted or Undecided, supports the belief. A link left Undecided counts as current,
; though no reading's row can have one, since expiry is a reason that always stands.
(= (gc-relevance-standing $labelled $reading)
   (if (gc-reading-definite $reading)
       (let $row (gc-reading-row $reading)
         (gc-relevance-row-standing (gc-relevance-status-of $labelled (Row $row)) (gc-relevance-row-link $labelled (Row $row))))
       Unknown))
(= (gc-relevance-row-standing $status $link)
   (if (== $link Withdrawn) Decayed (if (== $status Refuted) Contested Support)))

(= (gc-relevance-row-link $labelled $row)
   (gc-relevance-link-state (car-atom (filter-atom $labelled $item (gc-relevance-links $item $row)))))

(= (gc-relevance-labels (Label $argument $status $check) $wanted) (== $argument $wanted))
(= (gc-relevance-labels (Link $row $state) $wanted) False)
(= (gc-relevance-label-status (Label $argument $status $check)) $status)
(= (gc-relevance-links (Link $row $state) $wanted) (== $row $wanted))
(= (gc-relevance-links (Label $argument $status $check) $wanted) False)
(= (gc-relevance-link-state (Link $row $state)) $state)

(= (gc-relevance-observations $kind $standings)
   (map-atom (filter-atom $standings $standing (gc-relevance-standing-is $standing $kind)) $kept
             (gc-relevance-standing-observation $kept)))
(= (gc-relevance-standing-is (Standing $kind $id) $wanted) (== $kind $wanted))
(= (gc-relevance-standing-observation (Standing $kind $id)) $id)

(= (gc-relevance-fact $signal $state)
   (if (== $state "detected")
       (Some (Fact $signal True))
       (if (== $state "refuted") (Some (Fact $signal False)) None)))
