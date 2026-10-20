;;; Purpose: derive closed typed attention rows and normalized query cues from native SNARS indexes.

;; A reference denotes a statement; an ordinary filler with the same key denotes a concept.
;; Connector keys follow SNARS's own recursive term-key rule.
;; am[implements a-integrate-ecan-packaged-graph-1017]
;; am[rests-on c-integrate-native-index-typed-closure-1017]
(= (gc-attention-filler-node $filler)
 (case $filler
  (((sn-ref $sid) (AttentionStatement $sid))
   ($other (AttentionConcept (sn term-key $filler))))))

;; Every stored statement has one graph node, including isolated or unsupported interned nodes.
;; Graph membership grants no licence to use a statement as an inference premise.
;; am[implements a-integrate-ecan-packaged-graph-1017]
(= (gc-attention-statements)
 (msort (unique-atom (collapse (match &self (sn stmt $sid $tree) $sid)))))

;; The native writer uses sub/obj for the binary fast path and rk for all other argument roles.
;; Time: three indexed matches and one deduplication over the statement's index rows.
;; am[implements a-integrate-ecan-packaged-graph-1017]
;; am[rests-on c-integrate-native-index-typed-closure-1017]
(= (gc-attention-index-rows $sid)
 (unique-atom (collapse (superpose (
  (match &self (sn sub $key $sid) (Index s $key))
  (match &self (sn obj $key $sid) (Index o $key))
  (match &self (sn rk $role $key $sid) (Index $role $key)))))))

;; Matching the typed filler disambiguates a statement reference from a coincident label.
;; Time: I*A role/key comparisons before sorting, I index rows and A canonical arguments.
;; am[implements a-integrate-ecan-packaged-graph-1017]
(= (gc-attention-index-links $sid)
 (match &self (sn stmt $sid $tree)
  (let* (($args (sn args-of $tree))
         ($rows (gc-attention-index-rows $sid)))
   (msort (unique-atom (collapse
    (let (Index $role $key) (superpose $rows)
     (let (arg $role $filler) (superpose $args)
      (if (== (sn term-key $filler) $key)
       (gc-attention-filler-node $filler)
       (empty))))))))))

;; These facts exist only inside the caller's speculative world; module loading creates none.
;; One row contains the node's balance and adjacency, so a link update preserves its balance.
;; am[implements a-integrate-ecan-packaged-graph-1017]
(= (gc-attention-ensure-node! $node)
 (if (== () (collapse (once (match &self (gc-attention-row $node $value $links) True))))
  (let $added (add-atom &self (gc-attention-row $node 0.0 ())) True)
  False))

;; Time: one row lookup and O(d log d) sorting, d existing neighbors plus one candidate.
;; am[implements a-integrate-ecan-packaged-graph-1017]
(= (gc-attention-link! $node $neighbor)
 (let* (($ensured (gc-attention-ensure-node! $node))
        ((Row $node $balance $links)
         (match &self (gc-attention-row $node $balance $links) (Row $node $balance $links)))
        ($next (msort (unique-atom (cons-atom $neighbor $links)))))
  (if (== $links $next) False
   (let* (($removed (remove-atom &self (gc-attention-row $node $balance $links)))
          ($added (add-atom &self (gc-attention-row $node $balance $next))))
    True))))

;; Each new statement is indexed once; both ends are ensured before publishing a closed graph.
;; A new node starts at zero, so inference cannot create attention currency.
;; Time: index-links plus two adjacency insertions per distinct neighbor.
;; am[implements a-integrate-ecan-packaged-graph-1017]
;; am[rests-on c-integrate-query-attention-domain-1017]
(= (gc-attention-add-statement! $sid)
 (if (not (== () (collapse (once (match &self (gc-attention-indexed $sid) True)))))
  False
  (let* (($node (AttentionStatement $sid))
         ($ensured (gc-attention-ensure-node! $node))
         ($links (gc-attention-index-links $sid))
         ($linked (collapse
          (let $neighbor (superpose $links)
           (let* (($out (gc-attention-link! $node $neighbor))
                  ($in (gc-attention-link! $neighbor $node))) True))))
         ($marked (add-atom &self (gc-attention-indexed $sid))))
   True)))

;; Rebuilding skips indexed statements, preserving every balance and edge.
;; Time: one add-statement call per distinct native statement.
;; am[implements a-integrate-ecan-packaged-graph-1017]
;; am[addresses i-integrate-attention-unevaluated-list-1017]
(= (gc-attention-build!)
 (let* (($statements (gc-attention-statements))
        ($built (collapse
         (let $sid (superpose $statements) (gc-attention-add-statement! $sid)))))
  True))

;; Time: V row reads and O(V log V) comparisons, V graph nodes.
;; am[implements a-integrate-ecan-packaged-graph-1017]
(= (gc-attention-rows)
 (msort (collapse (match &self (gc-attention-row $node $balance $links)
                  (Row $node $balance $links)))))

;; The row already exists by construction; no second balance store is maintained.
;; am[implements a-integrate-ecan-packaged-graph-1017]
(= (gc-attention-set-balance! $node $next)
 (match &self (gc-attention-row $node $old $links)
  (let* (($removed (remove-atom &self (gc-attention-row $node $old $links)))
         ($added (add-atom &self (gc-attention-row $node $next $links))))
   True)))

;; Query identity and fillers use the graph's same typed key mapping.
;; Repeated roles, arguments and cues do not receive repeated allocations.
;; Time: A projections and O(A log A) comparisons, A query arguments plus its own statement.
;; am[implements a-integrate-ecan-packaged-graph-1017]
;; am[addresses i-integrate-attention-unevaluated-list-1017]
(= (gc-attention-query-nodes $canonical)
 (let* (($self (AttentionStatement (sn sid $canonical)))
        ($args (sn args-of $canonical))
        ($fillers (collapse
         (let (arg $role $filler) (superpose $args)
          (gc-attention-filler-node $filler)))))
  (msort (unique-atom (cons-atom $self $fillers)))))

;; Seeding assigns one unit across the distinct cues already present, or zero if none is present.
;; Only this query entry assigns currency; later graph growth and diffusion preserve it.
;; Time: Q presence checks, V balance writes and V*Q membership comparisons.
;; am[implements a-integrate-ecan-packaged-graph-1017]
;; am[rests-on c-integrate-query-attention-domain-1017]
;; am[addresses i-integrate-attention-unevaluated-list-1017]
(= (gc-attention-seed! $canonical)
 (let* (($nodes (gc-attention-query-nodes $canonical))
        ($present (collapse
         (let $node (superpose $nodes)
          (match &self (gc-attention-row $node $balance $links) $node))))
        ($share (if (== $present ()) 0.0 (/ 1.0 (size-atom $present))))
        ($rows (gc-attention-rows))
        ($written (collapse
         (let (Row $node $old $links) (superpose $rows)
          (gc-attention-set-balance! $node
           (if (== () (collapse (once (let $node (superpose $present) True)))) 0.0 $share))))))
  $present))
