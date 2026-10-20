;;; Purpose: consume query-directed frontier work as the first supported forward witness.

;; A witness requires receipt or proof support, irrespective of the opinion's polarity or weight.
;; Exhausting this bounded, lossy frontier establishes incompleteness, never falsity.
;; Time: one support check per native step plus the selected native rule's work.
;; The caller's RunBudget bounds the entire operation, including graph work and this recursion.
;; am[implements a-integrate-ecan-packaged-query-1017]
(= (gc-attention-search! $canonical $sid $steps)
 (if (sn supported? $sid)
  (Search Witness $steps (collapse (ask! $canonical)))
  (if (== (sn frontier) ())
   (Search Incomplete $steps ())
   (let $derived (collapse (sn step!))
    (gc-attention-search! $canonical $sid (+ $steps 1))))))

;; Query cues share one unit. Rebuilding admission reconsiders supported pairs the old cap omitted.
;; Original rules, evidence arithmetic, receipts and trust are not replaced by attention.
;; Time: graph build, seed and cycle, followed by native touching of each supported statement.
;; am[implements a-integrate-ecan-packaged-query-1017]
(= (gc-attention-start! $canonical $sid)
 (let* (($built (gc-attention-build!))
        ($cues (gc-attention-seed! $canonical))
        ($diffused (gc-attention-diffuse!))
        ($active (add-atom &self (gc-attention-active)))
        ($cleared (sn_cell_put sn-frontier ()))
        ($statements (gc-attention-statements))
        ($admitted (collapse
         (let $candidate (superpose $statements)
          (if (sn supported? $candidate) (sn fr-touch! $candidate) (empty))))))
  (gc-attention-search! $canonical $sid 0)))

;; The compiled equation contains the complete query. No forward work survives its speculation.
;; Already supported answers return immediately without constructing an attention graph.
;; A Witness is an available opinion and provenance, not a best-proof or entailment claim.
;; am[implements a-integrate-ecan-packaged-query-1017]
;; am[rests-on c-integrate-compiled-query-natural-boundary-1017]
(= (gc forward-query-record $statement)
 (let* (($canonical (sn canon $statement))
        ($sid (sn sid $canonical))
        ((Search $status $steps $answers)
         (if (sn supported? $sid)
          (gc-attention-search! $canonical $sid 0)
          (gc-attention-start! $canonical $sid))))
  (goalchainer-snars-v1 forward-query ok
   (forward-query
    (statement $canonical) (sid $sid) (status $status) (steps $steps) (answers $answers)))))

;; A planner's condition: the same search, classified inside its own speculation, so a belief
;; the search derived is read before the speculation discards it. A supported statement is
;; classified as it stands. Incomplete leaves the statement unsupported, hence Undecided:
;; an exhausted frontier never makes a condition fail. The polarity, pos or neg, names the
;; literal: neg classifies (Not S) through the complement of S's opinion.
;; am[implements a-rt-ob-condition-1017@dc8180] am[rests-on c-integrate-runtime-obligations-ruling-1017@6a2fe6]
;; am[rests-on c-integrate-condition-projection-endpoints-1017@364ddb] am[implements a-rt-ob-negation-track-1017@a1a80d]
(= (gc condition-record $statement $polarity $theta)
 (let* (($canonical (sn canon $statement))
        ($sid (sn sid $canonical))
        ((Search $search $steps $answers)
         (if (sn supported? $sid)
          (gc-attention-search! $canonical $sid 0)
          (gc-attention-start! $canonical $sid))))
  (goalchainer-snars-v1 condition ok
   (condition
    (statement $canonical) (sid $sid) (polarity $polarity) (threshold $theta) (search $search)
    (steps $steps) (status (sn condition-of $sid $polarity $theta))
    (opinion (sn literal-view $sid $polarity))))))
