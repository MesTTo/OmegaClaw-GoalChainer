; Purpose: decide what a decision does with each memory item it is handed: which slots carry
; acceptability evidence, the ranges that evidence must lie in, its weight in evidence units, whose
; evidence it is, which one item of each identity is fused or read, and which reader failures leave
; a memory text unread.
;
;   (gc-memory-slots) -> (("SLOT" ENCODING) ...)
;   (gc-memory-text-omissions) -> (REASON ...)
;   (gc-memory-admit (ITEM ...) ("CANDIDATE ACTION" ...) "REQUEST-DIGEST")
;     -> (goalchainer-memory-v1 admit ok (DISPOSITION ...))
;      | (goalchainer-memory-v1 admit rejected (Rejected REASON SUBJECT DETAIL))
;
; An item is (Item INDEX NoSlot) for one with neither a slot nor text; (Item INDEX BlankText) for an
; unslotted item whose text is blank; (Item INDEX (Text "DIGEST")) for an unslotted item carrying
; text, as WMTM's {id, content, sti} items do; (Item INDEX (Slot "SLOT") Unread) for a slot this
; module does not read; or (Item INDEX (Slot "SLOT") (Read ENCODING "ACTION" FIRST SECOND
; (Provenance BELIEF CLUSTER EVENT DOMAIN) "DIGEST")), where ENCODING is stv or ec, FIRST and SECOND
; are the STV strength and confidence or the EC support and opposition, each provenance field is a
; string or None, and DIGEST is the host's digest of the item's content. REQUEST-DIGEST is the
; host's digest of the request text, in the same form. The host has already checked the types,
; decoded the atom and required every number to be finite.
;
; A disposition is (Disposition INDEX STATUS REASON IDENTITY DETAIL), one per item in index order,
; DETAIL being an admitted item's (Fused (Evidence POSITIVE NEGATIVE) (Opinion STRENGTH
; CONFIDENCE)), a duplicate's representative index, or None. Every item is accounted for, so
; nothing a caller sends vanishes without a reason.
; am[implements a-ev-mr-memory@8da5fe] am[addresses i-ev-memory-dropped-silently@e6ebd2]
; am[addresses i-ev-dedup-identity-gaps@4f9730] am[rests-on c-integrate-user-metta-policy-1016@9eb3d0]
; am[implements a-ev-wt-policy-1017@3df281]
;
; The three entries Python calls declare their types, as goal_chainer.runtime.evaluator requires:
; the items and candidates Atom so hole data stays inert, the request digest String.
; am[implements a-rt-rb-migrate-evidence-1018@4fa74b] am[rests-on c-ev-rb-precise-param-types-1018@6b8293]

!(import! &self (library lib_functional))

; The two slots PR 2's petta-memory handoff cache stamps on acceptability evidence; every other
; slot belongs to another consumer of the cache.
(: gc-memory-slots (-> Expression))
(= (gc-memory-slots)
   (("acceptability-belief-evidence" stv) ("contextual-appraisal-evidence" ec)))

; Evidence weight w reads as confidence w / (w + 2), the convention PR 2 and SNARS share, so an STV
; opinion carries w = 2c / (1 - c) units split by its strength and an EC packet its counts as given.
; am[rests-on c-ev-evidence-weight-k2@54cc87]
(= (gc-memory-horizon) 2.0)
(= (gc-memory-counts stv $strength $confidence)
   (let $weight (/ (* (gc-memory-horizon) $confidence) (- 1.0 $confidence))
     (Evidence (* $strength $weight) (* (- 1.0 $strength) $weight))))
(= (gc-memory-counts ec $support $opposition) (Evidence $support $opposition))
(= (gc-memory-weight (Evidence $positive $negative)) (+ $positive $negative))
(= (gc-memory-confidence $counts)
   (let $weight (gc-memory-weight $counts) (/ $weight (+ $weight (gc-memory-horizon)))))
(= (gc-memory-opinion (Evidence $positive $negative))
   (Opinion (/ $positive (+ $positive $negative)) (gc-memory-confidence (Evidence $positive $negative))))

; A strength is a probability; a confidence of 1 would claim unbounded evidence, which recalled
; testimony never has; counts are never negative. Ordering operators only: == tells 1.0 from 1.
; am[rests-on c-ev-metta-eq-identity@fe37ed]
(= (gc-memory-violation stv $strength $confidence)
   (if (or (< $strength 0.0) (> $strength 1.0))
       StrengthOutOfRange
       (if (or (< $confidence 0.0) (>= $confidence 1.0)) ConfidenceOutOfRange Valid)))
(= (gc-memory-violation ec $support $opposition)
   (if (or (< $support 0.0) (< $opposition 0.0)) NegativeCount Valid))

; Whose evidence an item is: its promoted belief, else the promotion that produced it, else its
; content, so copies of one belief are one piece of evidence however often the cache emits them.
(= (gc-memory-identity (Provenance $belief $cluster $event $domain) $digest)
   (if (not (== $belief None))
       (Identity belief (Values $belief))
       (if (and (not (== $cluster None)) (not (== $event None)))
           (Identity promotion (Values $cluster $event))
           (Identity content (Values $digest)))))

(= (gc-memory-read? (Item $index NoSlot)) False)
(= (gc-memory-read? (Item $index BlankText)) False)
(= (gc-memory-read? (Item $index (Text $digest))) False)
(= (gc-memory-read? (Item $index $slot Unread)) False)
(= (gc-memory-read? (Item $index $slot (Read $encoding $action $first $second $provenance $digest))) True)
(= (gc-memory-index (Item $index $form)) $index)
(= (gc-memory-index (Item $index $slot $content)) $index)
(= (gc-memory-action (Item $index $slot (Read $encoding $action $first $second $provenance $digest))) $action)
(= (gc-memory-item-identity (Item $index $slot (Read $encoding $action $first $second $provenance $digest)))
   (gc-memory-identity $provenance $digest))
(= (gc-memory-item-counts (Item $index $slot (Read $encoding $action $first $second $provenance $digest)))
   (gc-memory-counts $encoding $first $second))

(= (gc-memory-item-violation (Item $index $slot (Read $encoding $action $first $second $provenance $digest)))
   (let $violation (gc-memory-violation $encoding $first $second)
     (if (== $violation Valid) Valid (Rejected $violation (Index $index) None))))

; One identity naming two actions is malformed: it would fuse one piece of evidence into two
; statements. Checked over every read item, candidates or not; the detail names each action with
; the first item that carries it.
(= (gc-memory-identity-conflict ($identity $members))
   (let $actions (unique-atom (map-atom $members $member (gc-memory-action $member)))
     (if (> (size-atom $actions) 1)
         (Rejected IdentityNamesTwoActions $identity
                   (Conflict $actions
                             (map-atom $actions $action
                               (gc-memory-index
                                 (car-atom (filter-atom $members $member (== (gc-memory-action $member) $action)))))))
         Valid)))

; PR 2's representative rule: the direct STV value first, then the most conservative confidence,
; then the earliest item, which makes the choice total.
(= (gc-memory-encoding-rank stv) 0)
(= (gc-memory-encoding-rank ec) 1)
(= (gc-memory-representative-key (Item $index $slot (Read $encoding $action $first $second $provenance $digest)))
   (Key (gc-memory-encoding-rank $encoding)
        (gc-memory-confidence (gc-memory-counts $encoding $first $second))
        $index))

(= (gc-memory-fusable? $item $candidates)
   (and (is-member (gc-memory-action $item) $candidates)
        (> (gc-memory-weight (gc-memory-item-counts $item)) 0.0)))

; Time: g group lookups per fusable item, g = distinct identities. Space: the groups.
(= (gc-memory-representative $identity $groups)
   (let $group (car-atom (filter-atom $groups $candidate (== (index-atom $candidate 0) $identity)))
     (gc-memory-index (car-atom (sort-by gc-memory-representative-key (index-atom $group 1))))))

; A memory text carries no slot. It is read as part of the request's own context, because
; nothing WMTM hands over makes it independent of the request (c-ev-wmtm-provenance-1017).
; Its identity is its content, which only removes copies and implies no independence: the first
; item with a digest is the one read, a later one is a duplicate of it, and a copy of the request is
; a duplicate of the request, which is read already. A blank text says nothing. An item's sti,
; WMTM's attention value, weighs nothing (c-ev-sti-is-attention-1017).
; am[implements a-ev-wt-policy-1017@3df281] am[rests-on c-ev-wmtm-provenance-1017@b5f425]
; am[rests-on c-ev-sti-is-attention-1017@b09ea3] am[rests-on c-ev-wmtm-holds-request-text-1017@37c7c3]
(= (gc-memory-text? (Item $index (Text $digest))) True)
(= (gc-memory-text? (Item $index NoSlot)) False)
(= (gc-memory-text? (Item $index BlankText)) False)
(= (gc-memory-text? (Item $index $slot $content)) False)
(= (gc-memory-text-digest (Item $index (Text $digest))) $digest)

; The reader failures that leave a memory text unread, and so deny authorization, rather than fail
; the decision: not_cached and refused describe the text or its replay cache, while every other
; reason names a failed service (c-ev-missing-answer-reasons-1017), which the decision reports as
; its own typed error. The parent ruled so (c-ev-ruling-omission-1017).
; am[implements a-ev-wt-omission-1017@4177f4] am[rests-on c-ev-missing-answer-reasons-1017@e499af]
(: gc-memory-text-omissions (-> Expression))
(= (gc-memory-text-omissions) (not_cached refused))

(= (gc-memory-disposition (Item $index NoSlot) $groups $candidates $texts $request)
   (Disposition $index ignored NoGoalChainerSlot None None))
(= (gc-memory-disposition (Item $index BlankText) $groups $candidates $texts $request)
   (Disposition $index empty BlankText None None))
(= (gc-memory-disposition (Item $index (Text $digest)) $groups $candidates $texts $request)
   (let $identity (Identity content (Values $digest))
     (if (== $digest $request)
         (Disposition $index duplicate SameAsRequest $identity None)
         (let $first (gc-memory-index
                       (car-atom (filter-atom $texts $text (== (gc-memory-text-digest $text) $digest))))
           (if (== $first $index)
               (Disposition $index text ContextText $identity None)
               (Disposition $index duplicate SameIdentity $identity $first))))))
(= (gc-memory-disposition (Item $index $slot Unread) $groups $candidates $texts $request)
   (Disposition $index ignored SlotNotConsumed None None))
(= (gc-memory-disposition (Item $index $slot (Read $encoding $action $first $second $provenance $digest)) $groups $candidates $texts $request)
   (let* (($identity (gc-memory-identity $provenance $digest))
          ($counts (gc-memory-counts $encoding $first $second)))
     (if (not (is-member $action $candidates))
         (Disposition $index ignored NotACandidateAction $identity None)
         (if (<= (gc-memory-weight $counts) 0.0)
             (Disposition $index empty ZeroEvidence $identity None)
             (let $representative (gc-memory-representative $identity $groups)
               (if (== $representative $index)
                   (Disposition $index admitted Admitted $identity (Fused $counts (gc-memory-opinion $counts)))
                   (Disposition $index duplicate SameIdentity $identity $representative)))))))

; Time: n range checks, then grouping n read items by identity (n * g key comparisons), then one
; disposition per item, a text's against the t texts. Space: n items and their groups.
; am[implements a-ev-wt-policy-1017@3df281]
(: gc-memory-admit (-> Atom Atom String Expression))
(= (gc-memory-admit $items $candidates $request)
   (let* (($read (filter-atom $items $item (gc-memory-read? $item)))
          ($violations (filter-atom (map-atom $read $item (gc-memory-item-violation $item))
                                    $violation (not (== $violation Valid)))))
     (if (not (== $violations ()))
         (goalchainer-memory-v1 admit rejected (car-atom $violations))
         (let $conflicts (filter-atom (map-atom (group-by gc-memory-item-identity $read) $group
                                                (gc-memory-identity-conflict $group))
                                      $conflict (not (== $conflict Valid)))
           (if (not (== $conflicts ()))
               (goalchainer-memory-v1 admit rejected (car-atom $conflicts))
               (let* (($groups (group-by gc-memory-item-identity
                                 (filter-atom $read $item (gc-memory-fusable? $item $candidates))))
                      ($texts (filter-atom $items $item (gc-memory-text? $item))))
                 (goalchainer-memory-v1 admit ok
                   (map-atom $items $item (gc-memory-disposition $item $groups $candidates $texts $request)))))))))
