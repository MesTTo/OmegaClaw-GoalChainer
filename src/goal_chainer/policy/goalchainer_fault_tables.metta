; Purpose: read any fault table over named subjects and collect its faults in order: every failing
; row of a table whose rows are independent, or only the first failing row of one whose later rows
; read what earlier rows established, so each policy states each of its checks once, as a row.
;
;   (gc-table-faults READING TABLE CONTEXT ((Subject NAME TERM) ...))
;     -> ((Fault REASON NAME MESSAGE) | (Defect REASON NAME (ANSWER ...)) ...)
;   (gc-table-first-failing TABLE CONTEXT TERM)
;     -> Holds | (Row REASON HOLDS ...) | (Defect REASON TERM (ANSWER ...))
;
; READING is Every or First. TABLE is ((Row REASON HOLDS MESSAGE) ...): REASON a string naming the
; check, HOLDS a predicate called as (HOLDS CONTEXT TERM), and MESSAGE a template its caller fills
; with its own values. The reader reads each row's REASON and HOLDS, and the MESSAGE only of a row
; it reports, so a table read only through gc-table-first-failing, such as the receipt counting
; table, may leave the message out. NAME is any atom that names the subject in a fault, an index,
; an id or a term such as (Node RULE ID CONTROL), and TERM is what the predicates read. Faults come
; subject by subject, each subject's rows in table order.
;
; A predicate answers exactly True or False. Any other answer is the table's defect, never the
; subject's fault: no answer, several, or its own call left unreduced because its predicate is
; misspelled. It is reported as (Defect REASON NAME ANSWERS) with every answer the call gave, so a
; caller can tell a mistake in its own policy from a fault in its input.
;
; Every function here is untyped, so a MeTTa caller hands it computed tables and subject lists
; that are evaluated before the call; a typed entry a host calls is a thin wrapper over it. Each
; equation keeps its pattern variables apart, since two let or case forms in one equation share
; them.
; am[implements a-rel-nd-shared-table-reader-1018@24e3dd] am[rests-on c-rel-nd-table-reader-interface-1018@267b09]
; am[rests-on c-rel-nd-reader-two-readings-1018@81343b] am[rests-on c-rel-nd-table-defect-1018@b4a907]
; am[rests-on c-ev-pk-typed-entry-wrapper-1018@ef5a23] am[rests-on c-brs-k-case-vars-clause-scoped-1018@de7554]

; One row's verdict on one term: Holds, (Failed ROW), or (Undefined ROW ANSWERS) for a predicate
; that answered anything but exactly True or False.
(= (gc-table-verdict $row $context $term)
   (gc-table-judged $row (collapse (gc-table-asked $row $context $term))))
(= (gc-table-asked $row $context $term) (let $holds (index-atom $row 2) ($holds $context $term)))
(= (gc-table-judged $row $answers)
   (if (== $answers (True))
       Holds
       (if (== $answers (False)) (Failed $row) (Undefined $row $answers))))

; The first verdict that is not Holds, reading no row after it, since a later row may read what an
; earlier one established. Time: at most one predicate call per row.
(= (gc-table-first-verdict $rows $context $term)
   (if (== $rows ())
       Holds
       (gc-table-after (gc-table-verdict (car-atom $rows) $context $term) (cdr-atom $rows) $context $term)))
(= (gc-table-after $verdict $rest $context $term)
   (if (== $verdict Holds) (gc-table-first-verdict $rest $context $term) $verdict))

; The verdicts a reading reports for one term. Time: one predicate call per row for Every, at most
; one per row for First.
(= (gc-table-failed Every $rows $context $term)
   (filter-atom (map-atom $rows $row (gc-table-verdict $row $context $term)) $verdict
                (not (== $verdict Holds))))
(= (gc-table-failed First $rows $context $term)
   (gc-table-listed (gc-table-first-verdict $rows $context $term)))
(= (gc-table-listed Holds) ())
(= (gc-table-listed (Failed $row)) ((Failed $row)))
(= (gc-table-listed (Undefined $row $answers)) ((Undefined $row $answers)))

(= (gc-table-fault $name (Failed $row)) (Fault (index-atom $row 1) $name (index-atom $row 3)))
(= (gc-table-fault $name (Undefined $row $answers)) (Defect (index-atom $row 1) $name $answers))

; Time: for s subjects and r rows, s * r predicate calls at most, and s list appends.
(= (gc-table-faults $reading $rows $context $subjects)
   (foldl-atom $subjects () $faults $subject
     (append $faults (gc-table-subject-faults $reading $rows $context $subject))))
(= (gc-table-subject-faults $reading $rows $context (Subject $name $term))
   (map-atom (gc-table-failed $reading $rows $context $term) $verdict (gc-table-fault $name $verdict)))

(= (gc-table-first-failing $rows $context $term)
   (gc-table-reported $term (gc-table-first-verdict $rows $context $term)))
(= (gc-table-reported $term Holds) Holds)
(= (gc-table-reported $term (Failed $row)) $row)
(= (gc-table-reported $term (Undefined $row $answers)) (Defect (index-atom $row 1) $term $answers))
