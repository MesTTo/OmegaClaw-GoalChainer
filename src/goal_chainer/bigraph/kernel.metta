; Purpose: the bigraph structural kernel. It checks contract bigraph terms and reaction rules, composes
; bigraphs, finds every occurrence of a solid redex with its sites, positional links, active context and
; application conditions, rewrites an occurrence through its decomposition and instantiation, decides
; exact isomorphism beside an invariant bucket, and lists successors keeping each occurrence's multiplicity.
; Typed one-answer entries serve goal_chainer.runtime's evaluator.
; am[implements a-integrate-brs-structural-kernel-1018@dc4d19]

; A bigraph is one term (contract section 2.1):
;   (Bigraph (Inner SITES (X ...)) (Outer ROOTS (Y ...))
;            (Nodes (N ID CONTROL) ...) (Place (In CHILD PARENT) ...) (Link (P ID PORT LINK) ... (I X LINK) ...))
; CHILD is a node id or (Site k), PARENT a node id or (Root j), LINK (Edge E) or (Name Y). An edge exists
; only through the points reaching it, so no term can hold an idle edge.
;
; Every symbol this module defines starts bg-. No tuple it builds is headed by caller data: pymetta 0.9.4
; calls a code literal whose head is bound to a function name, so (RID SID) would become a call once a
; module defines RID. Pairs therefore carry constant heads such as (Image KEY VALUE) and (At INDEX VALUE),
; and a one-element list is built with cons-atom.
; am[rests-on c-brs-k-function-heads-evaluate-1018@90a5f4] am[rests-on c-brs-k-values-not-reevaluated-1018@ea5789]
; am[implements c-brs-k-inert-heads-1018@e36b32]

; ===== Lists ==========================================================================================

; Time: one append per inner list, each copying its own elements once.
(= (bg--flat $lists)
   (if (== $lists ()) ()
       (let ($head $rest) (decons-atom $lists) (append $head (bg--flat $rest)))))

; (0 1 ... N-1).
(= (bg--range $n) (bg--range-from 0 $n))
(= (bg--range-from $i $n) (if (< $i $n) (cons-atom $i (bg--range-from (+ $i 1) $n)) ()))

; The first row of ROWS whose field at INDEX is KEY, or ().
; Time: rows scanned up to the match.
(= (bg--row-with $index $key $rows)
   (if (== $rows ()) ()
       (let ($row $rest) (decons-atom $rows)
         (if (== (index-atom $row $index) $key) $row (bg--row-with $index $key $rest)))))

; (VALUE) for the first (HEAD KEY VALUE) row of ROWS with that KEY, or () when none has it, so a VALUE of
; any shape is told apart from absence.
(= (bg--find $key $rows)
   (if (== $rows ()) ()
       (let ($row $rest) (decons-atom $rows)
         (if (== (index-atom $row 1) $key) (cons-atom (index-atom $row 2) ()) (bg--find $key $rest)))))

; The VALUE of the first (HEAD KEY VALUE) row with that KEY, or DEFAULT.
(= (bg--assoc $key $rows $default)
   (let $found (bg--find $key $rows) (if (== $found ()) $default (car-atom $found))))

; Whether X is an element of LIST, answering once however often X occurs there: lib_functional's
; is-member answers True once per occurrence, which multiplies the answers of whatever branches on it.
; Time: one pass over LIST.
; am[implements a-brs-k-member-once-1018@ed3afd] am[rests-on c-ev-pk-is-member-per-occurrence-1018@c8243c]
(= (bg--member? $x $list) (not (== (filter-atom $list $y (== $y $x)) ())))

(= (bg--keys $rows) (map-atom $rows $row (index-atom $row 1)))
(= (bg--values $rows) (map-atom $rows $row (index-atom $row 2)))

; Each element of XS that occurs more than once, once: what is left after one copy of each is taken away.
; Time: the engine's AVL counts behind subtraction-atom, n log n.
; am[rests-on c-brs-k-list-primitives-cost-1018@30216a]
(= (bg--duplicates $xs) (unique-atom (subtraction-atom $xs (unique-atom $xs))))

; Sorted (BgPair KEY VALUE) rows as (BgGroup KEY (VALUE ...)), values in input order.
; Time: one pass.
(= (bg--group $pairs)
   (if (== $pairs ()) ()
       (let* ((($first $rest) (decons-atom $pairs))
              ((BgPair $key $value) $first)
              ($tail (bg--group $rest)))
         (if (== $tail ())
             (cons-atom (BgGroup $key (cons-atom $value ())) ())
             (let (BgGroup $next $values) (car-atom $tail)
               (if (== $next $key)
                   (cons-atom (BgGroup $key (cons-atom $value $values)) (cdr-atom $tail))
                   (cons-atom (BgGroup $key (cons-atom $value ())) $tail)))))))

(= (bg--compound? $x) (case (get-metatype $x) ((Expression (not (== $x ()))) ($other False))))
(= (bg--list? $x) (== (get-metatype $x) Expression))
(= (bg--headed? $head $x) (if (bg--compound? $x) (== (car-atom $x) $head) False))
(= (bg--row? $head $size $row) (if (bg--headed? $head $row) (== (size-atom $row) $size) False))
(= (bg--site? $x) (bg--headed? Site $x))
(= (bg--root? $x) (bg--headed? Root $x))
(= (bg--natural? $x)
   (if (== (get-type $x) Number) (if (>= $x 0) (== $x (trunc-math $x)) False) False))

; True when X holds no variable. Time: one visit per atom of X.
(= (bg--ground? $x)
   (case (get-metatype $x)
     ((Variable False)
      (Expression (bg--all-ground? $x))
      ($other True))))
(= (bg--all-ground? $xs)
   (if (== $xs ()) True
       (let ($head $rest) (decons-atom $xs) (if (bg--ground? $head) (bg--all-ground? $rest) False))))

; ===== Search trees ====================================================================================
; pymetta's lists are linked: index-atom walks to its position and is-member scans, so a lookup inside a
; loop over a state's rows would make the loop quadratic. Rows ordered by their first field live in a
; persistent red-black tree instead (Okasaki, "Red-black trees in a functional setting", JFP 9(4), 1999):
; BgLeaf, or (BgNode COLOUR LEFT ROW RIGHT) with COLOUR BgRed or BgBlack. Keys compare in the standard
; order of terms that msort sorts by, so a tree built from msort-ed rows agrees with the sort.
; No equation body in this module calls its own recursion twice, directly or through functions that call
; back: pymetta 0.9.4 then memoizes the whole recursive group and keys every call by its arguments, so a
; search walking a tree that way would pay a scan of the tree per level.
; am[implements a-brs-k-st-trees-1018@2f963f] am[implements a-brs-k-no-auto-memo-1018@69c76e]
; am[rests-on c-brs-k-index-atom-walks-1018@3a5ea7] am[rests-on c-brs-k-list-primitives-cost-1018@30216a]
; am[rests-on c-brs-k-auto-memo-1018@9c39b3] am[rests-on c-brs-k-two-call-sites-linear-1018@3e5582]

; True when A sorts before B or equals it. Time: one two-element msort.
(= (bg--before? $a $b) (== (car-atom (msort (cons-atom $a (cons-atom $b ())))) $a))

; The tree of ROWS, sorted by their first field with distinct keys, built in one pass the way SWI-Prolog's
; ord_list_to_rbtree and Haskell's Data.Map.fromDistinctAscList build theirs: the left subtree takes the
; first half, the next row is the root and the right subtree takes the rest. Nodes down to the deepest
; full level are black and those below it red, so every path holds the same number of black nodes. The
; recursion runs as one loop over a stack of what is left to do above the subtree in hand, its
; continuation defunctionalised (Ager, Biernacki, Danvy and Midtgaard, "A functional correspondence
; between evaluators and abstract machines", PPDP 2003), since a body building both halves would have
; pymetta memoize the builder.
; Time: 4n + 1 steps of one case each, n = rows: one per subtree, empty ones included, and two more per row.
(= (bg--tree $rows)
   (let $n (size-atom $rows)
     (bg--build (BgBuilding (BgBuild $n 1) BgBottom $rows) (bg--full-depth $n 0 1))))
; The number of full levels in a balanced tree of N rows: the largest D with 2^D - 1 <= N.
(= (bg--full-depth $n $depth $next)
   (if (> $next $n) $depth (bg--full-depth $n (+ $depth 1) (+ (* 2 $next) 1))))
; The tree that (BgBuilding TASK STACK ROWS) finishes as. TASK is (BgBuild N DEPTH), the tree of the next
; N of ROWS with its root at DEPTH, or (BgBuilt TREE), a subtree just finished. STACK is BgBottom or a
; frame over the rest: (BgLeftOf N DEPTH BELOW) awaits the left subtree of an N-row tree rooted at DEPTH,
; and (BgRightOf COLOUR LEFT ROW BELOW) the right subtree under ROW.
(= (bg--build $state $full)
   (case $state
     (((BgBuilding (BgBuilt $tree) BgBottom $rows) $tree)
      ($building (bg--build (bg--build-step $building $full) $full)))))
(= (bg--build-step (BgBuilding $task $stack $rows) $full)
   (case (BgStep $task $stack)
     (((BgStep (BgBuild 0 $depth) $below) (BgBuilding (BgBuilt BgLeaf) $below $rows))
      ((BgStep (BgBuild $n $depth) $below)
       (BgBuilding (BgBuild (floor-div (- $n 1) 2) (+ $depth 1)) (BgLeftOf $n $depth $below) $rows))
      ((BgStep (BgBuilt $left) (BgLeftOf $n $depth $below))
       (BgBuilding (BgBuild (- (- $n 1) (floor-div (- $n 1) 2)) (+ $depth 1))
                   (BgRightOf (if (> $depth $full) BgRed BgBlack) $left (car-atom $rows) $below)
                   (cdr-atom $rows)))
      ((BgStep (BgBuilt $right) (BgRightOf $colour $left $row $below))
       (BgBuilding (BgBuilt (BgNode $colour $left $row $right)) $below $rows)))))

; The row of TREE whose first field is KEY, or (). Time: one comparison per level, at most
; 2 log2(n + 1) levels.
(= (bg--tree-row $key $tree)
   (case $tree
     ((BgLeaf ())
      ((BgNode $colour $left $row $right)
       (let $probe (index-atom $row 1)
         (if (== $probe $key) $row (bg--tree-row $key (if (bg--before? $key $probe) $left $right))))))))
(= (bg--in? $key $tree) (not (== (bg--tree-row $key $tree) ())))

; TREE with ROW added, in place of the row with ROW's key if it has one. Time: one comparison and one
; balance per level.
(= (bg--tree-insert $row $tree)
   (let (BgNode $colour $left $top $right) (bg--tree-ins $row $tree) (BgNode BgBlack $left $top $right)))
(= (bg--tree-ins $row $tree)
   (case $tree
     ((BgLeaf (BgNode BgRed BgLeaf $row BgLeaf))
      ((BgNode $colour $left $here $right)
       (let* (($key (index-atom $row 1)) ($probe (index-atom $here 1)))
         (if (== $key $probe)
             (BgNode $colour $left $row $right)
             (let $before (bg--before? $key $probe)
               (bg--grafted $before $colour $left $here $right (bg--tree-ins $row (if $before $left $right))))))))))
; The node rebuilt over CHILD, the subtree an insertion went into: its left one when BEFORE.
(= (bg--grafted $before $colour $left $here $right $child)
   (if $before (bg--balance $colour $child $here $right) (bg--balance $colour $left $here $child)))
; Okasaki's four rotations of a black node over a red child that has a red child.
(= (bg--balance $colour $left $row $right)
   (case (BgBalance $colour $left $row $right)
     (((BgBalance BgBlack (BgNode BgRed (BgNode BgRed $a1 $x1 $b1) $y1 $c1) $z1 $d1)
       (BgNode BgRed (BgNode BgBlack $a1 $x1 $b1) $y1 (BgNode BgBlack $c1 $z1 $d1)))
      ((BgBalance BgBlack (BgNode BgRed $a2 $x2 (BgNode BgRed $b2 $y2 $c2)) $z2 $d2)
       (BgNode BgRed (BgNode BgBlack $a2 $x2 $b2) $y2 (BgNode BgBlack $c2 $z2 $d2)))
      ((BgBalance BgBlack $a3 $x3 (BgNode BgRed (BgNode BgRed $b3 $y3 $c3) $z3 $d3))
       (BgNode BgRed (BgNode BgBlack $a3 $x3 $b3) $y3 (BgNode BgBlack $c3 $z3 $d3)))
      ((BgBalance BgBlack $a4 $x4 (BgNode BgRed $b4 $y4 (BgNode BgRed $c4 $z4 $d4)))
       (BgNode BgRed (BgNode BgBlack $a4 $x4 $b4) $y4 (BgNode BgBlack $c4 $z4 $d4)))
      ($balanced (BgNode $colour $left $row $right)))))

; A map (BgMap ROWS TREE): rows sorted by their first field with distinct keys, walked in order, and
; their tree, looked up in log time.
(= (bg--map $rows) (BgMap $rows (bg--tree $rows)))
(= (bg--map-rows (BgMap $rows $tree)) $rows)
(= (bg--map-tree (BgMap $rows $tree)) $tree)
(= (bg--map-row $key (BgMap $rows $tree)) (bg--tree-row $key $tree))
; The second field of MAP's row for KEY, or DEFAULT.
(= (bg--map-value $key $map $default)
   (let $row (bg--map-row $key $map) (if (== $row ()) $default (index-atom $row 2))))
; The tree of the distinct elements of XS as (BgKey X) rows. Time: a sort, n log n.
(= (bg--set $xs) (bg--tree (map-atom (unique-atom (msort $xs)) $x (BgKey $x))))

; Each element of LIST with the others, (BgPick X OTHERS), the first element first. Time: one step per
; element passed over.
(= (bg--pick $list)
   (if (== $list ()) (empty) (let ($head $tail) (decons-atom $list) (BgPick $head $tail))))
(= (bg--pick $list)
   (if (== $list ())
       (empty)
       (let* ((($head $tail) (decons-atom $list))
              ((BgPick $x $others) (bg--pick $tail)))
         (BgPick $x (cons-atom $head $others)))))

; ===== Terms ===========================================================================================
; am[implements a-brs-k-term-1018@9429da]

(= (bg-nodes (Bigraph $inner $outer $nodes $place $link)) (cdr-atom $nodes))
(= (bg-place (Bigraph $inner $outer $nodes $place $link)) (cdr-atom $place))
(= (bg-link (Bigraph $inner $outer $nodes $place $link)) (cdr-atom $link))
(= (bg-sites (Bigraph (Inner $m $xs) $outer $nodes $place $link)) $m)
(= (bg-inner-names (Bigraph (Inner $m $xs) $outer $nodes $place $link)) $xs)
(= (bg-roots (Bigraph $inner (Outer $n $ys) $nodes $place $link)) $n)
(= (bg-outer-names (Bigraph $inner (Outer $n $ys) $nodes $place $link)) $ys)

; The term with every row and name list in sort order: two terms built from the same rows are equal.
(= (bg-term $m $xs $n $ys $nodes $place $link)
   (Bigraph (Inner $m (msort $xs)) (Outer $n (msort $ys))
            (cons-atom Nodes (msort $nodes)) (cons-atom Place (msort $place)) (cons-atom Link (msort $link))))
(= (bg-normal $s)
   (bg-term (bg-sites $s) (bg-inner-names $s) (bg-roots $s) (bg-outer-names $s) (bg-nodes $s) (bg-place $s) (bg-link $s)))

; A ground bigraph from its rows: roots 1 + the largest (Root j) placed (at least one), outer names those
; its links name.
(= (bg-make $nodes $place $link)
   (bg-term 0 () (bg--root-count $place) (bg--link-names $link) $nodes $place $link))
(= (bg--root-count $place)
   (foldl-atom $place 1 $acc $row
     (case (index-atom $row 2)
       (((Root $j) (if (> (+ $j 1) $acc) (+ $j 1) $acc))
        ($other $acc)))))
(= (bg--link-names $link)
   (unique-atom (bg--flat (map-atom $link $row
     (case (bg--row-link $row) (((Name $y) (cons-atom $y ())) ($other ())))))))
(= (bg--row-link $row) (case $row (((P $id $port $l) $l) ((I $x $l) $l) ($other ()))))

; A rule or builder makes anonymous ids, (new ...); every other id names an observed entity.
(= (bg-anonymous? $id) (bg--headed? new $id))

(= (bg-control $s $id) (index-atom (bg--row-with 1 $id (bg-nodes $s)) 2))
(= (bg-parent $s $child) (index-atom (bg--row-with 1 $child (bg-place $s)) 2))
(= (bg-children $s $parent)
   (msort (map-atom (filter-atom (bg-place $s) $row (== (index-atom $row 2) $parent)) $row (index-atom $row 1))))
(= (bg-ports $s $id)
   (map-atom (msort (map-atom (filter-atom (bg-link $s) $row (bg--port-of? $id $row)) $row
                      (BgPair (index-atom $row 2) (index-atom $row 3))))
             $pair (index-atom $pair 2)))
(= (bg--port-of? $id $row) (if (bg--row? P 4 $row) (== (index-atom $row 1) $id) False))
(= (bg--edges $s)
   (unique-atom (bg--flat (map-atom (bg-link $s) $row
     (case (bg--row-link $row) (((Edge $e) (cons-atom $e ())) ($other ())))))))
(= (bg--ids $s) (map-atom (bg-nodes $s) $row (index-atom $row 1)))

; BASE, a (new ...) term, extended by the smallest natural K for which no id of S, or of IDS, is
; (new ... K): fresh ids stay disjoint from retained ones under repeated reaction.
; Time: the ids' set, n log n, then one tree lookup per candidate K, at most ids + 1 candidates.
; am[rests-on c-ev-brs-fresh-ids-disjoint-1018@e864ac]
(= (bg-fresh $base $s) (bg--fresh-in $base (bg--set (bg--ids $s))))
(= (bg-fresh-among $base $ids) (bg--fresh-in $base (bg--set $ids)))
; BASE extended by the smallest natural K for which (BASE ... K) is no key of TREE.
(= (bg--fresh-in $base $tree) (bg--fresh-from $base 0 $tree))
(= (bg--fresh-from $base $k $tree)
   (let $id (append $base (cons-atom $k ()))
     (if (bg--in? $id $tree) (bg--fresh-from $base (+ $k 1) $tree) $id)))

; ===== Signatures ======================================================================================
; A domain's controls: (Signature (Control KEY ARITY KIND) ...), KIND atomic, active or passive. A control
; term's declaration is the row keyed by the term itself, else, for an expression, the row keyed by its
; head; () when neither exists.
; am[implements c-brs-k-signature-keying-1018@51c974]
(= (bg-declaration $sig $control)
   (let $exact (bg--row-with 1 $control (cdr-atom $sig))
     (if (== $exact ())
         (if (bg--compound? $control) (bg--row-with 1 (car-atom $control) (cdr-atom $sig)) ())
         $exact)))
(= (bg-arity $sig $control) (let $row (bg-declaration $sig $control) (if (== $row ()) () (index-atom $row 2))))
(= (bg-kind $sig $control) (let $row (bg-declaration $sig $control) (if (== $row ()) () (index-atom $row 3))))

; ===== Well-formedness =================================================================================
; Every way TERM fails the contract's well-formedness against SIG, sorted; () when it is well-formed.
; Time: sorts of the rows, n log n, plus one membership test per placed node against its parents, and a
; breadth-first walk from the roots costing one group lookup per node.
; am[implements a-brs-k-term-1018@9429da]
(= (bg-faults $sig $term) (msort (unique-atom (bg--term-faults $sig $term))))

(= (bg--term-faults $sig $term)
   (case $term
     (((Bigraph (Inner $m $xs) (Outer $n $ys) $nodes $place $link)
       (let $shape (bg--shape-faults $m $xs $n $ys $nodes $place $link)
         (if (== $shape ())
             (bg--flat ((bg--signature-faults $sig)
                        (bg--node-faults $sig (cdr-atom $nodes))
                        (bg--place-faults $sig $m $n (cdr-atom $nodes) (cdr-atom $place))
                        (bg--link-faults $sig $xs $ys (cdr-atom $nodes) (cdr-atom $link))))
             $shape)))
      ($other (cons-atom (BadTerm $other) ())))))

(= (bg--shape-faults $m $xs $n $ys $nodes $place $link)
   (bg--flat ((if (bg--natural? $m) () (cons-atom (BadFace Inner $m) ()))
              (if (bg--natural? $n) () (cons-atom (BadFace Outer $n) ()))
              (if (bg--names? $xs) () (cons-atom (BadNames Inner $xs) ()))
              (if (bg--names? $ys) () (cons-atom (BadNames Outer $ys) ()))
              (if (bg--headed? Nodes $nodes) () (cons-atom (BadSection Nodes) ()))
              (if (bg--headed? Place $place) () (cons-atom (BadSection Place) ()))
              (if (bg--headed? Link $link) () (cons-atom (BadSection Link) ())))))
(= (bg--names? $names)
   (if (bg--list? $names)
       (if (bg--all-ground? $names) (== (bg--duplicates $names) ()) False)
       False))

(= (bg--signature-faults $sig)
   (if (bg--headed? Signature $sig)
       (let $rows (cdr-atom $sig)
         (bg--flat ((map-atom (filter-atom $rows $row (not (bg--control-row? $row))) $row (BadControl $row))
                    (map-atom (bg--duplicates (map-atom (filter-atom $rows $row (bg--control-row? $row)) $row (index-atom $row 1)))
                              $key (DuplicateControl $key)))))
       (cons-atom (BadSignature $sig) ())))
; am[implements a-brs-k-member-once-1018@ed3afd]
(= (bg--control-row? $row)
   (if (bg--row? Control 4 $row)
       (let (Control $key $arity $kind) $row
         (if (bg--ground? $key)
             (if (bg--natural? $arity) (bg--member? $kind (atomic active passive)) False)
             False))
       False))

(= (bg--node-faults $sig $rows)
   (let* (($good (filter-atom $rows $row (bg--row? N 3 $row)))
          ($ids (map-atom $good $row (index-atom $row 1))))
     (bg--flat ((map-atom (filter-atom $rows $row (not (bg--row? N 3 $row))) $row (BadRow $row))
                (map-atom (bg--duplicates $ids) $id (DuplicateNode $id))
                (bg--flat (map-atom $good $row (bg--node-row-faults $sig $row)))))))
(= (bg--node-row-faults $sig (N $id $control))
   (bg--flat ((if (bg--ground? $id) () (cons-atom (NonGroundId $id) ()))
              (if (bg--reserved-id? $id) (cons-atom (ReservedId $id) ()) ())
              (if (bg--ground? $control) () (cons-atom (NonGroundControl $id $control) ()))
              (if (== (bg-declaration $sig $control) ()) (cons-atom (UndeclaredControl $id $control) ()) ()))))
; Ids headed Edge, Name, Site or Root would read as links or places in an occurrence's images.
; am[implements c-brs-k-witness-agreed-1018@2d9ea2]
; am[implements a-brs-k-member-once-1018@ed3afd]
(= (bg--reserved-id? $id) (if (bg--compound? $id) (bg--member? (car-atom $id) (Edge Name Site Root)) False))

(= (bg--place-faults $sig $m $n $nodes $rows)
   (let* (($good (filter-atom $rows $row (bg--row? In 3 $row)))
          ($ids (map-atom (filter-atom $nodes $row (bg--row? N 3 $row)) $row (index-atom $row 1)))
          ($placeable (append $ids (map-atom (bg--range $m) $k (Site $k))))
          ($children (map-atom $good $row (index-atom $row 1)))
          ($parents (unique-atom (map-atom $good $row (index-atom $row 2))))
          ($node-parents (filter-atom $parents $p (not (bg--root? $p))))
          ($root-parents (filter-atom $parents $p (bg--root? $p))))
     (bg--flat ((map-atom (filter-atom $rows $row (not (bg--row? In 3 $row))) $row (BadRow $row))
                (map-atom (subtraction-atom (unique-atom $children) $placeable) $c (UnknownChild $c))
                (map-atom (subtraction-atom $node-parents $ids) $p (UnknownParent $p))
                (map-atom (filter-atom $root-parents $p (not (bg--root-in? $p $n))) $p (UnknownParent $p))
                (map-atom (bg--duplicates $children) $c (TwoParents $c))
                (map-atom (subtraction-atom (unique-atom $placeable) $children) $c (NoParent $c))
                (bg--atomic-parent-faults $sig $nodes $node-parents)
                (bg--cycle-faults (unique-atom (intersection-atom $ids $children)) $good)))))
(= (bg--root-in? (Root $j) $n) (if (bg--natural? $j) (< $j $n) False))

(= (bg--atomic-parent-faults $sig $nodes $parents)
   (let $parent-set (bg--set $parents)
     (bg--flat (map-atom (filter-atom $nodes $row (bg--row? N 3 $row)) $row
       (let (N $id $control) $row
         (if (== (bg-kind $sig $control) atomic)
             (if (bg--in? $id $parent-set) (cons-atom (AtomicParent $id) ()) ())
             ()))))))

; Nodes with a parent row that no walk down from a root reaches lie on or under a cycle.
; Time: a sort of the rows, then one tree lookup and at most one insertion per child walked.
(= (bg--cycle-faults $placed $rows)
   (let* (($groups (bg--map (bg--group (msort (map-atom $rows $row (BgPair (index-atom $row 2) (index-atom $row 1)))))))
          ($start (bg--flat (map-atom (filter-atom (bg--map-rows $groups) $g (bg--root? (index-atom $g 1))) $g (index-atom $g 2))))
          ($reached (bg--reach $start $groups BgLeaf)))
     (map-atom (filter-atom $placed $id (not (bg--in? $id $reached))) $id (Cycle $id))))
; SEEN, a tree of (BgKey X) rows, with everything reachable down from FRONTIER added; a child met again,
; as under two parent rows, is not walked twice.
(= (bg--reach $frontier $groups $seen)
   (if (== $frontier ())
       $seen
       (let* ((($x $rest) (decons-atom $frontier))
              ($new (not (bg--in? $x $seen))))
         (bg--reach (if $new (append (bg--map-value $x $groups ()) $rest) $rest) $groups
                    (if $new (bg--tree-insert (BgKey $x) $seen) $seen)))))

(= (bg--link-faults $sig $xs $ys $nodes $rows)
   (let* (($ports (filter-atom $rows $row (bg--row? P 4 $row)))
          ($inners (filter-atom $rows $row (bg--row? I 3 $row)))
          ($expected (bg--flat (map-atom (filter-atom $nodes $row (bg--row? N 3 $row)) $row (bg--expected-ports $sig $row))))
          ($present (map-atom $ports $row (BgPort (index-atom $row 1) (index-atom $row 2))))
          ($names (map-atom $inners $row (index-atom $row 1)))
          ($outer (bg--set $ys)))
     (bg--flat ((map-atom (filter-atom $rows $row (not (or (bg--row? P 4 $row) (bg--row? I 3 $row)))) $row (BadRow $row))
                (map-atom (subtraction-atom (unique-atom $expected) $present) $p (MissingPort $p))
                (map-atom (subtraction-atom (unique-atom $present) $expected) $p (BadPort $p))
                (map-atom (bg--duplicates $present) $p (DuplicatePort $p))
                (map-atom (subtraction-atom $xs $names) $x (MissingInnerName $x))
                (map-atom (subtraction-atom (unique-atom $names) $xs) $x (UnknownInnerName $x))
                (map-atom (bg--duplicates $names) $x (DuplicateInnerName $x))
                (bg--flat (map-atom (append $ports $inners) $row (bg--link-target-faults $outer $row)))))))
(= (bg--expected-ports $sig (N $id $control))
   (let $arity (bg-arity $sig $control)
     (if (bg--natural? $arity) (map-atom (bg--range $arity) $k (BgPort $id $k)) ())))
(= (bg--link-target-faults $outer $row)
   (case (bg--row-link $row)
     (((Edge $e) (if (bg--ground? $e) () (cons-atom (BadLink $row) ())))
      ((Name $y) (if (bg--in? $y $outer) () (cons-atom (UnknownName $y) ())))
      ($other (cons-atom (BadLink $row) ())))))

; ===== Rules ===========================================================================================
; A rule is (Rule NAME REDEX REACTUM (Eta (k j) ...) (Conditions COND ...) (Priority P)): REDEX and REACTUM
; bigraphs sharing their outer face and inner names, Eta mapping every reactum site k to a redex site j.
; Every way RULE fails against SIG, sorted. The redex must have a node and be solid, as BigraphER requires:
; every region holds a node, no site sits directly under a region, no node holds two sites, every outer
; name has a port, an inner name reaches only a closed edge and no edge holds two. Each closed redex edge
; has a port too, so an occurrence's node map fixes its edge and name maps.
; am[implements a-brs-k-term-1018@9429da] am[rests-on c-brs-k-solid-redex-1018@7d9a0b]
(= (bg-rule-faults $sig $rule) (msort (unique-atom (bg--rule-faults $sig $rule))))

(= (bg--rule-faults $sig $rule)
   (case $rule
     (((Rule $name $redex $reactum $eta $conditions $priority)
       (if (bg--ground? $rule)
           (let $terms (append (map-atom (bg--term-faults $sig $redex) $f (Redex $f))
                               (map-atom (bg--term-faults $sig $reactum) $f (Reactum $f)))
             (if (== $terms ())
                 (bg--flat ((bg--interface-faults $name $redex $reactum)
                            (map-atom (bg--solidity $redex) $why (NotSolid $name $why))
                            (bg--eta-faults $name $redex $reactum $eta)
                            (bg--condition-faults $sig $name $redex $conditions)
                            (bg--priority-faults $name $priority)))
                 $terms))
           (cons-atom (NonGround $name) ())))
      ($other (cons-atom (BadRule $other) ())))))
; get-type reads its argument unevaluated, so the priority value is bound first.
(= (bg--priority-faults $name $priority)
   (if (bg--row? Priority 2 $priority)
       (let $p (index-atom $priority 1) (if (== (get-type $p) Number) () (cons-atom (BadPriority $name $priority) ())))
       (cons-atom (BadPriority $name $priority) ())))

(= (bg--interface-faults $name $redex $reactum)
   (bg--flat ((if (== (bg-roots $redex) (bg-roots $reactum)) () (cons-atom (OuterFaceMismatch $name Roots) ()))
              (if (== (msort (bg-outer-names $redex)) (msort (bg-outer-names $reactum))) () (cons-atom (OuterFaceMismatch $name Names) ()))
              (if (== (msort (bg-inner-names $redex)) (msort (bg-inner-names $reactum))) () (cons-atom (InnerNamesMismatch $name) ()))
              (if (== (bg-nodes $redex) ()) (cons-atom (NoRedexNode $name) ()) ())
              (map-atom (filter-atom (bg-outer-names $redex) $y (bg--headed? Via $y)) $y (ReservedName $name $y)))))

; The reasons a pattern bigraph is not solid (BigraphER place.ml:243-260, link.ml:314-331), plus a closed
; edge with no port, which no node map would fix.
(= (bg--solidity $b)
   (let* (($place (bg-place $b))
          ($link (bg-link $b))
          ($parents (map-atom $place $row (index-atom $row 2)))
          ($site-parents (map-atom (filter-atom $place $row (bg--site? (index-atom $row 1))) $row (index-atom $row 2)))
          ($port-links (map-atom (filter-atom $link $row (bg--headed? P $row)) $row (index-atom $row 3)))
          ($inner-links (map-atom (filter-atom $link $row (bg--headed? I $row)) $row (index-atom $row 2)))
          ($inner-edges (filter-atom $inner-links $l (bg--headed? Edge $l))))
     (bg--flat ((map-atom (subtraction-atom (map-atom (bg--range (bg-roots $b)) $j (Root $j)) $parents) $r (IdleRoot $r))
                (map-atom (filter-atom $site-parents $p (bg--root? $p)) $p (SiteUnderRoot $p))
                (map-atom (bg--duplicates $site-parents) $p (TwoSites $p))
                (map-atom (subtraction-atom (map-atom (bg-outer-names $b) $y (Name $y)) $port-links) $l (IdleName $l))
                (map-atom (filter-atom $inner-links $l (bg--headed? Name $l)) $l (InnerNameOnName $l))
                (map-atom (bg--duplicates $inner-edges) $l (SharedInnerName $l))
                (map-atom (subtraction-atom (unique-atom $inner-edges) $port-links) $l (PortlessEdge $l))))))

(= (bg--eta-faults $name $redex $reactum $eta)
   (if (bg--headed? Eta $eta)
       (let* (($entries (cdr-atom $eta))
              ($good (filter-atom $entries $e (bg--eta-entry? $e (bg-sites $reactum) (bg-sites $redex))))
              ($ks (map-atom $good $e (index-atom $e 0))))
         (bg--flat ((map-atom (filter-atom $entries $e (not (bg--eta-entry? $e (bg-sites $reactum) (bg-sites $redex)))) $e (BadEta $name $e))
                    (map-atom (bg--duplicates $ks) $k (BadEta $name (Twice $k)))
                    (map-atom (subtraction-atom (bg--range (bg-sites $reactum)) $ks) $k (BadEta $name (Untaken $k))))))
       (cons-atom (BadEta $name $eta) ())))
(= (bg--eta-entry? $e $reactum-sites $redex-sites)
   (if (bg--list? $e)
       (if (== (size-atom $e) 2)
           (let ($k $j) $e
             (if (bg--natural? $k) (if (bg--natural? $j) (if (< $k $reactum-sites) (< $j $redex-sites) False) False) False))
           False)
       False))

; A kernel condition is (Present|Absent Context|Parameter|(Parameter k) B), B a solid bigraph. Other heads
; belong to a projection's own bg-holds-condition clause and are not checked here.
; am[rests-on c-brs-k-conditions-occur-1018@c9b346]
(= (bg--condition-faults $sig $name $redex $conditions)
   (if (bg--headed? Conditions $conditions)
       (bg--flat (map-atom (cdr-atom $conditions) $c (bg--one-condition-faults $sig $name $redex $c)))
       (cons-atom (BadConditions $name $conditions) ())))
(= (bg--one-condition-faults $sig $name $redex $c)
   (if (or (bg--headed? Present $c) (bg--headed? Absent $c))
       (if (== (size-atom $c) 3)
           (let (($kind $where $pattern)) (cons-atom $c ())
             (if (bg--location? $where (bg-sites $redex))
                 (let $faults (bg--term-faults $sig $pattern)
                   (if (== $faults ())
                       (map-atom (bg--solidity $pattern) $why (BadCondition $name $c (NotSolid $why)))
                       (map-atom $faults $f (BadCondition $name $c $f))))
                 (cons-atom (BadCondition $name $c BadLocation) ())))
           (cons-atom (BadCondition $name $c BadShape) ()))
       ()))
(= (bg--location? $where $sites)
   (case $where
     ((Context True)
      (Parameter True)
      ((Parameter $k) (if (bg--natural? $k) (< $k $sites) False))
      ($other False))))

; ===== Occurrences =====================================================================================
; An occurrence of a solid redex R in a bigraph G (Milner 2009, chapter 7: G = C o (R x id) o D) is fixed
; by an injective, control-preserving node map that keeps nesting, from which follow:
;   Roots   (At j P): the place of G holding R's region j; no image is P or above it, and under the
;           signature P and everything above it are active;
;   Edges   (Image E E'): R's closed edge E as G's edge E', injective, holding exactly the images of E's
;           ports plus, when R has an inner name on E, only ports of parameter nodes or G's inner names;
;   Names   (Image Y L): the link L of G that R's outer name Y reaches; two names may share one link, never
;           an edge some closed edge of R took;
;   Inners  (Image X L): the link of G that R's inner name X reaches;
;   Params  (At k (C ...)): the children of site k's parent image that are no image, k's parameter.
; Every port keeps its position: the image of port i of a redex node is port i of its image node.
; am[implements a-brs-k-occurrence-1018@0ed298] am[rests-on c-brs-k-closed-edge-exact-1018@5cb9f0]
; am[rests-on c-brs-k-open-names-function-1018@71fa97] am[rests-on c-integrate-brs-positional-oracle-1018@6f9f3a]

; An index over G: (BgIndex RECORDS ROOTKIDS POINTS BYCONTROL). RECORDS maps each node id to (BgRec ID
; CONTROL PARENT KIDS PORTS), KIDS its children (node ids and sites) and PORTS its links in port order;
; ROOTKIDS lists (BgGroup (Root j) KIDS); POINTS maps each link to (BgGroup LINK (POINT ...)), a point
; (Port ID K) or (Inner X); BYCONTROL maps each control to (BgGroup CONTROL (ID ...)).
; Time: four sorts, n log n for n rows, one merge of them by id and three tree builds, linear.
; am[implements a-brs-k-st-index-1018@191a78]
(= (bg--index $g)
   (let* (($nodes (msort (bg-nodes $g)))
          ($place (bg-place $g))
          ($link (bg-link $g))
          ($parents (msort (filter-atom $place $row (not (bg--site? (index-atom $row 1))))))
          ($kids (bg--group (msort (map-atom $place $row (BgPair (index-atom $row 2) (index-atom $row 1))))))
          ($ports (bg--group (msort (map-atom (filter-atom $link $row (bg--headed? P $row)) $row
                                     (BgPair (index-atom $row 1) (BgPair (index-atom $row 2) (index-atom $row 3)))))))
          ($records (bg--records $nodes $parents (filter-atom $kids $grp (not (bg--root? (index-atom $grp 1)))) $ports))
          ($rootkids (filter-atom $kids $grp (bg--root? (index-atom $grp 1))))
          ($points (bg--group (msort (map-atom $link $row (bg--point-pair $row)))))
          ($bycontrol (bg--group (msort (map-atom $nodes $row (BgPair (index-atom $row 2) (index-atom $row 1)))))))
     (BgIndex (bg--map $records) $rootkids (bg--map $points) (bg--map $bycontrol))))

; NODES and PARENTS sorted by id over one id set; KIDS and PORTS grouped by id over subsets of it, in the
; same order, so a head is taken exactly when its key is the current id.
(= (bg--records $nodes $parents $kids $ports)
   (if (== $nodes ()) ()
       (let* ((($node $more-nodes) (decons-atom $nodes))
              ((N $id $control) $node)
              (($prow $more-parents) (decons-atom $parents))
              ($take-kids (bg--head-key? $id $kids))
              ($take-ports (bg--head-key? $id $ports)))
         (cons-atom (BgRec $id $control (index-atom $prow 2)
                           (if $take-kids (index-atom (car-atom $kids) 2) ())
                           (if $take-ports (map-atom (index-atom (car-atom $ports) 2) $pair (index-atom $pair 2)) ()))
                    (bg--records $more-nodes $more-parents
                                 (if $take-kids (cdr-atom $kids) $kids)
                                 (if $take-ports (cdr-atom $ports) $ports))))))
(= (bg--head-key? $key $groups) (if (== $groups ()) False (== (index-atom (car-atom $groups) 1) $key)))
(= (bg--point-pair $row)
   (case $row
     (((P $id $k $l) (BgPair $l (Port $id $k)))
      ((I $x $l) (BgPair $l (Inner $x))))))

(= (bg--record $ix $id) (bg--map-row $id (index-atom $ix 1)))
(= (bg--kids-of $ix $place)
   (if (bg--root? $place)
       (bg--assoc $place (index-atom $ix 2) ())
       (let $rec (bg--record $ix $place) (if (== $rec ()) () (index-atom $rec 4)))))
(= (bg--points-of $ix $l) (bg--map-value $l (index-atom $ix 3) ()))

; The node ids of IDS and of everything below them. Time: one record lookup per node below.
(= (bg--below $ix $ids)
   (if (== $ids ()) ()
       (let $nodes (filter-atom $ids $i (not (bg--site? $i)))
         (append $nodes (bg--below $ix (bg--flat (map-atom $nodes $i (bg--kids-of $ix $i))))))))

; (BgRedex RNODES EDGEPORTS INNERS ROOTS): RNODES (BgRnode ID CONTROL PARENT NKIDS SITE PORTS) parent-first,
; NKIDS its node children, SITE its one site's index or -1, PORTS its links in port order; EDGEPORTS
; (BgGroup E ((Port ID K) ...)) for each closed edge; INNERS (Image X LINK) for each inner name.
(= (bg--redex $r)
   (let* (($place (bg-place $r))
          ($link (bg-link $r))
          ($kids (bg--group (msort (map-atom $place $row (BgPair (index-atom $row 2) (index-atom $row 1))))))
          ($order (bg--parent-first (map-atom (bg--range (bg-roots $r)) $j (Root $j)) $kids))
          ($ports (bg--group (msort (map-atom (filter-atom $link $row (bg--headed? P $row)) $row
                                     (BgPair (index-atom $row 1) (BgPair (index-atom $row 2) (index-atom $row 3)))))))
          ($edge-ports (bg--group (msort (bg--flat (map-atom (filter-atom $link $row (bg--headed? P $row)) $row
                                    (case (index-atom $row 3)
                                      (((Edge $e) (cons-atom (BgPair $e (Port (index-atom $row 1) (index-atom $row 2))) ()))
                                       ($other ()))))))))
          ($inners (map-atom (filter-atom $link $row (bg--headed? I $row)) $row (Image (index-atom $row 1) (index-atom $row 2)))))
     (BgRedex (map-atom $order $id (bg--rnode $id (bg-nodes $r) $place $kids $ports)) $edge-ports $inners (bg-roots $r))))
(= (bg--parent-first $frontier $kids)
   (if (== $frontier ()) ()
       (let $level (filter-atom (bg--flat (map-atom $frontier $p (bg--assoc $p $kids ()))) $c (not (bg--site? $c)))
         (append $level (bg--parent-first $level $kids)))))
(= (bg--rnode $id $nodes $place $kids $ports)
   (let* (($children (bg--assoc $id $kids ()))
          ($sites (filter-atom $children $c (bg--site? $c))))
     (BgRnode $id (index-atom (bg--row-with 1 $id $nodes) 2) (index-atom (bg--row-with 1 $id $place) 2)
              (size-atom (filter-atom $children $c (not (bg--site? $c))))
              (if (== $sites ()) -1 (index-atom (car-atom $sites) 1))
              (map-atom (bg--assoc $id $ports ()) $pair (index-atom $pair 2)))))

; Every embedding of REDEX in the bigraph IX indexes, one answer each, as (BgEmbedding MAP EMAP NMAP RHO
; PARAMS INNERS). SIG gives control kinds for active context; (Signature) treats every control as active.
; PINS, (Image RID AID) rows, fix the images of the redex nodes they name, so checking a given node map
; runs the search that finds one; () pins nothing.
; Time: per search node, a record lookup (log n) and a scan of the partial maps (k) for each of the redex
; node's ports; the search tree is pruned by control, nesting, degree and links at every node.
(= (bg--embedding $sig $redex $ix $pins)
   (let* (($rx (bg--redex $redex))
          ($st (bg--assign $ix (index-atom $rx 1) (BgSt () () () () ()) $pins)))
     (bg--finish $sig $ix $rx $st)))

; superpose takes the list it spreads from a variable: given a call, it spreads the call's own parts.
(= (bg--assign $ix $rnodes $st $pins)
   (if (== $rnodes ()) $st
       (let* ((($rnode $rest) (decons-atom $rnodes))
              ($candidates (bg--candidates $ix $rnode $st $pins))
              ($aid (superpose $candidates))
              ($next (bg--extend $ix $rnode $aid $st)))
         (bg--assign $ix $rest $next $pins))))

; A region's first node may be any node of its control; every later node of that region must be a child
; of the region's place, and every other node a child of its parent's image. A pinned node's one candidate
; is its pin, when the pin is one of these.
(= (bg--candidates $ix $rnode $st $pins)
   (let $pin (bg--find (index-atom $rnode 1) $pins)
     (if (== $pin ())
         (bg--placed-candidates $ix $rnode $st)
         (filter-atom (bg--placed-candidates $ix $rnode $st) $aid (== $aid (car-atom $pin))))))
(= (bg--placed-candidates $ix (BgRnode $rid $control $parent $nkids $site $ports) (BgSt $map $used $emap $nmap $rho))
   (case $parent
     (((Root $j)
       (let $place (bg--find $j $rho)
         (if (== $place ()) (bg--map-value $control (index-atom $ix 4) ()) (bg--kids-of $ix (car-atom $place)))))
      ($other (bg--kids-of $ix (bg--assoc $parent $map ()))))))

; am[implements a-brs-k-member-once-1018@ed3afd]
(= (bg--extend $ix (BgRnode $rid $control $parent $nkids $site $rports) $aid (BgSt $map $used $emap $nmap $rho))
   (let $rec (bg--record $ix $aid)
     (if (== $rec ())
         (empty)
         (let (BgRec $id $acontrol $aparent $akids $aports) $rec
           (if (== $acontrol $control)
               (if (bg--member? $aid $used)
                   (empty)
                   (if (bg--degree-ok? (size-atom $akids) $nkids $site)
                       (let (BgLinks $emap2 $nmap2) (bg--link-ports $rports $aports (BgLinks $emap $nmap))
                         (BgSt (cons-atom (Image $rid $aid) $map) (cons-atom $aid $used) $emap2 $nmap2
                               (bg--root-image $parent $aparent $rho)))
                       (empty)))
               (empty))))))
(= (bg--degree-ok? $akids $nkids $site) (if (== $site -1) (== $akids $nkids) (>= $akids $nkids)))
(= (bg--root-image $parent $aparent $rho)
   (case $parent
     (((Root $j) (if (== (bg--find $j $rho) ()) (cons-atom (At $j $aparent) $rho) $rho))
      ($other $rho))))

; The edge and name maps (BgLinks EMAP NMAP) extended by one node's ports, or no answer when a port
; contradicts them.
(= (bg--link-ports $rports $aports $links)
   (if (== $rports ())
       $links
       (bg--link-ports (cdr-atom $rports) (cdr-atom $aports) (bg--link-port (car-atom $rports) (car-atom $aports) $links))))
; The maps with the redex port's link LR matched to the agent port's link LA, or no answer.
(= (bg--link-port $lr $la (BgLinks $emap $nmap))
   (case $lr
     (((Edge $re)
       (case $la
         (((Edge $ae)
           (let $known (bg--find $re $emap)
             (if (== $known ())
                 (if (bg--edge-free? $ae $emap $nmap) (BgLinks (cons-atom (Image $re $ae) $emap) $nmap) (empty))
                 (if (== (car-atom $known) $ae) (BgLinks $emap $nmap) (empty)))))
          ($other (empty)))))
      ((Name $y)
       (let $known (bg--find $y $nmap)
         (if (== $known ())
             (if (bg--not-a-taken-edge? $la $emap) (BgLinks $emap (cons-atom (Image $y $la) $nmap)) (empty))
             (if (== (car-atom $known) $la) (BgLinks $emap $nmap) (empty))))))))
; am[implements a-brs-k-member-once-1018@ed3afd]
(= (bg--edge-free? $ae $emap $nmap)
   (if (bg--member? $ae (bg--values $emap)) False (not (bg--member? (Edge $ae) (bg--values $nmap)))))
; am[implements a-brs-k-member-once-1018@ed3afd]
(= (bg--not-a-taken-edge? $la $emap)
   (case $la (((Edge $ae) (not (bg--member? $ae (bg--values $emap)))) ($other True))))

(= (bg--finish $sig $ix (BgRedex $rnodes $edge-ports $inners $roots) (BgSt $map $used $emap $nmap $rho))
   (if (bg--all-active? $sig $ix $rho $used)
       (let $params (bg--params $ix $rnodes $map $used)
         (if (bg--edges-exact? $ix $edge-ports $inners $map $emap $params)
             (BgEmbedding $map $emap $nmap $rho $params
                          (map-atom $inners $row (Image (index-atom $row 1) (bg--image-link (index-atom $row 2) $emap $nmap))))
             (empty)))
       (empty)))

; No region's place is an image or lies below one, and, under SIG, no place from it up to its root is
; passive.
(= (bg--all-active? $sig $ix $rho $used)
   (if (== $rho ()) True
       (let ($row $rest) (decons-atom $rho)
         (if (bg--context-ok? $sig $ix (index-atom $row 2) $used) (bg--all-active? $sig $ix $rest $used) False))))
; am[implements a-brs-k-member-once-1018@ed3afd]
(= (bg--context-ok? $sig $ix $place $used)
   (if (bg--root? $place) True
       (if (bg--member? $place $used) False
           (let (BgRec $id $control $parent $kids $ports) (bg--record $ix $place)
             (if (== (bg-kind $sig $control) passive) False (bg--context-ok? $sig $ix $parent $used))))))

(= (bg--params $ix $rnodes $map $used)
   (map-atom (filter-atom $rnodes $rn (>= (index-atom $rn 5) 0)) $rn
     (At (index-atom $rn 5) (msort (subtraction-atom (bg--kids-of $ix (bg--assoc (index-atom $rn 1) $map ())) $used)))))

; Each closed redex edge's image holds the images of its ports and, only where an inner name reaches the
; edge, ports of parameter nodes or inner names of G besides. The parameter's nodes are collected only
; for such an edge.
(= (bg--edges-exact? $ix $edge-ports $inners $map $emap $params)
   (if (== $emap ())
       True
       (if (bg--edge-exact? $ix $edge-ports $inners $map (car-atom $emap) $params)
           (bg--edges-exact? $ix $edge-ports $inners $map (cdr-atom $emap) $params)
           False)))
; am[implements a-brs-k-member-once-1018@ed3afd]
(= (bg--edge-exact? $ix $edge-ports $inners $map (Image $re $ae) $params)
   (let $extra (subtraction-atom (bg--points-of $ix (Edge $ae)) (map-atom (bg--assoc $re $edge-ports ()) $pt (bg--port-image $pt $map)))
     (if (== $extra ())
         True
         (if (bg--member? (Edge $re) (bg--values $inners))
             (bg--parameter-points? $extra (bg--set (bg--below $ix (bg--flat (bg--values $params)))))
             False))))
(= (bg--port-image (Port $rid $k) $map) (Port (bg--assoc $rid $map ()) $k))
(= (bg--parameter-points? $points $below)
   (if (== $points ())
       True
       (if (bg--parameter-point? (car-atom $points) $below) (bg--parameter-points? (cdr-atom $points) $below) False)))
(= (bg--parameter-point? $point $below) (case $point (((Inner $x) True) ((Port $id $k) (bg--in? $id $below)))))
(= (bg--image-link $l $emap $nmap)
   (case $l
     (((Edge $re) (Edge (bg--assoc $re $emap ())))
      ((Name $y) (bg--assoc $y $nmap ())))))

; Every occurrence of RULE in G whose application conditions hold, one answer each:
; (Occurrence NAME (Roots ...) (Nodes ...) (Edges ...) (Names ...) (Inners ...) (Params ...)).
; A condition no clause decides answers (Error COND (UnhandledCondition ANSWERS)) in its place. With PINS,
; only the occurrences whose node map agrees with them.
; am[implements a-brs-k-occurrence-1018@0ed298]
(= (bg-occurrence $sig $rule $g) (bg--occurrence-in $sig $rule $g (bg--index $g) ()))
(= (bg--occurrence-in $sig $rule $g $ix $pins)
   (let* (((Rule $name $redex $reactum $eta $conditions $priority) $rule)
          ((BgEmbedding $map $emap $nmap $rho $params $inners) (bg--embedding $sig $redex $ix $pins))
          ($occ (Occurrence $name (cons-atom Roots (msort $rho)) (cons-atom Nodes (msort $map))
                            (cons-atom Edges (msort $emap)) (cons-atom Names (msort $nmap))
                            (cons-atom Inners (msort $inners)) (cons-atom Params (msort $params)))))
     (bg--admitted (cdr-atom $conditions) $occ $g)))

(= (bg--admitted $conditions $occ $g)
   (if (== $conditions ())
       $occ
       (let* ((($c $rest) (decons-atom $conditions))
              ($answers (collapse (bg-holds-condition $c $occ $g))))
         (case $answers
           (((True) (bg--admitted $rest $occ $g))
            ((False) (empty))
            ($other (Error $c (UnhandledCondition $answers))))))))

(= (bg--occurrence-section $occ $head) (cdr-atom (car-atom (filter-atom (cdr-atom (cdr-atom $occ)) $s (bg--headed? $head $s)))))

; What OCC sends a redex node, (Edge RE) or (Name Y) to; () when OCC has no such key.
(= (bg-image $occ $x)
   (case $x
     (((Edge $re) (let $found (bg--find $re (bg--occurrence-section $occ Edges))
                    (if (== $found ()) () (Edge (car-atom $found)))))
      ((Name $y) (bg--assoc $y (bg--occurrence-section $occ Names) ()))
      ($rid (bg--assoc $rid (bg--occurrence-section $occ Nodes) ())))))
; Site K's parameter: the ids at its roots, () when the redex has no site K.
(= (bg-parameter $occ $k) (bg--assoc $k (bg--occurrence-section $occ Params) ()))

; Conditions of conditional bigraphs (Archibald, Calder, Sevegnani, ICGT 2020): B must, or must not, occur
; in the occurrence's context, its whole parameter, or one site's parameter. A projection adds clauses
; for its own condition heads.
; am[implements c-brs-k-conditions-occur-1018@c9b346]
(= (bg-holds-condition (Present $where $pattern) $occ $g) (bg--occurs-in? $where $pattern $occ $g))
(= (bg-holds-condition (Absent $where $pattern) $occ $g) (not (bg--occurs-in? $where $pattern $occ $g)))
(= (bg--occurs-in? $where $pattern $occ $g)
   (not (== (collapse (once (bg--embedding (Signature) $pattern (bg--index (bg--condition-target $where $occ $g)) ()))) ())))
(= (bg--condition-target $where $occ $g)
   (let (Decomposition $context $parameter) (bg-decompose $occ $g)
     (case $where
       ((Context $context)
        (Parameter $parameter)
        ((Parameter $k) (bg--component $parameter $k))))))

; ===== Decomposition ===================================================================================
; OCC's decomposition of the ground G = C o (R x id_I) o D (Milner 2009): C holds the context nodes, a site
; for each redex region and inner names for R's outer names and for I; D holds the parameter nodes, a
; region for each redex site and outer names for R's inner names and for I. I has one name (Via LINK) for
; each link of G that the parameter reaches outside the redex and outside itself.
; Time: n log n: G's index, sets of the image and parameter nodes, and one tree lookup per row of G.
; am[implements a-brs-k-react-algebra-1018@fd3d1f] am[implements a-brs-k-st-reaction-1018@560e12]
(= (bg-decompose $occ $g) (bg--decompose $occ $g (bg--index $g)))
; am[implements a-brs-k-member-once-1018@ed3afd]
(= (bg--decompose $occ $g $ix)
   (let* (($images (bg--set (bg--values (bg--occurrence-section $occ Nodes))))
          ($params (bg--occurrence-section $occ Params))
          ($parameter-ids (bg--below $ix (bg--flat (bg--values $params))))
          ($parameter-nodes (bg--set $parameter-ids))
          ($edge-images (map-atom (bg--occurrence-section $occ Edges) $row (Edge (index-atom $row 2))))
          ($inners (bg--occurrence-section $occ Inners))
          ($names (bg--occurrence-section $occ Names))
          ($roots (bg--occurrence-section $occ Roots))
          ($parameter-ports (bg--flat (map-atom $parameter-ids $id (bg--port-rows $id 0 (index-atom (bg--record $ix $id) 5)))))
          ($internal (bg--set (bg--internal-edges $ix $parameter-ports $parameter-nodes $edge-images)))
          ($vias (unique-atom (bg--flat (map-atom $parameter-ports $row
                   (let $l (index-atom $row 3)
                     (if (bg--member? $l $edge-images) () (if (bg--in? $l $internal) () (cons-atom $l ())))))))))
     (Decomposition
       (bg-term (size-atom $roots) (append (bg--keys $names) (map-atom $vias $l (Via $l)))
                (bg-roots $g) (bg-outer-names $g)
                (filter-atom (bg-nodes $g) $row (bg--context-node? (index-atom $row 1) $images $parameter-nodes))
                (append (filter-atom (bg-place $g) $row (bg--context-node? (index-atom $row 1) $images $parameter-nodes))
                        (map-atom $roots $row (In (Site (index-atom $row 1)) (index-atom $row 2))))
                (append (filter-atom (bg-link $g) $row
                          (if (bg--row? P 4 $row) (bg--context-node? (index-atom $row 1) $images $parameter-nodes) False))
                        (append (map-atom $names $row (I (index-atom $row 1) (index-atom $row 2)))
                                (map-atom $vias $l (I (Via $l) $l)))))
       (bg-term 0 () (size-atom $params) (append (bg--keys $inners) (map-atom $vias $l (Via $l)))
                (map-atom $parameter-ids $id (N $id (index-atom (bg--record $ix $id) 2)))
                (bg--parameter-place $ix $params $parameter-ids)
                (map-atom $parameter-ports $row (bg--parameter-port $row $inners $internal))))))
; Neither an image nor a parameter node.
(= (bg--context-node? $id $images $parameter-nodes)
   (if (bg--in? $id $images) False (not (bg--in? $id $parameter-nodes))))
; Edges every point of which is a parameter port, which stay inside D. The edge images are the redex's
; closed edges, a handful, so scanning them stays short.
; am[implements a-brs-k-member-once-1018@ed3afd]
(= (bg--internal-edges $ix $parameter-ports $parameter-nodes $edge-images)
   (filter-atom (unique-atom (filter-atom (map-atom $parameter-ports $row (index-atom $row 3)) $l (bg--headed? Edge $l))) $l
     (if (bg--member? $l $edge-images) False (bg--all-parameter-ports? (bg--points-of $ix $l) $parameter-nodes))))
(= (bg--all-parameter-ports? $points $parameter-nodes)
   (if (== $points ()) True
       (let ($point $rest) (decons-atom $points)
         (case $point
           (((Port $id $k) (if (bg--in? $id $parameter-nodes) (bg--all-parameter-ports? $rest $parameter-nodes) False))
            ($other False))))))
; D's place rows: each parameter root in its site's region and every other parameter node in its parent.
(= (bg--parameter-place $ix $params $parameter-ids)
   (let* (($roots (bg--flat (map-atom $params $row (map-atom (index-atom $row 2) $c (In $c (Root (index-atom $row 1)))))))
          ($root-set (bg--set (map-atom $roots $r (index-atom $r 1)))))
     (append $roots
             (bg--flat (map-atom $parameter-ids $id
               (if (bg--in? $id $root-set) () (cons-atom (In $id (index-atom (bg--record $ix $id) 3)) ())))))))
(= (bg--parameter-port (P $id $k $l) $inners $internal)
   (let $through (filter-atom $inners $row (== (index-atom $row 2) $l))
     (if (== $through ())
         (if (bg--in? $l $internal) (P $id $k $l) (P $id $k (Name (Via $l))))
         (P $id $k (Name (index-atom (car-atom $through) 1))))))

; D's region K as a prime bigraph keeping D's outer names, a link leaving the region becoming the name
; (Via LINK). Time: D's index and one tree lookup per row of the region.
(= (bg--component $d $k)
   (let* (($ix (bg--index $d))
          ($id-list (bg--below $ix (bg--kids-of $ix (Root $k))))
          ($ids (bg--set $id-list))
          ($ports (bg--flat (map-atom $id-list $id (bg--port-rows $id 0 (index-atom (bg--record $ix $id) 5)))))
          ($leaving (unique-atom (filter-atom (map-atom $ports $row (index-atom $row 3)) $l
                      (if (bg--headed? Edge $l) (not (bg--all-parameter-ports? (bg--points-of $ix $l) $ids)) False))))
          ($leaving-set (bg--set $leaving)))
     (bg-term 0 () 1 (append (bg-outer-names $d) (map-atom $leaving $l (Via $l)))
              (map-atom $id-list $id (N $id (index-atom (bg--record $ix $id) 2)))
              (map-atom $id-list $id
                (let $parent (index-atom (bg--record $ix $id) 3) (In $id (if (== $parent (Root $k)) (Root 0) $parent))))
              (map-atom $ports $row
                (if (bg--in? (index-atom $row 3) $leaving-set)
                    (P (index-atom $row 1) (index-atom $row 2) (Name (Via (index-atom $row 3))))
                    $row)))))

; ===== Algebra =========================================================================================
; Composition, tensor, parallel and merge products, as BigraphER's comp, tens, ppar and par.
; am[implements a-brs-k-algebra-1018@e81ae4]

; F o G: G's roots fill F's sites and G's outer names meet F's inner names. Supports must be disjoint.
; Time: maps of F's site parents and inner links, then one tree lookup per row of G and the sort of the
; result's rows, n log n.
(= (bg--compose $f $g)
   (let* (($fplace (bg-place $f))
          ($flink (bg-link $f))
          ($site-parents (bg--map (msort (map-atom (filter-atom $fplace $row (bg--site? (index-atom $row 1))) $row
                                           (At (index-atom (index-atom $row 1) 1) (index-atom $row 2))))))
          ($inner-links (bg--map (msort (map-atom (filter-atom $flink $row (bg--headed? I $row)) $row
                                          (Image (index-atom $row 1) (index-atom $row 2)))))))
     (bg-term (bg-sites $g) (bg-inner-names $g) (bg-roots $f) (bg-outer-names $f)
              (append (bg-nodes $f) (bg-nodes $g))
              (append (filter-atom $fplace $row (not (bg--site? (index-atom $row 1))))
                      (map-atom (bg-place $g) $row (bg--composed-place $row $site-parents)))
              (append (filter-atom $flink $row (bg--headed? P $row))
                      (map-atom (bg-link $g) $row (bg--composed-link $row $inner-links))))))
(= (bg--composed-place (In $c $p) $site-parents)
   (case $p (((Root $j) (In $c (bg--map-value $j $site-parents ()))) ($other (In $c $p)))))
(= (bg--composed-link $row $inner-links)
   (case $row
     (((P $id $k (Name $y)) (P $id $k (bg--map-value $y $inner-links ())))
      ((I $x (Name $y)) (I $x (bg--map-value $y $inner-links ())))
      ($other $row))))

(= (bg-compose $f $g)
   (let $faults (bg--flat ((if (== (bg-sites $f) (bg-roots $g)) () (cons-atom (InterfaceMismatch Places (bg-sites $f) (bg-roots $g)) ()))
                           (if (== (msort (bg-inner-names $f)) (msort (bg-outer-names $g))) () (cons-atom (InterfaceMismatch Names (bg-inner-names $f) (bg-outer-names $g)) ()))
                           (bg--support-faults $f $g)))
     (if (== $faults ()) (bg--compose $f $g) (Refused bg-compose $faults))))
(= (bg--support-faults $f $g)
   (append (map-atom (intersection-atom (bg--ids $f) (bg--ids $g)) $id (SharedNode $id))
           (map-atom (intersection-atom (bg--edges $f) (bg--edges $g)) $e (SharedEdge $e))))

; F and G side by side, G's roots and sites numbered after F's, under the outer names given: F x G keeps
; both name sets apart, F || G joins a name both have into one link.
(= (bg--juxtapose $f $g $outer-names)
   (let* (($rf (bg-roots $f)) ($sf (bg-sites $f)))
     (bg-term (+ $sf (bg-sites $g)) (append (bg-inner-names $f) (bg-inner-names $g))
              (+ $rf (bg-roots $g)) $outer-names
              (append (bg-nodes $f) (bg-nodes $g))
              (append (bg-place $f) (map-atom (bg-place $g) $row (bg--shifted-place $row $rf $sf)))
              (append (bg-link $f) (bg-link $g)))))
; A case pattern's variables belong to the whole clause, so the two cases bind different names.
(= (bg--shifted-place (In $c $p) $rf $sf)
   (In (case $c (((Site $k) (Site (+ $k $sf))) ($child $child)))
       (case $p (((Root $j) (Root (+ $j $rf))) ($parent $parent)))))
(= (bg--tensor $f $g) (bg--juxtapose $f $g (append (bg-outer-names $f) (bg-outer-names $g))))
(= (bg--parallel $f $g) (bg--juxtapose $f $g (unique-atom (append (bg-outer-names $f) (bg-outer-names $g)))))

(= (bg-tensor $f $g)
   (let $faults (bg--flat ((bg--support-faults $f $g)
                           (map-atom (intersection-atom (bg-inner-names $f) (bg-inner-names $g)) $x (SharedName Inner $x))
                           (map-atom (intersection-atom (bg-outer-names $f) (bg-outer-names $g)) $y (SharedName Outer $y))))
     (if (== $faults ()) (bg--tensor $f $g) (Refused bg-tensor $faults))))
(= (bg-parallel $f $g)
   (let $faults (append (bg--support-faults $f $g)
                        (map-atom (intersection-atom (bg-inner-names $f) (bg-inner-names $g)) $x (SharedName Inner $x)))
     (if (== $faults ()) (bg--parallel $f $g) (Refused bg-parallel $faults))))
; F | G, BigraphER's par: F || G with all its roots merged into one.
(= (bg-merge-product $f $g)
   (let $p (bg-parallel $f $g)
     (if (bg--headed? Refused $p)
         (Refused bg-merge-product (index-atom $p 2))
         (bg--compose (bg--tensor (bg-merge (bg-roots $p)) (bg-identity 0 (bg-outer-names $p))) $p))))

; One root holding N sites; the identity on M places and the names NAMES.
(= (bg-merge $n) (bg-term $n () 1 () () (map-atom (bg--range $n) $i (In (Site $i) (Root 0))) ()))
(= (bg-identity $m $names)
   (bg-term $m $names $m $names ()
            (map-atom (bg--range $m) $i (In (Site $i) (Root $i)))
            (map-atom $names $x (I $x (Name $x)))))

; ===== Reaction ========================================================================================
; RULE at OCC in the ground G answers (Successor NAME OCC G'), G' = C o (R' x id_I) o eta(D) with C, D and I
; OCC's decomposition (Milner 2009, chapter 8). R' is the reactum, each node id the redex shares taking that
; node's image and every other node and closed edge a fresh id. eta(D) puts at reactum site k the parameter
; of redex site eta(k): the first site taking it keeps its nodes, each later one a copy whose nodes are
; named (new NAME (Copy k) X K), and a parameter no site takes is discarded with everything beneath it.
; Copies keep every link of the original, internal closed edges included. An occurrence whose copies would
; hold a named node answers (Refused NAME OCC (DuplicatesNamed (ID ...))): no reaction clones an observed
; entity, while moving or discarding one stays legal.
; am[implements a-brs-k-react-1018@41ec8d] am[implements a-brs-k-react-algebra-1018@fd3d1f]
; am[rests-on c-brs-k-instantiation-shares-links-1018@fe57cf] am[implements a-brs-k-st-reaction-1018@560e12]
;
; bg-apply rewrites only an OCC that is one of RULE's occurrences in G now: the occurrence search, its node
; map pinned to OCC's, must find OCC itself with every condition holding. Otherwise it answers (BgFaulty
; Occurrence ((NotAnOccurrence NAME))), or the Error of a condition no clause decides, so an occurrence
; kept from an earlier state licenses no rewrite. The search's own paths apply through bg--apply-in, which
; trusts the occurrence they just found, so no match is checked twice.
; am[implements a-brs-k-checked-apply-1018@f3812e] am[addresses i-brs-k-apply-unchecked-1018@ba49d8]
; am[implements a-brs-k-member-once-1018@ed3afd]
(= (bg-apply $sig $rule $g $occ)
   (let* (($ix (bg--index $g))
          ($found (collapse (bg--occurrence-in $sig $rule $g $ix (bg--occurrence-pins $occ)))))
     (if (bg--member? $occ $found)
         (bg--apply-in $rule $g $ix $occ)
         (let $errors (filter-atom $found $answer (bg--headed? Error $answer))
           (if (== $errors ()) (BgFaulty Occurrence ((NotAnOccurrence (index-atom $rule 1)))) (car-atom $errors))))))
; OCC's node map, () for a term without one, which then matches no occurrence.
(= (bg--occurrence-pins $occ)
   (if (bg--headed? Occurrence $occ)
       (if (> (size-atom $occ) 2)
           (let $sections (filter-atom (cdr-atom (cdr-atom $occ)) $s (bg--headed? Nodes $s))
             (if (== $sections ()) () (cdr-atom (car-atom $sections))))
           ())
       ()))
(= (bg--apply-in $rule $g $ix $occ)
   (let* (((Rule $name $redex $reactum $eta-section $conditions $priority) $rule)
          ($eta (cdr-atom $eta-section))
          ($cloned (bg--cloned-named $eta $occ $ix)))
     (if (== $cloned ())
         (Successor $name $occ (bg--rewrite $name $reactum $eta $occ $g $ix))
         (Refused $name $occ (DuplicatesNamed $cloned)))))

(= (bg--cloned-named $eta $occ $ix)
   (let* (($params (bg--occurrence-section $occ Params))
          ($copied (filter-atom (unique-atom (map-atom $eta $entry (index-atom $entry 1))) $j (> (bg--uses $j $eta) 1))))
     (msort (filter-atom (bg--below $ix (bg--flat (map-atom $copied $j (bg--assoc $j $params ())))) $id (not (bg-anonymous? $id))))))
(= (bg--uses $j $eta) (size-atom (filter-atom $eta $entry (== (index-atom $entry 1) $j))))

; Fresh ids are checked against G's node ids and edges alone: the reaction's own bases are pairwise
; distinct, (new NAME ID) for distinct reactum ids and edges and (new NAME (Copy k) X) for distinct site
; and node pairs, so no two ids it makes can meet.
(= (bg--rewrite $name $reactum $eta $occ $g $ix)
   (let* (((Decomposition $context $parameter) (bg--decompose $occ $g $ix))
          ($vias (filter-atom (bg-inner-names $context) $x (bg--headed? Via $x)))
          ($ids (bg--map-tree (index-atom $ix 1)))
          ($body (bg--rename-reactum $name $reactum $occ $ids (bg--set (bg--edges $g))))
          ($instance (bg--instantiate $name $eta $parameter $ids)))
     (bg--compose $context (bg--compose (bg--tensor $body (bg-identity 0 $vias)) $instance))))

; The reactum with each id the redex shares mapped to its image and every other node id and closed edge
; given a fresh id against IDS and EDGES, the trees of G's node ids and edges.
(= (bg--rename-reactum $name $reactum $occ $ids $edges)
   (let* (($node-map (bg--renaming $name (bg--ids $reactum) (bg--occurrence-section $occ Nodes) $ids))
          ($edge-map (bg--renaming $name (bg--edges $reactum) (bg--occurrence-section $occ Edges) $edges)))
     (bg-term (bg-sites $reactum) (bg-inner-names $reactum) (bg-roots $reactum) (bg-outer-names $reactum)
              (map-atom (bg-nodes $reactum) $row (N (bg--assoc (index-atom $row 1) $node-map ()) (index-atom $row 2)))
              (map-atom (bg-place $reactum) $row
                (In (bg--renamed-place (index-atom $row 1) $node-map) (bg--renamed-place (index-atom $row 2) $node-map)))
              (map-atom (bg-link $reactum) $row (bg--renamed-link $row $node-map $edge-map)))))
; Each id of IDS mapped to its image in IMAGES, else to (new NAME ID K) with K fresh against the tree
; TAKEN. Time: one tree lookup per fresh candidate.
(= (bg--renaming $name $ids $images $taken)
   (map-atom $ids $id
     (let $image (bg--find $id $images)
       (if (== $image ())
           (Image $id (bg--fresh-in (new $name $id) $taken))
           (Image $id (car-atom $image))))))
(= (bg--renamed-place $x $node-map) (if (bg--site? $x) $x (if (bg--root? $x) $x (bg--assoc $x $node-map ()))))
(= (bg--renamed-link $row $node-map $edge-map)
   (case $row
     (((P $id $k $l) (P (bg--assoc $id $node-map ()) $k (bg--renamed-edge $l $edge-map)))
      ((I $x $l) (I $x (bg--renamed-edge $l $edge-map))))))
(= (bg--renamed-edge $l $edge-map) (case $l (((Edge $e) (Edge (bg--assoc $e $edge-map ()))) ($other $l))))

; eta(D): reactum site K holds redex site ETA(K)'s region of the parameter D, its first taker keeping the
; nodes and every later one a copy whose ids are fresh against TAKEN, the tree of G's node ids.
; Time: D's index, then per site taking a region one record lookup per node of it and, for a copy, a
; fresh id per node and a map of them, n log n in all.
(= (bg--instantiate $name $eta $parameter $taken)
   (let* (($ix (bg--index $parameter))
          ($entries (msort $eta))
          ($rows (bg--flat (map-atom $entries $entry (bg--instance-part $name $entry $eta $ix $taken)))))
     (bg-term 0 () (size-atom $entries) (bg-outer-names $parameter)
              (map-atom $rows $row (index-atom $row 1))
              (map-atom $rows $row (index-atom $row 2))
              (bg--flat (map-atom $rows $row (index-atom $row 3))))))
(= (bg--instance-part $name $entry $eta $ix $taken)
   (let* ((($k $j) $entry)
          ($roots (bg--kids-of $ix (Root $j)))
          ($ids (bg--below $ix $roots))
          ($map (if (== $k (bg--first-use $j $eta))
                    BgSame
                    (bg--map (msort (map-atom $ids $id (Image $id (bg--fresh-in (new $name (Copy $k) $id) $taken)))))))
          ($root-set (bg--set $roots)))
     (map-atom $ids $id (bg--node-rows (bg--record $ix $id) $root-set $k $map))))
(= (bg--first-use $j $eta)
   (car-atom (msort (map-atom (filter-atom $eta $entry (== (index-atom $entry 1) $j)) $entry (index-atom $entry 0)))))
; An id under MAP: itself where the site keeps the region (BgSame), its copy's id otherwise.
(= (bg--renamed-id $id $map) (if (== $map BgSame) $id (bg--map-value $id $map ())))
(= (bg--node-rows (BgRec $id $control $parent $kids $ports) $root-set $k $map)
   (let $new-id (bg--renamed-id $id $map)
     (BgRows (N $new-id $control)
             (In $new-id (if (bg--in? $id $root-set) (Root $k) (bg--renamed-id $parent $map)))
             (bg--port-rows $new-id 0 $ports))))
(= (bg--port-rows $id $k $links)
   (if (== $links ()) ()
       (let ($l $rest) (decons-atom $links) (cons-atom (P $id $k $l) (bg--port-rows $id (+ $k 1) $rest)))))

; ===== Identity ========================================================================================
; A and B are one state when an isomorphism maps A onto B that fixes named nodes, roots, sites and open
; names, is a bijection on anonymous nodes keeping controls and parents, and a bijection on closed edges
; keeping which positional port or inner name each edge links (contract section 2.2). Anonymous nodes are
; matched parent-first from the roots and the named nodes, which map to themselves: for each matched pair
; of places, the first place's anonymous children of one signature take the second's children of that
; signature, each member picking one node of the group's pool, the first that keeps the edge maps
; consistent first. The edge maps grow as red-black trees in both directions, so a port pair that
; contradicts an earlier one ends its branch at once; a complete map is checked against every place and
; link row.
; Time: two views at bg--view's cost, then one pick per anonymous node and one tree lookup or insertion per
; port, n log n, and signature comparisons while grouping and matching children, within bg--view's
; (V + n) log n bound, while no group needs a second pick; backtracking is exponential only across
; equal-signature siblings that the link rows tell apart.
; am[implements a-brs-k-iso-1018@f2617a] am[implements a-brs-k-st-iso-1018@7fcfce]
; am[implements a-brs-k-transitions-cache-1018@b1c921]
(= (bg-iso $a $b)
   (if (bg--iso-precheck $a $b) (bg--views-match (bg--view $a) (bg--view $b)) False))
; Isomorphism of two states given their views, which a caller comparing one state with many builds once.
; am[implements a-brs-k-transitions-cache-1018@b1c921]
(= (bg--views-iso $va $vb)
   (if (bg--iso-precheck (index-atom $va 1) (index-atom $vb 1)) (bg--views-match $va $vb) False))
; Whether the search finds an isomorphism between the two viewed states.
; am[implements a-brs-k-transitions-cache-1018@b1c921]
(= (bg--views-match $va $vb) (not (== (collapse (once (bg--iso-search $va $vb))) ())))
; The parts of state S that isomorphism and its bucket read, (BgView S INDEX SIGNATURES), SIGNATURES the
; signature map of INDEX. A view never changes, so a caller comparing one state with many builds it once.
; Time: the index, n log n, and one signature per node built from references to its children's, linear in
; n, plus the comparisons that sort each node's children by signature. A comparison walks two signatures
; while they agree, so the sorts take at most (V + n) log n steps, V the total size of the signatures
; written out in full, n times the mean depth: 2.25n on the room and host scaling states, up to n^2/2 on a
; chain, and walked in full only where siblings repeat a deep subtree. Space: the index's trees and n
; signature rows, O(n + ports) cells, since a signature holds its children's by reference.
; am[implements a-brs-k-transitions-cache-1018@b1c921] am[rests-on c-brs-k-signatures-shared-1018@1858ac]
(= (bg--view $s) (let $ix (bg--index $s) (BgView $s $ix (bg--signature-map $ix))))
(= (bg--iso-precheck $a $b)
   (if (== (bg-sites $a) (bg-sites $b))
       (if (== (bg-roots $a) (bg-roots $b))
           (if (== (msort (bg-inner-names $a)) (msort (bg-inner-names $b)))
               (if (== (msort (bg-outer-names $a)) (msort (bg-outer-names $b)))
                   (if (== (size-atom (bg-nodes $a)) (size-atom (bg-nodes $b)))
                       (if (== (size-atom (bg-link $a)) (size-atom (bg-link $b)))
                           (== (msort (filter-atom (bg-nodes $a) $row (not (bg-anonymous? (index-atom $row 1)))))
                               (msort (filter-atom (bg-nodes $b) $row (not (bg-anonymous? (index-atom $row 1))))))
                           False)
                       False)
                   False)
               False)
           False)
       False))
; The parent-first search over two views, from the roots and the named nodes.
; am[implements a-brs-k-transitions-cache-1018@b1c921]
(= (bg--iso-search (BgView $a $ixa $siga) (BgView $b $ixb $sigb))
   (let* (($named (filter-atom (bg--map-rows (index-atom $ixa 1)) $rec (not (bg-anonymous? (index-atom $rec 1)))))
          ($seed (append (bg--flat (map-atom $named $rec (bg--zip-links (index-atom $rec 5) (index-atom (bg--record $ixb (index-atom $rec 1)) 5))))
                         (map-atom (bg-inner-names $a) $x (BgPair (bg--inner-link $a $x) (bg--inner-link $b $x)))))
          ($edges (bg--link-pairs $seed (BgEdges BgLeaf BgLeaf)))
          ($start (append (map-atom (bg--range (bg-roots $a)) $j (BgPair (Root $j) (Root $j)))
                          (map-atom $named $rec (BgPair (index-atom $rec 1) (index-atom $rec 1))))))
     (bg--iso-walk $start () $edges $ixa $ixb $siga $sigb $a $b)))
(= (bg--inner-link $s $x) (index-atom (car-atom (filter-atom (bg-link $s) $row (if (bg--headed? I $row) (== (index-atom $row 1) $x) False))) 2))
(= (bg--zip-links $as $bs)
   (if (== $as ()) ()
       (let* ((($a $ra) (decons-atom $as)) (($b $rb) (decons-atom $bs)))
         (cons-atom (BgPair $a $b) (bg--zip-links $ra $rb)))))
; The edge maps (BgEdges FORWARD BACKWARD), trees of (Image E F) and (Image F E) rows, extended by pairs
; of corresponding links, or no answer when a pair contradicts them: an open name corresponds only to
; itself, and closed edges correspond one to one.
(= (bg--link-pairs $pairs $edges)
   (if (== $pairs ()) $edges (bg--link-pairs (cdr-atom $pairs) (bg--link-pair (car-atom $pairs) $edges))))
(= (bg--link-pair (BgPair $la $lb) $edges)
   (case $la
     (((Name $y) (if (== $la $lb) $edges (empty)))
      ((Edge $e) (case $lb (((Edge $f) (bg--edge-pair $e $f $edges)) ($other (empty))))))))
(= (bg--edge-pair $e $f (BgEdges $forward $backward))
   (let $known (bg--tree-row $e $forward)
     (if (== $known ())
         (if (bg--in? $f $backward)
             (empty)
             (BgEdges (bg--tree-insert (Image $e $f) $forward) (bg--tree-insert (Image $f $e) $backward)))
         (if (== (index-atom $known 2) $f) (BgEdges $forward $backward) (empty)))))
; PAIRS holds matched places whose children are still to match, MAP the anonymous pairs matched so far as
; (Image X Y) rows.
(= (bg--iso-walk $pairs $map $edges $ixa $ixb $siga $sigb $a $b)
   (if (== $pairs ())
       (bg--iso-close $map $edges $a $b)
       (let* ((($pair $rest) (decons-atom $pairs))
              ((BgPair $pa $pb) $pair)
              ((BgMatched $kids $map2 $edges2)
               (bg--match-groups (bg--signed-kids $ixa $siga $pa) (bg--signed-kids $ixb $sigb $pb) $map $edges $ixa $ixb)))
         (bg--iso-walk (append $kids $rest) $map2 $edges2 $ixa $ixb $siga $sigb $a $b))))
; P's anonymous children grouped by signature: (BgGroup SIGNATURE (ID ...)) in signature order.
(= (bg--signed-kids $ix $sigs $p)
   (bg--group (msort (map-atom (filter-atom (bg--kids-of $ix $p) $c (bg-anonymous? $c)) $c
                       (BgPair (bg--map-value $c $sigs ()) $c)))))
; Each signature group of XS matched with the group of YS that has the same signature, in step:
; (BgMatched PAIRS MAP EDGES) with the matched pairs, or no answer.
(= (bg--match-groups $xs $ys $map $edges $ixa $ixb)
   (if (== $xs ())
       (if (== $ys ()) (BgMatched () $map $edges) (empty))
       (if (== $ys ())
           (empty)
           (let* ((($gx $restx) (decons-atom $xs))
                  (($gy $resty) (decons-atom $ys))
                  ((BgGroup $sx $members) $gx)
                  ((BgGroup $sy $pool) $gy))
             (if (== $sx $sy)
                 (let* (((BgMatched $pairs $map2 $edges2) (bg--match-group $members $pool $map $edges $ixa $ixb))
                        ((BgMatched $more $map3 $edges3) (bg--match-groups $restx $resty $map2 $edges2 $ixa $ixb)))
                   (BgMatched (append $pairs $more) $map3 $edges3))
                 (empty))))))
; Each member of XS takes a node of POOL whose ports keep the edge maps consistent, the pool's earliest
; such node first; the pool must end empty.
(= (bg--match-group $xs $pool $map $edges $ixa $ixb)
   (if (== $xs ())
       (if (== $pool ()) (BgMatched () $map $edges) (empty))
       (let* ((($x $rest) (decons-atom $xs))
              ((BgPick $y $others) (bg--pick $pool))
              ($edges2 (bg--link-pairs (bg--zip-links (index-atom (bg--record $ixa $x) 5) (index-atom (bg--record $ixb $y) 5)) $edges))
              ((BgMatched $pairs $map2 $edges3) (bg--match-group $rest $others (cons-atom (Image $x $y) $map) $edges2 $ixa $ixb)))
         (BgMatched (cons-atom (BgPair $x $y) $pairs) $map2 $edges3))))
(= (bg--iso-close $map $edges $a $b)
   (let* (($nodes (bg--map (msort $map)))
          ((BgEdges $forward $backward) $edges))
     (if (== (msort (map-atom (bg-place $a) $row (In (bg--mapped (index-atom $row 1) $nodes) (bg--mapped (index-atom $row 2) $nodes))))
             (msort (bg-place $b)))
         (if (== (msort (map-atom (bg-link $a) $row (bg--mapped-link $row $nodes $forward))) (msort (bg-link $b)))
             (BgIso $map $edges)
             (empty))
         (empty))))
(= (bg--mapped $p $nodes) (if (bg-anonymous? $p) (bg--map-value $p $nodes ()) $p))
(= (bg--mapped-link $row $nodes $forward)
   (case $row
     (((P $id $k $l) (P (bg--mapped $id $nodes) $k (bg--mapped-edge $l $forward)))
      ((I $x $l) (I $x (bg--mapped-edge $l $forward))))))
; An edge no pair mapped stays apart from every edge of B.
(= (bg--mapped-edge $l $forward)
   (case $l
     (((Edge $e) (let $row (bg--tree-row $e $forward) (if (== $row ()) (Edge (BgUnmapped $e)) (Edge (index-atom $row 2)))))
      ($other $l))))

; The map of (Image ID SIGNATURE) rows for every node of an indexed bigraph, SIGNATURE (Sg NAMED CONTROL
; (KID ...) (COLOUR ...)): NAMED the id of a named node and Anon otherwise, KID its children's signatures
; sorted, COLOUR per port (Open Y), or (Closed (TYPE ...)) for an edge whose points have those
; control-and-port types. Any isomorphism of the contract keeps every signature (AHU 1974 for the place
; forest, refined by links).
; Time: one visit per node building its signature from references to its children's and sorting them,
; and one tree lookup per port, then a sort of the rows by id, n log n; the children's sorts compare
; signatures within the (V + n) log n steps bg--view states.
; am[rests-on c-brs-k-signatures-shared-1018@1858ac]
(= (bg--signature-map $ix)
   (let* (($types (bg--map (bg--edge-types $ix)))
          ((BgSignedKids $sigs $rows)
           (bg--signed-all $ix $types (bg--flat (map-atom (index-atom $ix 2) $grp (index-atom $grp 2))) () ())))
     (bg--map (msort $rows))))
; (BgSigned SIGNATURE ROWS): ID's signature, and ROWS with (Image X SIGNATURE) added for ID and every node
; below it.
(= (bg--signed $ix $types $id $rows)
   (if (bg--site? $id)
       (BgSigned (SiteSig (index-atom $id 1)) $rows)
       (let* (((BgRec $x $control $parent $kids $ports) (bg--record $ix $id))
              ((BgSignedKids $kid-sigs $rows2) (bg--signed-all $ix $types $kids () $rows))
              ($sig (Sg (if (bg-anonymous? $id) Anon $id) $control (msort $kid-sigs) (map-atom $ports $l (bg--colour $l $types)))))
         (BgSigned $sig (cons-atom (Image $id $sig) $rows2)))))
; (BgSignedKids SIGNATURES ROWS): the signatures of IDS, consed onto SIGS, and ROWS with every row their
; subtrees add.
(= (bg--signed-all $ix $types $ids $sigs $rows)
   (if (== $ids ())
       (BgSignedKids $sigs $rows)
       (let* ((($id $rest) (decons-atom $ids))
              ((BgSigned $sig $rows2) (bg--signed $ix $types $id $rows)))
         (bg--signed-all $ix $types $rest (cons-atom $sig $sigs) $rows2))))
(= (bg--colour $l $types) (case $l (((Name $y) (Open $y)) ((Edge $e) (Closed (bg--map-value $l $types ()))))))
; (Image (Edge E) (TYPE ...)) per closed edge in link order, TYPE each point's control and port.
(= (bg--edge-types $ix)
   (map-atom (filter-atom (bg--map-rows (index-atom $ix 3)) $grp (bg--headed? Edge (index-atom $grp 1))) $grp
     (Image (index-atom $grp 1) (msort (map-atom (index-atom $grp 2) $pt (bg--point-type $ix $pt))))))
(= (bg--point-type $ix $pt)
   (case $pt
     (((Port $id $k) (PortType (index-atom (bg--record $ix $id) 2) $k))
      ((Inner $x) (InnerType $x)))))

; An isomorphism invariant of S: its faces and, per root, its children's signatures sorted. Isomorphic
; states share it; search compares states with one bucket by bg-iso, so its completeness never matters.
; am[implements a-brs-k-transitions-cache-1018@b1c921]
(= (bg-bucket $s) (bg--view-bucket (bg--view $s)))
; The bucket read from a view: a site's signature is (SiteSig K) and a node's is its signature map row.
; am[implements a-brs-k-transitions-cache-1018@b1c921]
(= (bg--view-bucket (BgView $s $ix $sigs))
   (Bucket (Inner (bg-sites $s) (msort (bg-inner-names $s))) (Outer (bg-roots $s) (msort (bg-outer-names $s)))
           (map-atom (bg--range (bg-roots $s)) $j
             (At $j (msort (map-atom (bg--kids-of $ix (Root $j)) $k
                              (if (bg--site? $k) (SiteSig (index-atom $k 1)) (bg--map-value $k $sigs ()))))))))

; ===== Successors ======================================================================================
; Every outcome of RULE in G, one per occurrence: (Successor NAME OCC G'), (Refused NAME OCC REASON), or an
; occurrence's Error. One index of G serves the occurrence search and every reaction.
; am[implements a-brs-k-successors-1018@311dd0]
(= (bg-react-outcome $sig $rule $g) (bg--react-outcome-in $sig $rule $g (bg--index $g)))
(= (bg--react-outcome-in $sig $rule $g $ix)
   (let $occ (bg--occurrence-in $sig $rule $g $ix ())
     (if (bg--headed? Error $occ) $occ (bg--apply-in $rule $g $ix $occ))))
; (Step NAME OCC G') for each occurrence of RULE in G that is not refused.
(= (bg-react $sig $rule $g) (bg--react-in $sig $rule $g (bg--index $g)))
(= (bg--react-in $sig $rule $g $ix)
   (case (bg--react-outcome-in $sig $rule $g $ix)
     (((Successor $name $occ $next) (Step $name $occ $next))
      ((Refused $name $occ $reason) (empty))
      ($other $other))))

; Every step of the class of RULES with the largest priority that has one, one step per occurrence: a rule
; takes part only when no rule of larger priority steps in G, as BigraphER scans its priority classes.
; am[rests-on c-brs-k-priority-scan-1018@ffad25]
(= (bg-successors $sig $rules $g) (bg--first-enabled $sig (bg--priority-classes $rules) $g (bg--index $g)))
(= (bg--priority-classes $rules)
   (let $levels (reverse (msort (unique-atom (map-atom $rules $r (bg--priority $r)))))
     (map-atom $levels $p (filter-atom $rules $r (== (bg--priority $r) $p)))))
(= (bg--priority (Rule $name $redex $reactum $eta $conditions (Priority $p))) $p)
(= (bg--first-enabled $sig $classes $g $ix)
   (if (== $classes ()) ()
       (let* ((($class $rest) (decons-atom $classes))
              ($steps (collapse (bg--react-in $sig (superpose $class) $g $ix))))
         (if (== $steps ()) (bg--first-enabled $sig $rest $g $ix) $steps))))

; bg-successors' steps merged by state identity: (Transition G' ((Fired NAME COUNT OCC) ...)) per isomorphism
; class of successor, COUNT the occurrences of NAME reaching it and OCC the first of them. States are
; compared by bucket and then by isomorphism, each successor's view built once and each class keeping its
; representative's; raw counts survive the merge for weighted projections.
; Time: per successor one view at bg--view's cost and its bucket, then one isomorphism search against each
; class whose bucket it shares. Space: each class keeps its representative's view beside its state until
; the merge ends, an index and a signature map per class.
; am[implements c-brs-k-witness-agreed-1018@2d9ea2] am[implements a-brs-k-transitions-cache-1018@b1c921]
; am[rests-on c-brs-k-transitions-rebuilds-1018@7e4420]
(= (bg-transitions $sig $rules $g)
   (map-atom (foldl-atom (bg-successors $sig $rules $g) () $classes $step (bg--merge-step $step $classes)) $c
     (case $c (((BgClass $bucket (BgView $state $ix $sigs) $fireds) (Transition $state $fireds)) ($other $other)))))
; A step joins its class by its view's bucket and isomorphism; any other answer is kept as it is.
; am[implements a-brs-k-transitions-cache-1018@b1c921]
(= (bg--merge-step $step $classes)
   (case $step
     (((Step $name $occ $next) (let $view (bg--view $next) (bg--merge-into $name $occ $view (bg--view-bucket $view) $classes)))
      ($other (append $classes (cons-atom $other ()))))))
; VIEW is the successor's view and BUCKET its bucket.
; am[implements a-brs-k-transitions-cache-1018@b1c921]
(= (bg--merge-into $name $occ $view $bucket $classes)
   (if (== $classes ())
       (cons-atom (BgClass $bucket $view (cons-atom (Fired $name 1 $occ) ())) ())
       (let ($class $rest) (decons-atom $classes)
         (if (bg--same-class? $class $bucket $view)
             (cons-atom (bg--fired-class $class $name $occ) $rest)
             (cons-atom $class (bg--merge-into $name $occ $view $bucket $rest))))))
; am[implements a-brs-k-transitions-cache-1018@b1c921]
(= (bg--same-class? $class $bucket $view)
   (case $class (((BgClass $b $rep $fireds) (if (== $b $bucket) (bg--views-iso $view $rep) False)) ($other False))))
; am[implements a-brs-k-transitions-cache-1018@b1c921]
(= (bg--fired-class (BgClass $b $rep $fireds) $name $occ) (BgClass $b $rep (bg--fire $name $occ $fireds)))
(= (bg--fire $name $occ $fireds)
   (if (== $fireds ())
       (cons-atom (Fired $name 1 $occ) ())
       (let ($fired $rest) (decons-atom $fireds)
         (let (Fired $n $count $first) $fired
           (if (== $n $name)
               (cons-atom (Fired $n (+ $count 1) $first) $rest)
               (cons-atom $fired (bg--fire $name $occ $rest)))))))

; ===== Entries =========================================================================================
; One-answer entries for goal_chainer.runtime.evaluator. Every parameter is typed Atom, so caller data
; enters inert whatever its heads name, and each result keeps its own type, since an entry typed to return
; Atom would answer its body unevaluated. An entry given a state and rules checks them first and answers
; (BgFaulty State (FAULT ...)) or (BgFaulty (Rule NAME) (FAULT ...)) instead of running on a faulty input;
; inside, the kernel trusts what it built. Apply also refuses an occurrence the state does not have now.
; am[implements a-brs-k-evaluator-1018@39680b] am[rests-on c-jk-atom-entry-inert-1018@63e37f]
; am[rests-on c-rt-atom-return-unevaluated-1018@364854]
(: bg-run-faults (-> Atom Atom Expression))
(= (bg-run-faults $sig $term) (bg-faults $sig $term))
(: bg-run-rule-faults (-> Atom Atom Expression))
(= (bg-run-rule-faults $sig $rule) (bg-rule-faults $sig $rule))
(: bg-run-occurrences (-> Atom Atom Atom Expression))
(= (bg-run-occurrences $sig $rule $state)
   (let $faults (bg--input-faults $sig (cons-atom $rule ()) $state)
     (if (== $faults ()) (collapse (bg-occurrence $sig $rule $state)) $faults)))
(: bg-run-apply (-> Atom Atom Atom Atom Expression))
(= (bg-run-apply $sig $rule $state $occ)
   (let $faults (bg--input-faults $sig (cons-atom $rule ()) $state)
     (if (== $faults ()) (bg-apply $sig $rule $state $occ) $faults)))
(: bg-run-outcomes (-> Atom Atom Atom Expression))
(= (bg-run-outcomes $sig $rule $state)
   (let $faults (bg--input-faults $sig (cons-atom $rule ()) $state)
     (if (== $faults ()) (collapse (bg-react-outcome $sig $rule $state)) $faults)))
(: bg-run-successors (-> Atom Atom Atom Expression))
(= (bg-run-successors $sig $rules $state)
   (let $faults (bg--input-faults $sig $rules $state)
     (if (== $faults ()) (bg-successors $sig $rules $state) $faults)))
(: bg-run-transitions (-> Atom Atom Atom Expression))
(= (bg-run-transitions $sig $rules $state)
   (let $faults (bg--input-faults $sig $rules $state)
     (if (== $faults ()) (bg-transitions $sig $rules $state) $faults)))
(: bg-run-iso (-> Atom Atom Bool))
(= (bg-run-iso $a $b) (bg-iso $a $b))
(: bg-run-bucket (-> Atom Expression))
(= (bg-run-bucket $state) (bg-bucket $state))
(: bg-run-decompose (-> Atom Atom Expression))
(= (bg-run-decompose $occ $state) (bg-decompose $occ $state))
(: bg-run-compose (-> Atom Atom Expression))
(= (bg-run-compose $f $g) (bg-compose $f $g))
(: bg-run-tensor (-> Atom Atom Expression))
(= (bg-run-tensor $f $g) (bg-tensor $f $g))
(: bg-run-parallel (-> Atom Atom Expression))
(= (bg-run-parallel $f $g) (bg-parallel $f $g))
(: bg-run-merge-product (-> Atom Atom Expression))
(= (bg-run-merge-product $f $g) (bg-merge-product $f $g))

; () when STATE and every rule of RULES are sound against SIG, else the first faulty one's faults.
(= (bg--input-faults $sig $rules $state)
   (let $faults (bg-faults $sig $state)
     (if (== $faults ()) (bg--rules-faults $sig $rules) (BgFaulty State $faults))))
(= (bg--rules-faults $sig $rules)
   (if (== $rules ())
       ()
       (let* ((($rule $rest) (decons-atom $rules))
              ($faults (bg-rule-faults $sig $rule)))
         (if (== $faults ()) (bg--rules-faults $sig $rest) (BgFaulty (bg--rule-label $rule) $faults)))))
(= (bg--rule-label $rule)
   (case $rule (((Rule $name $redex $reactum $eta $conditions $priority) (Rule $name)) ($other Rule))))

; Every entry once on two rooms whose hosts hold two items each and a rule turning an item online while
; copying its host's other items, with a condition on the context and one on a site's parameter. It runs
; outside speculation when the group is prepared, so the code the entries reach stays compiled; it writes
; nothing and answers True only when every entry answers as this state requires.
; am[implements a-brs-k-evaluator-1018@39680b] am[rests-on c-brs-k-evaluator-agreed-1018@e9d6d0]
(: bg-warm-up (-> Bool))
(= (bg-warm-up)
   (let* (($sig (Signature (Control Room 1 active) (Control Host 1 active) (Control Item 0 atomic)
                           (Control Online 0 atomic) (Control Box 0 passive)))
          ($state (Bigraph (Inner 0 ()) (Outer 1 ())
                    (Nodes (N (new w r 0) Room) (N (new w h 0) Host) (N (new w i 0 0) Item) (N (new w i 0 1) Item)
                           (N (new w r 1) Room) (N (new w h 1) Host) (N (new w i 1 0) Item) (N (new w i 1 1) Item))
                    (Place (In (new w r 0) (Root 0)) (In (new w h 0) (new w r 0)) (In (new w i 0 0) (new w h 0))
                           (In (new w i 0 1) (new w h 0)) (In (new w r 1) (Root 0)) (In (new w h 1) (new w r 1))
                           (In (new w i 1 0) (new w h 1)) (In (new w i 1 1) (new w h 1)))
                    (Link (P (new w r 0) 0 (Edge (w 0))) (P (new w h 0) 0 (Edge (w 0)))
                          (P (new w r 1) 0 (Edge (w 1))) (P (new w h 1) 0 (Edge (w 1))))))
          ($renamed (Bigraph (Inner 0 ()) (Outer 1 ())
                      (Nodes (N (new v r 1) Room) (N (new v h 1) Host) (N (new v i 1 0) Item) (N (new v i 1 1) Item)
                             (N (new v r 0) Room) (N (new v h 0) Host) (N (new v i 0 0) Item) (N (new v i 0 1) Item))
                      (Place (In (new v r 0) (Root 0)) (In (new v h 0) (new v r 0)) (In (new v i 0 0) (new v h 0))
                             (In (new v i 0 1) (new v h 0)) (In (new v r 1) (Root 0)) (In (new v h 1) (new v r 1))
                             (In (new v i 1 0) (new v h 1)) (In (new v i 1 1) (new v h 1)))
                      (Link (P (new v r 0) 0 (Edge (v 0))) (P (new v h 0) 0 (Edge (v 0)))
                            (P (new v r 1) 0 (Edge (v 1))) (P (new v h 1) 0 (Edge (v 1))))))
          ($faulty (Bigraph (Inner 0 ()) (Outer 1 ()) (Nodes (N n Nope)) (Place (In n (Root 0))) (Link)))
          ($room (Bigraph (Inner 1 ()) (Outer 1 (p)) (Nodes (N Q Room)) (Place (In Q (Root 0)) (In (Site 0) Q)) (Link (P Q 0 (Name p)))))
          ($online (Bigraph (Inner 0 ()) (Outer 1 ()) (Nodes (N O Online)) (Place (In O (Root 0))) (Link)))
          ($rule (Rule warm
                   (Bigraph (Inner 1 ()) (Outer 1 ()) (Nodes (N R Room) (N H Host) (N I Item))
                            (Place (In R (Root 0)) (In H R) (In I H) (In (Site 0) H)) (Link (P R 0 (Edge e)) (P H 0 (Edge e))))
                   (Bigraph (Inner 2 ()) (Outer 1 ()) (Nodes (N R Room) (N H Host) (N O Online))
                            (Place (In R (Root 0)) (In H R) (In O H) (In (Site 0) H) (In (Site 1) H)) (Link (P R 0 (Edge e)) (P H 0 (Edge e))))
                   (Eta (0 0) (1 0))
                   (Conditions (Present Context $room) (Absent (Parameter 0) $online))
                   (Priority 0)))
          ($rules (cons-atom $rule ()))
          ($identity (bg-identity 1 ()))
          ($occurrences (bg-run-occurrences $sig $rule $state))
          ($occ (car-atom $occurrences))
          ($step (bg-run-apply $sig $rule $state $occ))
          ($outcomes (bg-run-outcomes $sig $rule $state))
          ($successors (bg-run-successors $sig $rules $state))
          ($transitions (bg-run-transitions $sig $rules $state))
          ($parts (bg-run-decompose $occ $state))
          ($refused (bg-run-occurrences $sig $rule $faulty))
          ($composed (bg-run-compose $identity $state)))
     (and (and (== (size-atom $occurrences) 4) (== (size-atom $outcomes) 4))
          (and (and (== (size-atom $successors) 4) (== (size-atom $transitions) 1))
               (and (and (bg-run-iso $state $renamed) (== (bg-run-bucket $state) (bg-run-bucket $renamed)))
                    (and (and (bg--headed? Successor $step) (bg--headed? Decomposition $parts))
                         (and (and (== (bg-run-faults $sig $state) ()) (not (== (bg-run-faults $sig $faulty) ())))
                              (and (and (== (bg-run-rule-faults $sig $rule) ()) (bg--headed? BgFaulty $refused))
                                   (and (bg-run-iso $composed $state)
                                        (and (bg--headed? Refused (bg-run-tensor $state $state))
                                             (and (== (bg-roots (bg-run-parallel $room $online)) 2)
                                                  (== (bg-roots (bg-run-merge-product $room $online)) 1))))))))))))
