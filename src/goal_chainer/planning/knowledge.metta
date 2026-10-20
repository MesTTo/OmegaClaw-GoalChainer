; Purpose: the planning projection's knowledge layer over the bigraph kernel (src/goal_chainer/bigraph):
; what a state establishes about each evidential literal, the state builder that turns
; justification's knowledge into structure, polarity writes compiled per prior knowledge, the
; loader's refusals of a read that would take an omitted node as evidence, the two condition
; clauses the projection adds to bg-holds-condition, K0's settle, and a snapshot's classification
; of the journal's done instances as completed, uncertain or open.
;
;   (gc-pk-knowledge LIT STATE) -> (Known True) | (Known False) | Unknown
;   (gc-pk-build WORLD ((Answer LIT ANSWER) ...)) -> (Built STATE ((Assumable LIT VALUE) ...))
;   (gc-pk-compile-sets DECLARED) -> RULE, once per prior-knowledge variant
;   (gc-pk-faults DECLARED EVIDENTIAL) -> ((FAULT ...) ...)
;   (gc-pk-settle STATE CHANGED POSSIBLE INFLIGHT) -> (Settled STATE CHANGED)
;   (gc-pk-classify STATE CHANGED WORLDS) -> (Classified STATE CHANGED)
;
; A literal is (Lit SUBJECT ENTITY (Via LINK ...)): it holds of the named node ENTITY when ENTITY
; has a child of control SUBJECT whose ports link, in order, to the Via links; it is established
; false when ENTITY has such a child of control (Not SUBJECT), its absence witness; it is unknown
; when ENTITY has neither (contract revision 5, section 2.3). An ANSWER is
; gc-justification-knowledge's: (Known V Checked) builds the subject or the witness, (Known V
; Unchecked) offers an assumption the planner may only explain with, and Unknown builds nothing.
; EVIDENTIAL is ((Evidential SUBJECT ENTITY-CONTROL) ...). Every pair and triple carries a
; constructor head no module defines, since a tuple headed by caller data is evaluated as a call
; once some module defines that name (c-ev-brs-list-heads-evaluate-1018).
; am[implements a-ev-pk-builder-1018@cfcf1f] am[rests-on c-ev-brs-list-heads-evaluate-1018@924cc0]
; Python reaches these functions only through planning/projection.metta's typed gc-pk-run- entries,
; so every function here is an untyped worker: an Atom-typed parameter would hand an internal caller's
; computed argument over unevaluated (c-ev-pk-typed-entry-wrapper-1018).
; am[rests-on c-ev-pk-typed-entry-wrapper-1018@ef5a23]

!(import! &self (library lib_functional))

; --- polarity --------------------------------------------------------------------------------------
(= (gc-pk-polarity $subject $value) (if (== $value True) $subject (Not $subject)))
(= (gc-pk-opposite $control) (case $control (((Not $s) $s) ($s (Not $s)))))
(= (gc-pk-subject-of $control) (case $control (((Not $s) $s) ($s $s))))
(= (gc-pk-lit-subject (Lit $subject $entity $via)) $subject)
(= (gc-pk-lit-entity (Lit $subject $entity $via)) $entity)
(= (gc-pk-lit-links (Lit $subject $entity $via)) (cdr-atom $via))

; --- knowledge of a literal --------------------------------------------------------------------------
; The nodes under LIT's entity that hold its subject or its witness, linked to its Via links in order.
; Time: for c children of the entity, c control reads and c port reads (bg-ports, the kernel's).
; am[implements a-ev-pk-membership-gc-has-1018@f2f7e4] am[implements a-ev-pk-maybe-enabled-k0-1018@287f15]
(= (gc-pk-knowledge-nodes $lit $state)
   (let* (($subject (gc-pk-lit-subject $lit))
          ($links (gc-pk-lit-links $lit)))
     (filter-atom (bg-children $state (gc-pk-lit-entity $lit)) $c
       (and (gc-has ($subject (Not $subject)) (bg-control $state $c)) (== (bg-ports $state $c) $links)))))
; Time: gc-pk-knowledge-nodes', and one control read per node it finds.
; am[implements a-ev-pk-membership-gc-has-1018@f2f7e4]
(= (gc-pk-knowledge $lit $state)
   (let* (($subject (gc-pk-lit-subject $lit))
          ($found (map-atom (gc-pk-knowledge-nodes $lit $state) $c (bg-control $state $c))))
     (if (gc-has $found $subject)
         (Known True)
         (if (gc-has $found (Not $subject)) (Known False) Unknown))))

; --- the state builder ---------------------------------------------------------------------------------
; LIT's subject (VALUE True) or witness (VALUE False) under its entity, its ports linked to the Via
; links in order, under a fresh anonymous id named after HOW: build, assume or inquire.
(= (gc-pk-add-knowledge $state $lit $value $how)
   (let* (($subject (gc-pk-lit-subject $lit))
          ($entity (gc-pk-lit-entity $lit))
          ($id (bg-fresh (new $how $subject $entity) $state)))
     (gc-pk-extend $state ((N $id (gc-pk-polarity $subject $value))) ((In $id $entity))
                   (gc-pk-ports $id (gc-pk-lit-links $lit) 0))))
(= (gc-pk-ports $id $links $k)
   (if (== $links ()) () (cons-atom (P $id $k (car-atom $links)) (gc-pk-ports $id (cdr-atom $links) (+ $k 1)))))
; A term with rows appended to its Nodes, Place and Link sections and its faces unchanged.
(= (gc-pk-extend (Bigraph $inner $outer $nodes $place $link) $more-nodes $more-place $more-links)
   (Bigraph $inner $outer (append $nodes $more-nodes) (append $place $more-place) (append $link $more-links)))

; Only checked knowledge becomes structure (i-ev-brs-unchecked-as-structure-1018): an unchecked
; answer is an assumption the planner may explain with, never act on.
; Time: one add per checked literal, each a fresh-id search over the state's ids.
(= (gc-pk-build $world $answers)
   (foldl-atom $answers (Built $world ()) $acc $a (gc-pk-build-one $acc $a)))
(= (gc-pk-build-one (Built $state $assumable) (Answer $lit $answer))
   (case $answer
     (((Known $value Checked) (Built (gc-pk-add-knowledge $state $lit $value build) $assumable))
      ((Known $value Unchecked) (Built $state (cons-atom (Assumable $lit $value) $assumable)))
      (Unknown (Built $state $assumable)))))

; --- polarity writes compiled per prior knowledge ------------------------------------------------------------
; A declared rule is (Declared NAME REDEX REACTUM ETA CONDITIONS PRIORITY (Sets (Set RID SUBJECT
; VALUE (Via LINK ...)) ...)), REDEX and REACTUM contract Bigraph terms, RID a redex node of an
; evidential entity with a site under it, the Via links the redex's own. Each entry sets the literal
; whatever it was: one variant keeps a prior of the same polarity, one matches and replaces the
; opposite, and one adds it where the generated Unknown condition finds neither, TVLA's focus before
; update (c-ev-brs-tvla-three-valued-1018). Several entries compile to the product of their variants.
; A rule that changes nothing, its reactum its redex and its Eta the identity, is no rule: it rewrites
; every state it matches to itself, and in Finish and Derive's priority class it would stay enabled
; forever and pre-empt every ordinary step (i-ev-pk-derive-noop-blocks-1018). Only a Derive can be
; one, its variant keeping every literal it sets or a Derive whose writes all keep what it reads,
; since Start, an executed step and Finish each change the agenda.
; am[implements a-ev-brs-compiled-sets-1018@1ec6e4] am[rests-on c-ev-brs-tvla-three-valued-1018@a074bd]
; am[implements a-ev-pk-noop-variants-dropped-1018@2d74fc] am[addresses i-ev-pk-derive-noop-blocks-1018@e0a1cf]
(= (gc-pk-sets-of (Declared $name $redex $reactum $eta $conds $priority $sets))
   (if (== (cdr-atom $sets) ())
       (if (gc-pk-changes-nothing? $redex $reactum $eta) (empty) (Rule $name $redex $reactum $eta $conds $priority))
       (let* ((($set $rest) (decons-atom (cdr-atom $sets)))
              ((Variant $rx $rc $cs) (gc-pk-set-variant $set $redex $reactum $conds)))
         (gc-pk-sets-of (Declared $name $rx $rc $eta $cs $priority (cons-atom Sets $rest))))))
; am[implements a-ev-pk-noop-variants-dropped-1018@2d74fc]
(= (gc-pk-changes-nothing? $redex $reactum $eta)
   (and (== $redex $reactum) (gc-pk-all (map-atom (cdr-atom $eta) $row (== (index-atom $row 0) (index-atom $row 1))))))

(= (gc-pk-set-variant (Set $rid $subject $value $via) $redex $reactum $conds)
   (let* (($node (gc-pk-polarity $subject $value))
          ($prior (Prior $rid $subject))
          ($post (Post $rid $subject))
          ($links (cdr-atom $via)))
     (superpose
       ((Variant (gc-pk-extend $redex ((N $prior $node)) ((In $prior $rid)) (gc-pk-ports $prior $links 0))
                 (gc-pk-extend $reactum ((N $prior $node)) ((In $prior $rid)) (gc-pk-ports $prior $links 0))
                 $conds)
        (Variant (gc-pk-extend $redex ((N $prior (gc-pk-opposite $node))) ((In $prior $rid)) (gc-pk-ports $prior $links 0))
                 (gc-pk-extend $reactum ((N $post $node)) ((In $post $rid)) (gc-pk-ports $post $links 0))
                 $conds)
        (Variant $redex
                 (gc-pk-extend $reactum ((N $post $node)) ((In $post $rid)) (gc-pk-ports $post $links 0))
                 (append $conds ((Unknown (Parameter (gc-pk-site-under $redex $rid)) $subject $via))))))))

(= (gc-pk-site-under $term $rid)
   (let $sites (filter-atom (bg-children $term $rid) $c (case $c (((Site $k) True) ($o False))))
     (let (Site $k) (car-atom $sites) $k)))

; --- the projection's condition clauses -----------------------------------------------------------------------
; Generated only by gc-pk-compile-sets: the parameter's roots hold neither polarity of SUBJECT
; linked to the occurrence's images of the Via links, so the literal is unknown there.
; am[implements a-ev-pk-membership-gc-has-1018@f2f7e4]
(= (bg-holds-condition (Unknown (Parameter $k) $subject $via) $occ $state)
   (let $images (map-atom (cdr-atom $via) $l (bg-image $occ $l))
     (not (gc-pk-any (map-atom (bg-parameter $occ $k) $root
            (and (gc-has ($subject (Not $subject)) (bg-control $state $root))
                 (== (bg-ports $state $root) $images)))))))
; An act binds its action's redex nodes to declared entities (a-ev-pk-compile-1018): a bound node's
; image must be that entity, so the claimant task never stands in for the focal one.
(= (bg-holds-condition (Image $rid $entity) $occ $state) (== (bg-image $occ $rid) $entity))

(= (gc-pk-any $flags) (foldl-atom $flags False $acc $f (or $acc $f)))
(= (gc-pk-all $flags) (foldl-atom $flags True $acc $f (and $acc $f)))

; --- load-time refusals ---------------------------------------------------------------------------------------
; A rule loads only with no fault. A read of an evidential literal goes through its subject or its
; witness, never through structural absence (i-jk-absence-not-evidence-1018); a closed redex node of
; an evidential entity would read the absence of every unknown child (i-ev-brs-closed-evidential-redex-1018);
; a parameter moved or merged under another evidential entity can leave a witness beside a subject
; (i-ev-brs-parameter-merge-1018); and a polarity placed under a matched node must replace one the
; redex matched there, a blind write going through Sets instead (i-ev-brs-blind-write-1018).
; am[implements a-ev-brs-refuse-closed-evidential-redex-1018@39b0cd] am[implements a-ev-brs-evidential-frame-check-1018@046321]
; Time: each check one pass over the rule's nodes, place rows or conditions, times a membership test
; in the e evidential declarations.
(= (gc-pk-faults (Declared $name $redex $reactum $eta $conds $priority $sets) $evidential)
   (let* (($controls (gc-pk-flatten (map-atom $evidential $e (case $e (((Evidential $s $c) ($s (Not $s))))))))
          ($entities (map-atom $evidential $e (case $e (((Evidential $s $c) $c))))))
     (gc-pk-flatten ((gc-pk-absence-faults $name $conds $controls)
                     (gc-pk-closed-faults $name $redex $entities)
                     (gc-pk-frame-faults $name $redex $reactum $eta $entities)
                     (gc-pk-polarity-faults $name $redex $reactum $controls)))))

; am[implements a-ev-pk-membership-gc-has-1018@f2f7e4]
(= (gc-pk-absence-faults $name $conds $controls)
   (gc-pk-flatten (map-atom (cdr-atom $conds) $c
     (case $c
       (((Absent $where $pattern)
         (map-atom (filter-atom (bg-nodes $pattern) $n (gc-has $controls (index-atom $n 2))) $n
           (StructuralAbsent $name (index-atom $n 2))))
        ((Unknown $where $subject $via) ((HandWrittenUnknown $name $subject)))
        ($other ()))))))

; am[implements a-ev-pk-membership-gc-has-1018@f2f7e4]
(= (gc-pk-closed-faults $name $redex $entities)
   (gc-pk-flatten (map-atom (filter-atom (bg-nodes $redex) $n (gc-has $entities (index-atom $n 2))) $n
     (if (gc-pk-any (map-atom (bg-children $redex (index-atom $n 1)) $c (gc-pk-site? $c)))
         ()
         ((ClosedEvidentialNode $name (index-atom $n 1)))))))

; Each reactum site paired with the redex node its parameter comes from, (From TARGET SOURCE).
; am[implements a-ev-pk-membership-gc-has-1018@f2f7e4]
(= (gc-pk-frame-faults $name $redex $reactum $eta $entities)
   (let* (($rids (map-atom (bg-nodes $redex) $n (index-atom $n 1)))
          ($sourced (gc-pk-flatten (map-atom (bg-place $reactum) $r
                      (case $r
                        (((In (Site $k) $target)
                          ((From $target (bg-parent $redex (Site (gc-pk-eta-source $k $eta))))))
                         ($other ()))))))
          ($evidential (filter-atom $sourced $s
                         (case $s (((From $target $source)
                                    (and (gc-has $rids $source) (gc-has $entities (bg-control $redex $source))))))))
          ($moved (filter-atom $evidential $s
                    (case $s (((From $target $source) (and (gc-has $rids $target) (not (== $target $source))))))))
          ($targets (map-atom $evidential $s (case $s (((From $target $source) $target)))))
          ($merged (filter-atom (unique-atom $targets) $t (> (size-atom (filter-atom $targets $u (== $u $t))) 1))))
     (append (map-atom $moved $s (case $s (((From $target $source) (Frame $name moved $source $target)))))
             (map-atom $merged $t (Frame $name merged $t)))))
(= (gc-pk-eta-source $k $eta)
   (let $rows (filter-atom (cdr-atom $eta) $e (== (index-atom $e 0) $k)) (index-atom (car-atom $rows) 1)))

; Under a node the rule creates there is no prior knowledge, so any polarity may be placed there.
; am[implements a-ev-pk-membership-gc-has-1018@f2f7e4]
(= (gc-pk-polarity-faults $name $redex $reactum $controls)
   (let $rids (map-atom (bg-nodes $redex) $n (index-atom $n 1))
     (gc-pk-flatten (map-atom (filter-atom (bg-nodes $reactum) $n (gc-has $controls (index-atom $n 2))) $n
       (let* (($id (index-atom $n 1))
              ($subject (gc-pk-subject-of (index-atom $n 2)))
              ($under (bg-parent $reactum $id))
              ($read (filter-atom (bg-children $redex $under) $c
                       (and (not (gc-pk-site? $c)) (== (gc-pk-subject-of (bg-control $redex $c)) $subject)))))
         (if (and (gc-has $rids $under) (== $read ())) ((UnreadPolarity $name $under $subject)) ()))))))

(= (gc-pk-site? $c) (case $c (((Site $k) True) ($o False))))
(= (gc-pk-flatten $lists) (foldl-atom $lists () $acc $l (append $acc $l)))

; --- possible effects: K0's cancellation -------------------------------------------------------------------------
; A Finish or Derive is maybe-enabled when each of its reads is true or unknown and one is unknown: it steps in
; some completion of the unknown literals and not in another, so its effects hold in some worlds only, and the
; state may keep no knowledge they contradict. Each maybe-enabled rule therefore forgets every literal it
; writes whose opposite the state knows, K0's cancellation rule, while the kernel's firing of an enabled rule
; is its support rule (c-ev-pk-k0-cancellation-sound-1018). A world moves only where something moved it, so a
; rule whose reads are all as the snapshot settled them cancels only the written literals that have moved:
; CHANGED lists every literal some world may hold, then or later, otherwise than at the snapshot: every literal
; a step wrote, and every literal a rule with a moved read may set, each of its writes the state does not know
; with the written value, whether known opposite and forgotten or unknown (a-jk-po-k0-changed-1018). An unknown
; one moves too: in the world where it was false at the snapshot, an attempt in flight that sets it lands after
; the readings, and a Derive reading it then steps (i-ev-pk-unknown-write-unmoved-1018). An instance whose Finish is maybe-enabled
; may have finished in some world, so its Done markers are forgotten: neither its Finish nor any of its steps
; can then match, its procedure stays barred by its node, and it goes on cancelling while its Finish's
; literal reads may hold. An act still in flight, INFLIGHT's item, may have applied its reaction in some world.
; POSSIBLE is compile.metta's (Possible (MAY ...) (ACTS ...) (FINISH ...)); an item is (Item READS WRITES DONES).
; Time: per pass, for i maybe-enabled items with r reads and w writes each, (r + w) knowledge reads, each over
; the c children of its entity, and a CHANGED scan per read and write; a pass that neither forgets nor adds to
; CHANGED ends it, and each pass but the last forgets a literal the state knew or adds a written literal to
; CHANGED, so a state knowing l literals under rules writing m distinct literals settles in at most l + m + 1 passes.
; am[implements a-ev-pk-maybe-enabled-k0-1018@287f15] am[rests-on c-ev-pk-k0-cancellation-sound-1018@5acd4f]
; am[addresses i-ev-pk-maybe-enabled-priority-1018@4095c9] am[implements a-ev-pk-moved-writes-join-1018@68c796]
; am[addresses i-ev-pk-unknown-write-unmoved-1018@b09997]
(= (gc-pk-settle $state $changed $possible $inflight)
   (case (gc-pk-settle-pass $state $changed (append $inflight (gc-pk-maybe-items $state $possible)))
     (((Pass $next $more True) (gc-pk-settle $next $more $possible $inflight))
      ((Pass $same $kept False) (Settled $same $kept)))))
; am[implements a-ev-pk-maybe-enabled-k0-1018@287f15]
(= (gc-pk-maybe-items $state (Possible $mays $acts $finishes))
   (gc-pk-flatten (map-atom $mays $m (gc-pk-maybe-of $m $state))))
; am[implements a-ev-pk-maybe-enabled-k0-1018@287f15]
(= (gc-pk-maybe-of $may $state)
   (case $may
     (((May Derive $derive-reads $derive-writes)
       (if (gc-pk-maybe? $derive-reads $state) ((Item $derive-reads $derive-writes ())) ()))
      ((May (Finish $name $ids) $finish-reads $finish-writes)
       (gc-pk-flatten (map-atom (gc-pk-instances-of $name $state) $i
         (let $dones (map-atom $ids $d (Holds (Lit (Done $d) $i (Via)) True))
           (if (gc-pk-maybe? (append $dones $finish-reads) $state)
               ((Item (append $dones $finish-reads) $finish-writes $dones))
               ()))))))))
(= (gc-pk-instances-of $name $state)
   (map-atom (filter-atom (bg-nodes $state) $row (== (index-atom $row 2) (Instance $name))) $kept (index-atom $kept 1)))
; Every read is true or unknown, and one is unknown.
(= (gc-pk-maybe? $reads $state)
   (let $known (map-atom $reads $h (case $h (((Holds $lit $value) (Read (gc-pk-knowledge $lit $state) $value)))))
     (and (gc-pk-all (map-atom $known $k (case $k (((Read $answer $wanted)
                                                    (let $opposite (not $wanted) (not (== $answer (Known $opposite)))))))))
          (gc-pk-any (map-atom $known $u (case $u (((Read $found $sought) (== $found Unknown)))))))))
; One item's moves on (Pass STATE CHANGED MOVED): each write when a read has moved, else only those that have
; moved themselves, then each Done of an uncertain instance, which the state knows true until it is forgotten.
; am[implements a-ev-pk-maybe-enabled-k0-1018@287f15] am[implements a-ev-pk-moved-writes-join-1018@68c796]
(= (gc-pk-settle-pass $state $changed $items)
   (foldl-atom $items (Pass $state $changed False) $acc $item (gc-pk-cancel-item $acc $item)))
(= (gc-pk-cancel-item (Pass $s $c $moved) (Item $reads $writes $dones))
   (let* (($read-moved (gc-pk-any (map-atom $reads $h (gc-pk-moved? $h $c))))
          ($targets (if $read-moved $writes (filter-atom $writes $w (gc-pk-moved? $w $c))))
          ($after (foldl-atom $targets (Pass $s $c $moved) $acc $t (gc-pk-move-write $acc $t))))
     (foldl-atom $dones $after $acc2 $d (gc-pk-forget-done $acc2 $d))))
(= (gc-pk-moved? (Holds $lit $value) $changed) (gc-has $changed $lit))
; A write the rule may set: forgotten when the state knows its opposite, and in CHANGED unless the state knows
; it with the written value, the one case no world can move it.
(= (gc-pk-move-write (Pass $s $c $moved) (Holds $lit $value))
   (case (gc-pk-knowledge $lit $s)
     (((Known $known) (if (== $known $value) (Pass $s $c $moved) (gc-pk-forgotten $s $c $lit)))
      (Unknown (if (gc-has $c $lit) (Pass $s $c $moved) (Pass $s (cons-atom $lit $c) True))))))
(= (gc-pk-forget-done (Pass $s $c $moved) (Holds $lit $value))
   (if (== (gc-pk-knowledge $lit $s) (Known $value)) (gc-pk-forgotten $s $c $lit) (Pass $s $c $moved)))
; LIT forgotten, and in CHANGED once.
(= (gc-pk-forgotten $s $c $lit)
   (Pass (gc-pk-forget $s $lit) (if (gc-has $c $lit) $c (cons-atom $lit $c)) True))
; The state without LIT's knowledge nodes, which are atomic, so their own rows are all they hold.
; am[implements a-ev-pk-maybe-enabled-k0-1018@287f15]
(= (gc-pk-forget (Bigraph $inner $outer $nodes $place $link) $lit)
   (let $ids (gc-pk-knowledge-nodes $lit (Bigraph $inner $outer $nodes $place $link))
     (Bigraph $inner $outer
              (cons-atom Nodes (filter-atom (cdr-atom $nodes) $n (not (gc-has $ids (index-atom $n 1)))))
              (cons-atom Place (filter-atom (cdr-atom $place) $p (not (gc-has $ids (index-atom $p 1)))))
              (cons-atom Link (filter-atom (cdr-atom $link) $l (not (gc-has $ids (index-atom $l 1))))))))

; --- the journal's done instances at a snapshot ------------------------------------------------------------------
; The readings observe the world at rest, after it settled from the journal's last receipt and before any
; act in flight lands, and nothing observes whether an instance finished in that settling
; (c-ev-pc-rest-only-readings-1019), so each executor instance whose executed steps all have receipts is
; classified by the worlds search.metta's gc-pk-admitted found at rest, which record it open or closed
; (a-jk-pc-r3-exact-amend-1019). Closed in every one, every world finished it before the readings: it is completed,
; its node taking control (Completed "P" KIND) without its markers, matched only by compile.metta's journal
; Finish, which moves nothing. Its Achieves are in the readings, or overwritten before them, or, where no
; checked reading covers one and every world holds it with the Finish's value, entailed: those join the
; state, as the readings do, and KIND is Wrote, the plan's start resting on its procedure's record, else
; Silent. Writing an Achieves over a reading would upgrade a prediction over checked evidence, so none is.
; Open in every world, no world finished it: it stays as it is. Otherwise some world finished it in that
; settling and another did not, as c-jk-pf-cx-transient-finish-1019 shows, so it is uncertain: its Done
; markers are forgotten, as the settle forgets an instance whose Finish is maybe-enabled, and join CHANGED,
; so its Finish goes on weakening whenever no literal it reads is known false. Only checked knowledge and
; the library decide this, so an assumption never does, and an instance the plan starts is never
; classified, since only a snapshot is. With no world the snapshot is refused before anything is classified.
; Time: per done instance, one membership test in each world's open instances, and for a completed one
; w knowledge reads and per write a scan of each world's values, w its Finish's writes.
; am[implements a-ev-pc-r3-classify-1019@314db6] am[implements a-jk-pc-r3-exact-amend-1019@9a3391]
; am[rests-on c-ev-pc-rest-only-readings-1019@3bd16e] am[rests-on c-ev-pc-r3-syntactic-overcautious-1019@d007da]
(= (gc-pk-classify $state $changed (Worlds $touched $finishing $rests))
   (case (foldl-atom $finishing (Pass $state $changed False) $acc $f (gc-pk-classify-instance $acc $f $rests))
     (((Pass $classified $more $moved) (Classified $classified $more)))))
; am[implements a-jk-pc-r3-exact-amend-1019@9a3391]
(= (gc-pk-classify-instance (Pass $s $c $moved) (Finishing $instance $name $ids $reads $writes) $rests)
   (let* (($dones (map-atom $ids $d (Lit (Done $d) $instance (Via))))
          ($open (size-atom (filter-atom $rests $r (case $r (((World $values $still) (gc-has $still $instance))))))))
     (if (== $open (size-atom $rests))
         (Pass $s $c $moved)
         (if (== $open 0)
             (let* (($entailed (filter-atom $writes $h (case $h (((Holds $lit $value)
                                 (and (== (gc-pk-knowledge $lit $s) Unknown)
                                      (gc-pk-all (map-atom $rests $e (case $e (((World $held $left) (gc-has $held $h))))))))))))
                    ($without (foldl-atom $dones $s $w $marker (gc-pk-forget $w $marker)))
                    ($known (foldl-atom $entailed $without $k $g (case $g (((Holds $glit $gvalue) (gc-pk-add-knowledge $k $glit $gvalue build)))))))
               (Pass (gc-pk-recontrol $known $instance (Completed $name (if (== $entailed ()) Silent Wrote))) $c $moved))
             (foldl-atom $dones (Pass $s $c $moved) $uncertain $marker (gc-pk-forgotten-of $uncertain $marker))))))
(= (gc-pk-forgotten-of (Pass $s $c $moved) $lit) (gc-pk-forgotten $s $c $lit))
; The state with node ID's control replaced by CONTROL.
(= (gc-pk-recontrol (Bigraph $inner $outer $nodes $place $link) $id $control)
   (Bigraph $inner $outer
            (cons-atom Nodes (map-atom (cdr-atom $nodes) $n (if (== (index-atom $n 1) $id) (N $id $control) $n)))
            $place $link))
