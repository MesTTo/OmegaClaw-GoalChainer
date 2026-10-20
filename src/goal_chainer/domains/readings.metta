; Purpose: the reading section's relational checks, each a row of a fault table over the facts the
; section contributes, read by the shared fault-table reader, so every fault of a domain's reading
; section is reported with the domain's other faults and the domain loader only builds the facts and
; renders the faults.
;
;   (gc-rd-run-faults (Domain FACT ...)) -> ((Fault REASON FACT MESSAGE) | (Defect ...) ...)
;   (gc-rd-checks-warm-up) -> True
;
; The section contributes these facts (goal_chainer.domains.readings.FACTS), every name a string:
;
;   (Readings NAME)                      the section, named by its gc-reading-domain
;   (Declared "signal" ID)               a proposition, in the core's id table beside the gc-signals
;   (Declared "choice" ID)               a choice, in the core's id table
;   (Proposition ID)                     a proposition, apart from the gc-signals
;   (Option NAME DIRECTION)              an answer option and the evidence direction it gives
;   (Decided NAME)                       an answer option whose direction gives evidence
;   (Choice ID (Options OPTION ...))     a choice and the options it offers, in order
;   (Binding SIGNAL CONTROL)             a binding of the proposition SIGNAL over CONTROL's entities
;
; and reads the bigraph section's (Control NAME (Ports PORT ...) KIND), (Entity ID CONTROL) and
; (Described ID), the last for each entity declared with a description.
;
; The core's duplicate-id row already reports two propositions, two choices, or a proposition and a
; gc-signal, sharing an id; these rows report what the core cannot see. A declaration's per-value
; checks, nonempty texts, reading symbols and option directions, are ReadingDeclaration's own, and a
; singleton's exactly-once is read_section's, so every fault here is between values. A fault names
; the fact that failed, and the loader renders it before the row's message. The tables read the
; domain's fact list as their context, through the shared vocabulary's gc-of and gc-count-at, which
; the domain checks' group loads first.
; am[implements a-dr-dt-tables-1018@5ec9b6] am[implements a-dr-declaration-checks-on-shared-reader-1018@7af2b0]
; am[rests-on c-rel-nd-reader-two-readings-1018@81343b] am[rests-on c-dr-dt-core-same-kind-duplicates-1018@3c4ed3]
; am[rests-on c-dr-dt-choice-copies-cascade-1018@8dfe84]
; am[implements a-rel-facts-helpers-one-home-1018@ff4910]

; --- facts ----------------------------------------------------------------------------------------
; Each fact with one head, its own subject.
(= (gc-rd-subjects $facts $head) (map-atom (gc-of $facts $head) $chosen (Subject $chosen $chosen)))

; --- the tables -----------------------------------------------------------------------------------
; A section with no option has no decided one either, so that table reads First and reports only
; the option missing; every other row is independent and reads Every.
; am[implements a-dr-dt-tables-1018@5ec9b6]
(= (gc-rd-option-presence-table)
   ((Row "no-answer-option" gc-rd-row-has-option "declares no gc-reading-option")
    (Row "no-decided-option" gc-rd-row-has-decided
         "declares no gc-reading-option whose direction is for or against, so no answer is evidence")))
(= (gc-rd-section-table)
   ((Row "no-reading" gc-rd-row-has-reading "declares no gc-reading-proposition or gc-reading-choice, so it asks nothing")))
(= (gc-rd-option-table)
   ((Row "duplicate-answer" gc-rd-row-option-once "is not the only gc-reading-option of its name")))
(= (gc-rd-choice-table)
   ((Row "choice-is-proposition" gc-rd-row-choice-not-proposition
         "shares its id with a gc-reading-proposition, so the two would be one Jev question")
    (Row "empty-choice" gc-rd-row-choice-offers "offers no option")
    (Row "duplicate-choice-option" gc-rd-row-choice-options-distinct "offers one option more than once")))
; A binding over an undeclared control offers no entity either, so its control table reads First and
; reports only the control missing; its other rows are independent and read Every. An entity under a
; control no binding names needs no description, so the description row holds of it.
; am[implements a-bnd-faults-1019@b5dc70] am[rests-on c-bnd-linking-by-descriptions-1019@e01edd]
(= (gc-rd-binding-control-table)
   ((Row "binding-undeclared-control" gc-rd-row-binding-control "names a control no gc-brs-control declares")
    (Row "binding-offers-no-entity" gc-rd-row-binding-entity
         "names a control no gc-brs-entity is declared under, so it offers only no match")))
(= (gc-rd-binding-table)
   ((Row "binding-undeclared-proposition" gc-rd-row-binding-proposition
         "binds no gc-reading-proposition of its id, so it has no statement to place")
    (Row "duplicate-binding" gc-rd-row-binding-once "is not the only gc-reading-binding of its signal and control")))
(= (gc-rd-entity-table)
   ((Row "undescribed-bound-entity" gc-rd-row-bound-entity-described
         "is offered by a gc-reading-binding but has no description for Jev to choose it by")))

; --- the rows -------------------------------------------------------------------------------------
; Each row is called as (ROW FACTS FACT), FACTS the domain's fact list, and answers True or False
; exactly once.
; am[implements a-dr-dt-tables-1018@5ec9b6]
(= (gc-rd-row-has-option $facts (Readings $name)) (> (size-atom (gc-of $facts Option)) 0))
(= (gc-rd-row-has-decided $facts (Readings $name)) (> (size-atom (gc-of $facts Decided)) 0))
(= (gc-rd-row-has-reading $facts (Readings $name))
   (> (+ (size-atom (gc-of $facts Proposition)) (size-atom (gc-of $facts Choice))) 0))

(= (gc-rd-row-option-once $facts (Option $name $direction)) (== (gc-count-at $facts Option 1 $name) 1))

; A choice reads its own options, so two choices sharing an id, which the core reports, never make
; either one's options look repeated.
(= (gc-rd-row-choice-not-proposition $facts (Choice $id $options)) (== (gc-count-at $facts Proposition 1 $id) 0))
(= (gc-rd-row-choice-offers $facts (Choice $id $options)) (> (size-atom (cdr-atom $options)) 0))
(= (gc-rd-row-choice-options-distinct $facts (Choice $id $options))
   (let $offered (cdr-atom $options) (== (size-atom (unique-atom $offered)) (size-atom $offered))))

; am[implements a-bnd-faults-1019@b5dc70]
(= (gc-rd-row-binding-control $facts (Binding $signal $control)) (> (gc-count-at $facts Control 1 $control) 0))
(= (gc-rd-row-binding-entity $facts (Binding $signal $control)) (> (gc-count-at $facts Entity 2 $control) 0))
(= (gc-rd-row-binding-proposition $facts (Binding $signal $control)) (> (gc-count-at $facts Proposition 1 $signal) 0))
(= (gc-rd-row-binding-once $facts (Binding $signal $control))
   (== (gc-count (gc-of $facts Binding) (Binding $signal $control)) 1))
(= (gc-rd-row-bound-entity-described $facts (Entity $id $control))
   (or (== (gc-count-at $facts Binding 2 $control) 0) (> (gc-count-at $facts Described 1 $id) 0)))

; --- the entry ------------------------------------------------------------------------------------
; The loader's validation runner calls this typed entry with the domain's facts; the worker below it
; is untyped, so the tables it hands the shared reader are evaluated before the call. Two copies of
; one duplicated option or binding fail alike, so each fault is kept once, in table order.
; Time: for o options, p propositions, c choices of at most k options each, b bindings, n bigraph
; controls and e entities, about o * o + c * (p + k * k) + o + p + c + b * (n + e + p + b) + e * b
; comparisons, every count a filter over the domain's facts.
; am[implements a-dr-dt-tables-1018@5ec9b6] am[rests-on c-ev-pk-typed-entry-wrapper-1018@ef5a23]
; am[implements a-bnd-faults-1019@b5dc70]
(: gc-rd-run-faults (-> Atom Expression))
(= (gc-rd-run-faults $domain) (gc-rd-faults $domain))
(= (gc-rd-faults $domain)
   (let* (($facts (cdr-atom $domain))
          ($sections (gc-rd-subjects $facts Readings))
          ($present (gc-table-faults First (gc-rd-option-presence-table) $facts $sections))
          ($asking (gc-table-faults Every (gc-rd-section-table) $facts $sections))
          ($options (gc-table-faults Every (gc-rd-option-table) $facts (gc-rd-subjects $facts Option)))
          ($choices (gc-table-faults Every (gc-rd-choice-table) $facts (gc-rd-subjects $facts Choice)))
          ($bound (gc-rd-subjects $facts Binding))
          ($controls (gc-table-faults First (gc-rd-binding-control-table) $facts $bound))
          ($bindings (gc-table-faults Every (gc-rd-binding-table) $facts $bound))
          ($entities (gc-table-faults Every (gc-rd-entity-table) $facts (gc-rd-subjects $facts Entity))))
     (unique-atom (append $present (append $asking (append $options (append $choices
                  (append $controls (append $bindings $entities)))))))))

; One section on which every row is called, outside any speculation: its nine faults are no decided
; option, the duplicated answer once, of its two choices one sharing a proposition's id and repeating
; an option, the other offering none, the twice-written binding over the undeclared control C once
; for the control and once as a duplicate, the binding of the undeclared z, and k, the undescribed
; entity under the bound control K; j, under no bound control, needs no description.
; am[implements a-dr-dt-tables-1018@5ec9b6] am[implements a-bnd-faults-1019@b5dc70]
(: gc-rd-checks-warm-up (-> Bool))
(= (gc-rd-checks-warm-up)
   (== (size-atom (gc-rd-faults (Domain (Readings "w") (Option "a" "none") (Option "a" "none") (Proposition "p")
                                        (Choice "p" (Options "x" "x")) (Choice "q" (Options))
                                        (Binding "p" "C") (Binding "p" "C") (Binding "z" "K")
                                        (Control "K" (Ports) "atomic") (Entity "k" "K")
                                        (Control "J" (Ports) "atomic") (Entity "j" "J"))))
       9))
