; Purpose: the needs section's relational checks, each a row of an Every-reading fault table over the
; facts the section and the domain core contribute, read by the shared fault-table reader, so every fault
; of the section is reported at once and the domain loader only builds the facts and renders the faults.
;
;   (gc-need-run-faults (Domain FACT ...)) -> ((Fault REASON FACT MESSAGE) | (Defect ...) ...)
;   (gc-need-checks-warm-up) -> True
;
; The section contributes these facts (goal_chainer.domains.needs.FACTS), every name a string:
;
;   (Need ID GOAL)                                  a need and the goal it regulates
;   (NeedWidth ID WIDTH)                            HI - LO of its scale, a positive float
;   (Expectation ACTION NEED CHANGE ESTIMATOR)      a declared change, a float, and its estimator class
;
; and reads the core's (Declared "goal" ID) and (Declared "action" ID). A need regulates exactly one
; goal and a goal at most one need, since a goal's declared priority is its one need's importance and
; two needs on one goal would count that priority twice; one action has at most one declared change
; per need. Membership counts matching facts or asks the shared vocabulary's gc-has, which the domain
; checks' group loads first, never is-member, which answers once per occurrence
; (c-ev-pk-is-member-per-occurrence-1018).
; am[implements a-v2m-need-forms-1019@6ee59c] am[rests-on c-v2-priority-provenance-boundary-1019@575bf7]
; am[related a-rel-nd-validation-runner-1018@f3f0b6] am[rests-on c-ev-pk-is-member-per-occurrence-1018@c8243c]

!(import! &self (library lib_functional))

; --- facts ----------------------------------------------------------------------------------------------
; The facts of one head and their counts at a place come from the shared vocabulary's gc-of and
; gc-count-at, over the domain term's facts (a-rel-facts-helpers-one-home-1018).
; am[related a-rel-facts-helpers-one-home-1018@ff4910]
(= (gc-need-subjects $domain $head) (map-atom (gc-of (cdr-atom $domain) $head) $chosen (Subject $chosen $chosen)))
(= (gc-need-has-at $domain $head $place $value) (> (gc-count-at (cdr-atom $domain) $head $place $value) 0))
(= (gc-need-declared? $domain $kind $id)
   (> (size-atom (filter-atom (gc-of (cdr-atom $domain) Declared) $fact
                    (and (== (index-atom $fact 1) $kind) (== (index-atom $fact 2) $id)))) 0))

; --- the tables -----------------------------------------------------------------------------------------
; am[implements a-v2m-need-forms-1019@6ee59c]
(= (gc-need-table)
   ((Row "duplicate-need" gc-need-row-need-once "is not the only gc-need of its id")
    (Row "undeclared-goal" gc-need-row-goal-declared "regulates a goal no gc-goal declares")
    (Row "goal-regulated-twice" gc-need-row-goal-once "regulates a goal another gc-need regulates too, which would count the goal's priority twice")))
(= (gc-need-expectation-table)
   ((Row "undeclared-expectation-action" gc-need-row-expectation-action "declares a change for an action no gc-action declares")
    (Row "undeclared-expectation-need" gc-need-row-expectation-need "declares a change of a need no gc-need declares")
    (Row "duplicate-expectation" gc-need-row-expectation-once "is not the only gc-need-expectation of its action and need")
    (Row "unknown-estimator" gc-need-row-expectation-estimator "names an estimator class the shared vocabulary does not hold")
    (Row "change-exceeds-scale" gc-need-row-expectation-width "declares a change larger than its need's whole scale")))

; --- the rows ---------------------------------------------------------------------------------------------
; Each row is called as (ROW DOMAIN FACT) and answers True or False exactly once.
; am[implements a-v2m-need-forms-1019@6ee59c]
(= (gc-need-row-need-once $domain (Need $id $goal)) (== (gc-count-at (cdr-atom $domain) Need 1 $id) 1))
(= (gc-need-row-goal-declared $domain (Need $id $goal)) (gc-need-declared? $domain "goal" $goal))
(= (gc-need-row-goal-once $domain (Need $id $goal)) (== (gc-count-at (cdr-atom $domain) Need 2 $goal) 1))

(= (gc-need-row-expectation-action $domain (Expectation $action $need $change $estimator))
   (gc-need-declared? $domain "action" $action))
(= (gc-need-row-expectation-need $domain (Expectation $action $need $change $estimator))
   (gc-need-has-at $domain Need 1 $need))
(= (gc-need-row-expectation-once $domain (Expectation $action $need $change $estimator))
   (== (size-atom (filter-atom (gc-of (cdr-atom $domain) Expectation) $fact
                    (and (== (index-atom $fact 1) $action) (== (index-atom $fact 2) $need)))) 1))
(= (gc-need-row-expectation-estimator $domain (Expectation $action $need $change $estimator))
   (gc-has (gc-estimator-classes) $estimator))
; An undeclared need is reported by undeclared-expectation-need alone; a declared one is checked
; against its first width.
(= (gc-need-row-expectation-width $domain (Expectation $action $need $change $estimator))
   (let $widths (filter-atom (gc-of (cdr-atom $domain) NeedWidth) $fact (== (index-atom $fact 1) $need))
     (if (== $widths ())
         True
         (<= (gc-need-magnitude $change) (index-atom (car-atom $widths) 2)))))
(= (gc-need-magnitude $x) (if (< $x 0) (- 0 $x) $x))

; --- the entry ----------------------------------------------------------------------------------------------
; The loader's validation runner calls this typed entry with the domain's facts; the worker below it is
; untyped, so the tables it hands the shared reader are evaluated before the call.
; am[implements a-v2m-need-forms-1019@6ee59c] am[rests-on c-ev-pk-typed-entry-wrapper-1018@ef5a23]
(: gc-need-run-faults (-> Atom Expression))
(= (gc-need-run-faults $domain) (gc-need-faults $domain))
(= (gc-need-faults $domain)
   (let* (($needs (gc-table-faults Every (gc-need-table) $domain (gc-need-subjects $domain Need)))
          ($expectations (gc-table-faults Every (gc-need-expectation-table) $domain (gc-need-subjects $domain Expectation))))
     (append $needs $expectations)))

; One section whose every table has a subject, so a warm-up calls each row once outside any
; speculation; its seven faults are two duplicate needs, an undeclared goal, an undeclared
; expectation action and need, an unknown estimator and a change wider than its scale.
; am[implements a-v2m-need-forms-1019@6ee59c]
(= (gc-need-checks-warm-up)
   (== (size-atom (gc-need-faults (Domain (Declared "goal" "g") (Declared "action" "a")
                                          (Need "n" "g") (Need "n" "h") (NeedWidth "n" 1.0)
                                          (Expectation "b" "m" 0.5 "measured")
                                          (Expectation "a" "n" 2.0 "guessed"))))
       7))
