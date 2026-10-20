; Purpose: the planning projection's entries goal_chainer.planning.projection calls, each a typed
; wrapper over an untyped worker: the digestion of a domain's bigraph section into the kernel's
; signature, the declared world and the compiler's anchors and reactions; the agenda and the rows the
; executor's journal gives; the state rebuilt from justification's knowledge of the evidence; the plan,
; each step with its instance and named images; and admission of one plan step against a rebuilt
; state, each refusing a snapshot no world at rest fits (ai-planning-projection.md proposal 3, sections 1,
; 2, 4, 6 and 7).
;
;   (gc-pk-run-plan MODEL GOAL EVIDENCE TRACKS)
;     -> (Planned ANSWER (RULE ...)) | (Refused (Problem KIND DETAIL) ...)
;   (gc-pk-run-admit MODEL STEP INSTANCE IMAGES EVIDENCE)
;     -> (Admission VERDICT (RULE ...)) | (Refused ...)
;   (gc-pk-warm-up) -> True
;
; MODEL is (Model SECTION NAMES LIBRARY). SECTION is (Section FORM ...), the domain's bigraph forms
; as data:
;   (gc-brs-control NAME (Ports PORT ...) KIND)     KIND atomic, active or passive
;   (gc-brs-entity ID CONTROL)                      a declared entity, ID a symbol
;   (gc-brs-in ID PARENT)                           PARENT an entity or (Root J)
;   (gc-brs-link ID PORT LINK)                      LINK (Edge E) or (Name Y)
;   (gc-brs-literal L (On ENTITY) (Via NAME ...))   the anchor of a signal or statement literal, or of
;                                                   (On (Signal "S") ENTITY) at each entity a reading
;                                                   binding of S offers
;   (gc-brs-reaction "ACTION" (Redex TERM) (Reactum TERM) (Eta ...) (Conditions ...))
; NAMES and LIBRARY are the procedure policy's (policy/goalchainer_procedure.metta), which accepts the
; library against the domain's names and the section's anchors before anything is planned. GOAL is
; (Goal L ...), procedure literals. EVIDENCE is (Evidence (EVENT ...) (READING ...) (ROW ...) AS-OF):
; the executor's journal, the readings, each the shared vocabulary's (Reading ...) (domains/vocabulary.metta)
; or an entity reading (EntityReading SIGNAL ENTITY STATE ESTIMATOR VALIDITY ID) a reading binding placed
; (reading_projection.entity_term), any other justification rows, and AS-OF in microseconds since the
; epoch. An EVENT is
;   (Started "INSTANCE" "PROCEDURE" "JOURNAL")       each executed step known not done
;   (Dispatched "INSTANCE" "STEP" "ATTEMPT" "DECISION" AT)  the step's not-done row withdrawn while it runs;
;                                                    DECISION its witness digest, AT its dispatch instant
;   (Receipt "RECEIPT" "INSTANCE" "STEP" "ATTEMPT" APPLIED)  APPLIED True or False: done or not done
;   (Superseded "RECEIPT" "LATEST")                  an earlier receipt of an attempt, withdrawn
;   (Finished "INSTANCE")                            the instance leaves the agenda
; TRACKS are search.metta's. An ANSWER is search.metta's with each (Taken NAME OCC) a (Took NAME INSTANCE
; IMAGES): INSTANCE the executor's (Inst "ID") the step reads, Planned for an instance the plan starts,
; or None for Start and Derive, which read none; IMAGES ((Bound NODE IMAGE) ...) each redex node whose
; image is a declared entity or the agenda. STEP is a rule's name (Step INDEX "PROCEDURE" PART), and a
; VERDICT is (Admitted OCCURRENCE), (Blocked (Unmet LIT VALUE) ...) or (Ambiguous N). Each answer also
; lists the compiled rules a plan step's witness digests: all of them for a plan, the step's for an
; admission. A snapshot whose checked literals no world settles to at rest, search.metta's Unadmitted, is
; (Refused (Problem Contradicted ((Holds LIT VALUE) ...))), naming what it knows of the literals Derives and
; the done journal instances' Finishes touch (a-ev-pc-c1-admission-1019). No module defines a gc-brs- name,
; so section data is never evaluated (c-ev-brs-list-heads-evaluate-1018).
; am[implements a-ev-pk-rb-group-1018@ba3846] am[implements a-ev-pk-projection-1018@e5d57e]
; am[implements a-ev-pk-python-api-1018@db9b94] am[rests-on c-ev-pk-typed-entry-wrapper-1018@ef5a23]
; am[implements a-ev-pc-c1-admission-1019@92a093]

!(import! &self (library lib_functional))

; Two subcalls are inherent where a plan answer's branches are walked, so that walk declines pymetta's
; automatic memoization (c-brs-k-auto-memo-1018).
; am[implements a-ev-pk-no-auto-memo-1018@7bf95a] am[rests-on c-brs-k-auto-memo-1018@9c39b3]
!(add-atom &metta (cache gc-pk-took-answer refuse))

; --- the section --------------------------------------------------------------------------------------------
(= (gc-pk-forms $section $head) (filter-atom (cdr-atom $section) $form (== (car-atom $form) $head)))

; Every planner control the world and the rules use beside the domain's own, each declared as the exact
; compound term it is: the agenda's (Agenda), each procedure's instance (Instance "P") and completed
; journal instance (Completed "P" Silent) or (Completed "P" Wrote), each executed step's Done marker and its
; witness, and each anchored
; literal in both polarities with one port per Via link. A domain's controls are plain names, so none can
; equal one, where declaring the heads Signal, Not or Done let a domain control of that name collide
; (c-jk-po-control-named-not-b3c52ef-1018).
; am[implements a-ev-pk-projection-1018@e5d57e] am[implements a-ev-pk-exact-controls-1018@0f428d]
; am[addresses i-ev-pk-control-name-collisions-1018@00f38e]
(= (gc-pk-signature $section $anchors $library)
   (cons-atom Signature
     (append (map-atom (gc-pk-forms $section gc-brs-control) $form
               (case $form (((gc-brs-control $name $ports $kind) (Control $name (size-atom (cdr-atom $ports)) $kind)))))
       (append (cons-atom (Control (Agenda) 0 active) (gc-pk-library-controls $library))
               (gc-pk-flatten (map-atom (cdr-atom $anchors) $a (gc-pk-literal-controls $a)))))))
; am[implements a-ev-pk-exact-controls-1018@0f428d]
(= (gc-pk-literal-controls (Anchor $l $entity $control $via))
   (let $n (size-atom (cdr-atom $via)) ((Control $l $n atomic) (Control (Not $l) $n atomic))))
; Each procedure's instance control, and each executed step id's Done marker and witness once, since two
; procedures may name a step alike.
; am[implements a-ev-pk-exact-controls-1018@0f428d] am[implements a-ev-pc-r3-journal-finish-1019@ea2ea1]
(= (gc-pk-library-controls (Library $procedures $investigators))
   (append (gc-pk-flatten (map-atom $procedures $p ((Control (Instance (index-atom $p 1)) 0 active)
                                                     (Control (Completed (index-atom $p 1) Silent) 0 active)
                                                     (Control (Completed (index-atom $p 1) Wrote) 0 active))))
           (gc-pk-flatten (map-atom (unique-atom (gc-pk-flatten (map-atom $procedures $p (gc-pk-executed-ids (index-atom $p 1) $procedures))))
                            $d ((Control (Done $d) 0 atomic) (Control (Not (Done $d)) 0 atomic))))))

; Every entity port's link in the declared world: the section's gc-brs-link for that port, else a
; closed edge of the port's own, so every port is linked as the kernel requires and the compiled
; rules can name each link (compile.metta's Ports). (Ports (Port ENTITY INDEX LINK) ...).
(= (gc-pk-ports-table $section)
   (let* (($entities (gc-pk-forms $section gc-brs-entity))
          ($controls (gc-pk-forms $section gc-brs-control))
          ($links (gc-pk-forms $section gc-brs-link)))
     (cons-atom Ports (gc-pk-flatten (map-atom $entities $e
       (let* (($id (index-atom $e 1))
              ($rows (filter-atom $controls $c (== (index-atom $c 1) (index-atom $e 2))))
              ($names (if (== $rows ()) () (cdr-atom (index-atom (car-atom $rows) 2)))))
         (map-atom (gc-pk-numbered $names 0) $n
           (case $n (((Numbered $k $port)
                      (Port $id $k (gc-pk-declared-link $id $port $links))))))))))))
(= (gc-pk-declared-link $id $port $links)
   (let $found (filter-atom $links $l (case $l (((gc-brs-link $i $p $link) (and (== $i $id) (== $p $port))))))
     (if (== $found ()) (Edge (Port $id $port)) (index-atom (car-atom $found) 3))))

; The declared world in region 0 and up, and the agenda alone in the region after the last. The agenda
; node is (Agenda), of control (Agenda), terms no entity's or control's plain name can be, so a domain may
; name an entity agenda
; (i-ev-pk-entity-name-collisions-1018); every other node the planner adds is an executor's
; (Inst "ID") or a fresh (new ...) id.
; am[implements a-ev-pk-projection-1018@e5d57e] am[addresses i-ev-pk-entity-name-collisions-1018@b3416a]
(= (gc-pk-world $section $ports)
   (let* (($entities (gc-pk-forms $section gc-brs-entity))
          ($roots (gc-pk-root-count (gc-pk-forms $section gc-brs-in)))
          ($nodes (map-atom $entities $e (N (index-atom $e 1) (index-atom $e 2))))
          ($place (map-atom (gc-pk-forms $section gc-brs-in) $i (case $i (((gc-brs-in $id $parent) (In $id $parent))))))
          ($points (map-atom (cdr-atom $ports) $p (case $p (((Port $id $k $link) (P $id $k $link))))))
          ($names (unique-atom (gc-pk-flatten (map-atom (cdr-atom $ports) $p (case $p (((Port $id $k (Name $y)) ($y)) ($other ()))))))))
     (Bigraph (Inner 0 ()) (Outer (+ $roots 1) $names)
              (cons-atom Nodes (append $nodes ((N (Agenda) (Agenda)))))
              (cons-atom Place (append $place ((In (Agenda) (Root $roots)))))
              (cons-atom Link $points))))
(= (gc-pk-root-count $ins)
   (foldl-atom $ins 1 $acc $i
     (case $i (((gc-brs-in $id (Root $j)) (if (> (+ $j 1) $acc) (+ $j 1) $acc)) ($other $acc)))))
(= (gc-pk-entity-control-of $id $entities)
   (let $rows (filter-atom $entities $e (== (index-atom $e 1) $id))
     (if (== $rows ()) (Undeclared $id) (index-atom (car-atom $rows) 2))))

; Each literal's anchor, its entity's control and its Via names resolved to the declared links.
(= (gc-pk-anchors $section)
   (let* (($entities (gc-pk-forms $section gc-brs-entity))
          ($links (gc-pk-forms $section gc-brs-link)))
     (cons-atom Anchors
       (map-atom (gc-pk-forms $section gc-brs-literal) $form
         (case $form
           (((gc-brs-literal $l (On $entity) $via)
             (Anchor $l $entity (gc-pk-entity-control-of $entity $entities)
                     (cons-atom Via (map-atom (cdr-atom $via) $name (gc-pk-link-named $name $links)))))))))))
(= (gc-pk-link-named $name $links)
   (let $found (filter-atom $links $l (case $l (((gc-brs-link $id $port (Edge $e)) (== $e $name))
                                                ((gc-brs-link $id $port (Name $y)) (== $y $name)))))
     (if (== $found ()) (Unlinked $name) (index-atom (car-atom $found) 3))))
(= (gc-pk-reactions $section)
   (cons-atom Reactions
     (map-atom (gc-pk-forms $section gc-brs-reaction) $form
       (case $form (((gc-brs-reaction $action (Redex $redex) (Reactum $reactum) $eta $conditions)
                     (Reaction $action $redex $reactum $eta $conditions)))))))

; What the planner refuses in the section before it builds anything: a world or reaction the kernel
; faults, a link on a port its entity's control does not declare, an anchor on an undeclared entity or
; through an undeclared link, and a literal anchored twice, which compile.metta's gc-pk-anchor would
; otherwise resolve to its first anchor without a word: one literal has one place.
; Time: one kernel fault pass over the world and each reaction, plus a scan per link and anchor.
; am[implements a-ev-pk-projection-1018@e5d57e]
(= (gc-pk-section-problems $section $sig $world $anchors $reactions $ports)
   (let $subjects (map-atom (cdr-atom $anchors) $a (index-atom $a 1))
   (gc-pk-flatten
     ((map-atom (bg-faults $sig $world) $f (Problem World $f))
      (map-atom (unique-atom (filter-atom $subjects $s (> (size-atom (filter-atom $subjects $t (== $t $s))) 1))) $s
        (Problem DuplicateAnchor $s))
      (map-atom (filter-atom (gc-pk-forms $section gc-brs-link) $l
                  (case $l (((gc-brs-link $id $port $link)
                             (not (gc-pk-any (map-atom (cdr-atom $ports) $p (== $p (Port $id (index-atom $p 2) $link)))))))))
                $l (Problem UndeclaredPort $l))
      (gc-pk-flatten (map-atom (cdr-atom $reactions) $r
        (case $r (((Reaction $action $redex $reactum $eta $conds)
                   (map-atom (bg-rule-faults $sig (Rule $action $redex $reactum $eta $conds (Priority 0))) $f
                     (Problem Reaction (Fault $action $f))))))))
      (gc-pk-flatten (map-atom (cdr-atom $anchors) $a
        (case $a (((Anchor $l $entity $control $via)
                   (append (case $control (((Undeclared $e) ((Problem UndeclaredEntity (Literal $l $e)))) ($c ())))
                           (map-atom (filter-atom (cdr-atom $via) $v (case $v (((Unlinked $n) True) ($o False)))) $v
                             (Problem UnlinkedVia (Literal $l $v)))))))))))))

; (Digested SIG WORLD DOMAIN LITERALS) or (Refused PROBLEM ...): the section's own problems and the
; library's, which the procedure policy finds against the domain's names and the section's anchors
; (a-ev-pk-acceptance-anchors-1018), so compilation only ever sees anchored literals.
; am[implements a-ev-pk-acceptance-anchors-1018@cb1e61] am[addresses i-ev-pk-unanchored-literal-1018@6de537]
(= (gc-pk-digest (Model $section $names $library))
   (let* (($anchors (gc-pk-anchors $section))
          ($reactions (gc-pk-reactions $section))
          ($ports (gc-pk-ports-table $section))
          ($sig (gc-pk-signature $section $anchors $library))
          ($world (gc-pk-world $section $ports))
          ($problems (append (gc-pk-section-problems $section $sig $world $anchors $reactions $ports)
                             (gc-procedures-problems $library $names $section))))
     (if (== $problems ())
         (Digested $sig $world (Domain $anchors $reactions $ports)
                   (cons-atom Literals (map-atom (cdr-atom $anchors) $a (case $a (((Anchor $l $e $c $via) (Lit $l $e $via)))))))
         (cons-atom Refused $problems))))
(= (gc-pk-model-library (Model $section $names $library)) $library)

; --- rules ------------------------------------------------------------------------------------------------------
; Every evidential subject the rules read: each anchored literal under its entity's control, and each
; executed step's Done marker under its procedure's instance.
(= (gc-pk-evidential (Domain $anchors $reactions $ports) (Library $procedures $investigators))
   (append (map-atom (cdr-atom $anchors) $a (case $a (((Anchor $l $e $c $via) (Evidential $l $c)))))
           (gc-pk-flatten (map-atom $procedures $p (case $p (((Procedure $name $achieves $when $steps)
             (map-atom (filter-atom $steps $s (gc-pk-executed? $s)) $s (Evidential (Done (gc-pk-step-id $s)) (Instance $name))))))))))
; (Rules RULE ...), every compiled variant, or (Refused (Problem Rule FAULT) ...).
(= (gc-pk-rules $sig $domain $library)
   (let* (($declared (gc-pk-compile $library $domain))
          ($evidential (gc-pk-evidential $domain $library))
          ($faults (gc-pk-flatten (map-atom $declared $d (gc-pk-faults $d $evidential))))
          ($rules (gc-pk-flatten (map-atom $declared $d (collapse (gc-pk-sets-of $d)))))
          ($kernel (gc-pk-flatten (map-atom $rules $r (map-atom (bg-rule-faults $sig $r) $f (Fault (index-atom $r 1) $f))))))
     (if (== (append $faults $kernel) ())
         (cons-atom Rules $rules)
         (cons-atom Refused (map-atom (append $faults $kernel) $f (Problem Rule $f))))))

; --- the journal --------------------------------------------------------------------------------------------------
; The instances the journal started and has not finished, each (Started "INSTANCE" "PROCEDURE").
(= (gc-pk-agenda $events)
   (let $finished (gc-pk-flatten (map-atom $events $e (gc-pk-finished-id $e)))
     (cons-atom Agenda (gc-pk-flatten (map-atom $events $e (gc-pk-open-start $e $finished))))))
(= (gc-pk-finished-id $e) (case $e (((Finished $i) ($i)) ($other ()))))
; am[implements a-ev-pk-membership-gc-has-1018@f2f7e4]
(= (gc-pk-open-start $e $finished)
   (case $e (((Started $i $p $j) (if (gc-has $finished $i) () ((Started $i $p)))) ($other ()))))
; Started instances the library does not declare.
(= (gc-pk-agenda-problems $agenda (Library $procedures $investigators))
   (map-atom (filter-atom (cdr-atom $agenda) $s
               (case $s (((Started $i $p) (not (gc-pk-any (map-atom $procedures $q (== (index-atom $q 1) $p))))))))
             $s (Problem UnknownProcedure $s)))

; Rows follow c-ev-pk-typed-rows-1018: the journal's and receipts' sources are Observations, a
; superseded receipt's row is withdrawn by the latest receipt's Observation, and a dispatch withdraws
; the step's not-done row by a stated reason while its attempt is in flight. Each executed step of a
; started instance comes from the library, so the journal names only the instance and its procedure.
; Time: one pass over the events per kind, each dispatch and supersession scanning the rows of its kind.
(= (gc-pk-execution-rows $events $library)
   (let* (($started (gc-pk-flatten (map-atom $events $e (gc-pk-started-rows $e $library))))
          ($dispatched (gc-pk-flatten (map-atom $events $e (gc-pk-dispatched-rows $e $started))))
          ($receipts (gc-pk-flatten (map-atom $events $e (gc-pk-receipt-rows $e))))
          ($superseded (gc-pk-flatten (map-atom $events $e (gc-pk-superseded-rows $e $receipts)))))
     (append $started (append $dispatched (append $receipts $superseded)))))
(= (gc-pk-started-rows $e (Library $procedures $investigators))
   (case $e
     (((Started $i $p $j)
       (map-atom (gc-pk-executed-ids $p $procedures) $s
         (From (Not (On (Done $s) (Inst $i))) (Observation (Journal $j "deterministic" Forever)))))
      ($other ()))))
(= (gc-pk-executed-ids $name $procedures)
   (gc-pk-flatten (map-atom (filter-atom $procedures $q (== (index-atom $q 1) $name)) $q
     (case $q (((Procedure $n $achieves $when $steps)
                (map-atom (filter-atom $steps $x (gc-pk-executed? $x)) $x (gc-pk-step-id $x))))))))
(= (gc-pk-dispatched-rows $e $started)
   (case $e
     (((Dispatched $i $s $a $decision $at)
       (map-atom (filter-atom $started $r (gc-pk-not-done-row-of? $r $i $s))
                 $r (Withdrawn $r (Stated (Dispatched (Inst $i) $s $a)))))
      ($other ()))))
(= (gc-pk-not-done-row-of? $row $i $s)
   (case $row
     (((From (Not (On (Done $s2) (Inst $i2))) $source) (and (== $s2 $s) (== $i2 $i)))
      ($other False))))
(= (gc-pk-receipt-rows $e)
   (case $e
     (((Receipt $r $i $s $a True)
       ((From (On (Done $s) (Inst $i)) (Observation (Receipt $r "deterministic" Forever)))))
      ((Receipt $r $i $s $a False)
       ((From (Not (On (Done $s) (Inst $i))) (Observation (Receipt $r "deterministic" Forever)))))
      ($other ()))))
(= (gc-pk-superseded-rows $e $receipts)
   (case $e
     (((Superseded $old $latest)
       (map-atom (filter-atom $receipts $row (gc-pk-receipt-row-of? $row $old))
                 $row (Withdrawn $row (Observation (Receipt $latest "deterministic" Forever)))))
      ($other ()))))
(= (gc-pk-receipt-row-of? $row $receipt)
   (case $row
     (((From $claim (Observation (Receipt $r $estimator $validity))) (== $r $receipt))
      ($other False))))

; --- the state ---------------------------------------------------------------------------------------------------
; A literal instance's claim: its subject when the domain anchors the subject on that entity, else
; (On SUBJECT ENTITY), as for an instance's Done marker (c-ev-pk-reading-claim-bare-1018).
(= (gc-pk-claim (Lit $subject $entity $via) $anchors)
   (if (gc-pk-any (map-atom (cdr-atom $anchors) $a (case $a (((Anchor $l $e $c $v) (and (== $l $subject) (== $e $entity)))))))
       $subject
       (On $subject $entity)))

; The agenda's instances as nodes under the agenda, and each executed step's Done literal on them.
; am[implements a-ev-pk-projection-1018@e5d57e] am[addresses i-ev-pk-entity-name-collisions-1018@b3416a]
(= (gc-pk-with-instances (Bigraph $inner $outer $nodes $place $link) $agenda)
   (Bigraph $inner $outer
            (append $nodes (map-atom (cdr-atom $agenda) $s (case $s (((Started $i $p) (N (Inst $i) (Instance $p)))))))
            (append $place (map-atom (cdr-atom $agenda) $s (case $s (((Started $i $p) (In (Inst $i) (Agenda)))))))
            $link))
(= (gc-pk-instance-literals $agenda (Library $procedures $investigators))
   (gc-pk-flatten (map-atom (cdr-atom $agenda) $s
     (case $s (((Started $i $p)
                (map-atom (gc-pk-executed-ids $p $procedures) $x (Lit (Done $x) (Inst $i) (Via)))))))))

; (Built STATE ASSUMABLE) from the evidence, or (Refused ...) for a journal starting a procedure the
; library does not declare, an extra row that is not a statement's, or a snapshot justification refuses.
; The rows are bound before they reach justification's typed entry, which would take a computed
; argument unevaluated (c-rel-typed-entry-let-bound-1018).
; Time: one justification of the rows, then one knowledge read and one build step per literal.
; am[implements a-ev-pk-signal-evidence-one-owner-1018@bda917] am[implements a-bnd-planner-row-1019@c65aa2]
(= (gc-pk-state $world $domain $literals $library (Evidence $events $readings $rows $as-of))
   (let* (($agenda (gc-pk-agenda $events))
          ($problems (append (gc-pk-agenda-problems $agenda $library) (gc-pk-extra-row-problems $rows)))
          ($signal-readings (filter-atom $readings $r (== (car-atom $r) Reading)))
          ($entity-readings (filter-atom $readings $r (== (car-atom $r) EntityReading)))
          ($all-rows (append (gc-pk-execution-rows $events $library)
                             (append (gc-reading-rows $signal-readings) (append (gc-pk-entity-rows $entity-readings) $rows)))))
     (if (== $problems ())
         (let $justification (gc-justify (At $as-of) $all-rows)
           (gc-pk-build-from $world $domain $literals $agenda $library $justification))
         (cons-atom Refused $problems))))

; Each entity reading's row is the row the shared vocabulary's gc-reading-rows gives its signal's own Reading,
; its claim placed on the entity: detected claims (On (Signal S) E), refuted (Not (On (Signal S) E)), and an
; unknown reading has no row. The bare (Signal S) is never claimed, so an entity reading informs its entity's
; qualified literal alone (c-bnd-bare-instance-breaks-separation-1019), and its estimator, model-proposed
; whatever the probability, leaves that literal unchecked.
; Time: one row rule per entity reading.
; am[implements a-bnd-planner-row-1019@c65aa2] am[rests-on c-bnd-bare-instance-breaks-separation-1019@435e9e]
; am[rests-on c-rel-vocabulary-in-review-digest-1019@875991]
(= (gc-pk-entity-rows $readings)
   (gc-pk-flatten (map-atom $readings $r
     (case $r (((EntityReading $signal $entity $state $estimator $validity $id)
                (map-atom (gc-reading-rows ((Reading $signal $state $estimator $validity $id))) $row
                  (gc-pk-entity-row $row $entity))))))))
(= (gc-pk-entity-row (From (Not $claim) $source) $entity) (From (Not (On $claim $entity)) $source))
(= (gc-pk-entity-row (From (Signal $signal) $source) $entity) (From (On (Signal $signal) $entity) $source))

; Extra rows argue about statements alone and reach the planner's own evidence only through claims. Each
; is a statement row, one claiming (Statement T) or (Not (Statement T)) from any source but an observation
; of a kind the planner builds rows for itself, or withdraws one for a reason that is a statement row,
; named (Row ROW), or any other reference but such an observation. A Reading belongs to the readings, a
; Journal entry or a Receipt to the executor's journal, and every row the planner builds cites one of
; them, so a reference to such an observation or row would read it by its identity, which outlives its
; standing: an expired reading's row is still an accepted row while only its link is withdrawn
; (c-rel-pk-reading-row-reason-launders-1018). So signals come only from the readings' rows and execution
; progress only from the journal's, every signal's label is the one the reading rows alone give it, as the
; relevance review reads it (c-ev-pk-signal-standing-from-signal-rows-1018), and no statement is checked
; by a reading or receipt nobody holds (c-rel-pk-reading-observation-launders-1018). A statement may still
; rest on a signal's claim, (Claim (Signal S)), so a reading's defeat reaches it.
; None of these predicates recurses, since a source is never a row, so none is memoized
; (c-brs-k-auto-memo-1018).
; am[implements a-ev-pk-signal-evidence-one-owner-1018@bda917] am[rests-on c-ev-pk-signal-standing-from-signal-rows-1018@d2fc3b]
; am[rests-on c-rel-pk-reading-observation-launders-1018@11309c] am[rests-on c-rel-pk-reading-row-reason-launders-1018@0fd564]
(= (gc-pk-extra-row-problems $rows)
   (map-atom (filter-atom $rows $row (not (gc-pk-extra-row? $row))) $row (Problem ExtraRow $row)))
(= (gc-pk-extra-row? $row)
   (case $row
     (((Withdrawn $withdrawn $reason) (and (gc-pk-statement-row? $withdrawn) (gc-pk-extra-reason? $reason)))
      ($other (gc-pk-statement-row? $row)))))
(= (gc-pk-statement-row? $row)
   (case $row
     (((From $claim $source) (and (gc-pk-statement-claim? $claim) (not (gc-pk-owned-reference? $source))))
      ($other False))))
(= (gc-pk-statement-claim? $claim)
   (case $claim (((Not (Statement $negated)) True) ((Statement $text) True) ($other False))))
(= (gc-pk-extra-reason? $reason)
   (case $reason
     (((Row $named) (gc-pk-statement-row? $named))
      ($other (not (gc-pk-owned-reference? $reason))))))
; am[implements a-ev-pk-membership-gc-has-1018@f2f7e4]
(= (gc-pk-owned-reference? $reference)
   (case $reference
     (((Observation $observation)
       (if (== (get-metatype $observation) Expression) (gc-has (Reading Journal Receipt) (car-atom $observation)) False))
      ($other False))))
(= (gc-pk-build-from $world $domain $literals $agenda $library $justification)
   (if (== (car-atom $justification) Refused)
       $justification
       (let* (((Domain $anchors $reactions $ports) $domain)
              ($all (append (cdr-atom $literals) (gc-pk-instance-literals $agenda $library)))
              ($answers (map-atom $all $lit
                          (let $claim (gc-pk-claim $lit $anchors)
                            (Answer $lit (gc-justification-knowledge $claim $justification))))))
         (gc-pk-build (gc-pk-with-instances $world $agenda) $answers))))

; The model digested, its rules compiled and the state rebuilt from the evidence, (Prepared SIG
; DOMAIN LITERALS RULES STATE ASSUMABLE), or the first stage's (Refused ...).
(= (gc-pk-prepared $model $evidence)
   (case (gc-pk-digest $model)
     (((Digested $sig $world $domain $literals)
       (let $rules-answer (gc-pk-rules $sig $domain (gc-pk-model-library $model))
         (if (== (car-atom $rules-answer) Refused)
             $rules-answer
             (let $built (gc-pk-state $world $domain $literals (gc-pk-model-library $model) $evidence)
               (if (== (car-atom $built) Refused)
                   $built
                   (case $built
                     (((Built $state $assumable)
                       (Prepared $sig $domain $literals (cdr-atom $rules-answer) $state $assumable)))))))))
      ($refused $refused))))

; --- the plan ---------------------------------------------------------------------------------------------------
(= (gc-pk-goal $goal $domain)
   (cons-atom Goal (map-atom (cdr-atom $goal) $l (case (gc-pk-lit $l $domain) (((Valued $lit $value) (Holds $lit $value)))))))
(= (gc-pk-investigators (Library $procedures $investigators) $domain)
   (cons-atom Investigators
     (map-atom $investigators $i
       (case $i (((Investigator $name $observes)
                  (Investigator $name (unique-atom (map-atom $observes $l
                    (case (gc-pk-lit (gc-pk-subject-of $l) $domain) (((Valued $lit $value) $lit))))))))))))

; A step's instance and named images: Start and Derive read no instance; any other step reads the
; executor's (Inst "ID") or an instance the plan started, whose fresh (new ...) id names nothing outside
; the plan. Its images are each other redex node whose image is a declared entity or the agenda, never
; a fresh anonymous id (proposal 3, section 4). The nodes are those of every compiled variant bearing
; the step's name, since variants differ in their knowledge nodes and the kernel's bg-image answers ()
; for a node the occurrence does not map.
; am[implements a-ev-pk-python-api-1018@db9b94]
; am[implements a-ev-pk-membership-gc-has-1018@f2f7e4]
(= (gc-pk-took (Taken $name $occ) $rules)
   (let $nodes (gc-pk-rule-nodes $name $rules)
     (Took $name
           (if (gc-has $nodes Inst) (gc-pk-instance-of (bg-image $occ Inst)) None)
           (gc-pk-flatten (map-atom (filter-atom $nodes $node (not (== $node Inst))) $node
             (let $image (bg-image $occ $node)
               (if (gc-pk-named-node? $image) ((Bound $node $image)) ())))))))
(= (gc-pk-instance-of $image) (case $image (((Inst $i) (Inst $i)) ($other Planned))))
; The node ids of every compiled variant bearing NAME, each once: a witness names its images among
; them, and admission refuses an image naming any other node.
; am[implements a-ev-pk-python-api-1018@db9b94] am[implements a-integrate-planner-input-failures-1018@b84418]
(= (gc-pk-rule-nodes $name $rules)
   (unique-atom (gc-pk-flatten (map-atom (filter-atom $rules $r (== (index-atom $r 1) $name)) $r
                  (map-atom (bg-nodes (index-atom $r 2)) $n (index-atom $n 1))))))
(= (gc-pk-named-node? $id)
   (if (== $id ()) False (if (== (get-metatype $id) Expression) (not (== (car-atom $id) new)) True)))
; The answer with every plan's steps as Took: the plan itself, each inquiry branch, and NoPlan's
; explanatory alternative.
(= (gc-pk-took-answer $answer $rules)
   (case $answer
     (((Plan $steps $class $assumed) (Plan (map-atom $steps $t (gc-pk-took $t $rules)) $class $assumed))
      ((Inquire $l $i (True $yes) (False $no))
       (Inquire $l $i (True (gc-pk-took-answer $yes $rules)) (False (gc-pk-took-answer $no $rules))))
      ((NoPlan $unsolved (Alternative $plan)) (NoPlan $unsolved (Alternative (gc-pk-took-answer $plan $rules))))
      ($other $other))))

; The answer for GOAL from the prepared model, its built state settled first by what each Finish, Derive and
; act in flight may change (a-ev-pk-maybe-enabled-k0-1018), or the refusal of a snapshot no world at rest fits.
; am[implements a-ev-pk-projection-1018@e5d57e] am[implements a-ev-pk-maybe-enabled-k0-1018@287f15]
; am[implements a-ev-pc-c1-admission-1019@92a093]
(: gc-pk-run-plan (-> Atom Atom Atom Atom Expression))
(= (gc-pk-run-plan $model $goal $evidence $tracks) (gc-pk-plan-worker $model $goal $evidence $tracks))
(= (gc-pk-plan-worker $model $goal $evidence $tracks)
   (case (gc-pk-prepared $model $evidence)
     (((Prepared $sig $domain $literals $rules $state $assumable)
       (let* (($library (gc-pk-model-library $model))
              ($possible (gc-pk-possible $library $domain))
              ($answer (gc-pk-respond $sig (gc-pk-goal $goal $domain) $rules $library $tracks $literals
                                      (gc-pk-investigators $library $domain) (Built $state $assumable)
                                      $possible (gc-pk-inflight $state $library $possible))))
         (case $answer
           (((Unadmitted $known) (Refused (Problem Contradicted $known)))
            ($planned (Planned (gc-pk-took-answer $planned $rules) $rules))))))
      ($refused $refused))))

; Each executed step of an open instance whose Done the snapshot leaves unknown is an attempt in flight: in
; some world it has completed and applied its action's reaction, so it is an item whose one read, its Done,
; has moved, and every such Done starts CHANGED (a-jk-po-k0-changed-1018). An instance the planner starts
; has every Done known, so only the executor's journal puts an attempt in flight.
;   (gc-pk-inflight STATE LIBRARY POSSIBLE) -> (Moved INFLIGHT CHANGED)
; Time: per instance of a procedure with s executed steps, s knowledge reads, and a scan of the acts per pending step.
; am[implements a-ev-pk-maybe-enabled-k0-1018@287f15]
(= (gc-pk-inflight $state (Library $procedures $investigators) (Possible $mays $acts $finishes))
   (let $pending (gc-pk-flatten (map-atom (bg-nodes $state) $row (gc-pk-pending-of $row $procedures $state)))
     (Moved (gc-pk-flatten (map-atom $pending $p (gc-pk-inflight-item $p $acts)))
            (map-atom $pending $q (case $q (((Pending $name $step $done) $done)))))))
(= (gc-pk-pending-of $row $procedures $state)
   (case $row
     (((N $i (Instance $name))
       (gc-pk-flatten (map-atom (gc-pk-executed-ids $name $procedures) $s
         (let $done (Lit (Done $s) $i (Via))
           (if (== (gc-pk-knowledge $done $state) Unknown) ((Pending $name $s $done)) ())))))
      ($other ()))))
(= (gc-pk-inflight-item (Pending $name $step $done) $acts)
   (let $writes (gc-pk-flatten (map-atom $acts $a (case $a (((Acts $an $as $aw) (if (and (== $an $name) (== $as $step)) $aw ()))))))
     (if (== $writes ()) () ((Item ((Holds $done True)) $writes ())))))

; --- admission ---------------------------------------------------------------------------------------------------
; One plan step against the state rebuilt from the evidence: its rules' occurrences on the executor's
; INSTANCE, (Inst "ID") or None for Start and Derive, whose named images are the witness's IMAGES,
; grouped into successor classes by isomorphism. None: Blocked, naming each read the state does not
; establish; one class: Admitted with a representative occurrence; more: Ambiguous with their number.
; The kernel's bg-react-outcome answers each occurrence once, applied: (Successor NAME OCC G'), or
; (Refused NAME OCC REASON) for an occurrence no reaction may apply, which is never admissible, or an
; (Error ...) for a condition no clause decides, which refuses the admission. The answer lists the
; step's rules, which the caller digests to tell a stale witness.
; Time: per rule bearing the step's name, every occurrence the kernel finds, each applied once, and an
; isomorphism test against each class found so far.
; am[implements a-ev-pk-projection-1018@e5d57e] am[addresses i-ev-pk-admission-undefined-outcomes-1018@29b76d]
(: gc-pk-run-admit (-> Atom Atom Atom Atom Atom Expression))
(= (gc-pk-run-admit $model $step $instance $images $evidence) (gc-pk-admit-worker $model $step $instance $images $evidence))
; A witness image naming a node none of the step's rules has is the caller's malformed witness, refused
; as (Problem UnknownImage (Bound NODE IMAGE)), never compared and answered Blocked on nothing; a step
; whose rules are all gone answers its digest's Stale instead, since its images name nodes of rules the
; planner no longer compiles. A snapshot no world at rest fits is refused as plan refuses it, and the step
; is admitted against the state with the journal's done instances classified, as plan reads it, so a
; completed instance admits only its journal Finish and an uncertain one nothing.
; am[implements a-integrate-planner-input-failures-1018@b84418] am[implements a-ev-pc-c1-admission-1019@92a093]
; am[implements a-ev-pc-r3-classify-1019@314db6]
(= (gc-pk-admit-worker $model $step $instance $images $evidence)
   (case (gc-pk-prepared $model $evidence)
     (((Prepared $sig $domain $literals $rules $state $assumable)
       (let* (($library (gc-pk-model-library $model))
              ($possible (gc-pk-possible $library $domain))
              ($worlds (gc-pk-admitted $sig $rules $possible $literals $state))
              ($named (filter-atom $rules $r (== (index-atom $r 1) $step)))
              ($nodes (gc-pk-rule-nodes $step $rules))
              ($unknown (if (== $named ()) ()
                            (filter-atom $images $b (case $b (((Bound $node $image) (not (gc-has $nodes $node)))))))))
         (if (gc-pk-no-world? $worlds)
             (Refused (Problem Contradicted (gc-pk-touched-known $worlds $state)))
             (case (gc-pk-classify $state () $worlds)
               (((Classified $classified $changed)
                 (Admission (if (== $unknown ())
                                (gc-pk-admit-on $sig $domain $library $named $step $instance $images $classified)
                                (cons-atom Refused (map-atom $unknown $u (Problem UnknownImage $u))))
                            $named)))))))
      ($refused $refused))))
(= (gc-pk-admit-on $sig $domain $library $rules $step $instance $images $state)
   (let* (($outcomes (gc-pk-flatten (map-atom $rules $r (collapse (bg-react-outcome $sig $r $state)))))
          ($errors (filter-atom $outcomes $o (== (car-atom $o) Error)))
          ($admissible (filter-atom $outcomes $o (gc-pk-admissible? $o $instance $images)))
          ($classes (foldl-atom $admissible () $acc $c (gc-pk-add-class $acc $c))))
     (if (not (== $errors ()))
         (cons-atom Refused (map-atom $errors $e (Problem Kernel $e)))
         (if (== $classes ())
             (cons-atom Blocked (gc-pk-unmet $domain $library $step $instance $state))
             (if (== (size-atom $classes) 1)
                 (case (car-atom $classes) (((Successor $name $occ $next) (Admitted $occ))))
                 (Ambiguous (size-atom $classes)))))))
; An image pins a node the occurrence's rule has; a variant without that node, the journal Finish that matches
; a completed instance and touches no entity, is not pinned by it, since bg-image answers () for a node the
; occurrence does not map. A node no variant of the step has is UnknownImage before anything is compared.
; am[implements a-ev-pc-r3-journal-finish-1019@ea2ea1]
(= (gc-pk-admissible? $outcome $instance $images)
   (case $outcome
     (((Successor $name $occ $next)
       (and (if (== $instance None) True (== (bg-image $occ Inst) $instance))
            (gc-pk-all (map-atom $images $b (case $b (((Bound $node $image)
              (let $found (bg-image $occ $node) (or (== $found ()) (== $found $image))))))))))
      ($other False))))
(= (gc-pk-add-class $classes (Successor $name $occ $next))
   (if (gc-pk-any (map-atom $classes $c (case $c (((Successor $n2 $o2 $g2) (bg-iso $next $g2))))))
       $classes
       (append $classes ((Successor $name $occ $next)))))

; Each read of STEP the state does not establish for INSTANCE: its When and passed Achieve literals,
; each executed predecessor's Done and its own not-done witness; Start reads When alone, a Derive its When
; and its Achieve steps' literals, as compile.metta's Derive rule reads them, once each, and Finish every
; executed step's Done and the Achieve literals nothing follows. A block naming nothing is a step with no
; transition though every literal it reads holds, as for a Derive whose writes the evidence already holds
; (i-ev-pc-admit-unnamed-block-1019).
; am[implements a-ev-pc-admit-derive-reads-1019@450a34] am[addresses i-ev-pc-admit-unnamed-block-1019@cd9f50]
(= (gc-pk-unmet $domain $library $step $instance $state)
   (case $step
     (((Step $index $name $part)
       (filter-atom (gc-pk-procedure-reads $name $part $library $instance $domain) $u (gc-pk-unmet? $u $state))))))
(= (gc-pk-unmet? (Unmet $lit $value) $state) (not (== (gc-pk-knowledge $lit $state) (Known $value))))
(= (gc-pk-procedure-reads $name $part (Library $procedures $investigators) $instance $domain)
   (let $rows (filter-atom $procedures $p (== (index-atom $p 1) $name))
     (if (== $rows ())
         ()
         (case (car-atom $rows)
           (((Procedure $n $achieves $when $steps) (gc-pk-step-reads $part $when $steps $instance $domain)))))))
; am[implements a-ev-pc-admit-derive-reads-1019@450a34]
(= (gc-pk-step-reads $part $when $steps $instance $domain)
   (let $when-reads (gc-pk-literal-reads $when $domain)
     (case $part
       ((Start $when-reads)
        (Derive (gc-pk-literal-reads (unique-atom (append $when (gc-pk-flatten (map-atom $steps $s (gc-pk-step-literals $s)))))
                                     $domain))
        (Finish (gc-pk-finish-reads $steps $instance $domain))
        ($id (append $when-reads (gc-pk-act-reads $id $steps $instance $domain)))))))
(= (gc-pk-literal-reads $literals $domain)
   (map-atom $literals $l (case (gc-pk-lit $l $domain) (((Valued $lit $value) (Unmet $lit $value))))))
(= (gc-pk-finish-reads $steps $instance $domain)
   (case (gc-pk-before (gc-pk-terminal-ids $steps) $steps)
     (((Reach $done $reads)
       (append (gc-pk-done-reads $done $instance True) (gc-pk-literal-reads $reads $domain))))))
(= (gc-pk-act-reads $id $steps $instance $domain)
   (let $self (car-atom (filter-atom $steps $s (== (gc-pk-step-id $s) $id)))
     (case (gc-pk-before (gc-pk-step-after $self) $steps)
       (((Reach $done $reads)
         (append (gc-pk-literal-reads $reads $domain)
                 (cons-atom (Unmet (Lit (Done $id) $instance (Via)) False)
                            (gc-pk-done-reads $done $instance True))))))))
(= (gc-pk-done-reads $ids $instance $value)
   (map-atom $ids $d (Unmet (Lit (Done $d) $instance (Via)) $value)))

; --- warm-up ------------------------------------------------------------------------------------------------------
; Compiles every worker the entries reach once, outside any speculation: acceptance, a plan and an
; admission over a one-entity section, a one-procedure library whose Finish waits on its signal, and a
; journal that started, dispatched, receipted and finished an instance: once with the signal detected, so
; the instance is completed, once refuted, so it is uncertain, and once finished, so each later evaluate
; call runs already-compiled code.
; am[implements a-ev-pc-r3-classify-1019@314db6]
(: gc-pk-warm-up (-> Bool))
(= (gc-pk-warm-up)
   (let* (($section (Section (gc-brs-control Thing (Ports) active) (gc-brs-entity thing Thing)
                             (gc-brs-in thing (Root 0)) (gc-brs-literal (Signal "w") (On thing) (Via))))
          ($names (Names (Actions ("act")) (Signals ("w"))))
          ($library (Library ((Procedure "p" ((Signal "w")) () ((Act "a" "act" () (Binds)) (Achieve "c" (Signal "w") ("a")))))
                             ((Investigator "i" ((Signal "w"))))))
          ($model (Model $section $names $library))
          ($open (Evidence ((Started "x" "p" "j") (Dispatched "x" "a" "t" "sha256:warm-up" 0) (Receipt "r" "x" "a" "t" True))
                           ((Reading "w" "detected" "deterministic" Forever "o")) () 0))
          ($waiting (Evidence ((Started "x" "p" "j") (Dispatched "x" "a" "t" "sha256:warm-up" 0) (Receipt "r" "x" "a" "t" True))
                              ((Reading "w" "refuted" "deterministic" Forever "o")) () 0))
          ($closed (Evidence ((Started "x" "p" "j") (Finished "x")) () () 0))
          ($planned (gc-pk-plan-worker $model (Goal (Signal "w")) $open ()))
          ($uncertain (gc-pk-plan-worker $model (Goal (Not (Signal "w"))) $waiting ()))
          ($inquired (gc-pk-plan-worker $model (Goal (Not (Signal "w"))) $closed ((Track "p" (Signal "w") True))))
          ($admitted (gc-pk-admit-worker $model (Step 0 "p" Finish) (Inst "x") () $open))
          ($accepted (gc-procedures-run-check $library $names $section))
          ($attempts (gc-pk-feedback-attempts $library ((Started "x" "p" "j") (Dispatched "x" "a" "t" "sha256:warm-up" 0)
                                                        (Receipt "r" "x" "a" "t" True))
                                              ((Document "r" "t" "act" "sha256:warm-up" (At 1) 2))))
          ($counts (gc-pk-feedback-counts (Promotion 1) ("p") ((Trial "p" 0 "confirmed" "asserted")))))
     (and (and (and (== (car-atom $planned) Planned) (== (car-atom $uncertain) Planned)) (== (car-atom $inquired) Planned))
          (and (and (== (car-atom $admitted) Admission) (== $accepted Accepted))
               (and (== (car-atom $attempts) Attempts) (== (car-atom $counts) Counts))))))
