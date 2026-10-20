;;; Purpose: believe a batch's semantic readings as ordinary SNARS evidence: each source's readings
;;; of each declared proposition once, from the mean of what that source's texts assert, as the
;;; statement (has-property "request" ID).
;;;
;;; Request evidence arrives as `(gc-reading $source $trust $id $answer $p $provenance)` facts,
;;; one per text and declared proposition, written by the semantic reader against the reading
;;; declaration the batch carries in place of a fixed table. The policy holds no domain's knowledge:
;;; it states no property of any action and registers no rewrite rule.

;;; The statement that SUBJECT has PROPERTY, the relation every reading is believed in.
;;; am[implements a-ie-s7-metta-1018@0ca8fe]
(= (gc has-property $subject $property)
   (sn p so "has-property" ((arg s (sn c $subject)) (arg o (sn c $property)))))

;;; A decided reading's evidence: 8 units times the probability of the answer Jev decided. The 8
;;; is the per-property weight of the HyperBase label scan this rule replaced, kept as a
;;; model-proposed assumption until reviewed outcomes calibrate it; it is not a calibration.
;;; am[rests-on c-reading-weight-assumed-1016]
(= (gc reading-weight) 8.0)

;;; One reading as the unit of evidence it asserts, (Unit SOURCE ID PROVENANCE POSITIVE NEGATIVE
;;; TRUST). What an answer means comes from its option in the batch's reading declaration, whose
;;; rows every policy batch carries: an answer whose direction is `for` asserts evidence for its proposition,
;;; `against` evidence against, and `none`, the text saying nothing that settles it, asserts
;;; nothing, because silence is not refutation. Renaming or adding an answer there needs no change
;;; here.
;;; am[implements a-jev-decided-nli-1016@7239ba]
;;; am[implements a-jev-derive-answers-1016@4b73ac]
;;; am[implements a-ev-wt-context-mean-1017@46162f]
;;; am[rests-on c-orch-three-way-semantics-1016@b92763]
(= (gc reading-unit $source $trust $id $answer $p $provenance)
   (match &self (gc-reading-option $answer $direction $description)
     (let $weight (* (gc reading-weight) $p)
       (gc direction-unit $direction $source $trust $id $weight $provenance))))
(= (gc direction-unit for $source $trust $id $weight $provenance)
   (Unit $source $id $provenance $weight 0.0 $trust))
(= (gc direction-unit against $source $trust $id $weight $provenance)
   (Unit $source $id $provenance 0.0 $weight $trust))
(= (gc direction-unit none $source $trust $id $weight $provenance) (empty))

;;; A unit's group key, its two counts, its source's trust and the reading clause it contributes.
;;; am[implements a-ev-wt-context-mean-1017@46162f]
(= (gc unit-key (Unit $source $id $provenance $positive $negative $trust)) (Key $source $id))
(= (gc unit-positive (Unit $source $id $provenance $positive $negative $trust)) $positive)
(= (gc unit-negative (Unit $source $id $provenance $positive $negative $trust)) $negative)
(= (gc unit-trust (Unit $source $id $provenance $positive $negative $trust)) $trust)
(= (gc unit-reading (Unit $source $id $provenance $positive $negative $trust)) (reading $id $provenance))

;;; The options one source's units of one proposition are believed with. A source's texts are one
;;; dependent body of evidence: the request and the working-memory texts read into its context say
;;; what that one context says, however often it restates it (c-ev-wmtm-provenance-1017). So the
;;; context's evidence is the mean of its asserted units, averaging fusion (Jøsang, Subjective
;;; Logic, 2016, Def. 12.7, Thm. 12.3, Eq. 12.21 for n arguments) over the source's statements: a
;;; none reading asserts no unit, so it is no argument, rather than a vacuous one with which
;;; averaging fusion would halve the evidence. In real arithmetic the mean is idempotent, and
;;; neither count nor their total ever exceeds the strongest unit's. A batch holds one trust per
;;; source (SnarsBatch), which SNARS applies to the mean as it would to each unit, since it scales
;;; both counts by trust (kernel.pl sn_ev_add_src). In floating point each count is the shifted
;;; mean below. Identical members stay exactly idempotent, but a mixed group's two counts, each
;;; averaged on its own, can total one ulp above the strongest unit, as nine contradicted readings
;;; and one supported at p 0.6 do; that is rounding, not evidence, and nothing clips it. Members
;;; are summed in msort order and their reading clauses rendered in reverse msort order, as the
;;; fold conses each in front, so neither depends on the order the facts arrived in. A lone unit
;;; is believed as itself, x0 + 0.0 / 1: its options are what one reading's always were.
;;; Time: one pass over the K members, which are already sorted.
;;; am[implements a-ev-wt-context-mean-1017@46162f] am[implements a-jev-reading-belief-1016@fbc8d9]
;;; am[rests-on c-ev-sl-abf-wbf-1017@33a7e6] am[rests-on c-ev-wmtm-provenance-1017@b5f425]
;;; am[rests-on c-integrate-context-mean-roundoff-1017@95e97a]
(= (gc group-options $members)
   (let* (($first (car-atom $members))
          ((Key $source $id) (gc unit-key $first))
          ($positive (gc shifted-mean (map-atom $members $unit (gc unit-positive $unit))))
          ($negative (gc shifted-mean (map-atom $members $unit (gc unit-negative $unit))))
          ($trust (gc unit-trust $first))
          ($clauses (foldl-atom $members ((estimator model-proposed)) $tail $unit
                      (let $clause (gc unit-reading $unit) (cons-atom $clause $tail)))))
     (cons-atom (evidence $positive $negative)
       (cons-atom (source $source) (cons-atom (trust $trust) $clauses)))))

;;; The shifted mean of a nonempty list of numbers, offset from its first value x0:
;;; x0 + Σ(x − x0)/n, which is x0 exactly when every value is, since every deviation is then
;;; exactly zero. A plain Σx/n drifts even then: three readings of 7.76 give 7.760000000000001.
;;; Time: one pass over the n values.
;;; am[implements a-ev-wt-context-mean-1017@46162f]
;;; am[rests-on c-parser-fold-mean-not-idempotent-1017@f25ccd]
(= (gc shifted-mean $values)
   (let $x0 (car-atom $values)
     (+ $x0 (/ (foldl-atom $values 0.0 $sum $x (+ $sum (- $x $x0))) (size-atom $values)))))

;;; Believe one source's readings of one declared proposition once, as the statement
;;; (has-property "request" ID). SNARS's sn c labels the id symbol by its bare name
;;; (c-dr-snars-label-symbol-1018), so the statement of a proposition such as sensitive-data names
;;; the concept a caller's (sn c "sensitive-data") names too, and every declared proposition,
;;; whatever its domain, is believed the same way. A reading whose id no proposition row of the
;;; declaration names believes nothing. The readings' provenance (model, answer key, grounding
;;; passage) and their estimator class ride along as open clauses, which believe! keeps in the
;;; statement's meta channel.
;;; am[implements a-ev-wt-context-mean-1017@46162f] am[implements a-jev-reading-belief-1016@fbc8d9]
;;; am[implements a-dr-one-name-1018@beba5e] am[rests-on c-dr-snars-label-symbol-1018@c809ec]
;;; am[implements a-ie-s7-metta-1018@0ca8fe]
(= (gc believe-group! $members)
   (let* (((Key $source $id) (gc unit-key (car-atom $members)))
          ($options (gc group-options $members)))
     (match &self (gc-reading-proposition $id $statement $question)
       (believe! (gc has-property (gc reading-subject) $id) $options))))

;;; The concept every reading is a property of: its statement is (has-property "request" ID).
;;; am[implements a-dr-one-name-1018@beba5e]
(= (gc reading-subject) "request")

;;; Turn every reading in the batch into ordinary SNARS evidence. Readings carry their own sources,
;;; and each source's readings of a proposition are believed once, so replaying the same text adds
;;; no second receipt. A batch carries the readings of the texts its session read, never those of
;;; other requests its store holds (SnarsSession._execute). Groups are believed in the order of
;;; their first fact, as each reading was before groups had more than one member.
;;; Time: U fact matches, then U membership tests per group for U units and G groups.
;;; am[implements a-jev-reading-belief-1016@fbc8d9] am[implements a-ev-wt-context-mean-1017@46162f]
(= (gc assert-request-context!)
   (let* (($units (collapse
                    (match &self (gc-reading $source $trust $id $answer $p $provenance)
                      (gc reading-unit $source $trust $id $answer $p $provenance))))
          ($keys (unique-atom (map-atom $units $unit (gc unit-key $unit))))
          ($believed
            (collapse
              (let $key (superpose $keys)
                (gc believe-group! (msort (filter-atom $units $unit (== (gc unit-key $unit) $key))))))))
     True))
