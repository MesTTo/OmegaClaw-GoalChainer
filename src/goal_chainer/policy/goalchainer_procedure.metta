; Purpose: the procedure layer's policy: which procedure library a domain accepts, every problem
; the library has in one answer, read at load time and again by the planner before it plans.
;
;   (gc-procedures-run-check LIBRARY NAMES SECTION) -> Accepted | (Refused (Problem KIND DETAIL) ...)
;   (gc-procedures-problems LIBRARY NAMES SECTION) -> ((Problem KIND DETAIL) ...)
;
; LIBRARY is (Library (PROCEDURE ...) (INVESTIGATOR ...)), a PROCEDURE
; (Procedure "NAME" (L ...) (L ...) (STEP ...)) with what it achieves, then its When conditions,
; then its steps, and an INVESTIGATOR (Investigator "NAME" (L ...)). A literal L is
; (Signal "SIGNAL"), (Statement "TEXT"), (On (Signal "SIGNAL") ENTITY), a signal on one declared
; entity, or (Not L) over one of the first three, and a STEP is
; (Act "ID" "ACTION" ("AFTER" ...) (Binds (Bound RID ENTITY) ...)), (Investigate "ID" L ("AFTER" ...))
; or (Achieve "ID" L ("AFTER" ...)). Binds name, for an act whose action declares a reaction, the
; declared entity each redex node of a declared control must be; acceptance checks them against the
; section's reactions both ways. NAMES is (Names (Actions ("ACTION" ...)) (Signals ("SIGNAL" ...))), the domain's
; declared names, and SECTION the domain's bigraph section (Section FORM ...), whose gc-brs-literal
; forms anchor the literals the planner can judge: a literal no form anchors is refused, since the
; planner could neither read it nor write it (i-ev-pk-unanchored-literal-1018). Every name is a
; string, so a domain's name is never evaluated (c-rel-strings-inert-1016). Judging literals and
; composing plans belong to justification's knowledge and the planning projection
; (planning/search.metta), which supersede the class composer (c-ev-brs-no-choice-measure-consumer-1018).
; am[implements a-ev-pl-ag-representation-1017@ca0cfc] am[rests-on c-integrate-user-metta-policy-1016@9eb3d0]
; am[implements a-ev-pk-acceptance-anchors-1018@cb1e61] am[rests-on c-rel-strings-inert-1016@947e27]

!(import! &self (library lib_functional))

; --- acceptance: every problem the library has, in one answer ---------------------------------

; The typed entry goal_chainer.planning.procedures calls; the planner's digest calls the worker below,
; since a typed entry hands an internal caller's computed argument over unevaluated
; (c-ev-pk-typed-entry-wrapper-1018).
; am[implements a-ev-pk-acceptance-anchors-1018@cb1e61] am[rests-on c-ev-pk-typed-entry-wrapper-1018@ef5a23]
(: gc-procedures-run-check (-> Atom Atom Atom Expression))
(= (gc-procedures-run-check $library $names $section)
   (let $problems (gc-procedures-problems $library $names $section)
     (if (== $problems ()) Accepted (cons-atom Refused $problems))))

; A library is acceptable when nothing in it names what the domain does not declare or anchor, no
; two procedures, investigators or steps of one procedure share a name, every After names an earlier
; step of the same procedure without a cycle, no procedure predicts a literal twice or a literal and
; its negation, and no Derives undo one another's writes in a cycle that could run forever.
; Each part is bound by let* before the list of parts is built, because only an expression whose
; head names a function is evaluated, so a list written of calls would stay a list of calls.
; am[implements a-ev-pl-ag-representation-1017@ca0cfc] am[implements a-ev-pk-acceptance-anchors-1018@cb1e61]
; am[implements a-ev-pc-r2-policy-1019@05d393]
(= (gc-procedures-problems (Library $procedures $investigators) (Names (Actions $actions) (Signals $signals)) $section)
   (let* (($anchored (gc-procedure-anchored $section))
          ($procedure-names (gc-procedure-duplicates procedure (map-atom $procedures $p (gc-procedure-name $p))))
          ($investigator-names (gc-procedure-duplicates investigator (map-atom $investigators $i (gc-investigator-name $i))))
          ($in-procedures (gc-procedure-flatten (map-atom $procedures $p (gc-procedure-problems $p $actions $signals $anchored $section))))
          ($in-investigators (gc-procedure-flatten (map-atom $investigators $i (gc-investigator-problems $i $signals $anchored))))
          ($undo-cycle (gc-procedure-undo-cycle $procedures)))
     (unique-atom (gc-procedure-flatten ($procedure-names $investigator-names $in-procedures $in-investigators $undo-cycle)))))

; The literals the section's gc-brs-literal forms anchor.
; am[implements a-ev-pk-acceptance-anchors-1018@cb1e61]
(= (gc-procedure-anchored $section)
   (map-atom (filter-atom (cdr-atom $section) $form (== (car-atom $form) gc-brs-literal)) $form (index-atom $form 1)))

(= (gc-procedure-name (Procedure $name $achieves $when $steps)) $name)
(= (gc-investigator-name (Investigator $name $observes)) $name)

; Time: s^2 comparisons per procedure for its After order, s = its steps, n^2 for the names, and a
; scan of the a anchored literals per literal; its Achieves literals compared pairwise, twice.
; am[implements a-ev-pl-ag-representation-1017@ca0cfc] am[implements a-ev-fb-achieves-once-1018@ba60a9]
(= (gc-procedure-problems (Procedure $name $achieves $when $steps) $actions $signals $anchored $section)
   (let* (($empty-achieves (if (== $achieves ()) ((Problem achieves-nothing $name)) ()))
          ($empty-steps (if (== $steps ()) ((Problem no-steps $name)) ()))
          ($repeated (gc-procedure-duplicates (achieves $name) $achieves))
          ($contradictions (gc-procedure-contradictions $name $achieves))
          ($literals (gc-procedure-literal-problems $name (append $achieves $when) $signals $anchored))
          ($step-names (gc-procedure-duplicates (step $name) (map-atom $steps $s (gc-procedure-step-id $s))))
          ($in-steps (gc-procedure-flatten (map-atom $steps $s (gc-procedure-step-problems $name $s $steps $actions $signals $anchored $section))))
          ($cycle (gc-procedure-cycle $name $steps)))
     (gc-procedure-flatten ($empty-achieves $empty-steps $repeated $contradictions $literals $step-names $in-steps $cycle))))

(= (gc-investigator-problems (Investigator $name $observes) $signals $anchored)
   (let* (($empty (if (== $observes ()) ((Problem observes-nothing $name)) ()))
          ($literals (gc-procedure-literal-problems $name $observes $signals $anchored)))
     (append $empty $literals)))

; A procedure predicting both L and (Not L) predicts nothing a receipt could grade. One predicting L twice is
; refused by gc-procedure-duplicates above, since one observation of its attempt would grade both copies
; (a-ev-fb-achieves-once-1018).
; am[implements a-ev-pk-membership-gc-has-1018@f2f7e4]
(= (gc-procedure-contradictions $name $achieves)
   (map-atom (filter-atom $achieves $l (gc-has $achieves (gc-procedure-negate $l))) $l
     (Problem contradictory-achieves ($name $l))))

(= (gc-procedure-negate (Not $l)) $l)
(= (gc-procedure-negate (Signal $s)) (Not (Signal $s)))
(= (gc-procedure-negate (Statement $t)) (Not (Statement $t)))
; am[implements a-ev-bnd-qualified-acceptance-1019@47bdad]
(= (gc-procedure-negate (On $signal $entity)) (Not (On $signal $entity)))

; A signal must be declared and anchored, a statement anchored; an undeclared signal is reported as
; undeclared alone, since anchoring it would not make it a signal of the domain. A signal on an entity
; must be a declared signal too, and anchored, which it is exactly where a reading binding of the signal
; offers the entity, since the section term derives those anchors and a section writes none itself.
; am[implements a-ev-pk-acceptance-anchors-1018@cb1e61]
(= (gc-procedure-literal-problems $owner $literals $signals $anchored)
   (gc-procedure-flatten (map-atom $literals $l (gc-procedure-literal-problem $owner $l $signals $anchored))))
(= (gc-procedure-literal-problem $owner (Not $l) $signals $anchored) (gc-procedure-literal-problem $owner $l $signals $anchored))
(= (gc-procedure-literal-problem $owner (Statement $text) $signals $anchored)
   (gc-procedure-unanchored $owner (Statement $text) $anchored))
; am[implements a-ev-pk-membership-gc-has-1018@f2f7e4]
(= (gc-procedure-literal-problem $owner (Signal $s) $signals $anchored)
   (if (gc-has $signals $s) (gc-procedure-unanchored $owner (Signal $s) $anchored) ((Problem undeclared-signal ($owner $s)))))
; am[implements a-ev-bnd-qualified-acceptance-1019@47bdad] am[implements a-ev-pk-membership-gc-has-1018@f2f7e4]
(= (gc-procedure-literal-problem $owner (On (Signal $s) $entity) $signals $anchored)
   (if (gc-has $signals $s)
       (gc-procedure-unanchored $owner (On (Signal $s) $entity) $anchored)
       ((Problem undeclared-signal ($owner $s)))))
; am[implements a-ev-pk-membership-gc-has-1018@f2f7e4]
(= (gc-procedure-unanchored $owner $literal $anchored)
   (if (gc-has $anchored $literal) () ((Problem unanchored-literal ($owner $literal)))))

(= (gc-procedure-step-id (Act $id $action $after $binds)) $id)
(= (gc-procedure-step-id (Investigate $id $literal $after)) $id)
(= (gc-procedure-step-id (Achieve $id $literal $after)) $id)
(= (gc-procedure-step-after (Act $id $action $after $binds)) $after)
(= (gc-procedure-step-after (Investigate $id $literal $after)) $after)
(= (gc-procedure-step-after (Achieve $id $literal $after)) $after)

; am[implements a-ev-pk-membership-gc-has-1018@f2f7e4]
(= (gc-procedure-step-problems $name $step $steps $actions $signals $anchored $section)
   (let $ids (map-atom $steps $s (gc-procedure-step-id $s))
     (append (gc-procedure-step-target-problems $name $step $actions $signals $anchored $section)
             (map-atom (filter-atom (gc-procedure-step-after $step) $a (not (gc-has $ids $a))) $a
               (Problem dangling-after ($name (gc-procedure-step-id $step) $a))))))

; An act names a declared action and binds each redex node at most once, and its binds and its action's
; reaction agree both ways: every redex node of a declared control is bound, and each bind names a redex
; node and a declared entity of that node's control; an action without a reaction has no node to bind.
; The planner hosts a step's reads under named entities, so an unbound node could only match an entity
; the step does not read, the matcher's choice, or none, and a bind no redex node can meet leaves the act
; unable to apply: the plan would be silently wrong or absent (c-ev-pk-unbound-node-wrong-target-1018).
; Time: per act, one scan of the section's forms per bind and of the redex nodes per node.
; am[implements a-ev-pk-bind-table-1018@761a0f] am[rests-on c-ev-pk-unbound-node-wrong-target-1018@bf7b36]
; am[implements a-ev-pk-membership-gc-has-1018@f2f7e4]
(= (gc-procedure-step-target-problems $name (Act $id $action $after $binds) $actions $signals $anchored $section)
   (let* (($rids (map-atom (cdr-atom $binds) $b (index-atom $b 1)))
          ($undeclared (if (gc-has $actions $action) () ((Problem undeclared-action ($name $id $action)))))
          ($duplicates (map-atom (filter-atom (unique-atom $rids) $r (> (size-atom (filter-atom $rids $x (== $x $r))) 1)) $r
                         (Problem duplicate-bind ($name $id $r))))
          ($nodes (gc-procedure-redex-nodes $action $section))
          ($binding (gc-procedure-flatten (map-atom (cdr-atom $binds) $c (gc-procedure-bind-problems $name $id $c $nodes $section))))
          ($unbound (map-atom (filter-atom $nodes $n (gc-procedure-unbound? $n $rids)) $m
                      (Problem unbound-node ($name $id (index-atom $m 1))))))
     (gc-procedure-flatten ($undeclared $duplicates $binding $unbound))))
(= (gc-procedure-step-target-problems $name (Investigate $id $literal $after) $actions $signals $anchored $section)
   (gc-procedure-literal-problem $name $literal $signals $anchored))
(= (gc-procedure-step-target-problems $name (Achieve $id $literal $after) $actions $signals $anchored $section)
   (gc-procedure-literal-problem $name $literal $signals $anchored))

; The (N ID CONTROL) nodes of the redex of the reaction the section declares for ACTION, none for an
; action it gives no reaction or a redex of another shape, which the bigraph kernel faults when the
; planner digests the section.
; am[implements a-ev-pk-bind-table-1018@761a0f]
(= (gc-procedure-redex-nodes $action $section)
   (let $reactions (filter-atom (cdr-atom $section) $form
                     (and (== (car-atom $form) gc-brs-reaction) (== (index-atom $form 1) $action)))
     (if (== $reactions ())
         ()
         (case (index-atom (car-atom $reactions) 2)
           (((Redex (Bigraph $inner $outer $listed $place $link)) (cdr-atom $listed))
            ($other ()))))))
; A node of a declared control is an entity's, which a bind must name; a knowledge literal's control is
; an expression and its node anonymous by design. The control is bound before get-metatype reads it,
; since get-metatype takes its argument unevaluated and would answer Expression for the call itself
; (c-rel-typed-entry-let-bound-1018).
; am[implements a-ev-pk-bind-table-1018@761a0f]
; am[implements a-ev-pk-membership-gc-has-1018@f2f7e4]
(= (gc-procedure-unbound? $node $rids)
   (let $control (index-atom $node 2)
     (and (== (get-metatype $control) Symbol) (not (gc-has $rids (index-atom $node 1))))))
; am[implements a-ev-pk-bind-table-1018@761a0f]
(= (gc-procedure-bind-problems $name $id (Bound $rid $entity) $nodes $section)
   (let* (($matched (filter-atom $nodes $k (== (index-atom $k 1) $rid)))
          ($declared (filter-atom (cdr-atom $section) $f
                       (and (== (car-atom $f) gc-brs-entity) (== (index-atom $f 1) $entity)))))
     (if (== $matched ())
         ((Problem unknown-bind ($name $id $rid)))
         (if (== $declared ())
             ((Problem undeclared-bind-entity ($name $id $entity)))
             (if (== (index-atom (car-atom $declared) 2) (index-atom (car-atom $matched) 2))
                 ()
                 ((Problem mistyped-bind ($name $id $rid $entity))))))))

; The After order is acyclic when repeatedly setting aside every step whose predecessors are all
; set aside empties the procedure, Kahn's algorithm; what is left names the cycle. A dangling After
; never becomes set aside, so its step is reported by gc-procedure-step-problems, not here.
; Time: at most s rounds of s steps each, s = the procedure's steps.
(= (gc-procedure-cycle $name $steps)
   (let $left (gc-procedure-unordered $steps () (map-atom $steps $s (gc-procedure-step-id $s)))
     (if (== $left ())
         ()
         ((Problem cyclic-after ($name (map-atom $left $s (gc-procedure-step-id $s))))))))

; am[implements a-ev-pk-membership-gc-has-1018@f2f7e4]
(= (gc-procedure-unordered $steps $done $ids)
   (let* (($ready (filter-atom $steps $s
                    (and (not (gc-has $done (gc-procedure-step-id $s)))
                         (gc-procedure-all (map-atom (gc-procedure-step-after $s) $a
                                             (or (gc-has $done $a) (not (gc-has $ids $a))))))))
          ($left (filter-atom $steps $s
                   (and (not (gc-has $done (gc-procedure-step-id $s)))
                        (not (gc-has $ready $s))))))
     (if (== $ready ())
         $left
         (gc-procedure-unordered $steps (append $done (map-atom $ready $s (gc-procedure-step-id $s))) $ids))))

; A name given twice is one problem naming the name, whatever kind of thing it names.
(= (gc-procedure-duplicates $kind $names)
   (map-atom (unique-atom (filter-atom $names $n (> (size-atom (filter-atom $names $m (== $m $n))) 1))) $n
     (Problem (duplicate $kind) $n)))

; --- termination: no Derive cycle ---------------------------------------------------------------
; A Derive, a procedure whose every step is an Achieve step, applies whenever its reads hold and it
; would change a literal, so within one settling it applies again only after another move writes the
; negation of one of its writes; a Finish applies once per open instance and an act in flight lands
; once, so only Derives can repeat (a-jk-pc-r2-undo-graph-1019). A Derive reads its When and its
; Achieve steps' literals, as compile.metta's Derive rule does, and writes the Achieves it does not
; read, as gc-pk-may-of counts them. The library is refused when its live undo graph has a cycle: an
; edge runs from Derive D' to another Derive D when D' writes the negation of a literal D writes, unless the
; two read opposite values of a subject no Derive writes; a Derive writing a literal and its negation is
; contradictory-achieves already. Such a subject changes only at the finitely many
; Finishes and landings of a settling, so between them the two are never both able to apply. Two
; Derives copying a into b both ways read a both ways, a subject no Derive writes, and are kept; two
; turning a into not-a and back once g holds read a both ways too, but a Derive writes a, so they are
; refused, naming the Derives left once every Derive with no edge in or no edge out among the rest is
; set aside: those on a cycle or between two.
; Time: d^2 Derive pairs, each a pairwise comparison of their writes and of their reads, d = the
; library's Derives; then at most d rounds setting Derives aside, each scanning the e edges.
; am[implements a-ev-pc-r2-policy-1019@05d393] am[implements a-jk-pc-r2-undo-graph-1019@fc3557]
; am[rests-on c-jk-pc-invariant-1019@bd062e]
(= (gc-procedure-undo-cycle $procedures)
   (let* (($derives (gc-procedure-flatten (map-atom $procedures $p (gc-procedure-derive-of $p))))
          ($derive-written (gc-procedure-flatten (map-atom $derives $d
                             (case $d (((Derive $dn $dr $dw) (map-atom $dw $w (gc-procedure-subject $w))))))))
          ($edges (gc-procedure-flatten (map-atom $derives $from
                    (gc-procedure-flatten (map-atom $derives $to
                      (if (and (not (== $from $to)) (gc-procedure-undoes? $from $to $derive-written))
                          ((Undo (gc-procedure-derive-name $from) (gc-procedure-derive-name $to)))
                          ()))))))
          ($left (gc-procedure-on-cycles (map-atom $derives $n (gc-procedure-derive-name $n)) $edges)))
     (if (== $left ()) () ((Problem cyclic-undo $left)))))
; (Derive NAME READS WRITES) for a procedure every one of whose steps is an Achieve step, else nothing; a
; procedure with no step has no Derive, no-steps refusing it.
; am[implements a-ev-pc-r2-policy-1019@05d393] am[implements a-ev-pk-membership-gc-has-1018@f2f7e4]
(= (gc-procedure-derive-of (Procedure $name $achieves $when $steps))
   (if (and (not (== $steps ())) (gc-procedure-all (map-atom $steps $s (gc-procedure-achieve-step? $s))))
       (let $reads (unique-atom (append $when (map-atom $steps $t (index-atom $t 2))))
         ((Derive $name $reads (filter-atom $achieves $l (not (gc-has $reads $l))))))
       ()))
(= (gc-procedure-achieve-step? $step) (case $step (((Achieve $id $literal $after) True) ($other False))))
(= (gc-procedure-derive-name (Derive $name $reads $writes)) $name)
(= (gc-procedure-subject $literal) (case $literal (((Not $inner) $inner) ($plain $plain))))
; FROM undoes TO when it writes the negation of TO's write and no subject outside WRITTEN, the subjects
; some Derive writes, is read one way by FROM and the other by TO.
; am[implements a-ev-pc-r2-policy-1019@05d393] am[implements a-ev-pk-membership-gc-has-1018@f2f7e4]
(= (gc-procedure-undoes? (Derive $from-name $from-reads $from-writes) (Derive $to-name $to-reads $to-writes) $written)
   (and (gc-procedure-any (map-atom $from-writes $w (gc-has $to-writes (gc-procedure-negate $w))))
        (not (gc-procedure-any (map-atom $from-reads $r
               (and (gc-has $to-reads (gc-procedure-negate $r)) (not (gc-has $written (gc-procedure-subject $r)))))))))
; The NODES on a cycle of EDGES or between two: each round sets aside every node with no edge from, or no
; edge to, a node still kept, until a round sets none aside.
; am[implements a-ev-pc-r2-policy-1019@05d393] am[implements a-ev-pk-membership-gc-has-1018@f2f7e4]
(= (gc-procedure-on-cycles $nodes $edges)
   (let* (($among (filter-atom $edges $e (case $e (((Undo $a $b) (and (gc-has $nodes $a) (gc-has $nodes $b)))))))
          ($kept (filter-atom $nodes $n
                   (and (gc-procedure-any (map-atom $among $i (case $i (((Undo $ia $ib) (== $ib $n))))))
                        (gc-procedure-any (map-atom $among $o (case $o (((Undo $oa $ob) (== $oa $n))))))))))
     (if (== (size-atom $kept) (size-atom $nodes)) $kept (gc-procedure-on-cycles $kept $edges))))

(= (gc-procedure-all $flags) (foldl-atom $flags True $acc $f (and $acc $f)))
(= (gc-procedure-any $flags) (foldl-atom $flags False $acc $f (or $acc $f)))
(= (gc-procedure-flatten $lists) (foldl-atom $lists () $acc $list (append $acc $list)))
