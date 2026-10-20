; Purpose: call the preserved experimental composer through the current typed evaluator.
; am[implements a-integrate-plan-eval-baseline-1019@1bbdc8]
(: gc-benchmark-compose (-> Atom Atom Atom Atom Expression))
(= (gc-benchmark-compose $goal $library $judged $tracks)
   (gc-agenda-compose $goal $library $judged $tracks))
