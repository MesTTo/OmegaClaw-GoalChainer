; Purpose: the bigraph section's relational checks, each a row of an Every-reading fault table over the
; facts the section and the domain core contribute, read by the shared fault-table reader, so every fault
; of a section is reported at once and the domain loader only builds the facts and renders the faults.
;
;   (gc-brs-run-faults (Domain FACT ...)) -> ((Fault REASON FACT MESSAGE) | (Defect ...) ...)
;   (gc-brs-checks-warm-up) -> True
;
; The section contributes these facts (goal_chainer.domains.bigraph.FACTS), every name a string:
;
;   (Control NAME (Ports PORT ...) KIND)       a control of the signature
;   (Entity ID CONTROL)                        a declared entity
;   (Described ID)                             an entity declared with a description, which only
;                                              the reading section's binding rows read
;   (Placed ID PARENT)                         PARENT an entity id or (Root "J")
;   (PortLink ID PORT (Edge E) | (Name Y))     what one port of an entity links to
;   (Anchor LITERAL ENTITY (Via LINK ...))     LITERAL (Signal NAME), (Statement TEXT) or (Literal TEXT)
;   (Reaction ACTION (Controls CONTROL ...))   an action's reaction and the node controls its terms use
;
; and reads the core's (Declared "signal" ID) and (Declared "action" ID). A fault names the fact that
; failed and the loader renders it before the row's message. Structural well-formedness of a reaction's
; terms needs the bigraph kernel, which the planner runs over the section before it plans; these rows
; check only what names what. Membership counts matching facts or asks the shared vocabulary's gc-has,
; which the domain checks' group loads first, never is-member, which answers once per occurrence
; (c-ev-pk-is-member-per-occurrence-1018).
; am[implements a-rel-brs-section-1018@b63f59] am[implements a-rel-nd-validation-runner-1018]
; am[rests-on c-ev-pk-is-member-per-occurrence-1018] am[related a-rel-member-once-1018]
; am[related a-bnd-faults-1019@b5dc70]

!(import! &self (library lib_functional))

; --- facts ----------------------------------------------------------------------------------------------
; The facts of one head and their counts at a place come from the shared vocabulary's gc-of and
; gc-count-at, over the domain term's facts (a-rel-facts-helpers-one-home-1018).
; am[related a-rel-facts-helpers-one-home-1018]
(= (gc-brs-subjects $domain $head) (map-atom (gc-of (cdr-atom $domain) $head) $chosen (Subject $chosen $chosen)))
(= (gc-brs-has-at $domain $head $place $value) (> (gc-count-at (cdr-atom $domain) $head $place $value) 0))
(= (gc-brs-all $flags) (foldl-atom $flags True $acc $flag (and $acc $flag)))
(= (gc-brs-declared? $domain $kind $id)
   (> (size-atom (filter-atom (gc-of (cdr-atom $domain) Declared) $fact
                    (and (== (index-atom $fact 1) $kind) (== (index-atom $fact 2) $id)))) 0))
(= (gc-brs-root? $node) (case $node (((Root $j) True) ($other False))))

; --- the tables -----------------------------------------------------------------------------------------
; am[implements a-rel-brs-section-1018@b63f59]
(= (gc-brs-control-table)
   ((Row "duplicate-control" gc-brs-row-control-once "is not the only gc-brs-control of its name")))
(= (gc-brs-entity-table)
   ((Row "undeclared-control" gc-brs-row-entity-control "has a control no gc-brs-control declares")
    (Row "duplicate-entity" gc-brs-row-entity-once "is not the only gc-brs-entity of its id")
    (Row "unplaced-entity" gc-brs-row-entity-placed "has no gc-brs-in placing it")
    (Row "entity-placed-twice" gc-brs-row-entity-placed-once "is placed by more than one gc-brs-in")))
(= (gc-brs-placement-table)
   ((Row "undeclared-placed-entity" gc-brs-row-placed-entity "places an entity no gc-brs-entity declares")
    (Row "undeclared-parent" gc-brs-row-placed-parent "places it under a parent that is neither a declared entity nor a root")
    (Row "cyclic-placement" gc-brs-row-placed-acyclic "places an entity inside itself, so the place graph is not a forest")))
(= (gc-brs-link-table)
   ((Row "undeclared-linked-entity" gc-brs-row-link-entity "links a port of an entity no gc-brs-entity declares")
    (Row "undeclared-port" gc-brs-row-link-port "links a port its entity's control does not declare")
    (Row "port-linked-twice" gc-brs-row-link-once "links a port another gc-brs-link also links")))
(= (gc-brs-anchor-table)
   ((Row "malformed-literal" gc-brs-row-anchor-literal "anchors something other than (Signal NAME) or (Statement SNARS-STATEMENT)")
    (Row "undeclared-signal" gc-brs-row-anchor-signal "anchors a signal the domain does not declare")
    (Row "undeclared-anchor-entity" gc-brs-row-anchor-entity "anchors its literal on an entity no gc-brs-entity declares")
    (Row "undeclared-via" gc-brs-row-anchor-via "names a Via link no gc-brs-link declares")
    (Row "anchored-twice" gc-brs-row-anchor-once "anchors a literal another gc-brs-literal anchors too, so the literal has no one place")))
(= (gc-brs-reaction-table)
   ((Row "undeclared-action" gc-brs-row-reaction-action "is a reaction of an action the domain does not declare")
    (Row "undeclared-node-control" gc-brs-row-reaction-controls "uses a node control no gc-brs-control declares")
    (Row "duplicate-reaction" gc-brs-row-reaction-once "is not the only reaction of its action")))

; --- the rows ---------------------------------------------------------------------------------------------
; Each row is called as (ROW DOMAIN FACT) and answers True or False exactly once.
; am[implements a-rel-brs-section-1018@b63f59]
(= (gc-brs-row-control-once $domain (Control $name $ports $kind)) (== (gc-count-at (cdr-atom $domain) Control 1 $name) 1))

(= (gc-brs-row-entity-control $domain (Entity $id $control)) (gc-brs-has-at $domain Control 1 $control))
(= (gc-brs-row-entity-once $domain (Entity $id $control)) (== (gc-count-at (cdr-atom $domain) Entity 1 $id) 1))
(= (gc-brs-row-entity-placed $domain (Entity $id $control)) (gc-brs-has-at $domain Placed 1 $id))
(= (gc-brs-row-entity-placed-once $domain (Entity $id $control)) (< (gc-count-at (cdr-atom $domain) Placed 1 $id) 2))

(= (gc-brs-row-placed-entity $domain (Placed $id $parent)) (gc-brs-has-at $domain Entity 1 $id))
(= (gc-brs-row-placed-parent $domain (Placed $id $parent))
   (if (gc-brs-root? $parent) True (gc-brs-has-at $domain Entity 1 $parent)))
; Walking up from the parent reaches a root, or a node no gc-brs-in places, before it meets a node
; already passed; a node placed twice is reported by entity-placed-twice and followed by its first
; placement. Each step calls the next once, so pymetta memoizes neither (c-brs-k-auto-memo-1018).
; Time: one scan of the placements per node on the path, p nodes at most.
(= (gc-brs-row-placed-acyclic $domain (Placed $id $parent)) (gc-brs-up $domain $parent ($id)))
(= (gc-brs-up $domain $node $passed)
   (if (gc-brs-root? $node)
       True
       (if (gc-has $passed $node)
           False
           (gc-brs-up-from $domain (gc-brs-of-parent $domain $node) (cons-atom $node $passed)))))
(= (gc-brs-up-from $domain $parents $passed)
   (if (== $parents ()) True (gc-brs-up $domain (car-atom $parents) $passed)))
(= (gc-brs-of-parent $domain $id)
   (map-atom (filter-atom (gc-of (cdr-atom $domain) Placed) $fact (== (index-atom $fact 1) $id)) $fact (index-atom $fact 2)))

(= (gc-brs-row-link-entity $domain (PortLink $id $port $link)) (gc-brs-has-at $domain Entity 1 $id))
; A port belongs to the control of the entity's first declaration; an undeclared entity is reported by
; undeclared-linked-entity alone.
(= (gc-brs-row-link-port $domain (PortLink $id $port $link))
   (let $entities (filter-atom (gc-of (cdr-atom $domain) Entity) $fact (== (index-atom $fact 1) $id))
     (if (== $entities ())
         True
         (let $controls (filter-atom (gc-of (cdr-atom $domain) Control) $fact (== (index-atom $fact 1) (index-atom (car-atom $entities) 2)))
           (if (== $controls ()) True (gc-has (cdr-atom (index-atom (car-atom $controls) 2)) $port))))))
(= (gc-brs-row-link-once $domain (PortLink $id $port $link))
   (== (size-atom (filter-atom (gc-of (cdr-atom $domain) PortLink) $fact
                    (and (== (index-atom $fact 1) $id) (== (index-atom $fact 2) $port)))) 1))

(= (gc-brs-row-anchor-literal $domain (Anchor $literal $entity $via))
   (case $literal (((Signal $name) True) ((Statement $text) True) ($other False))))
(= (gc-brs-row-anchor-signal $domain (Anchor $literal $entity $via))
   (case $literal (((Signal $name) (gc-brs-declared? $domain "signal" $name)) ($other True))))
(= (gc-brs-row-anchor-entity $domain (Anchor $literal $entity $via)) (gc-brs-has-at $domain Entity 1 $entity))
(= (gc-brs-row-anchor-via $domain (Anchor $literal $entity $via))
   (let $names (map-atom (gc-of (cdr-atom $domain) PortLink) $fact (index-atom (index-atom $fact 3) 1))
     (gc-brs-all (map-atom (cdr-atom $via) $link (gc-has $names $link)))))
(= (gc-brs-row-anchor-once $domain (Anchor $literal $entity $via)) (== (gc-count-at (cdr-atom $domain) Anchor 1 $literal) 1))

(= (gc-brs-row-reaction-action $domain (Reaction $action $controls)) (gc-brs-declared? $domain "action" $action))
; A node control is a declared control's name, or a knowledge literal's subject or witness, which the
; planner's signature declares for every anchored literal.
(= (gc-brs-row-reaction-controls $domain (Reaction $action $controls))
   (gc-brs-all (map-atom (cdr-atom $controls) $control (gc-brs-node-control? $domain $control))))
(= (gc-brs-node-control? $domain $control)
   (case $control
     (((Signal $name) True) ((Statement $text) True) ((Not $inner) True)
      ($plain (gc-brs-has-at $domain Control 1 $plain)))))
(= (gc-brs-row-reaction-once $domain (Reaction $action $controls)) (== (gc-count-at (cdr-atom $domain) Reaction 1 $action) 1))

; --- the entry ----------------------------------------------------------------------------------------------
; The loader's validation runner calls this typed entry with the domain's facts; the worker below it is
; untyped, so the tables it hands the shared reader are evaluated before the call.
; am[implements a-rel-nd-validation-runner-1018] am[rests-on c-ev-pk-typed-entry-wrapper-1018@ef5a23]
(: gc-brs-run-faults (-> Atom Expression))
(= (gc-brs-run-faults $domain) (gc-brs-faults $domain))
(= (gc-brs-faults $domain)
   (let* (($controls (gc-table-faults Every (gc-brs-control-table) $domain (gc-brs-subjects $domain Control)))
          ($entities (gc-table-faults Every (gc-brs-entity-table) $domain (gc-brs-subjects $domain Entity)))
          ($placements (gc-table-faults Every (gc-brs-placement-table) $domain (gc-brs-subjects $domain Placed)))
          ($links (gc-table-faults Every (gc-brs-link-table) $domain (gc-brs-subjects $domain PortLink)))
          ($anchors (gc-table-faults Every (gc-brs-anchor-table) $domain (gc-brs-subjects $domain Anchor)))
          ($reactions (gc-table-faults Every (gc-brs-reaction-table) $domain (gc-brs-subjects $domain Reaction))))
     (append $controls (append $entities (append $placements (append $links (append $anchors $reactions)))))))

; One section whose every table has a subject, so a warm-up calls each row once outside any
; speculation; its nine faults are two duplicate controls, an undeclared control, a cyclic placement,
; an undeclared signal, anchor entity and Via, and an undeclared action and node control.
; am[implements a-rel-nd-validation-runner-1018]
(= (gc-brs-checks-warm-up)
   (== (size-atom (gc-brs-faults (Domain (Control "Box" (Ports "p") "active") (Control "Box" (Ports) "atomic")
                                         (Entity "b" "Ghost") (Placed "b" "b") (PortLink "b" "q" (Edge "e"))
                                         (Anchor (Signal "s") "c" (Via "f")) (Reaction "a" (Controls "Ghost")))))
       9))
