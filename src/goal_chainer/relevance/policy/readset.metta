; Purpose: the relevance review's readset policy: which signals each kind of conclusion of a
; domain's theory can depend on, from the theory's rules alone, and which of them one review rests on.
;
;   (gc-relevance-cones (ConeInput (SIGNAL ...) (ACTION ...) ((Rule (LIT ...) (LIT ...)) ...) (LIT ...)))
;     -> (Cones ((For ACTION (SIGNAL ...)) ...)    candidacy: whether ACTION is a candidate
;               ((For ACTION (SIGNAL ...)) ...)    appraisal: its deontic status, contributions, effects
;               (SIGNAL ...)                       which goals are required
;               (SIGNAL ...))                      every duty, permission and prohibition
;   (gc-relevance-review-readset CONES (CANDIDATE ...))
;     -> (Readsets (SIGNAL ...) ((For CANDIDATE (SIGNAL ...)) ...))
;
; A rule is (Rule BODY HEADS), each a list of (Lit FUNCTOR (ARG ...)) with sign and deontic mode
; stripped; FUNCTOR is a string and an argument is (Const TEXT), a nested term included, or
; (Var NAME). The last ConeInput list holds the literals rules conclude under must, may or
; forbidden. SIGNAL, ACTION and CANDIDATE are strings.
;
; A stored proposal is only as fresh as the evidence it rests on, and in a defeasible theory
; that evidence is not only what supports the winner: a defeater that withdrew a rival's
; permission, a rule that kept a rival from being a candidate, and a rule that made a goal
; required decide the outcome too, and a new observation of a signal nobody had read can wake a
; dormant rule. So the readset is computed over every rule that could bear on a conclusion,
; rather than read off the proof of what happened to be concluded.
;
; The rule is the defeasible-logic proof condition: whether a literal is provable depends only on
; the rules whose head is that literal or its complement and, recursively, on the literals in
; their bodies (Billington; Antoniou, Billington, Governatori and Maher, ACM TOCL 2(2), 2001).
; Sign and mode are stripped before matching, so the deontic bridge (F p is O not-p; O p implies
; P p), defeaters and contrary-to-duty chains are covered by construction: they only ever relate
; literals about the same thing. A rule's other heads are part of its consequence too, since a
; chain's later duty arises when an earlier one is violated.
;
; Matching binds a head's variables against the query, consistently within that head, and a
; query position that is Wild constrains nothing. After substitution every unbound variable
; becomes Wild, so correlations between a body's variables are dropped. Both only ever add rules
; to a cone, so a cone over-approximates the true dependencies and never misses one
; (c-rel-cone-sound-1016 and its engine differential test).
; am[implements a-rel-compiler-1016@c69c38] am[rests-on c-rel-cone-sound-1016@092cec]
; am[implements a-rel-metta-policy-1016@fdaa20]

(= (gc-relevance-lit-functor (Lit $functor $args)) $functor)
(= (gc-relevance-lit-args (Lit $functor $args)) $args)
(= (gc-relevance-rule-body (Rule $body $heads)) $body)
(= (gc-relevance-rule-heads (Rule $body $heads)) $heads)

; ---- matching one literal against one rule head --------------------------------------------

; (Some BINDING) when the query can be the head, else None; BINDING is ((Bound (Var NAME) VALUE) ...).
(= (gc-relevance-match-literal $query $head)
   (if (and (== (gc-relevance-lit-functor $query) (gc-relevance-lit-functor $head))
            (== (size-atom (gc-relevance-lit-args $query)) (size-atom (gc-relevance-lit-args $head))))
       (gc-relevance-match-args (gc-relevance-lit-args $query) (gc-relevance-lit-args $head) ())
       None))

(= (gc-relevance-match-args $wanted $offered $binding)
   (if (== $wanted ())
       (Some $binding)
       (gc-relevance-match-rest
         (gc-relevance-match-arg (car-atom $wanted) (car-atom $offered) $binding)
         (cdr-atom $wanted) (cdr-atom $offered))))
(= (gc-relevance-match-rest None $wanted $offered) None)
(= (gc-relevance-match-rest (Some $binding) $wanted $offered) (gc-relevance-match-args $wanted $offered $binding))

(= (gc-relevance-match-arg $want (Var $name) $binding)
   (if (== $want Wild)
       (Some $binding)
       (gc-relevance-bind (Var $name) $want (gc-relevance-bound (Var $name) $binding) $binding)))
(= (gc-relevance-match-arg $want (Const $text) $binding)
   (if (or (== $want Wild) (== $want (Const $text))) (Some $binding) None))

(= (gc-relevance-bind $variable $want None $binding) (Some (cons-atom (Bound $variable $want) $binding)))
(= (gc-relevance-bind $variable $want (Some $value) $binding) (if (== $value $want) (Some $binding) None))

(= (gc-relevance-bound $variable $binding)
   (gc-relevance-first
     (map-atom (filter-atom $binding $b (gc-relevance-binds $b $variable)) $c (gc-relevance-bound-value $c))))
(= (gc-relevance-binds (Bound $variable $value) $wanted) (== $variable $wanted))
(= (gc-relevance-bound-value (Bound $variable $value)) $value)

; A literal with the binding applied and every unbound variable made Wild.
(= (gc-relevance-instantiate (Lit $functor $args) $binding)
   (Lit $functor (map-atom $args $a (gc-relevance-instantiate-arg $a $binding))))
(= (gc-relevance-instantiate-arg (Var $name) $binding)
   (gc-relevance-value-or Wild (gc-relevance-bound (Var $name) $binding)))
(= (gc-relevance-instantiate-arg (Const $text) $binding) (Const $text))
(= (gc-relevance-instantiate-arg Wild $binding) Wild)

; ---- the cone of a set of queries ----------------------------------------------------------

; Every literal a rule whose head matches PATTERN reads or concludes, instantiated.
; Time: one match per rule head.
(= (gc-relevance-expand $rules $pattern)
   (flatten-once (map-atom $rules $r (gc-relevance-expand-rule $r $pattern))))
(= (gc-relevance-expand-rule $rule $pattern)
   (flatten-once
     (map-atom (gc-relevance-rule-heads $rule) $h
       (gc-relevance-consequences $rule (gc-relevance-match-literal $pattern $h)))))
(= (gc-relevance-consequences $rule None) ())
(= (gc-relevance-consequences $rule (Some $binding))
   (map-atom (union-atom (gc-relevance-rule-body $rule) (gc-relevance-rule-heads $rule)) $l
     (gc-relevance-instantiate $l $binding)))

(= (gc-relevance-signals-of $signals $pattern)
   (if (and (== (gc-relevance-lit-functor $pattern) "signal") (== (size-atom (gc-relevance-lit-args $pattern)) 1))
       (gc-relevance-signal-arg $signals (car-atom (gc-relevance-lit-args $pattern)))
       ()))
; am[implements a-rel-member-once-1018@45ebae]
(= (gc-relevance-signal-arg $signals $arg)
   (if (== $arg Wild) $signals (if (gc-has $signals $arg) ($arg) ())))

; Breadth-first over instantiated patterns, each expanded once. The patterns are built from the
; domain's functors, constants and Wild, a finite set, so the search ends.
; Time: p expansions of r rule heads each, p = distinct patterns reached, plus p membership
; tests against the visited list, each a pass over it.
; am[implements a-rel-member-once-1018@45ebae]
(= (gc-relevance-closure $rules $signals $queue $seen $found)
   (if (== $queue ())
       $found
       (gc-relevance-visit $rules $signals (car-atom $queue) (cdr-atom $queue) $seen $found)))
(= (gc-relevance-visit $rules $signals $pattern $queue $seen $found)
   (if (gc-has $seen $pattern)
       (gc-relevance-closure $rules $signals $queue $seen $found)
       (gc-relevance-closure $rules $signals
         (union-atom $queue (gc-relevance-expand $rules $pattern))
         (cons-atom $pattern $seen)
         (union-atom $found (gc-relevance-signals-of $signals $pattern)))))

(= (gc-relevance-cone $rules $signals $queries)
   (map-atom (unique-atom (gc-relevance-closure $rules $signals
                            (map-atom $queries $q (gc-relevance-instantiate $q ())) () ()))
             $s (gc-relevance-const-text $s)))
(= (gc-relevance-const-text (Const $text)) $text)

; ---- the cones of a domain, and the readset of one review ------------------------------------

; The conclusions a review reads, by kind: candidacy (candidate ACTION); appraisal
; (do ACTION), (contributes ACTION GOAL BAND) and (effect ACTION DIMENSION BAND ESTIMATOR);
; (required GOAL); and every literal under a deontic operator.
; am[implements a-rel-mig-typed-entries-1018@c150af]
(: gc-relevance-cones (-> Atom Expression))
(= (gc-relevance-cones (ConeInput $signals $actions $rules $norms))
   (gc-relevance-cones-of (map-atom $signals $s (Const $s)) $actions $rules $norms))
(= (gc-relevance-cones-of $signals $actions $rules $norms)
   (Cones
     (map-atom $actions $a (For $a (gc-relevance-cone $rules $signals ((Lit "candidate" ((Const $a)))))))
     (map-atom $actions $b
       (For $b (gc-relevance-cone $rules $signals
                 ((Lit "do" ((Const $b)))
                  (Lit "contributes" ((Const $b) Wild Wild))
                  (Lit "effect" ((Const $b) Wild Wild Wild))))))
     (gc-relevance-cone $rules $signals ((Lit "required" (Wild))))
     (gc-relevance-cone $rules $signals $norms)))

; A review's readset holds every action's candidacy, because a rival that is not a candidate now
; can become one; every norm, because a duty on an action that is not a candidate, or a dilemma,
; changes the disposition by itself; which goals are required; and the appraisal of each current
; candidate, because the winner is decided by comparison with each of them. A candidate's own
; readset is its candidacy and its appraisal.
; am[implements a-rel-mig-typed-entries-1018@c150af]
(: gc-relevance-review-readset (-> Atom Atom Expression))
(= (gc-relevance-review-readset (Cones $candidacy $appraisal $requirement $norms) $candidates)
   (Readsets
     (unique-atom
       (flatten-once (union-atom ($requirement $norms)
                                 (union-atom (map-atom $candidacy $row (gc-relevance-for-value $row))
                                             (map-atom $candidates $c (gc-relevance-cone-of $appraisal $c))))))
     (map-atom $candidates $d
       (For $d (unique-atom (union-atom (gc-relevance-cone-of $candidacy $d) (gc-relevance-cone-of $appraisal $d)))))))
(= (gc-relevance-cone-of $table $action) (gc-relevance-value-or () (gc-relevance-lookup $table $action)))
