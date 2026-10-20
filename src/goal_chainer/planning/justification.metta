; Purpose: GoalChainer's justification kernel: from one immutable snapshot of evidence rows it
; computes, query-locally, which claims are accepted, refuted, undecided or unsupported, which
; are checked by an establishing observation, and which support rows hold, after AgenticMind's
; grounded acceptance, well-founded support and link withdrawal.
;
;   (gc-justify (At AS-OF) (ROW ...))
;     -> (Justification (Label REF STATUS CHECK) ... (Link (Row ROW) STATE) ...)
;      | (Refused (Problem KIND DETAIL) ...)
;   (gc-justify-frame (Frame (ARG ...) (SUPPORT ...) (ATTACK ...) (UNDERCUT ...) (ARG ...)))
;     -> (Justification (Label ARG STATUS CHECK) ... (Link LINK STATE) ...) | (Refused ...)
;   (gc-justification-knowledge LITERAL JUSTIFICATION) -> (Known True CHECK) | (Known False CHECK) | Unknown
;
; A ROW is (From CLAIM SOURCE) or (Withdrawn (From CLAIM SOURCE) REASON). A CLAIM is any ground
; literal L or (Not L), whatever its spelling. Every other argument is named by its category, in
; one reference vocabulary that rows and answers share:
;
;   REF ::= (Claim CLAIM) | (Observation OBS) | (Row ROW) | (Stated TERM)
;
; A SOURCE is (Observation OBS), an observation (KIND ID ESTIMATOR VALIDITY) with ESTIMATOR one of
; the shared vocabulary's (gc-estimator-classes) and VALIDITY Forever or (Until MICROSECONDS), or
; (Claim CLAIM), the claim of another From row, which chains support. A REASON is any REF: a
; claim, observation or row, whose standing decides the withdrawal, or (Stated TERM), a reason the
; caller states, such as (Stated (Moved "domain")) from a freshness check, which always stands. A
; term's role is what the caller wrote, never what else the snapshot happens to hold, so adding a
; row never reinterprets an existing source or reason (c-jk-source-role-by-membership-1018,
; c-jk-reason-role-by-membership-1018). A (Claim CLAIM) that no row claims is refused as
; DanglingClaim and a (Row ROW) that is no From row of the snapshot as DanglingRow. AS-OF is
; microseconds since the epoch, as (gc-reading-expired) reads it.
; A snapshot's answer labels every argument by its REF and gives each From row's Link, keyed by
; (Row ROW), the state of the row's support of its claim alone; a frame's answer labels every
; argument and gives every declared link its state. STATUS is Accepted, Refuted, Undecided or
; Unsupported, CHECK Checked or Unchecked, STATE Holds, Withdrawn or Undecided. Every list in an
; answer is in sort-atom order, so equal snapshots answer identical terms whatever order their rows
; came in.
;
; Inside, the REFs are the argument identities, and the kernel adds only its own beside them: the
; stale reason (Stale AS-OF) and the links (Infers ROW), (Premise ROW), (Rebut ROW ROW) and
; (Refute ROW). So no caller term, whatever its spelling, equals the kernel's bookkeeping, such as
; the stale reason that undercuts an expired row (c-integrate-jk-expiry-collision-measured-1018),
; and two categories never merge: a claim spelled like a row stands beside that row
; (c-jk-audit-claim-row-merge-1018). The answer leaves the kernel's own identities out.
; am[implements a-jk-id-tagged-1018@d1757d] am[implements a-jk-typed-boundary-1018@dee690]
; am[implements a-integrate-jk-categorical-boundary-1018@254af6]
; am[rests-on c-integrate-jk-expiry-collision-measured-1018@28be23] am[rests-on c-jk-audit-claim-row-merge-1018@428597]
; am[rests-on c-jk-source-role-by-membership-1018@41c6a1] am[rests-on c-jk-reason-role-by-membership-1018@19aaa7]
; am[rests-on c-jk-audit-link-ids-disjoint-1018@b4db9d]
;
; The entries take their arguments unevaluated, typed Atom: data whose head names a function, such
; as a Statement literal's (sn ...) tree, would otherwise run at the call (c-jk-atom-entry-inert-1018),
; and nothing inside re-evaluates it. A variable inside the data would unify with any claim in
; is-member (c-jk-variables-unify-1018), so a non-ground row is refused before anything reads it.
; am[implements a-jk-metta-kernel-1018@258f74] am[implements a-jk-contract-literal-rows-1018@5a7264]
; am[rests-on c-jk-atom-entry-inert-1018@63e37f] am[rests-on c-jk-variables-unify-1018@097cd2]

; --- the abstract frame: AgenticMind's argument layer ------------------------------------------
;
; A frame names every argument, every support and attack link (Support LINK FROM TO) and
; (Attack LINK FROM TO), each undercut (Undercut LINK REASON) and the arguments carrying an
; establishing evidence kind. Its semantics is the well-founded model of these rules, one per
; rule of AgenticMind f168fa5 the kernel ports:
;
;   holds(l)     l is not undercut                                      rules.lp edge_holds
;   undercut(l)  a reason r of l is accepted and founded                rules.lp edge_undercut
;   accepted(a)  every attack (l b a) has b defeated or l not holding   grounded.lp accepted_argument
;   defeated(a)  some attack (l b a) has b accepted and l holding       grounded.lp defeated_argument
;   founded(a)   a is not defeated, and nothing supports a or some
;                support (l s a) holds with s accepted and founded      claim.lp well_founded
;
; The attack universe is fixed by the declarations, so accepted reads every declared attack, and
; only a link's holding moves; founded is positive recursion, so a support cycle with no founded
; entry founds nothing. The rules negate undercut, holds and defeated, so the well-founded model is
; Van Gelder's alternating fixpoint over those three: from no assumption, the least closure with
; each negation read against the other bound, alternately, until the lower bound stops growing.
; An attack answered because its link does not hold is read as not holds, never as undercut: the
; double negation does not cancel in the well-founded model, and collapsing it decided an undercut
; that protects its own reason as Refuted where AgenticMind leaves it undecided
; (c-jk-double-negation-kept-1018).
; A cycle through negation, such as an undercut protecting its own reason, is left undecided in
; both bounds rather than settled either way: AgenticMind's stable models answer two models or
; none there (c-jk-dynamic-link-models-1018), and its own engine reads them undecided
; (c-jk-am-wfs-reading-1018).
; am[implements a-jk-semantics-1018@8cb82d] am[rests-on c-jk-am-wfs-reading-1018@a6fd08]
; am[rests-on c-jk-dynamic-link-models-1018@37385c] am[rests-on c-jk-double-negation-kept-1018@501361]

(: gc-justify-frame (-> Atom Expression))
(= (gc-justify-frame $frame)
   (let $problems (gc-justification-frame-problems $frame)
     (if (== $problems ())
         (gc-justification-answer (gc-justification-labelled $frame))
         (gc-justification-refused $problems))))

(= (gc-justification-answer (Labelled $labels $links))
   (cons-atom Justification (sort-atom (append $labels $links))))

(= (gc-justification-refused $problems) (cons-atom Refused (sort-atom (unique-atom $problems))))

(= (gc-justification-frame-arguments (Frame $arguments $supports $attacks $undercuts $established)) $arguments)
(= (gc-justification-frame-supports (Frame $arguments $supports $attacks $undercuts $established)) $supports)
(= (gc-justification-frame-attacks (Frame $arguments $supports $attacks $undercuts $established)) $attacks)
(= (gc-justification-frame-undercuts (Frame $arguments $supports $attacks $undercuts $established)) $undercuts)
(= (gc-justification-frame-established (Frame $arguments $supports $attacks $undercuts $established)) $established)

(= (gc-justification-link-id (Support $link $from $to)) $link)
(= (gc-justification-link-id (Attack $link $from $to)) $link)
(= (gc-justification-link-from (Support $link $from $to)) $from)
(= (gc-justification-link-from (Attack $link $from $to)) $from)
(= (gc-justification-link-to (Support $link $from $to)) $to)
(= (gc-justification-link-to (Attack $link $from $to)) $to)
(= (gc-justification-cut-link (Undercut $link $reason)) $link)
(= (gc-justification-cut-reason (Undercut $link $reason)) $reason)

; (HEAD X ...) with exactly ARITY arguments; anything else, a symbol or number included, is not.
(= (gc-justification-shaped $term $head $arity)
   (if (== (get-metatype $term) Expression)
       (if (== (size-atom $term) (+ $arity 1)) (== (car-atom $term) $head) False)
       False))

(= (gc-justification-is-list $term) (== (get-metatype $term) Expression))
; get-type types the atom it is given without evaluating it, so a value is bound before it is typed.
(= (gc-justification-typed $value $type) (== (get-type $value) $type))
(= (gc-justification-all $flags) (foldl-atom $flags True $acc $flag (and $acc $flag)))
(= (gc-justification-any $flags) (foldl-atom $flags False $acc $flag (or $acc $flag)))
(= (gc-justification-flatten $lists) (foldl-atom $lists () $acc $list (append $acc $list)))

; A frame is acceptable when it is ground, every link names declared arguments, no link id names
; two links, every undercut names a declared link and every established argument is declared.
; Time: (n + l)^2 membership tests, n = arguments, l = links and undercuts.
(= (gc-justification-frame-problems $frame)
   (if (not (gc-justification-shaped $frame Frame 5))
       ((Problem MalformedFrame $frame))
       (if (not (is-ground $frame))
           ((Problem NonGround $frame))
           (if (not (gc-justification-all (map-atom (cdr-atom $frame) $part (gc-justification-is-list $part))))
               ((Problem MalformedFrame $frame))
               (gc-justification-frame-member-problems
                 (gc-justification-frame-arguments $frame)
                 (gc-justification-frame-supports $frame)
                 (gc-justification-frame-attacks $frame)
                 (gc-justification-frame-undercuts $frame)
                 (gc-justification-frame-established $frame))))))

(= (gc-justification-frame-member-problems $arguments $supports $attacks $undercuts $established)
   (let* (($bad-supports (filter-atom $supports $s (not (gc-justification-shaped $s Support 3))))
          ($bad-attacks (filter-atom $attacks $a (not (gc-justification-shaped $a Attack 3))))
          ($bad-cuts (filter-atom $undercuts $u (not (gc-justification-shaped $u Undercut 2)))))
     (if (== (append $bad-supports (append $bad-attacks $bad-cuts)) ())
         (gc-justification-frame-link-problems $arguments (append $supports $attacks) $undercuts $established)
         (map-atom (append $bad-supports (append $bad-attacks $bad-cuts)) $bad (Problem MalformedLink $bad)))))

(= (gc-justification-frame-link-problems $arguments $links $undercuts $established)
   (let* (($ids (map-atom $links $l (gc-justification-link-id $l)))
          ($dangling (filter-atom $links $k
                        (not (and (is-member (gc-justification-link-from $k) $arguments)
                                  (is-member (gc-justification-link-to $k) $arguments)))))
          ($repeated (filter-atom (unique-atom $ids) $i
                        (> (size-atom (filter-atom $ids $j (== $j $i))) 1)))
          ($stray-cuts (filter-atom $undercuts $u
                          (not (and (is-member (gc-justification-cut-link $u) $ids)
                                    (is-member (gc-justification-cut-reason $u) $arguments)))))
          ($stray-established (filter-atom $established $e (not (is-member $e $arguments)))))
     (gc-justification-flatten
       ((map-atom $dangling $d (Problem DanglingLink $d))
        (map-atom $repeated $r (Problem RepeatedLink $r))
        (map-atom $stray-cuts $c (Problem DanglingUndercut $c))
        (map-atom $stray-established $x (Problem UndeclaredEstablished $x))))))

; Each argument's incoming attacks and supports as (In LINK FROM), indexed once, so a closure step
; reads only the links into each argument. Time: n * l comparisons, n = arguments, l = links.
(= (gc-justification-index $arguments $supports $attacks)
   (map-atom $arguments $a
     (Entry $a
       (map-atom (filter-atom $attacks $k (== (gc-justification-link-to $k) $a)) $k2
         (In (gc-justification-link-id $k2) (gc-justification-link-from $k2)))
       (map-atom (filter-atom $supports $s (== (gc-justification-link-to $s) $a)) $s2
         (In (gc-justification-link-id $s2) (gc-justification-link-from $s2))))))

(= (gc-justification-entry-argument (Entry $argument $attacks $supporters)) $argument)
(= (gc-justification-entry-attacks (Entry $argument $attacks $supporters)) $attacks)
(= (gc-justification-entry-supporters (Entry $argument $attacks $supporters)) $supporters)

; Each undercut link with every reason given against it. Time: u^2 comparisons, u = undercuts.
(= (gc-justification-cut-index $undercuts)
   (map-atom (unique-atom (map-atom $undercuts $u (gc-justification-cut-link $u))) $l
     (Cut $l (map-atom (filter-atom $undercuts $v (== (gc-justification-cut-link $v) $l)) $w
               (gc-justification-cut-reason $w)))))

(= (gc-justification-cut-of (Cut $link $reasons)) $link)
(= (gc-justification-cut-reasons (Cut $link $reasons)) $reasons)

(= (gc-justification-state-accepted (State $accepted $defeated $founded $undercut $holding)) $accepted)
(= (gc-justification-state-defeated (State $accepted $defeated $founded $undercut $holding)) $defeated)
(= (gc-justification-state-founded (State $accepted $defeated $founded $undercut $holding)) $founded)
(= (gc-justification-state-undercut (State $accepted $defeated $founded $undercut $holding)) $undercut)
(= (gc-justification-state-holding (State $accepted $defeated $founded $undercut $holding)) $holding)

(= (gc-justification-state-size (State $accepted $defeated $founded $undercut $holding))
   (+ (+ (+ (size-atom $accepted) (size-atom $defeated)) (+ (size-atom $founded) (size-atom $undercut)))
      (size-atom $holding)))

; One step of the least closure with the negations read against the other bound: CUT and BEATEN
; are its undercut and defeated sets and HELD its holding set, while HOLDING, the links CUT leaves,
; is this closure's own. Every set only grows from the empty state, so a step that adds nothing is
; the fixpoint, and equal sizes say so.
; Time per step: one membership test per incoming link and per undercut reason, each linear in the
; set it reads.
(= (gc-justification-step $index $cuts $cut $beaten $held (State $accepted $defeated $founded $undercut $holding))
   (let* (($accepted2 (map-atom (filter-atom $index $e (gc-justification-answered $e $defeated $held)) $e2
                         (gc-justification-entry-argument $e2)))
          ($defeated2 (map-atom (filter-atom $index $f (gc-justification-beaten $f $accepted $cut)) $f2
                         (gc-justification-entry-argument $f2)))
          ($founded2 (map-atom (filter-atom $index $g (gc-justification-founds $g $accepted $founded $cut $beaten)) $g2
                        (gc-justification-entry-argument $g2)))
          ($undercut2 (map-atom (filter-atom $cuts $c (gc-justification-cut-stands $c $accepted $founded)) $c2
                         (gc-justification-cut-of $c2))))
     (State $accepted2 $defeated2 $founded2 $undercut2 $holding)))

(= (gc-justification-answered (Entry $argument $attacks $supporters) $defeated $held)
   (gc-justification-all (map-atom $attacks $k (gc-justification-attack-answered $k $defeated $held))))
(= (gc-justification-attack-answered (In $link $from) $defeated $held)
   (or (is-member $from $defeated) (not (is-member $link $held))))

(= (gc-justification-beaten (Entry $argument $attacks $supporters) $accepted $cut)
   (gc-justification-any (map-atom $attacks $k (gc-justification-attack-lands $k $accepted $cut))))
(= (gc-justification-attack-lands (In $link $from) $accepted $cut)
   (and (is-member $from $accepted) (not (is-member $link $cut))))

(= (gc-justification-founds (Entry $argument $attacks $supporters) $accepted $founded $cut $beaten)
   (if (is-member $argument $beaten)
       False
       (if (== $supporters ())
           True
           (gc-justification-any (map-atom $supporters $s (gc-justification-holds-up $s $accepted $founded $cut))))))
(= (gc-justification-holds-up (In $link $from) $accepted $founded $cut)
   (if (is-member $link $cut) False (and (is-member $from $accepted) (is-member $from $founded))))

(= (gc-justification-cut-stands (Cut $link $reasons) $accepted $founded)
   (gc-justification-any (map-atom $reasons $r (and (is-member $r $accepted) (is-member $r $founded)))))

; The least model of the rules with the negations fixed by the other bound, ASSUMED.
; Time: at most n + l + 1 steps, n = arguments, l = links.
(= (gc-justification-closure $index $cuts $links $assumed)
   (let* (($cut (gc-justification-state-undercut $assumed))
          ($holding (filter-atom $links $l (not (is-member $l $cut)))))
     (gc-justification-close $index $cuts $cut (gc-justification-state-defeated $assumed)
       (gc-justification-state-holding $assumed) (State () () () () $holding))))
(= (gc-justification-close $index $cuts $cut $beaten $held $state)
   (let $next (gc-justification-step $index $cuts $cut $beaten $held $state)
     (if (== (gc-justification-state-size $next) (gc-justification-state-size $state))
         $state
         (gc-justification-close $index $cuts $cut $beaten $held $next))))

; The alternating fixpoint: TRUE starts empty and grows; POSSIBLE is the closure read against it.
; [source: Van Gelder, "The alternating fixpoint of logic programs with negation", JCSS 47(1),
;  1993; c-jk-reference-equals-am-1018 checks the same construction against AgenticMind]
; Time: at most n + l + 1 rounds of two closures.
(= (gc-justification-model $index $cuts $links)
   (gc-justification-alternate $index $cuts $links (State () () () () ())))
(= (gc-justification-alternate $index $cuts $links $true)
   (let* (($possible (gc-justification-closure $index $cuts $links $true))
          ($refined (gc-justification-closure $index $cuts $links $possible)))
     (if (== (gc-justification-state-size $refined) (gc-justification-state-size $true))
         (Model $true $possible)
         (gc-justification-alternate $index $cuts $links $refined))))

; --- labels ----------------------------------------------------------------------------------
;
; Refuted when definitely defeated, Accepted when definitely accepted and founded, Unsupported
; when grounds were offered and none reaches a founded entry even through supporters that are
; only undecided, and Undecided otherwise: in a conflict, or resting on contested grounds. The
; last split refines AgenticMind's unsupported, which reads contested grounds as lost too,
; because GoalChainer keeps conflicted apart from unknown (c-jk-contested-not-lost-1018).
; Checked follows claim.lp's verified and checked: not refuted, and established and standing
; itself, or held up through a link that certainly holds by a standing established supporter.
; Checked is provenance; a SNARS opinion or a model-proposed reading never makes it.
; am[implements a-jk-semantics-1018@8cb82d] am[rests-on c-jk-contested-not-lost-1018@34e299]
; am[rests-on c-jk-gc-evidence-contract-1018@0bac2c]
; A frame's arguments and establishing tags are sets, as a snapshot's rows are, so one listed twice
; is labelled or tagged once. pymetta's is-member answers once per occurrence, so a tag listed twice
; once doubled every answer that tested membership in the tags (c-jk-frame-established-repeat-1018).
; am[implements a-jk-frame-sets-1018@390a56] am[addresses i-jk-frame-established-repeat-1018@ae0089]
; am[rests-on c-ev-pk-is-member-per-occurrence-1018@c8243c]
(= (gc-justification-labelled $frame)
   (let* (($arguments (unique-atom (gc-justification-frame-arguments $frame)))
          ($supports (gc-justification-frame-supports $frame))
          ($attacks (gc-justification-frame-attacks $frame))
          ($established (unique-atom (gc-justification-frame-established $frame)))
          ($index (gc-justification-index $arguments $supports $attacks))
          ($cuts (gc-justification-cut-index (gc-justification-frame-undercuts $frame)))
          ($links (append $supports $attacks))
          ($model (gc-justification-model $index $cuts (map-atom $links $l (gc-justification-link-id $l)))))
     (gc-justification-label-model $index $established $links $model)))

(= (gc-justification-label-model $index $established $links (Model $true $possible))
   (let* (($in (gc-justification-state-accepted $true))
          ($out (gc-justification-state-defeated $true))
          ($founded (gc-justification-state-founded $true))
          ($surely-cut (gc-justification-state-undercut $true))
          ($maybe-cut (gc-justification-state-undercut $possible))
          ($maybe-founded (gc-justification-possibly-founded $index $out $surely-cut ()))
          ($standing (filter-atom $established $e (and (is-member $e $in) (is-member $e $founded)))))
     (Labelled
       (map-atom $index $entry
         (gc-justification-label $entry $in $out $founded $maybe-founded $standing $maybe-cut))
       (map-atom $links $link
         (Link (gc-justification-link-id $link)
               (gc-justification-link-state (gc-justification-link-id $link) $surely-cut $maybe-cut))))))

; Founded through links that may hold and supporters that are not refuted: the least closure,
; so a support cycle with no founded entry stays out. Time: at most n steps over the index.
(= (gc-justification-possibly-founded $index $out $surely-cut $found)
   (let $next (map-atom (filter-atom $index $e (gc-justification-may-found $e $out $surely-cut $found)) $e2
                (gc-justification-entry-argument $e2))
     (if (== (size-atom $next) (size-atom $found))
         $found
         (gc-justification-possibly-founded $index $out $surely-cut $next))))
(= (gc-justification-may-found (Entry $argument $attacks $supporters) $out $surely-cut $found)
   (if (is-member $argument $out)
       False
       (if (== $supporters ())
           True
           (gc-justification-any (map-atom $supporters $s (gc-justification-may-hold-up $s $out $surely-cut $found))))))
(= (gc-justification-may-hold-up (In $link $from) $out $surely-cut $found)
   (if (is-member $link $surely-cut) False (and (not (is-member $from $out)) (is-member $from $found))))

(= (gc-justification-label (Entry $argument $attacks $supporters) $in $out $founded $maybe-founded $standing $maybe-cut)
   (Label $argument
          (gc-justification-status $argument $supporters $in $out $founded $maybe-founded)
          (gc-justification-check $argument $supporters $out $standing $maybe-cut)))

(= (gc-justification-status $argument $supporters $in $out $founded $maybe-founded)
   (if (is-member $argument $out)
       Refuted
       (if (and (is-member $argument $in) (is-member $argument $founded))
           Accepted
           (if (and (not (== $supporters ())) (not (is-member $argument $maybe-founded)))
               Unsupported
               Undecided))))

(= (gc-justification-check $argument $supporters $out $standing $maybe-cut)
   (if (is-member $argument $out)
       Unchecked
       (if (is-member $argument $standing)
           Checked
           (if (gc-justification-any (map-atom $supporters $s (gc-justification-checks $s $standing $maybe-cut)))
               Checked
               Unchecked))))
(= (gc-justification-checks (In $link $from) $standing $maybe-cut)
   (and (is-member $from $standing) (not (is-member $link $maybe-cut))))

(= (gc-justification-link-state $link $surely-cut $maybe-cut)
   (if (is-member $link $maybe-cut)
       (if (is-member $link $surely-cut) Withdrawn Undecided)
       Holds))

; --- evidence rows ---------------------------------------------------------------------------
;
; Each From row is an argument of its own, premised on its source and supporting its claim, so a
; contrary reading rebuts the inference from source to claim and leaves the source's other claims
; alone (c-jk-rows-as-arguments-1018). Rows for contrary claims rebut each other when the
; attacker's tier is at least the target's, which is ASPIC+'s defeat for an attack a preference
; decides. An observation's tier is the one the shared vocabulary declares for its estimator class
; (gc-estimator-tier), and a row whose source is (Claim CLAIM) carries no class and ranks at the
; lowest declared tier (gc-lowest-estimator-tier). An establishing row, one whose class
; establishes (gc-establishes), also refutes the contrary claim. So two readings of one tier
; conflict, both left undecided rather than voted on, and an establishing reading is preferred
; over a model-relative contrary (c-jk-gc-evidence-contract-1018). That preference is
; GoalChainer's adopted defeasible source preference: it decides which reading a caller proceeds
; on, not that a measurement is true, and withdrawing or outliving the preferred reading
; reinstates its contrary. A withdrawal, or an observation past its validity
; (gc-reading-expired), undercuts every link the row speaks through whatever its tier: the claim
; loses that ground toward unknown and is not refuted. Accepted is an epistemic label and grants
; no authority, permission or promotion. The estimator classes, their tiers, the establishing cut
; and expiry have one home, the shared vocabulary module below relevance and the kernel, which
; the kernel calls and never copies.
; am[implements a-jk-contract-literal-rows-1018@5a7264] am[rests-on c-jk-rows-as-arguments-1018@57a47d]
; am[rests-on c-jk-claim-unit-literal-1018@1dd3c5] am[rests-on c-jk-literal-contrary-rows-1018@3e2d84]
; am[implements a-jk-rr-kernel-shared-1018@0d101b] am[rests-on c-integrate-reading-owner-rule-1018@9de720]
; am[rests-on c-jk-aspic-defeat-preference-1018@f2a246]

(: gc-justify (-> Atom Atom Expression))
(= (gc-justify $at $rows)
   (let $problems (gc-justification-snapshot-problems $at $rows)
     (if (== $problems ())
         (gc-justification-rows (gc-justification-as-of $at) (unique-atom $rows))
         (gc-justification-refused $problems))))

(= (gc-justification-as-of (At $moment)) $moment)

(= (gc-justification-snapshot-problems $at $rows)
   (if (not (gc-justification-shaped $at At 1))
       ((Problem MalformedTime $at))
       (if (not (gc-justification-typed (gc-justification-as-of $at) Number))
           ((Problem MalformedTime $at))
           (if (not (gc-justification-is-list $rows))
               ((Problem MalformedRows $rows))
               (let $shape (gc-justification-flatten (map-atom $rows $r (gc-justification-row-problems $r)))
                 (if (== $shape ()) (gc-justification-reference-problems (unique-atom $rows)) $shape))))))

(= (gc-justification-row-problems $row)
   (if (not (is-ground $row))
       ((Problem NonGround $row))
       (if (gc-justification-shaped $row From 2)
           (append (gc-justification-claim-problems (gc-justification-claim $row))
                   (gc-justification-source-problems (gc-justification-source $row)))
           (if (gc-justification-shaped $row Withdrawn 2)
               (if (gc-justification-shaped (gc-justification-withdrawn-row $row) From 2)
                   (gc-justification-reason-problems (gc-justification-withdrawn-reason $row))
                   ((Problem MalformedRow $row)))
               ((Problem MalformedRow $row))))))

(= (gc-justification-claim-problems $claim)
   (if (gc-justification-shaped $claim Not 1)
       (if (gc-justification-shaped (gc-justification-negated $claim) Not 1) ((Problem DoubleNegation $claim)) ())
       ()))

; A SOURCE is (Observation OBS) with OBS of the observation shape, or (Claim CLAIM); a REASON is
; any REF, a (Row ROW) one naming a From-shaped row.
; am[implements a-jk-typed-boundary-1018@dee690]
(= (gc-justification-source-problems $source)
   (if (or (gc-justification-shaped $source Claim 1) (gc-justification-observation-reference $source))
       ()
       ((Problem MalformedSource $source))))

(= (gc-justification-reason-problems $reason)
   (if (or (or (gc-justification-shaped $reason Claim 1) (gc-justification-shaped $reason Stated 1))
           (or (gc-justification-observation-reference $reason)
               (if (gc-justification-shaped $reason Row 1) (gc-justification-shaped (index-atom $reason 1) From 2) False)))
       ()
       ((Problem MalformedReason $reason))))

(= (gc-justification-observation-reference $reference)
   (if (gc-justification-shaped $reference Observation 1)
       (gc-justification-observation-shaped (index-atom $reference 1))
       False))

(= (gc-justification-claim (From $claim $source)) $claim)
(= (gc-justification-source (From $claim $source)) $source)
(= (gc-justification-withdrawn-row (Withdrawn $row $reason)) $row)
(= (gc-justification-withdrawn-reason (Withdrawn $row $reason)) $reason)
(= (gc-justification-negated (Not $literal)) $literal)

(= (gc-justification-contrary $claim)
   (if (gc-justification-shaped $claim Not 1) (gc-justification-negated $claim) (Not $claim)))

(= (gc-justification-froms $rows) (filter-atom $rows $r (gc-justification-shaped $r From 2)))
(= (gc-justification-withdrawals $rows) (filter-atom $rows $r (gc-justification-shaped $r Withdrawn 2)))
(= (gc-justification-claims $froms) (unique-atom (map-atom $froms $f (gc-justification-claim $f))))
; Every REF the snapshot's rows write: each source and each withdrawal reason.
(= (gc-justification-references $froms $withdrawals)
   (append (map-atom $froms $f (gc-justification-source $f))
           (map-atom $withdrawals $w (gc-justification-withdrawn-reason $w))))
; The terms the references of one category name, each once.
(= (gc-justification-named $references $category)
   (unique-atom (map-atom (filter-atom $references $r (gc-justification-shaped $r $category 1)) $r2
                  (index-atom $r2 1))))

; A (Claim CLAIM) a source or reason names must be the claim of a From row, a (Row ROW) a reason
; names a From row of the snapshot, and a withdrawal a From row of the snapshot, so no reference
; reaches past the snapshot. A stated reason is the caller's own and never meets a claim, since
; categories keep them apart.
; am[implements a-jk-typed-boundary-1018@dee690]
(= (gc-justification-reference-problems $rows)
   (let* (($froms (gc-justification-froms $rows))
          ($claims (gc-justification-claims $froms))
          ($withdrawals (gc-justification-withdrawals $rows))
          ($references (gc-justification-references $froms $withdrawals))
          ($unclaimed (filter-atom (gc-justification-named $references Claim) $c (not (is-member $c $claims))))
          ($unrowed (filter-atom (gc-justification-named $references Row) $n (not (is-member $n $froms))))
          ($dangling (filter-atom $withdrawals $d (not (is-member (gc-justification-withdrawn-row $d) $froms)))))
     (append (map-atom $unclaimed $x (Problem DanglingClaim (Claim $x)))
             (append (map-atom $unrowed $y (Problem DanglingRow (Row $y)))
                     (map-atom $dangling $z (Problem DanglingWithdrawal $z))))))

(= (gc-justification-observation-shaped $source)
   (if (gc-justification-is-list $source)
       (if (== (size-atom $source) 4)
           (and (gc-justification-known-estimator (index-atom $source 2))
                (gc-justification-validity-shaped (index-atom $source 3)))
           False)
       False))

(= (gc-justification-known-estimator $estimator)
   (if (gc-justification-typed $estimator String) (is-member $estimator (gc-estimator-classes)) False))

(= (gc-justification-validity-shaped $validity)
   (if (== $validity Forever)
       True
       (if (gc-justification-shaped $validity Until 1)
           (gc-justification-typed (index-atom $validity 1) Number)
           False)))

; Each From row with what the compile reads of it: (Record ROW CLAIM SOURCE TIER ESTABLISHING EXPIRED).
(= (gc-justification-row-record $row $as-of)
   (let $source (gc-justification-source $row)
     (if (gc-justification-shaped $source Claim 1)
         (Record $row (gc-justification-claim $row) $source (gc-lowest-estimator-tier) False False)
         (let $observation (index-atom $source 1)
           (let $class (index-atom $observation 2)
             (Record $row (gc-justification-claim $row) $source
                  (gc-estimator-tier $class)
                  (gc-establishes $class)
                  (gc-reading-expired $as-of (index-atom $observation 3))))))))

(= (gc-justification-record-row (Record $row $claim $source $tier $establishing $expired)) $row)
(= (gc-justification-record-claim (Record $row $claim $source $tier $establishing $expired)) $claim)
(= (gc-justification-record-source (Record $row $claim $source $tier $establishing $expired)) $source)
(= (gc-justification-record-tier (Record $row $claim $source $tier $establishing $expired)) $tier)
(= (gc-justification-record-establishing (Record $row $claim $source $tier $establishing $expired)) $establishing)
(= (gc-justification-record-expired (Record $row $claim $source $tier $establishing $expired)) $expired)

; Time: r^2 row comparisons for the contraries and the outgoing links, r = From rows, then the
; frame's own cost. Measured after the warm-up on random snapshots of 12, 25, 50 and 100 rows:
; 0.23, 0.48, 1.1 and 6.6 million inferences, 0.03 to 0.48 seconds
; (ai-tmp/justification/probe/ai-scaling.py, 2026-10-18 04:47).
; The frame names every argument and link by its category, so the stale reason and every link
; identity are the kernel's own and no caller term can equal one.
; am[implements a-jk-rr-row-report-1018@6747d2] am[implements a-jk-id-tagged-1018@d1757d]
(= (gc-justification-rows $as-of $rows)
   (let* (($froms (gc-justification-froms $rows))
          ($withdrawals (gc-justification-withdrawals $rows))
          ($claims (gc-justification-claims $froms))
          ($references (gc-justification-references $froms $withdrawals))
          ($observations (gc-justification-named $references Observation))
          ($stated (gc-justification-named $references Stated))
          ($records (map-atom $froms $f (gc-justification-row-record $f $as-of)))
          ($rebuts (gc-justification-flatten (map-atom $records $r (gc-justification-rebuts $r $records))))
          ($refutes (gc-justification-flatten (map-atom $records $q (gc-justification-refutes $q $claims))))
          ($attacks (append $rebuts $refutes))
          ($stale (Stale $as-of))
          ($expired (filter-atom $records $x (gc-justification-record-expired $x)))
          ($cuts (append
                   (gc-justification-flatten (map-atom $withdrawals $w
                     (gc-justification-cut-row (gc-justification-withdrawn-row $w) (gc-justification-withdrawn-reason $w) $attacks)))
                   (gc-justification-flatten (map-atom $expired $y
                     (gc-justification-cut-row (gc-justification-record-row $y) $stale $attacks)))))
          ($supports (gc-justification-flatten (map-atom $froms $p (gc-justification-row-supports $p))))
          ($established (append (map-atom (filter-atom $observations $o (gc-establishes (index-atom $o 2))) $o2 (Observation $o2))
                                (map-atom (filter-atom $records $t (gc-justification-record-establishing $t)) $t2
                                  (Row (gc-justification-record-row $t2)))))
          ($arguments (append (map-atom $claims $c (Claim $c))
                        (append (map-atom $observations $v (Observation $v))
                          (append (map-atom $froms $g (Row $g))
                            (append (map-atom $stated $z (Stated $z))
                                    (if (== $expired ()) () ($stale)))))))
          ($labelled (gc-justification-labelled (Frame $arguments $supports $attacks $cuts $established))))
     (gc-justification-row-answer $labelled)))

(= (gc-justification-row-supports $row)
   ((Support (Premise $row) (gc-justification-source $row) (Row $row))
    (Support (Infers $row) (Row $row) (Claim (gc-justification-claim $row)))))

(= (gc-justification-rebuts $record $records)
   (map-atom (filter-atom $records $other
               (and (== (gc-justification-record-claim $other) (gc-justification-contrary (gc-justification-record-claim $record)))
                    (not (< (gc-justification-record-tier $record) (gc-justification-record-tier $other)))))
             $target
     (Attack (Rebut (gc-justification-record-row $record) (gc-justification-record-row $target))
             (Row (gc-justification-record-row $record))
             (Row (gc-justification-record-row $target)))))

(= (gc-justification-refutes $record $claims)
   (let $contrary (gc-justification-contrary (gc-justification-record-claim $record))
     (if (and (gc-justification-record-establishing $record) (is-member $contrary $claims))
         ((Attack (Refute (gc-justification-record-row $record))
                  (Row (gc-justification-record-row $record))
                  (Claim $contrary)))
         ())))

; Every link a row speaks through, its support of the claim and each attack it makes, cut by
; REASON, the argument whose standing decides the withdrawal.
(= (gc-justification-cut-row $row $reason $attacks)
   (cons-atom (Undercut (Infers $row) $reason)
     (map-atom (filter-atom $attacks $a (== (gc-justification-link-from $a) (Row $row))) $a2
       (Undercut (gc-justification-link-id $a2) $reason))))

; Each From row is labelled as the argument it is, and its Link is the state of its support of the
; claim alone, Holds, Withdrawn or Undecided. The row's defeat and its link's undercut are apart,
; as ASPIC+ keeps a rebut, which a preference decides, apart from an undercut, which defeats
; whatever the preference: so a current row that lost to a preferred contrary reads Refuted with
; its link holding, while an expired or withdrawn row reads its link Withdrawn. A row grounds its
; claim exactly when its Label is Accepted and its Link Holds.
; Each label keeps its REF and each row's support of its claim is reported under (Row ROW); the
; stale reason and every other link are the kernel's own and stay out, by category and never by
; spelling (c-jk-audit-stale-filter-1018).
; Time: one pass over the n labels and l links.
; am[implements a-jk-rr-row-report-1018@6747d2] am[rests-on c-jk-aspic-defeat-preference-1018@f2a246]
; am[implements a-jk-id-tagged-1018@d1757d] am[rests-on c-jk-audit-stale-filter-1018@314287]
(= (gc-justification-row-answer (Labelled $labels $links))
   (cons-atom Justification
     (sort-atom
       (append (gc-justification-flatten (map-atom $labels $l (gc-justification-public-label $l)))
               (gc-justification-flatten (map-atom $links $k (gc-justification-public-link $k)))))))

(= (gc-justification-public-label (Label $argument $status $check))
   (if (== (car-atom $argument) Stale) () ((Label $argument $status $check))))

(= (gc-justification-public-link (Link $link $state))
   (if (== (car-atom $link) Infers) ((Link (Row (index-atom $link 1)) $state)) ()))

(= (gc-justification-label-argument (Label $argument $status $check)) $argument)
(= (gc-justification-label-status (Label $argument $status $check)) $status)
(= (gc-justification-label-check (Label $argument $status $check)) $check)

; --- knowledge ---------------------------------------------------------------------------------
;
; What the snapshot knows about a literal: True when the literal is accepted, False when its
; contrary is, Unknown otherwise. Silence is never False, so a caller testing an absence asks this
; rather than reading a missing atom as evidence (i-jk-absence-not-evidence-1018); the Unknown
; answer is GoalChainer's settlement vocabulary, nothing observed rather than false.
; It reads (Label (Claim L) ...) and (Label (Claim (Not L)) ...) and nothing else, so a stated
; reason, an observation or a row spelled like the literal never passes for its claim
; (c-jk-audit-knowledge-category-1018).
; Time: one pass over the answer's entries for each polarity.
; am[implements a-jk-knowledge-witness-1018@861c8d] am[implements a-jk-typed-boundary-1018@dee690]
; am[rests-on c-jk-audit-knowledge-category-1018@65cccb]
(: gc-justification-knowledge (-> Atom Atom Expression))
(= (gc-justification-knowledge $literal $justification)
   (let* (($entries (cdr-atom $justification))
          ($for (filter-atom $entries $l (gc-justification-accepted-as $l (Claim $literal))))
          ($against (filter-atom $entries $m (gc-justification-accepted-as $m (Claim (gc-justification-contrary $literal))))))
     (if (not (== $for ()))
         (Known True (gc-justification-label-check (car-atom $for)))
         (if (not (== $against ()))
             (Known False (gc-justification-label-check (car-atom $against)))
             Unknown))))

; Whether ENTRY is the Accepted label of REFERENCE.
(= (gc-justification-accepted-as $entry $reference)
   (if (gc-justification-shaped $entry Label 3)
       (if (== (gc-justification-label-argument $entry) $reference) (== (gc-justification-label-status $entry) Accepted) False)
       False))

; --- warm-up -----------------------------------------------------------------------------------
;
; The first evaluation in a process compiles what was imported: the rows below cost 848,410
; inferences on their first call and 36,119 on their second (measured 2026-10-18 with
; ai-tmp/justification/probe/ai-warm-expected.py). So this runs once per process, at startup or
; inside the first request's deadline, as fixed work no caller's inference budget pays for, as
; relevance's warm-up does (c-rel-inference-history-1016). It reaches a rebuttal, a refutation, an
; expiry, a chained ground, a withdrawal, a current row that lost beside withdrawn ones, a link
; undercut by the argument it protects and a knowledge query, and answers True only when each
; answer is the one the reference model gives.
; am[implements a-jk-metta-kernel-1018@258f74] am[implements a-jk-rr-row-report-1018@6747d2]
(= (gc-justification-warm-up)
   (let* (($rows (gc-justify (At 10)
                   ((From (Signal "w") (Observation (Warm "a" "measured" Forever)))
                    (From (Not (Signal "w")) (Observation (Warm "b" "model-proposed" Forever)))
                    (From (Signal "v") (Observation (Warm "c" "model-proposed" (Until 5))))
                    (From (Signal "u") (Claim (Signal "w")))
                    (Withdrawn (From (Signal "u") (Claim (Signal "w"))) (Stated (Warmed "x"))))))
          ($frame (gc-justify-frame
                    (Frame ("p" "q") ((Support "s" "p" "q")) ((Attack "k" "q" "p")) ((Undercut "k" "p")) ("q"))))
          ($known (gc-justification-knowledge (Not (Signal "w")) $rows)))
     (and (and (== $rows
                   (Justification
                     (Label (Claim (Not (Signal "w"))) Refuted Unchecked)
                     (Label (Claim (Signal "u")) Unsupported Unchecked)
                     (Label (Claim (Signal "v")) Unsupported Unchecked)
                     (Label (Claim (Signal "w")) Accepted Checked)
                     (Label (Observation (Warm "a" "measured" Forever)) Accepted Checked)
                     (Label (Observation (Warm "b" "model-proposed" Forever)) Accepted Unchecked)
                     (Label (Observation (Warm "c" "model-proposed" (Until 5))) Accepted Unchecked)
                     (Label (Row (From (Not (Signal "w")) (Observation (Warm "b" "model-proposed" Forever)))) Refuted Unchecked)
                     (Label (Row (From (Signal "u") (Claim (Signal "w")))) Accepted Unchecked)
                     (Label (Row (From (Signal "v") (Observation (Warm "c" "model-proposed" (Until 5))))) Accepted Unchecked)
                     (Label (Row (From (Signal "w") (Observation (Warm "a" "measured" Forever)))) Accepted Checked)
                     (Label (Stated (Warmed "x")) Accepted Unchecked)
                     (Link (Row (From (Not (Signal "w")) (Observation (Warm "b" "model-proposed" Forever)))) Holds)
                     (Link (Row (From (Signal "u") (Claim (Signal "w")))) Withdrawn)
                     (Link (Row (From (Signal "v") (Observation (Warm "c" "model-proposed" (Until 5))))) Withdrawn)
                     (Link (Row (From (Signal "w") (Observation (Warm "a" "measured" Forever)))) Holds)))
               (== $frame
                   (Justification (Label "p" Undecided Unchecked) (Label "q" Undecided Unchecked)
                                  (Link "k" Undecided) (Link "s" Holds))))
          (== $known (Known False Checked)))))
