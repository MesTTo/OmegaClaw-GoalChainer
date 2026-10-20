; Purpose: the list and option helpers every relevance policy module shares, and the library pack
; functions they build on.
;
; Every relevance policy module follows one data rule. Each value Python hands it, and each value
; it hands back, is a string, a number or a boolean; symbols appear only as the policy's own
; capitalized constructors, such as (Some X), (Elim ID REASON) and None. PeTTa evaluates any nested
; expression whose head names a function, and a bare symbol bound by (= NAME VALUE) evaluates
; too, so a domain name that arrived as a symbol could run as code; a string never does
; (c-rel-strings-inert-1016). Python builds inputs as pymetta atoms and passes them as holes, so
; no value is ever spliced into MeTTa text.
;
; Function names are global to the process's one engine, so every function here is prefixed
; gc-relevance-; constructors are capitalized and never defined as functions.
;
; An entry Python evaluates declares its type: each parameter is Atom, so an input arrives as the
; data it is and is never evaluated on the way in (c-jk-atom-entry-inert-1018), and the result is
; the answer's own type, Expression for each review entry and Bool for the warm-up, since an entry
; declared to return Atom answers its body unevaluated (c-rt-atom-return-unevaluated-1018).
; goal_chainer.runtime's evaluator calls no entry that declares no type, so the policy's helpers
; stay its own and keep evaluating the arguments their callers compute, such as gc-relevance-fold's
; (map-atom ...) of path values; a test reaches a helper in the module group's space.
;
; PeTTa compiles a function body to one clause, so a pattern variable bound in one `case` of a
; body stays bound in the next (c-rel-petta-case-scope-1016); every destructuring is its own small
; function, and clauses of one function never overlap, since every matching clause answers.
; am[implements a-rel-metta-policy-1016@fdaa20] am[rests-on c-rel-strings-inert-1016@947e27] am[rests-on c-rel-petta-case-scope-1016@431484]
; am[implements a-rel-mig-typed-entries-1018@c150af] am[rests-on c-jk-atom-entry-inert-1018@63e37f]
; am[rests-on c-rt-atom-return-unevaluated-1018@364854] am[rests-on c-rel-mig-helpers-in-group-space-1018@e7e8bf]

; partition, flatten-once and sort-by come from the operator's library pack (lib_functional,
; bundled with pymetta 0.9.4): partition answers (YES NO) in input order and sort-by is stable.
!(import! &self (library lib_functional))

(= (gc-relevance-sum $values) (foldl-atom $values 0.0 $acc $v (+ $acc $v)))
(= (gc-relevance-all $flags) (foldl-atom $flags True $acc $f (and $acc $f)))
(= (gc-relevance-any $flags) (foldl-atom $flags False $acc $f (or $acc $f)))

(= (gc-relevance-first $items) (if (== $items ()) None (Some (car-atom $items))))
(= (gc-relevance-unwrap (Some $value)) $value)
(= (gc-relevance-value-or $default None) $default)
(= (gc-relevance-value-or $default (Some $value)) $value)

; The first item whose score is largest, in list order: ((SCORE ITEM) ...) -> (SCORE ITEM).
; Time: one comparison per item.
(= (gc-relevance-argmax $scored)
   (foldl-atom (cdr-atom $scored) (car-atom $scored) $best $next
     (if (> (car-atom $next) (car-atom $best)) $next $best)))

; (For KEY VALUE) rows, the table shape every policy answers per-action results in.
(= (gc-relevance-for-key (For $key $value)) $key)
(= (gc-relevance-for-value (For $key $value)) $value)
(= (gc-relevance-lookup $table $key)
   (gc-relevance-first
     (map-atom (filter-atom $table $row (== (gc-relevance-for-key $row) $key)) $hit (gc-relevance-for-value $hit))))
