; Purpose: compile a procedure library into bigraph reaction rules over the domain's declared world
; and the agent's agenda (ai-planning-projection.md proposal 3, section 3).
;
;   (gc-pk-compile LIBRARY DOMAIN) -> ((Declared NAME REDEX REACTUM ETA CONDITIONS PRIORITY SETS) ...)
;
; LIBRARY is (Library (PROCEDURE ...) (INVESTIGATOR ...)) as goal_chainer.planning reads it, a step
; (Act "ID" "ACTION" ("AFTER" ...) (Binds (Bound RID ENTITY) ...)), (Investigate "ID" L ("AFTER" ...))
; or (Achieve "ID" L ("AFTER" ...)); Binds names, for an act whose action declares a reaction, the
; declared entity each bound redex node of that reaction must be. DOMAIN is (Domain (Anchors (Anchor
; L ENTITY CONTROL (Via LINK ...)) ...) (Reactions (Reaction "ACTION" REDEX REACTUM ETA CONDITIONS)
; ...) (Ports (Port ENTITY INDEX LINK) ...)) from the domain's bigraph section: each literal's entity,
; that entity's control and the declared links its subject reaches, each action's reaction as
; contract terms, and every entity port's link in the declared world, so a rule's entity node links
; each port through the name of that same link and the kernel's every-port rule holds on both sides.
;
; Every application of a procedure is an instance node under the planner's agenda node (Agenda), a
; term no entity's plain name can be, in the region after the world's, the agent's own record, never
; the world's. Rules are named
; (Step INDEX "PROCEDURE" PART):
;   Start      reads When; adds the instance with a not-done witness per executed step, barred
;              while an instance of the procedure is open (c-ev-pk-open-instance-bar-1018).
;   STEP-ID    reads When again, since When holds over the whole application
;              (c-ev-pk-when-invariant-1018), its own not-done witness, Done for each executed step
;              reached backward through After passing through Achieve steps, and those Achieve
;              steps' literals; writes Done; an act whose action declares a reaction is that
;              reaction too, its bound entities' reads hosted under the action's nodes.
;   Finish     reads every Done and the Achieve literals nothing follows; removes the instance and
;              sets the Achieves literals. Priority 1, with Derive, so an effect arrives with the
;              last executed step (c-ev-pk-finish-eager-1018).
;              Two more variants of the same name, the journal Finish, remove an instance of control
;              (Completed "P" KIND), one every world finished before the readings (knowledge.metta's
;              gc-pk-classify), reading and writing nothing, so the executor can journal Finished; KIND,
;              Silent or Wrote, says whether the classification entailed any of its Achieves.
;   Derive     for a procedure with no executed step: reads When and its Achieve literals, sets Achieves.
; Regions and sites are numbered action first, then one per unhosted entity, then the agenda, so an
; action's own numbering, which its Eta and conditions use, never shifts. Each entity node is
; pinned by (Image NODE ENTITY), each Via link by (Image (Name (Ln LINK)) LINK).
; am[implements a-ev-pk-compile-1018@4d30e0] am[rests-on c-ev-pk-when-invariant-1018@0182c1]
; am[rests-on c-ev-pk-finish-eager-1018@7fa12b] am[rests-on c-ev-pk-open-instance-bar-1018@6f0c91]
; am[implements a-ev-pc-r3-journal-finish-1019@ea2ea1]

!(import! &self (library lib_functional))

; --- steps and the partial order ------------------------------------------------------------------------
(= (gc-pk-step-id $s) (index-atom $s 1))
(= (gc-pk-step-after $s) (index-atom $s 3))
(= (gc-pk-executed? $s) (case $s (((Achieve $id $l $after) False) ($other True))))
(= (gc-pk-step-literals $s)
   (case $s (((Act $id $action $after $binds) ()) ((Investigate $id $l $after) ($l)) ((Achieve $id $l $after) ($l)))))

; Backward from IDS through After: an executed step is reached and stops the walk; an Achieve step
; leaves no marker, so its literal is collected and its own predecessors followed in turn. Every
; order After allows stays open, since a step waits only for these (proposal 3, section 3).
; Answers (Reach (EXECUTED-ID ...) (LITERAL ...)).
; The walk computes its next arguments before its one recursive call, since pymetta memoizes a
; function whose body calls it twice and keys each call by its whole arguments (c-brs-k-auto-memo-1018).
; Time: each step visited at most once per query; s steps.
; am[implements a-ev-pk-no-auto-memo-1018@7bf95a] am[rests-on c-brs-k-auto-memo-1018@9c39b3]
(= (gc-pk-before $ids $steps) (gc-pk-walk $ids $steps () ()))
(= (gc-pk-walk $ids $steps $executed $achieved)
   (if (== $ids ())
       (Reach (unique-atom $executed) (unique-atom $achieved))
       (let* ((($id $rest) (decons-atom $ids))
              ($step (car-atom (filter-atom $steps $s (== (gc-pk-step-id $s) $id))))
              ($stops (gc-pk-executed? $step)))
         (gc-pk-walk (if $stops $rest (append $rest (gc-pk-step-after $step)))
                     $steps
                     (if $stops (cons-atom $id $executed) $executed)
                     (if $stops $achieved (append $achieved (gc-pk-step-literals $step)))))))
; am[implements a-ev-pk-membership-gc-has-1018@f2f7e4]
(= (gc-pk-terminal-ids $steps)
   (let $needed (gc-pk-flatten (map-atom $steps $s (gc-pk-step-after $s)))
     (map-atom (filter-atom $steps $s (not (gc-has $needed (gc-pk-step-id $s)))) $s (gc-pk-step-id $s))))

; --- compilation -----------------------------------------------------------------------------------------------
(= (gc-pk-compile (Library $procedures $investigators) $domain)
   (gc-pk-flatten (map-atom (gc-pk-numbered $procedures 0) $ip (gc-pk-compile-procedure $ip $domain))))

; A procedure with executed steps compiles Start, each step, its Finish and its journal Finish, the last a
; variant named as the Finish is, as knowledge.metta's prior-knowledge variants share their rule's name, so
; plan conversion, admission and the cost read it as the Finish it is (a-ev-pc-r3-journal-finish-1019).
; am[implements a-ev-pc-r3-journal-finish-1019@ea2ea1] am[rests-on c-ev-pc-journal-finish-commutes-1019@409479]
(= (gc-pk-compile-procedure (Numbered $index (Procedure $name $achieves $when $steps)) $domain)
   (let $executed (filter-atom $steps $s (gc-pk-executed? $s))
     (if (== $executed ())
         ((gc-pk-rule (Step $index $name Derive) $domain
                      (append $when (gc-pk-flatten (map-atom $steps $s (gc-pk-step-literals $s))))
                      NoInstance $achieves 1 NoAction))
         (let (Reach $all-done $finish-reads) (gc-pk-before (gc-pk-terminal-ids $steps) $steps)
           (append
             (cons-atom (gc-pk-rule (Step $index $name Start) $domain $when
                                    (Starting $name (map-atom $executed $s (gc-pk-step-id $s))) () 0 NoAction)
               (map-atom $executed $s
                 (let (Reach $done $reads) (gc-pk-before (gc-pk-step-after $s) $steps)
                   (gc-pk-rule (Step $index $name (gc-pk-step-id $s)) $domain (append $when $reads)
                               (Advance $name (gc-pk-step-id $s) $done) () 0 (gc-pk-action-of $s $domain)))))
             ((gc-pk-rule (Step $index $name Finish) $domain $finish-reads
                          (Ending $name (map-atom $executed $s (gc-pk-step-id $s))) $achieves 1 NoAction)
              (gc-pk-rule (Step $index $name Finish) $domain () (Completing $name Silent) () 1 NoAction)
              (gc-pk-rule (Step $index $name Finish) $domain () (Completing $name Wrote) () 1 NoAction)))))))

; The act's declared reaction with its bindings, or NoAction for an investigation or an action the
; domain gives no reaction, whose effects are then its procedure's knowledge alone.
(= (gc-pk-action-of $step (Domain $anchors $reactions $ports))
   (case $step
     (((Act $id $action $after $binds)
       (let $rows (filter-atom (cdr-atom $reactions) $r (== (index-atom $r 1) $action))
         (if (== $rows ())
             NoAction
             (case (car-atom $rows)
               (((Reaction $a $redex $reactum $eta $conds) (WithAction $redex $reactum $eta $conds $binds)))))))
      ($other NoAction))))

; --- anchors ------------------------------------------------------------------------------------------------------
; A procedure literal's anchor: (Anchored SUBJECT VALUE ENTITY CONTROL (Via LINK ...)).
(= (gc-pk-anchor $literal (Domain $anchors $reactions $ports))
   (case $literal
     (((Not $inner) (case (gc-pk-anchor $inner (Domain $anchors $reactions $ports))
                      (((Anchored $s $v $e $c $via) (Anchored $s False $e $c $via)))))
      ($positive
       (let $rows (filter-atom (cdr-atom $anchors) $a (== (index-atom $a 1) $positive))
         (case (car-atom $rows) (((Anchor $l $entity $control $via) (Anchored $positive True $entity $control $via)))))))))
(= (gc-pk-anchored-entity (Anchored $s $v $e $c $via)) $e)
(= (gc-pk-same-literal? (Anchored $s $v $e $c $via) (Anchored $s2 $v2 $e2 $c2 $via2)) (and (== $s $s2) (== $e $e2)))

; --- the action's part ---------------------------------------------------------------------------------------------
; (Acting RA SA SA2 HOSTS REDEX-PART REACTUM-PART NAMES CONDITIONS ETA-ROWS): the action's roots, its
; redex and reactum sites, which entity each bound node hosts, its terms' rows with every node id
; renamed (Acted ID) so none meets a step's own, its outer names, its conditions with the bindings'
; pins, and its Eta rows. NoAction contributes nothing.
(= (gc-pk-acting NoAction) (Acting 0 0 0 () (Part () () ()) (Part () () ()) () () ()))
(= (gc-pk-acting (WithAction $redex $reactum $eta $conds $binds))
   (let (Bigraph (Inner $sa $xs) (Outer $ra $ys) $n $p $l) $redex
     (let (Bigraph (Inner $sa2 $xs2) $outer2 $n2 $p2 $l2) $reactum
       (Acting $ra $sa $sa2
               (map-atom (cdr-atom $binds) $b (case $b (((Bound $rid $entity) (Hosted $entity (Acted $rid))))))
               (gc-pk-renamed-part $redex) (gc-pk-renamed-part $reactum) $ys
               (append (cdr-atom $conds) (map-atom (cdr-atom $binds) $b (case $b (((Bound $rid $entity) (Image (Acted $rid) $entity))))))
               (cdr-atom $eta)))))
; Each case pattern names its variables apart from the equation head's, as the kernel's scope lint
; requires of every module (tests/metta_scope_lint.py, c-brs-k-case-vars-clause-scoped-1018).
; am[implements a-ev-pk-compile-1018@4d30e0] am[related c-brs-k-case-vars-clause-scoped-1018@de7554]
(= (gc-pk-renamed-part (Bigraph $inner $outer $nodes $place $link))
   (Part (map-atom (cdr-atom $nodes) $n (case $n (((N $id $c) (N (Acted $id) $c)))))
         (map-atom (cdr-atom $place) $r (case $r (((In $child $parent) (In (gc-pk-acted $child) (gc-pk-acted $parent))))))
         (map-atom (cdr-atom $link) $r (case $r (((P $pid $k $plink) (P (Acted $pid) $k $plink)) ($other $other))))))
(= (gc-pk-acted $place-id) (case $place-id (((Site $k) (Site $k)) ((Root $j) (Root $j)) ($id (Acted $id)))))
(= (gc-pk-host $entity $hosts)
   (let $rows (filter-atom $hosts $h (case $h (((Hosted $e $node) (== $e $entity)))))
     (if (== $rows ()) None (case (car-atom $rows) (((Hosted $e $node) $node))))))

; --- one rule -------------------------------------------------------------------------------------------------------
; READS and WRITES are procedure literals; INSTANCE is NoInstance, (Starting NAME (ID ...)),
; (Advance NAME ID (DONE-ID ...)) or (Ending NAME (ID ...)); ACTION is NoAction or (WithAction ...).
; A written literal the rule reads with the other value is replaced in place, and any other becomes a
; Sets entry; a written literal the rule reads with the same value changes nothing, so it is no write,
; and a Derive whose writes are all such writes compiles to no rule (knowledge.metta's gc-pk-sets-of).
; A literal read twice, by When and an Achieve step or by two Achieve steps, is read once: each read is
; its own redex node, and one literal has one node in a state (c-jk-po-derive-duplicate-read-b3c52ef-1018).
; So is a literal an act reads that its action's reaction already reads on the entity it binds: the read goes
; through the reaction's node, and the reactum carries the reaction's rewrite alone (gc-pk-acted-read).
; am[implements a-ev-pk-noop-variants-dropped-1018@2d74fc] am[addresses i-ev-pk-derive-noop-blocks-1018@e0a1cf]
; am[implements a-ev-pk-reads-once-1018@d8bb52] am[addresses i-ev-pk-duplicate-read-1018@ce5030]
; am[implements a-ev-pk-act-reads-once-1018@514fd9] am[addresses i-jk-po-act-reads-twice-1018@8b13c2]
(= (gc-pk-rule $name $domain $reads $instance $writes $priority $action)
   (let* (((Acting $ra $sa $sa2 $hosts $act-redex $act-reactum $act-names $act-conds $act-eta) (gc-pk-acting $action))
          ($readings (map-atom (unique-atom $reads) $l (ActedRead $l (gc-pk-acted-read $l $domain $hosts $act-redex))))
          ($read-once (map-atom (filter-atom $readings $x (case $x (((ActedRead $xl Separate) True) ($xo False)))) $y (index-atom $y 1)))
          ($acted-pins (gc-pk-flatten (map-atom $readings $z (case $z (((ActedRead $zl (Through $zp)) $zp) ($zo ()))))))
          ($read-anchors (gc-pk-numbered (map-atom $read-once $l (gc-pk-anchor $l $domain)) 0))
          ($write-anchors (map-atom (filter-atom $writes $l (not (gc-has $read-once $l))) $l (gc-pk-anchor $l $domain)))
          ($entities (unique-atom (append (map-atom $read-anchors $r (gc-pk-anchored-entity (index-atom $r 2)))
                                          (map-atom $write-anchors $w (gc-pk-anchored-entity $w)))))
          ($regions (gc-pk-numbered (filter-atom $entities $e (== (gc-pk-host $e $hosts) None)) 0))
          ($u (size-atom $regions))
          ($via-names (gc-pk-flatten (map-atom (append (map-atom $read-anchors $r (index-atom $r 2)) $write-anchors) $a
                        (case $a (((Anchored $s $v $e $c $via) (cdr-atom $via)))))))
          ($port-names (gc-pk-flatten (map-atom $regions $r (gc-pk-port-links (index-atom $r 2) $domain))))
          ($names (unique-atom (append $via-names $port-names)))
          ($world-redex (gc-pk-world-part $entities $regions $hosts $read-anchors $write-anchors Redex $ra $sa $domain))
          ($world-reactum (gc-pk-world-part $entities $regions $hosts $read-anchors $write-anchors Reactum $ra $sa2 $domain))
          ($inst-redex (gc-pk-agenda-part $instance (+ $ra $u) (+ $sa $u) Redex))
          ($inst-reactum (gc-pk-agenda-part $instance (+ $ra $u) (+ $sa2 $u) Reactum))
          ($roots (+ (+ $ra $u) (if (== $instance NoInstance) 0 1)))
          ($agenda-sites (gc-pk-agenda-sites $instance Redex))
          ($agenda-sites2 (gc-pk-agenda-sites $instance Reactum))
          ($pins (append (map-atom (cdr-atom (gc-pk-region-entities $regions)) $e (Image (Ent $e) $e))
                         (append (map-atom $names $l (Image (Name (Ln $l)) $l))
                                 (if (== $instance NoInstance) () ((Image (Agenda) (Agenda)))))))
          ($bar (case $instance
                  (((Starting $n $ids)
                    ((Absent (Parameter (+ $sa $u))
                             (Bigraph (Inner 1 ()) (Outer 1 ()) (Nodes (N i (Instance $n))) (Place (In i (Root 0)) (In (Site 0) i)) (Link)))))
                   ($other ()))))
          ($set (filter-atom $write-anchors $w (not (gc-pk-any (map-atom $read-anchors $r (gc-pk-same-literal? $w (index-atom $r 2))))))))
     (Declared $name
       (gc-pk-term (+ (+ $sa $u) $agenda-sites) $roots (append $act-names (map-atom $names $l (Ln $l))) (Parts $act-redex $world-redex $inst-redex))
       (gc-pk-term (+ (+ $sa2 $u) $agenda-sites2) $roots (append $act-names (map-atom $names $l (Ln $l))) (Parts $act-reactum $world-reactum $inst-reactum))
       (cons-atom Eta (append $act-eta
                              (append (map-atom (gc-pk-range $u) $r ((+ $sa2 $r) (+ $sa $r)))
                                      (map-atom (gc-pk-range $agenda-sites2) $r ((+ (+ $sa2 $u) $r) (+ (+ $sa $u) $r))))))
       (cons-atom Conditions (append $act-conds (append $pins (append $bar $acted-pins))))
       (Priority $priority)
       (cons-atom Sets (map-atom $set $w
         (case $w (((Anchored $s $v $e $c $via)
           (Set (gc-pk-entity-node $e $hosts) $s $v (cons-atom Via (map-atom (cdr-atom $via) $l (Name (Ln $l)))))))))))))

(= (gc-pk-region-entities $regions) (cons-atom Entities (map-atom $regions $r (index-atom $r 2))))
; How the rule reads LIT given its action's redex: Separate, by a node of its own, unless the redex holds a node of
; LIT's exact polarity control directly under the action's node that hosts LIT's entity; then (Through PINS), by
; that node alone, PINS pinning the link each of its ports reaches to LIT's Via link at that port, as a read node's
; ports are pinned. The node is then LIT's exactly: a child of LIT's entity of LIT's control whose ports reach its
; Via links (gc-pk-knowledge-nodes). A read of the opposite polarity stays Separate, so its act is never enabled
; (cortez-pereira's REACTION_READS_ITS_WHEN, c-jk-po-act-reads-when-twice-568231d-1018).
; Time: one anchor lookup, a scan of the action's redex nodes against its place rows, and one of its link rows.
; am[implements a-ev-pk-act-reads-once-1018@514fd9] am[rests-on c-jk-po-act-reads-when-twice-568231d-1018@492709]
(= (gc-pk-acted-read $lit $domain $hosts (Part $nodes $place $links))
   (case (gc-pk-anchor $lit $domain)
     (((Anchored $s $v $e $c $via)
       (let* (($host (gc-pk-host $e $hosts))
              ($control (gc-pk-polarity $s $v))
              ($found (filter-atom $nodes $n (case $n (((N $id $nc) (and (== $nc $control) (gc-has $place (In $id $host)))))))))
         (if (== $found ())
             Separate
             (gc-pk-through (index-atom (car-atom $found) 1) (cdr-atom $via) $links)))))))
; (Through PINS) for the action's node ID: the link each of its ports reaches, pinned to the Via link at that port.
(= (gc-pk-through $id $vias $links)
   (Through (gc-pk-flatten (map-atom $links $k
     (case $k (((P $pid $pk $plink) (if (== $pid $id) ((Image $plink (index-atom $vias $pk))) ()))
               ($ko ())))))))
(= (gc-pk-entity-node $entity $hosts) (let $host (gc-pk-host $entity $hosts) (if (== $host None) (Ent $entity) $host)))
(= (gc-pk-numbered $items $k)
   (if (== $items ()) () (cons-atom (Numbered $k (car-atom $items)) (gc-pk-numbered (cdr-atom $items) (+ $k 1)))))
(= (gc-pk-range $n) (if (== $n 0) () (append (gc-pk-range (- $n 1)) ((- $n 1)))))
; The agenda's sites: its own, and the instance's while the instance is in the term.
(= (gc-pk-agenda-sites $instance $side)
   (case $instance
     ((NoInstance 0)
      ((Starting $n $ids) 1)
      ((Advance $n $id $done) 2)
      ((Ending $n $all) (if (== $side Redex) 2 1))
      ((Completing $c $k) (if (== $side Redex) 2 1)))))

; The world's part of one side: every entity's read nodes (Read K), and on the reactum the written
; replacements (Wrote K), under the entity's own node in its region, or under the action's node that
; hosts it; knowledge ports linked to the Via names, and an unhosted entity's own ports to the names
; of its declared links. Answers (Part NODES PLACE LINKS).
(= (gc-pk-world-part $entities $regions $hosts $reads $writes $side $ra $sa $domain)
   (gc-pk-join-parts (map-atom $entities $entity
     (let* (($host (gc-pk-host $entity $hosts))
            ($region (filter-atom $regions $r (== (index-atom $r 2) $entity)))
            ($node (gc-pk-entity-node $entity $hosts))
            ($control (gc-pk-entity-control $entity $reads $writes))
            ($frame (if (== $host None)
                        (let $r (index-atom (car-atom $region) 1)
                          (Part ((N $node $control)) ((In $node (Root (+ $ra $r))) (In (Site (+ $sa $r)) $node))
                                (gc-pk-entity-points $node $entity $domain)))
                        (Part () () ())))
            ($mine (filter-atom $reads $x (== (gc-pk-anchored-entity (index-atom $x 2)) $entity)))
            ($kept (if (== $side Redex) $mine (filter-atom $mine $x (not (gc-pk-written? (index-atom $x 2) $writes)))))
            ($replaced (if (== $side Redex) () (filter-atom $mine $x (gc-pk-written? (index-atom $x 2) $writes))))
            ($read-part (gc-pk-join-parts (map-atom $kept $x (case $x (((Numbered $k (Anchored $s $v $e $c $via))
                           (gc-pk-knowledge-node (Read $k) (gc-pk-polarity $s $v) $node $via)))))))
            ($write-part (gc-pk-join-parts (map-atom $replaced $x (case $x (((Numbered $k (Anchored $s $v $e $c $via))
                            (gc-pk-knowledge-node (Wrote $k) (gc-pk-polarity $s (gc-pk-written-value (index-atom $x 2) $writes)) $node $via))))))))
       (gc-pk-join-parts ($frame $read-part $write-part))))))
(= (gc-pk-knowledge-node $id $control $parent $via)
   (Part ((N $id $control)) ((In $id $parent)) (gc-pk-ports $id (map-atom (cdr-atom $via) $l (Name (Ln $l))) 0)))
; An entity's ports in the declared world, each linked through the rule name of its world link.
(= (gc-pk-port-rows $entity (Domain $anchors $reactions $ports))
   (filter-atom (cdr-atom $ports) $p (== (index-atom $p 1) $entity)))
(= (gc-pk-port-links $entity $domain) (map-atom (gc-pk-port-rows $entity $domain) $p (index-atom $p 3)))
(= (gc-pk-entity-points $node $entity $domain)
   (map-atom (gc-pk-port-rows $entity $domain) $p (case $p (((Port $e $k $link) (P $node $k (Name (Ln $link))))))))
(= (gc-pk-entity-control $entity $reads $writes)
   (let $all (append (map-atom $reads $x (index-atom $x 2)) $writes)
     (case (car-atom (filter-atom $all $a (== (gc-pk-anchored-entity $a) $entity)))
       (((Anchored $s $v $e $c $via) $c)))))
(= (gc-pk-written? $anchored $writes) (gc-pk-any (map-atom $writes $w (gc-pk-same-literal? $anchored $w))))
(= (gc-pk-written-value $anchored $writes)
   (case (car-atom (filter-atom $writes $w (gc-pk-same-literal? $anchored $w))) (((Anchored $s $v $e $c $via) $v))))
(= (gc-pk-join-parts $parts)
   (foldl-atom $parts (Part () () ()) $acc $p
     (case (Pair $acc $p) (((Pair (Part $n1 $p1 $l1) (Part $n2 $p2 $l2)) (Part (append $n1 $n2) (append $p1 $p2) (append $l1 $l2)))))))

; The agenda's part: the agenda node (Agenda) at root RA with site SA, and the instance under it with
; site SA+1 holding its markers. Starting adds the instance with every step's not-done witness;
; Advance reads its own witness and DONE, and writes Done; Ending reads every Done and leaves the
; agenda alone with its site; Completing reads the completed instance alone and leaves the agenda the
; same way. The rule's own id for the agenda is the world's, so no entity's (Ent ID) can be it
; (i-ev-pk-entity-name-collisions-1018).
; am[implements a-ev-pk-compile-1018@4d30e0] am[addresses i-ev-pk-entity-name-collisions-1018@b3416a]
; am[implements a-ev-pc-r3-journal-finish-1019@ea2ea1]
(= (gc-pk-agenda-part $instance $ra $sa $side)
   (let $agenda (Part ((N (Agenda) (Agenda))) ((In (Agenda) (Root $ra)) (In (Site $sa) (Agenda))) ())
     (case $instance
       ((NoInstance (Part () () ()))
        ((Starting $name $ids)
         (if (== $side Redex)
             $agenda
             (gc-pk-join-parts ($agenda
               (Part (cons-atom (N Inst (Instance $name)) (map-atom $ids $d (N (Pending $d) (Not (Done $d)))))
                     (cons-atom (In Inst (Agenda)) (map-atom $ids $d (In (Pending $d) Inst)))
                     ())))))
        ((Advance $name $id $done)
         (gc-pk-join-parts ($agenda
           (Part (append ((N Inst (Instance $name)) (if (== $side Redex) (N Self (Not (Done $id))) (N Did (Done $id))))
                         (map-atom $done $d (N (Was $d) (Done $d))))
                 (append ((In Inst (Agenda)) (In (Site (+ $sa 1)) Inst) (In (if (== $side Redex) Self Did) Inst))
                         (map-atom $done $d (In (Was $d) Inst)))
                 ()))))
        ((Ending $name $all)
         (if (== $side Redex)
             (gc-pk-join-parts ($agenda
               (Part (cons-atom (N Inst (Instance $name)) (map-atom $all $d (N (Was $d) (Done $d))))
                     (append ((In Inst (Agenda)) (In (Site (+ $sa 1)) Inst)) (map-atom $all $d (In (Was $d) Inst)))
                     ())))
             $agenda))
        ((Completing $completed $kind)
         (if (== $side Redex)
             (gc-pk-join-parts ($agenda (Part ((N Inst (Completed $completed $kind))) ((In Inst (Agenda)) (In (Site (+ $sa 1)) Inst)) ())))
             $agenda))))))

(= (gc-pk-term $sites $roots $names (Parts $a $b $c))
   (let (Part $n $p $l) (gc-pk-join-parts ($a $b $c))
     (Bigraph (Inner $sites ()) (Outer $roots $names) (cons-atom Nodes $n) (cons-atom Place $p) (cons-atom Link $l))))

; --- literals as the planner names them ------------------------------------------------------------------
; A procedure literal as (Valued (Lit SUBJECT ENTITY (Via LINK ...)) VALUE), the form goals,
; investigators and the builder's answers use, anchored by the same domain rows as the rules.
(= (gc-pk-lit $literal $domain)
   (case (gc-pk-anchor $literal $domain) (((Anchored $s $v $e $c $via) (Valued (Lit $s $e $via) $v)))))

; --- what a Finish, a Derive and an act may change -------------------------------------------------------------------
; The literal reads and writes of each Finish and Derive, and the literals each act's declared reaction writes,
; which knowledge.metta's K0 cancellation reads (a-ev-pk-maybe-enabled-k0-1018), and each procedure's Finish,
; which its journal classification and search.metta's admission read:
;   (gc-pk-possible LIBRARY DOMAIN) -> (Possible (MAY ...) (ACTS ...) (FINISH ...))
;   MAY   (May Derive READS WRITES), or (May (Finish "PROCEDURE" ("ID" ...)) READS WRITES) naming the
;         procedure whose instances it finishes and its executed steps, whose Done it reads beside READS;
;   ACTS  (Acts "PROCEDURE" "STEP" WRITES) for an act whose action declares a reaction that writes a literal;
;   FINISH (Finish "PROCEDURE" ("ID" ...) READS WRITES) for every procedure with an executed step, a Finish
;         writing nothing included, since it still closes its instance.
; READS and WRITES are ((Holds LIT VALUE) ...). A write the rule reads with the same value is none, as in
; gc-pk-rule, and a MAY writing nothing is left out: it moves no literal in any world.
; Time: two passes over each procedure's steps and, per act with a reaction, one over its reactum's nodes.
; am[implements a-ev-pk-maybe-enabled-k0-1018@287f15] am[implements a-ev-pc-r3-classify-1019@314db6]
(= (gc-pk-possible (Library $procedures $investigators) $domain)
   (Possible (gc-pk-flatten (map-atom $procedures $p (gc-pk-may $p $domain)))
             (gc-pk-flatten (map-atom $procedures $q (gc-pk-acts $q $domain)))
             (gc-pk-flatten (map-atom $procedures $f (gc-pk-finish-of $f $domain)))))
(= (gc-pk-may (Procedure $name $achieves $when $steps) $domain)
   (let $executed (filter-atom $steps $s (gc-pk-executed? $s))
     (if (== $executed ())
         (gc-pk-may-of Derive (unique-atom (append $when (gc-pk-flatten (map-atom $steps $t (gc-pk-step-literals $t)))))
                       $achieves $domain)
         (case (gc-pk-before (gc-pk-terminal-ids $steps) $steps)
           (((Reach $all-done $finish-reads)
             (gc-pk-may-of (Finish $name (map-atom $executed $x (gc-pk-step-id $x))) (unique-atom $finish-reads)
                           $achieves $domain)))))))
(= (gc-pk-may-of $kind $reads $achieves $domain)
   (let $writes (filter-atom $achieves $l (not (gc-has $reads $l)))
     (if (== $writes ()) () ((May $kind (gc-pk-holds-all $reads $domain) (gc-pk-holds-all $writes $domain))))))
; am[implements a-ev-pc-r3-classify-1019@314db6] am[implements a-ev-pk-membership-gc-has-1018@f2f7e4]
(= (gc-pk-finish-of (Procedure $name $achieves $when $steps) $domain)
   (let $executed (filter-atom $steps $s (gc-pk-executed? $s))
     (if (== $executed ())
         ()
         (case (gc-pk-before (gc-pk-terminal-ids $steps) $steps)
           (((Reach $all-done $finish-reads)
             (let $reads (unique-atom $finish-reads)
               ((Finish $name (map-atom $executed $x (gc-pk-step-id $x)) (gc-pk-holds-all $reads $domain)
                        (gc-pk-holds-all (filter-atom $achieves $l (not (gc-has $reads $l))) $domain))))))))))
(= (gc-pk-holds-all $literals $domain)
   (map-atom $literals $l (case (gc-pk-lit $l $domain) (((Valued $lit $value) (Holds $lit $value))))))
; An act's reaction writes a literal its reactum places under a bound node more often than its redex does.
; am[implements a-ev-pk-maybe-enabled-k0-1018@287f15]
(= (gc-pk-acts (Procedure $name $achieves $when $steps) $domain)
   (gc-pk-flatten (map-atom (filter-atom $steps $s (gc-pk-executed? $s)) $t
     (case (gc-pk-action-of $t $domain)
       (((WithAction $redex $reactum $eta $conds $binds)
         (let $writes (gc-pk-reaction-writes $redex $reactum (cdr-atom $binds) $domain)
           (if (== $writes ()) () ((Acts $name (gc-pk-step-id $t) $writes)))))
        ($none ()))))))
(= (gc-pk-reaction-writes $redex $reactum $binds $domain)
   (unique-atom (gc-pk-flatten (map-atom $binds $b
     (case $b (((Bound $rid $entity)
                (map-atom (filter-atom (unique-atom (map-atom (bg-children $reactum $rid) $c (bg-control $reactum $c))) $control
                            (and (gc-pk-literal-control? $control)
                                 (> (gc-pk-count-control $reactum $rid $control) (gc-pk-count-control $redex $rid $control))))
                          $written (case (gc-pk-lit $written $domain) (((Valued $lit $value) (Holds $lit $value))))))))))))
(= (gc-pk-count-control $term $parent $control)
   (size-atom (filter-atom (bg-children $term $parent) $c (== (bg-control $term $c) $control))))
(= (gc-pk-literal-control? $control)
   (let $subject (case $control (((Not $inner) $inner) ($plain $plain)))
     (if (== (get-metatype $subject) Expression) (gc-has (Signal Statement) (car-atom $subject)) False)))
