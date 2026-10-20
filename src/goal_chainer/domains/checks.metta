; Purpose: the neutral domain core's relational checks, each a row of an Every-reading fault table
; over the facts a domain file's sections contribute, read by the shared fault-table reader, so
; every fault of a domain is reported at once and Python only builds the facts and reads the faults,
; and the declared signals no rule body reads, which a domain lists rather than refuses.
;
;   (gc-domain-core-faults (Domain FACT ...)) -> ((Fault REASON FACT MESSAGE) | (Defect ...) ...)
;   (gc-domain-unread-signals (Domain FACT ...)) -> ((Fault REASON FACT MESSAGE) | (Defect ...) ...)
;   (gc-domain-checks-warm-up) -> True
;
; Every name in a fact is a string, so a domain's ids compare with the shared vocabulary's classes
; and bands directly. The core reads these facts; a section may add its own, which the core leaves
; alone:
;
;   (Declared KIND ID)               KIND action, goal, signal, dimension or authority; a reading
;                                    proposition declares a signal too, through its section's facts
;   (Tier ACTION AUTHORITY)          the authority tier an action names
;   (Rank AUTHORITY RANK)            a tier's rank, as its canonical text
;   (Ceiling CLASS AUTHORITY)        an estimator ceiling
;   (Literal FUNCTOR (Args ARG ...)) a term of the theory; ARG a string, (Schematic NAME) or (Term)
;   (Label LABEL)                    a rule's label
;   (Prefer (Labels LABEL ...))      a prefer form's labels
;   (Reads SIGNAL), (ReadsSchematic) a rule body reading (signal SIGNAL), or (signal ?x)
;
; A fault names the fact that failed, and the loader renders it. Membership and counts are the
; shared vocabulary's gc-has and gc-count, which count matches rather than calling is-member, so a
; duplicated fact never makes a check answer twice; the facts of one head are its gc-of, and
; those holding one value at one place its gc-count-at.
; am[implements a-rel-nd-validation-runner-1018@f3f0b6] am[implements a-rel-nd-metta-validation-1018@56e89f]
; am[rests-on c-rel-nd-checks-as-constraints-1018@704895] am[rests-on c-rel-nd-ids-symbols-classes-strings-1018@fef3a2]
; am[rests-on c-ev-is-member-per-occurrence-1017@a98644]

; Each fact of one head its own subject: a fault names the fact that failed.
(= (gc-dc-subjects $facts $head) (map-atom (gc-of $facts $head) $chosen (Subject $chosen $chosen)))

; The declarations of one kind, each its own subject.
(= (gc-dc-declared-subjects $facts $kind)
   (map-atom (filter-atom $facts $fact (gc-dc-declares $fact $kind)) $chosen (Subject $chosen $chosen)))
(= (gc-dc-declares $fact $kind)
   (if (== (car-atom $fact) Declared) (== (index-atom $fact 1) $kind) False))

(= (gc-dc-declared-once $facts $declared) (== (gc-count $facts $declared) 1))
(= (gc-dc-action-not-goal $facts $action)
   (not (gc-has $facts (Declared "goal" (index-atom $action 2)))))
(= (gc-dc-tier-declared $facts $tier) (gc-has $facts (Declared "authority" (index-atom $tier 2))))
(= (gc-dc-rank-once $facts $rank) (== (gc-count-at $facts Rank 2 (index-atom $rank 2)) 1))
(= (gc-dc-class-known $facts $ceiling) (gc-has (gc-estimator-classes) (index-atom $ceiling 1)))
(= (gc-dc-ceiling-once $facts $ceiling) (== (gc-count-at $facts Ceiling 1 (index-atom $ceiling 1)) 1))
(= (gc-dc-ceiling-tier-declared $facts $ceiling)
   (gc-has $facts (Declared "authority" (index-atom $ceiling 2))))
(= (gc-dc-label-once $facts $label) (== (gc-count $facts $label) 1))
(= (gc-dc-prefer-declared $facts $prefer)
   (let $labels (cdr-atom (index-atom $prefer 1))
     (and (> (size-atom $labels) 1)
          (== (filter-atom $labels $label (not (gc-has $facts (Label $label)))) ()))))
(= (gc-dc-signal-read $facts $signal)
   (or (gc-has $facts (Reads (index-atom $signal 2))) (gc-has $facts (ReadsSchematic))))

; Which places of which literal name what: the review's literal grammar, so a theory term naming
; something undeclared is found wherever it stands. A term no row describes names nothing.
(= (gc-dc-literal-grammar)
   ((Grammar "signal" ("signal")) (Grammar "candidate" ("action")) (Grammar "do" ("action"))
    (Grammar "required" ("goal")) (Grammar "contributes" ("action" "goal" "band"))
    (Grammar "effect" ("action" "dimension" "band" "class"))))

(= (gc-dc-literal-declared $facts $literal)
   (let* (($arguments (cdr-atom (index-atom $literal 2)))
          ($rows (filter-atom (gc-dc-literal-grammar) $row (gc-dc-describes $row (index-atom $literal 1) (size-atom $arguments)))))
     (if (== $rows ()) True (gc-dc-arguments-declared $facts (index-atom (car-atom $rows) 2) $arguments))))
(= (gc-dc-describes $row $functor $arity)
   (and (== (index-atom $row 1) $functor) (== (size-atom (index-atom $row 2)) $arity)))

; Each place in turn; the walk calls itself once, so pymetta never memoizes it
; (c-brs-k-auto-memo-1018). Time: one membership count per place, at most four.
; am[rests-on c-brs-k-auto-memo-1018@9c39b3]
(= (gc-dc-arguments-declared $facts $kinds $arguments)
   (if (== $kinds ())
       True
       (and (gc-dc-argument-declared $facts (car-atom $kinds) (car-atom $arguments))
            (gc-dc-arguments-declared $facts (cdr-atom $kinds) (cdr-atom $arguments)))))

; A schematic or nested argument is resolved by grounding and checked nowhere; a band or a class
; is the shared vocabulary's, and any other name the domain's declaration of that kind.
(= (gc-dc-argument-declared $facts $kind $argument)
   (if (== (get-metatype $argument) Expression)
       True
       (if (== $kind "band")
           (gc-has (gc-bands) $argument)
           (if (== $kind "class")
               (gc-has (gc-estimator-classes) $argument)
               (gc-has $facts (Declared $kind $argument))))))

(= (gc-dc-declaration-table) ((Row "duplicate-id" gc-dc-declared-once "is declared more than once")))
(= (gc-dc-action-table)
   ((Row "action-is-goal" gc-dc-action-not-goal
         "is also declared as a goal, so a (contributes A G) literal would be ambiguous")))
(= (gc-dc-tier-table) ((Row "undeclared-tier" gc-dc-tier-declared "names an authority tier the domain does not declare")))
(= (gc-dc-rank-table)
   ((Row "duplicate-rank" gc-dc-rank-once "shares its rank with another tier, so the tiers are not totally ordered")))
(= (gc-dc-ceiling-table)
   ((Row "unknown-class" gc-dc-class-known "is not one of the shared vocabulary's estimator classes")
    (Row "duplicate-ceiling" gc-dc-ceiling-once "is not the class's only gc-estimator-ceiling")
    (Row "undeclared-ceiling-tier" gc-dc-ceiling-tier-declared "names an authority tier the domain does not declare")))
(= (gc-dc-literal-table) ((Row "undeclared-reference" gc-dc-literal-declared "names something the domain does not declare")))
(= (gc-dc-label-table) ((Row "duplicate-label" gc-dc-label-once "labels more than one rule")))
(= (gc-dc-prefer-table) ((Row "unknown-rule" gc-dc-prefer-declared "must name at least two rule labels the theory declares")))
(= (gc-dc-signal-table)
   ((Row "unread-signal" gc-dc-signal-read "is read by no rule body, so a reading of it would be silently inert")))

; Every table over its subjects, the faults in table order and each fault once, since two copies of
; one duplicated declaration fail alike. Each table reads only the facts its rows need, so a theory's
; many terms are never scanned once per subject.
; Time: for d declarations, t theory terms, a ranks, c ceilings and l labels, about
; d * d + t * (6 + d) + a * a + c * (c + d) + l * l comparisons.
(= (gc-dc-faults $facts)
   (let* (($declared (gc-of $facts Declared))
          ($ranks (gc-of $facts Rank))
          ($ceilings (gc-of $facts Ceiling))
          ($labels (gc-of $facts Label))
          ($once (gc-table-faults Every (gc-dc-declaration-table) $declared (gc-dc-subjects $declared Declared)))
          ($actions (gc-table-faults Every (gc-dc-action-table) $declared (gc-dc-declared-subjects $declared "action")))
          ($tiers (gc-table-faults Every (gc-dc-tier-table) $declared (gc-dc-subjects $facts Tier)))
          ($ordered (gc-table-faults Every (gc-dc-rank-table) $ranks (gc-dc-subjects $ranks Rank)))
          ($capped (gc-table-faults Every (gc-dc-ceiling-table) (append $ceilings $declared) (gc-dc-subjects $ceilings Ceiling)))
          ($literals (gc-table-faults Every (gc-dc-literal-table) $declared (gc-dc-subjects $facts Literal)))
          ($labelled (gc-table-faults Every (gc-dc-label-table) $labels (gc-dc-subjects $labels Label)))
          ($prefers (gc-table-faults Every (gc-dc-prefer-table) $labels (gc-dc-subjects $facts Prefer))))
     (unique-atom (append $once (append $actions (append $tiers (append $ordered (append $capped
                  (append $literals (append $labelled $prefers))))))))))

; A signal no rule body reads makes a reading of it change nothing a review concludes, but a shared
; domain may declare a condition only planning or classification reads, so the signal table's
; failing subjects are the domain's unread signals, listed rather than refused (i-rel-deadsignal-1016
; stays visible).
; Time: for d declarations and r reads, about d * r comparisons.
; am[implements a-rel-nd-unread-signals-1018@f57790]
(= (gc-dc-unread-signals $facts)
   (let* (($declared (gc-of $facts Declared))
          ($reads (append (gc-of $facts Reads) (gc-of $facts ReadsSchematic))))
     (gc-table-faults Every (gc-dc-signal-table) $reads (gc-dc-declared-subjects $declared "signal"))))

; The typed entry the loader calls through the common evaluator; its parameter is Atom, so the
; facts arrive as the data they are (c-jk-atom-entry-inert-1018), and it answers the worker's list.
; am[rests-on c-jk-atom-entry-inert-1018@63e37f] am[rests-on c-rt-atom-return-unevaluated-1018@364854]
(: gc-domain-core-faults (-> Atom Expression))
(= (gc-domain-core-faults $domain) (gc-dc-faults (cdr-atom $domain)))
; am[implements a-rel-nd-unread-signals-1018@f57790]
(: gc-domain-unread-signals (-> Atom Expression))
(= (gc-domain-unread-signals $domain) (gc-dc-unread-signals (cdr-atom $domain)))

; One duplicated declaration and one undeclared reference, each found once, and one unread signal,
; so the warm-up compiles the tables and the reader before any domain is checked.
; am[implements a-rel-nd-unread-signals-1018@f57790]
(: gc-domain-checks-warm-up (-> Bool))
(= (gc-domain-checks-warm-up)
   (and (== (size-atom (gc-dc-faults ((Declared "action" "a") (Declared "action" "a")
                                      (Literal "candidate" (Args "missing")))))
            2)
        (== (size-atom (gc-dc-unread-signals ((Declared "signal" "s") (Declared "signal" "t") (Reads "t"))))
            1)))
