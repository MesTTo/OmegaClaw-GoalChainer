; Purpose: the vocabulary every domain consumer shares, from section 8.2 of the goal relevance
; governor paper: the ordinal bands, worst to best, the estimator classes with the tier each is
; preferred at, the pure functions every policy reads them through, the one rule that turns a
; reading into the justification kernel's row, and list membership that answers once.
;
;   (gc-bands) -> ("BAND" ...)                          worst to best
;   (gc-estimator-classes) -> ("CLASS" ...)              in table order
;   (gc-estimator-tier "CLASS") -> NUMBER                no answer for a class not in the table
;   (gc-establishes "CLASS") -> True | False             whether the class is above the lowest tier
;   (gc-reading-expired AS-OF VALIDITY) -> True | False
;   (gc-reading-definite READING) -> True | False         whether its state is detected or refuted
;   (gc-reading-row READING) -> ROW                       a definite reading's justification row
;   (gc-reading-rows (READING ...)) -> (ROW ...)          the definite readings' rows, in order
;   (gc-count (ITEM ...) ITEM) -> NUMBER                  how often ITEM occurs in the list
;   (gc-has (ITEM ...) ITEM) -> True | False              answered once, however often ITEM occurs
;   (gc-of (FACT ...) HEAD) -> (FACT ...)                 the facts whose head is HEAD, in order
;   (gc-count-at (FACT ...) HEAD PLACE VALUE) -> NUMBER   how many of those hold VALUE at PLACE
;
; AS-OF is integer microseconds since the epoch and VALIDITY is Forever or (Until MICROSECONDS).
; READING is (Reading SIGNAL STATE ESTIMATOR VALIDITY ID): STATE is "detected", "refuted" or
; "unknown", ESTIMATOR an estimator class, and ID the caller's name for the observation.
; This file is the vocabulary's one home. The relevance policy and the justification kernel load
; it into their own module groups, and goal_chainer.domains.loader reads the two literal tables
; with the text parser on first use, without the engine or a separately maintained copy. The tables are values
; the functions read, never facts in a space: each module group loads its own copy into a space
; of its own, and a named space cannot match another space's facts.
; am[implements a-rel-rr-shared-module-1018@13aee9] am[implements a-rel-nd-vocabulary-down-1018@6e6c8d]
; am[rests-on c-rel-rr-shared-interface-1018@42d1ff] am[rests-on c-rel-rr-vocab-table-not-space-1018@29cd90]
; am[implements a-integrate-vocab-pure-read-1019@745f98]

(= (gc-bands)
   ("strongly-negative" "negative" "slightly-negative" "neutral" "slightly-positive" "positive" "strongly-positive"))

; is-member answers True once per occurrence (c-ev-is-member-per-occurrence-1017), so a list
; holding an element twice makes every rule branching on it answer twice. Counting the matches
; answers once whatever the list holds, so no caller has to keep its lists free of repeats.
; Time: one comparison per item.
; am[implements a-rel-member-once-1018@45ebae] am[rests-on c-ev-is-member-per-occurrence-1017@a98644]
(= (gc-count $items $item) (size-atom (filter-atom $items $other (== $other $item))))
(= (gc-has $items $item) (> (gc-count $items $item) 0))

; The facts of one head, and how many of them hold one value at one place: every section's tables
; read their facts through these two, so no table keeps a copy of its own.
; Time: one comparison per fact, and one more per fact of the head for gc-count-at.
; am[implements a-rel-facts-helpers-one-home-1018@ff4910]
(= (gc-of $facts $head) (filter-atom $facts $fact (== (car-atom $fact) $head)))
(= (gc-count-at $facts $head $place $value)
   (size-atom (filter-atom (gc-of $facts $head) $fact (== (index-atom $fact $place) $value))))

; Tier 1 holds the classes that can establish what happened: a measurement, an exact derivation
; from committed facts, or an identified person's declaration. Tier 0 holds the estimates: a
; model-proposed value, and a receipt-calibrated one calibrated on earlier receipts (section
; 8.2). AgenticMind's evidence cut makes the same split between what establishes a claim and
; what does not (vocabulary.lp, lines 87-104). A reading of a higher tier defeats a contrary of a
; lower one as an adopted, defeasible preference between sources, never as proof that a
; measurement is true, and two readings of one tier stay in conflict.
; am[rests-on c-rel-establishing-classes-1016@72edbb] am[rests-on c-integrate-reading-owner-rule-1018@9de720]
; am[rests-on c-rel-rr-kernel-needs-1018@308ea7]
(= (gc-estimator-class-table)
   ((Class "measured" 1) (Class "deterministic" 1) (Class "receipt-calibrated" 0)
    (Class "model-proposed" 0) (Class "human-asserted" 1)))

(= (gc-estimator-class-name (Class $name $tier)) $name)
(= (gc-estimator-class-tier (Class $name $tier)) $tier)

(= (gc-estimator-classes) (map-atom (gc-estimator-class-table) $class (gc-estimator-class-name $class)))

; A class's name appears once in the table, so a known class answers once and an unknown one
; answers nothing. The matching entries are bound before they are superposed, because superpose
; spreads the elements of the expression written in it: of a call written in place it answers the
; call's own parts, and an unbound part then matches the accessor's pattern.
; Time: one comparison per class.
; am[rests-on c-rel-superpose-spreads-written-expression-1018@af658d]
(= (gc-estimator-tier $name)
   (let* (($entries (filter-atom (gc-estimator-class-table) $entry (== (gc-estimator-class-name $entry) $name)))
          ($class (superpose $entries)))
     (gc-estimator-class-tier $class)))

; Time: one comparison per class.
(= (gc-lowest-estimator-tier)
   (let $tiers (map-atom (gc-estimator-class-table) $class (gc-estimator-class-tier $class))
     (foldl-atom (cdr-atom $tiers) (car-atom $tiers) $lowest $tier (if (< $tier $lowest) $tier $lowest))))

; Establishing is read off the tier, so every class that establishes ranks strictly above every
; class that does not, whatever tiers the table gives.
(= (gc-establishes $name) (> (gc-estimator-tier $name) (gc-lowest-estimator-tier)))

; A reading valid until an instant is still current at that instant (section 8.3: past its
; validity a reading decays toward unknown).
(= (gc-reading-expired $as-of Forever) False)
(= (gc-reading-expired $as-of (Until $until)) (< $until $as-of))

; A reading's row in the justification kernel's grammar, the one rule relevance and the planner
; build their rows by. A detected reading claims its signal and a refuted one the signal's
; negation, from an observation naming the reading by the caller's ID with its class and
; validity. Only those two states have a row: an unknown reading is silence, never a refutation,
; so no equation matches one and a call on it answers nothing (c-rel-pj-row-rule-unknown-refutes-1018).
; am[implements a-rel-pj-reading-row-1018@03ad71] am[implements a-dr-pj-api-1018@b3c793]
; am[rests-on c-rel-pj-row-rule-unknown-refutes-1018@82c7eb]
(= (gc-reading-row (Reading $signal "detected" $estimator $validity $id))
   (From (Signal $signal) (Observation (Reading $id $estimator $validity))))
(= (gc-reading-row (Reading $signal "refuted" $estimator $validity $id))
   (From (Not (Signal $signal)) (Observation (Reading $id $estimator $validity))))

; am[implements a-rel-pj-reading-row-1018@03ad71]
(= (gc-reading-definite (Reading $signal $state $estimator $validity $id))
   (or (== $state "detected") (== $state "refuted")))

; A caller binds the rows with let before it passes them to the kernel's typed entry, since an
; argument written in place reaches an Atom-typed parameter unevaluated
; (c-rel-typed-entry-let-bound-1018).
; Time: one state comparison per reading.
; am[implements a-rel-pj-reading-row-1018@03ad71] am[rests-on c-rel-typed-entry-let-bound-1018@bda6c4]
(= (gc-reading-rows $readings)
   (map-atom (filter-atom $readings $reading (gc-reading-definite $reading)) $definite (gc-reading-row $definite)))
