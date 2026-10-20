;;; SNARS module — THE subjective backward chainer (sbc; Wave K3, doctrine O25).
;;; Import via the snars.metta aggregator; load order lives there.
;;;
;;; ONE chainer, generic over a KB GENERATOR. This is the trueagi `chaining`
;;; skeleton (`/home/user/Dev/chaining` — synthesize / nilbc / pbc share it)
;;; with sampling removed: truth is COMPUTED by the subjective-logic algebra,
;;; never simulated. KB rows are typed triples
;;;   facts: (: <Opinion> <proof-leaf> <stmt>)
;;;   rules: (: <Opinion> <name> (-> <premise>... <conclusion>))
;;; and queries are the same triples with holes. Rule application is value-level
;;; modus ponens (`sn mp-op` = SL deduction J 9.1 with synthesized else-branch,
;;; per "Subjective Logic <-> Narsese" §3.4); multi-premise rules conjoin via
;;; binomial multiplication (`sn and-op`, J 7.1). Proofs are application trees;
;;; every proof path is returned (deterministic, no seeds — the §3.0d contrast
;;; to ProbLog's pbc, which needs the right random seed to see each path).
;;;
;;; The KB is sourced through (sbc-kb <gen>) — the generator seam (the `($kb)`
;;; nullary-thunk idiom of chaining/experimental/synthesis, here a tagged
;;; dispatch so it stays in PeTTa's fast smart-dispatch path). Two generators
;;; ship: `(space <kb>)` over any opinion-typed atomspace (benchmark KBs), and
;;; `snars` over the LIVE world — supported statements as facts (opinion = the
;;; current cell view) and the R5 registry's deductive rows as conditionals.
;;; So `(sn prove goal budget)` = sbc over the snars generator: goal-directed
;;; proof search across what SNARS currently believes + its registered rules,
;;; the sparse/goal-directed face of derive!'s dense forward sweep.
;;;
;;; `sbc-fused` collapses all proof paths and fuses them under the RECEIPT
;;; discipline (J §12 cumulative fusion's evidence-disjoint precondition = the
;;; NAL stamp-overlap rule, SLN doc §3.1): proofs sharing an axiom leaf are NOT
;;; pooled (the double-counting pbc/ProbLog would commit); stamp-disjoint proofs
;;; fuse cumulatively, growing confidence. The proof term's axiom leaves ARE its
;;; stamp, recovered structurally by `sn ax-leaves`.

(@doc sbc
  (@desc "Subjective backward chainer over a KB generator. Establishes a query (: $o $proof <conclusion>) either directly (a generated fact unifies it) or backward through a generated rule whose conclusion unifies it -- recursively proving premises, combining truth by mp-op (deduction) over and-op (premise conjunction). Depth-budgeted (Nat). Deterministic: every proof path is returned. KB sourced via (sbc-kb <gen>): (space <atomspace>) or snars.")
  (@params ((@param "KB generator tag, e.g. (space &kb) or snars")
            (@param "Maximum depth as Nat (see fromNumber)")
            (@param "Query triple (: $o $proof <conclusion>)")))
  (@return "Fulfilled query triple per proof path"))

(@doc sbc-fused
  (@desc "Collapse all proof paths of a conclusion and fuse under the receipt discipline: proofs sharing an axiom leaf are NOT pooled (no double counting -- the pbc/ProbLog independence flaw the stamp rule fixes, SLN doc §3.0d/§3.1); stamp-disjoint proofs fuse cumulatively, growing confidence.")
  (@params ((@param "KB generator tag") (@param "Maximum depth as Nat") (@param "Conclusion statement")))
  (@return "(Opinion b d u a) fused over evidence-disjoint proofs"))

(@doc (sn prove)
  (@desc "The SNARS-flavored backward chainer (K3; doctrine O25): sbc over the live world. Canonicalizes the goal (surface->sense), then goal-directs proof search across supported beliefs, those with a receipt or a proof (opinion = current cell view) + the R5 registry's deductive rows (ded-shape/structural projected as conditionals at the §3.7 structural-trust prior). Returns ask!-shaped (: opinion proof (stmt-tree)) triples -- one per proof path, holes allowed in the goal.")
  (@params ((@param "Typed SH goal tree (holes allowed in arg positions)")
            (@param "Depth budget (Number; backward rule applications)")))
  (@return "Proof triple per path found"))

(@doc (sn prove-fused)
  (@desc "Calibrated belief in a goal (K3): prove it every way within budget and fuse the stamp-disjoint paths (sbc-fused over the snars generator) -- the receipt-disciplined answer to 'what does the system believe about this goal', the goal-directed dual of the forward cells' accumulation.")
  (@params ((@param "Typed SH goal tree") (@param "Depth budget (Number)")))
  (@return "(Opinion b d u a) fused over evidence-disjoint proofs"))

(sn (function sbc))
(sn (function sbc-fused))
(sn (function prove))
(sn (function prove-fused))

;; ---- Nat depth (chaining-repo convention) ----
(: Nat Type)
(: Z Nat)
(: S (-> Nat Nat))
(: fromNumber (-> Number Nat))
(= (fromNumber $n) (if (<= $n 0) Z (S (fromNumber (- $n 1)))))

;; structural-trust prior for registry rules read as conditionals (SLN §3.7,
;; ONA STRUCTURAL_TRUTH): a near-certain rule that discounts each deductive step
;; by b_struct = 0.9. Per-rule reliability from the trust ledger is the upgrade.
(= (sn struct-tv) (Opinion 0.9 0.0 0.1 0.5))

;; ---- KB generators (the extension seam) ----
;; each yields (: <Opinion> <proof-leaf> <stmt>) rows -- facts AND (-> ...)
;; rules. Tagged dispatch keeps every call on PeTTa's fast smart-dispatch path.
;; (a) any opinion-typed atomspace, verbatim (benchmark KBs store the opinion):
(= (sbc-kb (space $kb)) (match $kb (: $o $p $s) (: $o $p $s)))
;; (b) the LIVE SNARS world: supported statements as facts (a receipt or a proof,
;; intern.metta; an interned reference asserts nothing, so it is no axiom), the
;; opinion the current cell view, evaluated so the chainer receives a concrete
;; Opinion, proof leaf = the statement sid (the axiom identity the receipt
;; discipline tracks).
(= (sbc-kb snars)
   (match &self (sn stmt $sid $tree)
     (if (sn supported? $sid)
         (let $o (sn view $sid) (: $o $sid $tree))
         (empty))))
;; the R5 registry's DEDUCTIVE rows projected as binary conditionals. Only
;; ded-shape and structural classes are backward-provable (abduction/induction
;; are hypothesis generation, not proof); a disabled row drops out.
(= (sbc-kb snars)
   (match &self (sn rw $name ded-shape $p1 $p2 $c)
     (if (and (sn rw-enabled? $name) (sn ctl-try? $name)) (: (sn struct-tv) $name (-> $p1 $p2 $c)) (empty))))
(= (sbc-kb snars)
   (match &self (sn rw $name structural $p1 $p2 $c)
     (if (and (sn rw-enabled? $name) (sn ctl-try? $name)) (: (sn struct-tv) $name (-> $p1 $p2 $c)) (empty))))
;; ---- SH-2: conditional ==> edges as backward rules (the unified-engine seam) ----
;; A stored conditional (==> A B) (conditional.metta's encoding) at its edge view
;; w_{B|A} becomes a unary rule (-> tree(A) tree(B)): the chainer proves B by
;; proving A and combining via mp-op (deduce with synth-else, truth.metta) -- the
;; BACKWARD face of conditional.metta's forward MP, now in the one engine (Q1).
;; sn-refs resolve to the interned antecedent/consequent trees (no match => the
;; clause yields nothing, safe). Gated by cond-rules?, like the forward rules.
;; The edge itself must be supported; its ends are only the rule's types, which
;; the chainer still has to prove.
;; The one-argument (mp <edge-sid>) rule head is evidence-bearing. ax-leaves
;; includes that sid so paths through one shared edge are not fused as disjoint.
(= (sbc-kb snars)
   (match &self (sn stmt $esid (sh (tag P d so ()) "==>" (args ((arg s (sn-ref $sa)) (arg o (sn-ref $sb))))))
     (if (and (sn cond-rules?) (sn supported? $esid))
         (match &self (sn stmt $sa $ta)
           (match &self (sn stmt $sb $tb)
             (let $o (sn view $esid) (: $o (mp $esid) (-> $ta $tb)))))
         (empty))))

;; ---- inference control: a positive-polarity focus set (fail-open) ----
;; (sn ctl <name>) rows license rules to TRY. THE FAIL-OPEN LAW (Continue, not
;; Terminate -- the streamed inf-ctl experiment's binding resolution): with NO
;; ctl rows the chainer tries every rule; with some, only the licensed ones.
;; Over-licensing merely over-continues (inefficient but safe); control never
;; prunes a sound branch -- it only narrows search when explicitly asserted.
;; Focus the search with (sn ctl-focus! name); lift it with (sn ctl-clear!).
(= (sn ctl-any?) (not (== () (collapse (once (match &self (sn ctl $n) True))))))
(= (sn ctl-try? $name)
   (if (sn ctl-any?)
       (not (== () (collapse (once (match &self (sn ctl $name) True)))))
       True))
(= (sn ctl-focus! $name)
   (if (== () (collapse (once (match &self (sn ctl $name) True))))
       (let $a (add-atom &self (sn ctl $name)) True) True))
(= (sn ctl-clear!)
   (let $r (collapse (match &self (sn ctl $n) (remove-atom &self (sn ctl $n)))) True))

;; ---- the chainer: pbc minus the random filter, KB read through the generator ----
;; CYCLE-SAFETY (correctness, no occurs-check flag needed -- probe-verified
;; 2026-06-13): proof search over open patterns is sound and terminating. A
;; cyclic term needs a variable unified with a term containing itself, which
;; requires both a repeated-variable conclusion AND a goal binding one position
;; to a function of another. Neither occurs here: SNARS conclusions are binary
;; (cop $x $y) with DISTINCT fillers, match freshens a rule's vars per use, KB
;; fact rows are ground (base-case unify binds holes to ground), and arg fillers
;; are concepts-or-holes -- never functions-of-holes. Empirically the hole-goal,
;; same-var-goal, and the pathological (refl $h (foo $h)) bait all terminate
;; (test-snars-sbc Part E). A global occurs_check would slow every unification in
;; the process for a structurally unreachable case -- it stays the documented
;; escape only if a future rule breaks the binary/distinct-var shape.
(: sbc (-> %Undefined% Nat %Undefined% %Undefined%))
;; base case: a generated fact/rule whose statement unifies the query
(= (sbc $gen $_ (: $o $prf $ccln))
   (let (: $o $prf $ccln) (sbc-kb $gen) (: $o $prf $ccln)))
;; unary rule application: antecedent through the conditional (mp-op)
(= (sbc $gen (S $k) (: $o ($rabs $rarg) $ccln))
   (let* (((: $oabs $rabs (-> $prms $ccln)) (sbc $gen $k (: $oabs $rabs (-> $prms $ccln))))
          ((: $oarg $rarg $prms) (sbc $gen $k (: $oarg $rarg $prms)))
          ($o (sn mp-op $oarg $oabs)))
     (: $o ($rabs $rarg) $ccln)))
;; binary rule application: premises conjoin (and-op) before the conditional
(= (sbc $gen (S $k) (: $o ($rabs $rarg1 $rarg2) $ccln))
   (let* (((: $oabs $rabs (-> $prms1 $prms2 $ccln)) (sbc $gen $k (: $oabs $rabs (-> $prms1 $prms2 $ccln))))
          ((: $oarg1 $rarg1 $prms1) (sbc $gen $k (: $oarg1 $rarg1 $prms1)))
          ((: $oarg2 $rarg2 $prms2) (sbc $gen $k (: $oarg2 $rarg2 $prms2)))
          ($o (sn mp-op (sn and-op $oarg1 $oarg2) $oabs)))
     (: $o ($rabs $rarg1 $rarg2) $ccln)))

;; ---- proof stamps: the AXIOM leaves of a proof term ----
;; a proof is either a bare leaf (an axiom: a fact name / statement sid) or an
;; application (<rule-name> <arg-proofs>...). Registered rule names are not
;; evidence, but a conditional rule head (mp <edge-sid>) carries the stored
;; edge's own evidence. Preserve that sid while walking argument proofs.
(: (sn rule-evidence-leaves) (-> %Undefined% Expression))
(= (sn rule-evidence-leaves $head)
   (case $head
     (((mp $esid) ($esid))
      ($other ()))))

(: (sn ax-leaves) (-> %Undefined% Expression))
(= (sn ax-leaves $p)
   (if (== (get-metatype $p) Expression)
       (if (== $p ()) ()
           (let ($head $tail) (decons-atom $p)
             (append (sn rule-evidence-leaves $head)
                     (sn ax-leaves-args $tail))))
       ($p)))
(= (sn ax-leaves-args $args)
   (if (== $args ()) ()
       (let ($h $t) (decons-atom $args) (append (sn ax-leaves $h) (sn ax-leaves-args $t)))))

;; lib_nars StampDisjoint shape: no shared axiom between two leaf sets
(= (sn stamp-disjoint $l1 $l2)
   (== () (collapse (let* (($x (superpose $l1))
                           ($y (superpose $l2)))
                      (case (== $x $y) ((True True)))))))

;; ---- fuse evidence-disjoint proofs; skip overlapping ones ----
(: (sn fuse-fold) (-> Atom %Undefined% %Undefined%))
(= (sn fuse-fold $ps (Acc $o $stamp))
   (if (== $ps ())
       $o
       (let ($head $tail) (decons-atom $ps)
         (let (: $oh $ph $ch) $head
           (if (sn stamp-disjoint $stamp (sn ax-leaves $ph))
               (sn fuse-fold $tail (Acc (sn fuse-op $o $oh) (msort (append $stamp (sn ax-leaves $ph)))))
               (sn fuse-fold $tail (Acc $o $stamp)))))))

(: (sn fuse-proofs) (-> Atom %Undefined%))
(= (sn fuse-proofs $ps)
   (if (== $ps ())
       (Opinion 0.0 0.0 1.0 0.5)
       (let ($head $tail) (decons-atom $ps)
         (let (: $o $prf $c) $head
           (sn fuse-fold $tail (Acc $o (msort (sn ax-leaves $prf))))))))

(= (sbc-fused $gen $depth $ccln)
   (sn fuse-proofs (collapse (sbc $gen $depth (: $o $prf $ccln)))))

;; ---- the SNARS surface: chain over the live world ----
;; goal canonicalized once (surface->sense, P-subtype->d) exactly as ask!.
(: (sn prove) (-> %Undefined% Number %Undefined%))
(= (sn prove $goal $budget)
   (let $cg (sn pat $goal)
     (sbc snars (fromNumber $budget) (: $o $prf $cg))))

(: (sn prove-fused) (-> %Undefined% Number %Undefined%))
(= (sn prove-fused $goal $budget)
   (let $cg (sn pat $goal)
     (sbc-fused snars (fromNumber $budget) $cg)))

;; ---- size-budgeted variant (optimization): bound total PROOF SIZE, not depth.
;; Each leaf (fact) is size 1; a rule application is 1 + the premise proof sizes,
;; and the budget is THREADED premise-to-premise -- premise 2 receives only what
;; premise 1 left (consume-and-pass, the chaining-repo `obc` shape). Strictly
;; finer than a depth cap (height != work: a depth-3 cap admits exponentially
;; many nodes, a size-3 cap admits exactly 3). Returns MkSized for introspection;
;; (sn prove-sized) unwraps to the standing triples.
(mb-lint-data-head MkSized)
(: sbc-sz (-> %Undefined% Number %Undefined% %Undefined%))
(= (sbc-sz $gen $s (: $o $prf $ccln))
   (if (< $s 1) (empty)
       (let (: $o $prf $ccln) (sbc-kb $gen) (MkSized 1 (: $o $prf $ccln)))))
(= (sbc-sz $gen $s (: $o ($rabs $rarg) $ccln))
   (if (< $s 2)
       (empty)
       (let* (((: $oabs $rabs (-> $prms $ccln)) (sbc-kb $gen))
              ((MkSized $a1 (: $oarg $rarg $prms)) (sbc-sz $gen (- $s 1) (: $oarg $rarg $prms)))
              ($o (sn mp-op $oarg $oabs)))
         (MkSized (+ $a1 1) (: $o ($rabs $rarg) $ccln)))))
(= (sbc-sz $gen $s (: $o ($rabs $rarg1 $rarg2) $ccln))
   (if (< $s 3)
       (empty)
       (let* (((: $oabs $rabs (-> $prms1 $prms2 $ccln)) (sbc-kb $gen))
              ((MkSized $a1 (: $oarg1 $rarg1 $prms1)) (sbc-sz $gen (- $s 1) (: $oarg1 $rarg1 $prms1)))
              ((MkSized $a2 (: $oarg2 $rarg2 $prms2)) (sbc-sz $gen (- (- $s 1) $a1) (: $oarg2 $rarg2 $prms2)))
              ($o (sn mp-op (sn and-op $oarg1 $oarg2) $oabs)))
         (MkSized (+ (+ $a1 $a2) 1) (: $o ($rabs $rarg1 $rarg2) $ccln)))))

(: (sn prove-sized) (-> %Undefined% Number %Undefined%))
(= (sn prove-sized $goal $maxsize)
   (let $cg (sn pat $goal)
     (let (MkSized $sz (: $o $prf $cg)) (sbc-sz snars $maxsize (: $o $prf $cg))
       (: $o $prf $cg))))

;; ---- K1: transactional counterfactuals (what-if!) ----
;; "if HYP held, what would follow for QUERY?" The kernel op sn_what_if runs
;; inside SWI snapshot/1: assert HYP (believe!), prove QUERY against the
;; augmented world with the pure chainer, then roll back EVERYTHING (cells,
;; space facts, sid memo) -- the chess-game envision/reset pattern collapsed to
;; one safe op, the KB bit-identical afterward. Returns the proof triples QUERY
;; holds under HYP; the results survive the rollback (snapshot keeps bindings).
;; Pure-chainer payoff: nothing is interned during the sweep, so the deduce-and-
;; graft janus re-entrancy that deferred this before is absent.
(: (sn what-if!) (-> %Undefined% Atom %Undefined% Number %Undefined%))
(= (sn what-if! $hyp $hopts $query $budget)
   (let $rs (sn_what_if $hyp $hopts $query $budget) (superpose $rs)))

;; calibrated counterfactual belief: assume HYP at strong evidence, return the
;; opinion QUERY would hold, receipt-fused over its proof paths under HYP.
(: (sn would?!) (-> %Undefined% %Undefined% Number %Undefined%))
(= (sn would?! $hyp $query $budget)
   (sn fuse-proofs (sn_what_if $hyp ((evidence 8.0 0.0) (source "what-if")) $query $budget)))

;; ---- obligations: the premises each route to a goal still needs ----
;; A route is a structural proof of the goal in which any statement-shaped premise
;; may stand open, carrying the caller's hypothesis opinion: the wrapped
;; generator's rows plus one open-leaf row, whose (sh ...) shape keeps it off rule
;; rows (-> ...). An open leaf lives only inside the route the search returns.
;; Nothing is interned, written or committed, so no route is a proof row and no
;; open premise becomes support.
(= (sbc-kb (obligations $gen $hyp)) (sbc-kb $gen))
(= (sbc-kb (obligations $gen $hyp)) (: $hyp (open (sh $t $c $a)) (sh $t $c $a)))

;; a route's leaves in proof order: each (open <tree>) whole, and each axiom sid as
;; ax-leaves reads it, the edge sid of a conditional rule head included
(= (sn route-leaves $p)
   (if (== (get-metatype $p) Expression)
       (if (== $p ()) ()
           (let ($head $tail) (decons-atom $p)
             (if (== $head open)
                 ($p)
                 (append (sn rule-evidence-leaves $head) (sn route-leaves-args $tail)))))
       ($p)))
(= (sn route-leaves-args $args)
   (if (== $args ()) ()
       (let ($h $t) (decons-atom $args) (append (sn route-leaves $h) (sn route-leaves-args $t)))))

;; a leaf as a route reports it: an open premise is Open; a held statement or edge
;; carries its tree, its condition at theta and its view, so evidence too weak or
;; contrary to meet the condition leaves it Undecided or Failed, never discharged
(= (sn route-leaf $leaf $theta)
   (case $leaf
     (((open $tree) (leaf open $tree Open))
      ($sid (match &self (sn stmt $sid $tree)
              (leaf $sid $tree (sn condition-of $sid pos $theta) (sn view $sid)))))))
(= (sn route-leaf-list $leaves $theta)
   (if (== $leaves ()) ()
       (let ($h $t) (decons-atom $leaves)
         (cons-atom (sn route-leaf $h $theta) (sn route-leaf-list $t $theta)))))

;; obligations: every structural route of a goal within the size bound, in msort
;; order, which states no preference. Each route reports its leaves and its
;; scenario: the opinion the goal would hold were every open premise to carry the
;; hypothesis, labelled with it and cut at theta. A scenario is neither attainable
;; confidence, expected information value nor a bound, and its cut holds only under
;; that hypothesis, so no route is dropped or ranked by it here.
;; The goal is canonicalised as ask! and prove canonicalise it.
;; Time: sbc-sz over the wrapped generator, at most $size nodes a route and in the
;; worst case exponential in $size, plus one condition and view per leaf.
(= (sn obligations $goal $hyp $size $theta)
   (sn obligations-at (sn pat $goal) $hyp $size $theta))
(= (sn obligations-at $cg $hyp $size $theta)
   (msort (collapse
     (let (MkSized $n (: $o $prf $cg)) (sbc-sz (obligations snars $hyp) $size (: $o $prf $cg))
       (route (leaves (sn route-leaf-list (sn route-leaves $prf) $theta))
              (scenario (hypothesis $hyp) (opinion $o) (status (sn condition $o $theta)))
              (proof $prf)
              (size $n))))))
