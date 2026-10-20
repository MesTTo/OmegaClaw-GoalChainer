; Purpose: the procedure layer's policy: which procedure library a domain accepts, how the review
; that decided a request judges a signal literal, and which procedures bring a goal about, at which
; class, and why a literal nothing can bring about stays unsolved.
;
;   (gc-procedures-check LIBRARY (Names (Actions "ACTION" ...) (Signals "SIGNAL" ...)))
;     -> Valid | (Invalid (Problem KIND DETAIL) ...)
;   (gc-procedure-signal-judgements ((Read LITERAL "STATE") ...)) -> ((Judged LITERAL STATUS) ...)
;   (gc-agenda-relevant GOAL LIBRARY) -> (LITERAL ...)
;   (gc-agenda-compose GOAL LIBRARY ((Judged LITERAL STATUS) ...) ((Track "PROCEDURE" LITERAL STATUS) ...))
;     -> (Composed GOAL CLASS ((Choice LITERAL "PROCEDURE" CLASS) ...) ((Unsolved LITERAL REASON) ...))
;        or (Composed GOAL Unsolved () ((Unsolved LITERAL REASON) ...))
;
; LIBRARY is (Library (PROCEDURE ...) (INVESTIGATOR ...)), a PROCEDURE
; (Procedure "NAME" (L ...) (L ...) (STEP ...)) with what it achieves, then its When conditions,
; then its steps, and an INVESTIGATOR (Investigator "NAME" (L ...)). A literal L is
; (Signal "SIGNAL"), (Statement "TEXT") or (Not L) over one of the first two, and a STEP is
; (Act "ID" "ACTION" ("AFTER" ...)), (Investigate "ID" L ("AFTER" ...)) or
; (Achieve "ID" L ("AFTER" ...)). Every name is a string, so a domain's name is never evaluated
; (c-rel-strings-inert-1016). STATUS is Holds, Fails or Undecided.
; am[implements a-ev-pl-ag-representation-1017@ca0cfc] am[rests-on c-integrate-user-metta-policy-1016@9eb3d0]

!(import! &self (library lib_functional))

; --- acceptance: every problem the library has, in one answer ---------------------------------

; A library is acceptable when nothing in it names what the domain does not declare, no two
; procedures, investigators or steps of one procedure share a name, every After names an earlier
; step of the same procedure without a cycle, and no procedure predicts a literal and its negation.
; Each part is bound by let* before the list of parts is built, because only an expression whose
; head names a function is evaluated, so a list written of calls would stay a list of calls.
; am[implements a-ev-pl-ag-representation-1017@ca0cfc]
(= (gc-procedures-check (Library $procedures $investigators) (Names (Actions $actions) (Signals $signals)))
   (let* (($procedure-names (gc-procedure-duplicates procedure (map-atom $procedures $p (gc-procedure-name $p))))
          ($investigator-names (gc-procedure-duplicates investigator (map-atom $investigators $i (gc-investigator-name $i))))
          ($in-procedures (gc-procedure-flatten (map-atom $procedures $p (gc-procedure-problems $p $actions $signals))))
          ($in-investigators (gc-procedure-flatten (map-atom $investigators $i (gc-investigator-problems $i $signals))))
          ($problems (unique-atom (gc-procedure-flatten ($procedure-names $investigator-names $in-procedures $in-investigators)))))
     (if (== $problems ()) Valid (cons-atom Invalid $problems))))

(= (gc-procedure-name (Procedure $name $achieves $when $steps)) $name)
(= (gc-investigator-name (Investigator $name $observes)) $name)

; Time: s^2 comparisons per procedure for its After order, s = its steps, and n^2 for the names.
; am[implements a-ev-pl-ag-representation-1017@ca0cfc]
(= (gc-procedure-problems (Procedure $name $achieves $when $steps) $actions $signals)
   (let* (($empty-achieves (if (== $achieves ()) ((Problem achieves-nothing $name)) ()))
          ($empty-steps (if (== $steps ()) ((Problem no-steps $name)) ()))
          ($contradictions (gc-procedure-contradictions $name $achieves))
          ($literals (gc-procedure-literal-problems $name (append $achieves $when) $signals))
          ($step-names (gc-procedure-duplicates (step $name) (map-atom $steps $s (gc-procedure-step-id $s))))
          ($in-steps (gc-procedure-flatten (map-atom $steps $s (gc-procedure-step-problems $name $s $steps $actions $signals))))
          ($cycle (gc-procedure-cycle $name $steps)))
     (gc-procedure-flatten ($empty-achieves $empty-steps $contradictions $literals $step-names $in-steps $cycle))))

(= (gc-investigator-problems (Investigator $name $observes) $signals)
   (let* (($empty (if (== $observes ()) ((Problem observes-nothing $name)) ()))
          ($literals (gc-procedure-literal-problems $name $observes $signals)))
     (append $empty $literals)))

; A procedure predicting both L and (Not L) predicts nothing a receipt could grade.
(= (gc-procedure-contradictions $name $achieves)
   (map-atom (filter-atom $achieves $l (is-member (gc-procedure-negate $l) $achieves)) $l
     (Problem contradictory-achieves ($name $l))))

(= (gc-procedure-negate (Not $l)) $l)
(= (gc-procedure-negate (Signal $s)) (Not (Signal $s)))
(= (gc-procedure-negate (Statement $t)) (Not (Statement $t)))

(= (gc-procedure-literal-problems $owner $literals $signals)
   (gc-procedure-flatten (map-atom $literals $l (gc-procedure-literal-problem $owner $l $signals))))
(= (gc-procedure-literal-problem $owner (Not $l) $signals) (gc-procedure-literal-problem $owner $l $signals))
(= (gc-procedure-literal-problem $owner (Statement $text) $signals) ())
(= (gc-procedure-literal-problem $owner (Signal $s) $signals)
   (if (is-member $s $signals) () ((Problem undeclared-signal ($owner $s)))))

(= (gc-procedure-step-id (Act $id $action $after)) $id)
(= (gc-procedure-step-id (Investigate $id $literal $after)) $id)
(= (gc-procedure-step-id (Achieve $id $literal $after)) $id)
(= (gc-procedure-step-after (Act $id $action $after)) $after)
(= (gc-procedure-step-after (Investigate $id $literal $after)) $after)
(= (gc-procedure-step-after (Achieve $id $literal $after)) $after)

(= (gc-procedure-step-problems $name $step $steps $actions $signals)
   (let $ids (map-atom $steps $s (gc-procedure-step-id $s))
     (append (gc-procedure-step-target-problems $name $step $actions $signals)
             (map-atom (filter-atom (gc-procedure-step-after $step) $a (not (is-member $a $ids))) $a
               (Problem dangling-after ($name (gc-procedure-step-id $step) $a))))))

(= (gc-procedure-step-target-problems $name (Act $id $action $after) $actions $signals)
   (if (is-member $action $actions) () ((Problem undeclared-action ($name $id $action)))))
(= (gc-procedure-step-target-problems $name (Investigate $id $literal $after) $actions $signals)
   (gc-procedure-literal-problem $name $literal $signals))
(= (gc-procedure-step-target-problems $name (Achieve $id $literal $after) $actions $signals)
   (gc-procedure-literal-problem $name $literal $signals))

; The After order is acyclic when repeatedly setting aside every step whose predecessors are all
; set aside empties the procedure, Kahn's algorithm; what is left names the cycle. A dangling After
; never becomes set aside, so its step is reported by gc-procedure-step-problems, not here.
; Time: at most s rounds of s steps each, s = the procedure's steps.
(= (gc-procedure-cycle $name $steps)
   (let $left (gc-procedure-unordered $steps () (map-atom $steps $s (gc-procedure-step-id $s)))
     (if (== $left ())
         ()
         ((Problem cyclic-after ($name (map-atom $left $s (gc-procedure-step-id $s))))))))

(= (gc-procedure-unordered $steps $done $ids)
   (let* (($ready (filter-atom $steps $s
                    (and (not (is-member (gc-procedure-step-id $s) $done))
                         (gc-procedure-all (map-atom (gc-procedure-step-after $s) $a
                                             (or (is-member $a $done) (not (is-member $a $ids))))))))
          ($left (filter-atom $steps $s
                   (and (not (is-member (gc-procedure-step-id $s) $done))
                        (not (is-member $s $ready))))))
     (if (== $ready ())
         $left
         (gc-procedure-unordered $steps (append $done (map-atom $ready $s (gc-procedure-step-id $s))) $ids))))

; A name given twice is one problem naming the name, whatever kind of thing it names.
(= (gc-procedure-duplicates $kind $names)
   (map-atom (unique-atom (filter-atom $names $n (> (size-atom (filter-atom $names $m (== $m $n))) 1))) $n
     (Problem (duplicate $kind) $n)))

(= (gc-procedure-all $flags) (foldl-atom $flags True $acc $f (and $acc $f)))
(= (gc-procedure-flatten $lists) (foldl-atom $lists () $acc $list (append $acc $list)))

; --- judging a signal literal from the review ---------------------------------------------------

; The review's evidence policy already gives each declared signal its effective state at the
; review's as-of, a definite reading past its validity having decayed to unknown, never to refuted
; (relevance/policy/evidence.metta). A detected signal holds, a refuted one fails, and an unknown or
; conflicted one is undecided: no evidence and disagreeing evidence alike satisfy nothing. A signal's
; states are definite, so its negation swaps holds and fails.
; am[implements a-ev-pl-ag-judgement-1017@fb6475] am[rests-on c-ev-pl-relevance-three-valued-1017@06897e]
(= (gc-procedure-signal-status "detected") Holds)
(= (gc-procedure-signal-status "refuted") Fails)
(= (gc-procedure-signal-status "unknown") Undecided)
(= (gc-procedure-signal-status "conflicted") Undecided)

(= (gc-procedure-opposite Holds) Fails)
(= (gc-procedure-opposite Fails) Holds)
(= (gc-procedure-opposite Undecided) Undecided)

(= (gc-procedure-signal-judgement (Signal $name) $state) (gc-procedure-signal-status $state))
(= (gc-procedure-signal-judgement (Not (Signal $name)) $state)
   (gc-procedure-opposite (gc-procedure-signal-status $state)))

; am[implements a-ev-pl-ag-judgement-1017@fb6475]
(= (gc-procedure-signal-judgements $reads)
   (map-atom $reads $read
     (let (Read $literal $state) $read
       (Judged $literal (gc-procedure-signal-judgement $literal $state)))))

; --- composition: which procedures bring the goal about ------------------------------------------

; The literals a goal can depend on: the goal, and for every procedure achieving a literal already
; reached, its When conditions and its achieve targets. An investigate step's literal is gathered
; evidence, never a precondition, so it adds nothing here.
; Time: at most r rounds over the p procedures, r = the literals reached.
; am[implements a-ev-pl-ag-class-selection-1017@b0ea0f]
(= (gc-agenda-relevant $goal (Library $procedures $investigators))
   (gc-agenda-closure ($goal) $procedures))

(= (gc-agenda-closure $reached $procedures)
   (let $next (unique-atom (append $reached
                (gc-procedure-flatten
                  (map-atom (filter-atom $procedures $p (gc-agenda-achieves-any $p $reached)) $p
                    (append (gc-agenda-when $p) (gc-agenda-targets $p))))))
     (if (== (size-atom $next) (size-atom $reached)) $reached (gc-agenda-closure $next $procedures))))

(= (gc-agenda-achieves-any (Procedure $name $achieves $when $steps) $literals)
   (not (== () (filter-atom $achieves $l (is-member $l $literals)))))
(= (gc-agenda-achieves (Procedure $name $achieves $when $steps) $literal) (is-member $literal $achieves))
(= (gc-agenda-when (Procedure $name $achieves $when $steps)) $when)
(= (gc-agenda-targets (Procedure $name $achieves $when $steps))
   (map-atom (filter-atom $steps $s (gc-agenda-achieve-step? $s)) $s (gc-agenda-step-literal $s)))
(= (gc-agenda-achieve-step? (Achieve $id $literal $after)) True)
(= (gc-agenda-achieve-step? (Act $id $action $after)) False)
(= (gc-agenda-achieve-step? (Investigate $id $literal $after)) False)
(= (gc-agenda-step-literal (Achieve $id $literal $after)) $literal)

; A class is (Class TIER READY), one of four points ordered componentwise: a way's TIER is
; established when its record for the literal it serves Holds, and it is READY when every When
; condition Holds. A derivation's class is the componentwise meet over its ways, its weakest link,
; and a class's program admits exactly the ways whose class is componentwise at least it. The list
; below is class order, established before unestablished, then ready before pending; it only picks
; one among the classes that derive a literal. The class is an order, never a probability.
; am[implements a-ev-pl-ag-class-selection-1017@b0ea0f] am[rests-on c-ev-pl-aspic-from-agenticmind-1017@5f0fd1]
; am[rests-on c-ev-pl-threshold-componentwise-1018@76a8b8]
(= (gc-agenda-classes)
   ((Class established ready) (Class established pending) (Class unestablished ready) (Class unestablished pending)))

(= (gc-agenda-status $literal $judged)
   (let $rows (filter-atom $judged $j (== (index-atom $j 1) $literal))
     (if (== $rows ()) Unjudged (index-atom (car-atom $rows) 2))))

; A procedure's record for one literal is Holds, Undecided or Fails as SNARS's track() cut it; no
; record is Undecided, an unestablished procedure, never an excluded one.
(= (gc-agenda-record $name $literal $tracks)
   (let $rows (filter-atom $tracks $t (and (== (index-atom $t 1) $name) (== (index-atom $t 2) $literal)))
     (if (== $rows ()) Undecided (index-atom (car-atom $rows) 3))))

; Whether a procedure may stand in a class's program for one literal: a refuted record undercuts
; it in every class, an established class needs an established record, and no When condition may
; fail; a pending class also admits Undecided When conditions, a ready one does not.
(= (gc-agenda-admits (Class $tier $ready) (Procedure $name $achieves $when $steps) $literal $judged $tracks)
   (let $record (gc-agenda-record $name $literal $tracks)
     (and (not (== $record Fails))
          (and (or (== $tier unestablished) (== $record Holds))
               (gc-procedure-all (map-atom $when $w (gc-agenda-condition-admitted $ready (gc-agenda-status $w $judged))))))))

(= (gc-agenda-condition-admitted $ready Holds) True)
(= (gc-agenda-condition-admitted ready Undecided) False)
(= (gc-agenda-condition-admitted pending Undecided) True)
(= (gc-agenda-condition-admitted $ready Fails) False)
(= (gc-agenda-condition-admitted $ready Unjudged) False)

; One class's tagged program: a literal that holds is a fact of cost 0, and each admitted procedure
; is one rule of cost 1 per literal it achieves, its premises its achieve targets. Its When
; conditions are already decided by admission, so they are no premises. The engine's tabled
; fixpoint (match-under) then gives each derivable literal its least cost: a support cycle with no
; founded entry derives nothing, and a minimum-cost rule's premises always cost less than its head,
; which is what makes the chosen graph acyclic (c-ev-pl-match-under-fits-1017). A fresh space per
; class keeps the derivation pure: nothing is written where anything else reads.
; Time: one match-under over r literals and the admitted rules, measured 6 ms at r = 10 and
; superlinear beyond (c-ev-pl-match-under-cost-1017).
; am[implements a-ev-pl-ag-class-selection-1017@b0ea0f] am[rests-on c-ev-pl-match-under-fits-1017@6c9bf6]
; am[rests-on c-ev-pl-match-under-cost-1017@6f5d5b]
(= (gc-agenda-program $class $relevant $procedures $judged $tracks)
   (append
     (map-atom (filter-atom $relevant $l (== (gc-agenda-status $l $judged) Holds)) $l (fact 0 (achieved $l)))
     (gc-procedure-flatten
       (map-atom $procedures $p
         (map-atom (filter-atom (gc-agenda-achieved-by $p) $l
                     (and (is-member $l $relevant) (gc-agenda-admits $class $p $l $judged $tracks))) $l
           (rule 1 (achieved $l) (cons-atom premises (map-atom (gc-agenda-targets $p) $t (achieved $t)))))))))

(= (gc-agenda-achieved-by (Procedure $name $achieves $when $steps)) $achieves)

; (Cost LITERAL COST) for every literal the class can derive.
(= (gc-agenda-costs $class $relevant $procedures $judged $tracks)
   (let* (($space (new-space))
          ($rows (gc-agenda-program $class $relevant $procedures $judged $tracks))
          ($added (map-atom $rows $row (add-atom $space $row)))
          ($answers (collapse (match-under $space tropical (achieved $literal)))))
     (map-atom $answers $answer (let ((achieved $l) $cost) $answer (Cost $l $cost)))))

(= (gc-agenda-cost $literal $costs)
   (let $rows (filter-atom $costs $c (== (index-atom $c 1) $literal))
     (if (== $rows ()) Unreached (index-atom (car-atom $rows) 2))))

; The goal's class is the first, in class order, at which it is derivable at all. Every literal the
; goal needs then takes the first class in the same order that is componentwise at least the goal's
; and derives it, and chooses there. Every way used is therefore admitted at the goal's class, so the
; goal's weakest link is its class: a stronger one would make it derivable at an earlier class.
; Class order only picks among the classes that derive a literal; which ways a class admits is
; componentwise (c-ev-pl-threshold-componentwise-1018).
; am[implements a-ev-pl-ag-class-goal-threshold-1018@158ba1] am[rests-on c-ev-pl-goal-threshold-exact-1018@f6effd]
; am[rests-on c-ev-pl-threshold-componentwise-1018@76a8b8]
(= (gc-agenda-compose $goal (Library $procedures $investigators) $judged $tracks)
   (let* (($relevant (gc-agenda-closure ($goal) $procedures))
          ($tables (map-atom (gc-agenda-classes) $c
                     (Table $c (gc-agenda-costs $c $relevant $procedures $judged $tracks))))
          ($reached (filter-atom $tables $t (not (== (gc-agenda-cost $goal (index-atom $t 2)) Unreached))))
          ($unsolved (gc-agenda-unsolved $goal $relevant $procedures $judged $tracks $tables)))
     (if (== $reached ())
         (Composed $goal Unsolved () $unsolved)
         (let* (((Table $class $costs) (car-atom $reached))
                ($chosen (gc-agenda-choose ($goal) $class () $procedures $judged $tracks $tables)))
           (Composed $goal $class (gc-agenda-weakest-links $chosen $judged $tracks) $unsolved)))))

; Each literal takes the first procedure, in declared order, admitted at its own class whose achieve
; targets cost less than it does there (AgentSpeak's library order, c-ev-pl-prior-art-1017); a
; literal that holds needs no choice. Its class depends only on it and the goal's class, never on
; which consumer reached it first, so a prerequisite two steps share is one choice that is right for
; both. A floor per consumer would make that choice depend on the order of the consumers
; (c-ev-pl-consumer-floor-order-dependent-1018), and one floor carried through the recursion failed
; outright (c-ev-pl-global-floor-defect-1018). The answer is (Chose LITERAL PROCEDURE) per literal.
; Time: one pass over the derivation, each literal choosing among its procedures once.
; am[implements a-ev-pl-ag-class-goal-threshold-1018@158ba1] am[rests-on c-ev-pl-prior-art-1017@cace0d]
; am[rests-on c-ev-pl-consumer-floor-order-dependent-1018@35434c] am[addresses i-ev-pl-global-floor-1018@f1fc08]
(= (gc-agenda-choose $pending $goal-class $chosen $procedures $judged $tracks $tables)
   (if (== $pending ())
       $chosen
       (let* ((($literal $rest) (decons-atom $pending)))
         (if (or (== (gc-agenda-status $literal $judged) Holds)
                 (not (== () (filter-atom $chosen $c (== (index-atom $c 1) $literal)))))
             (gc-agenda-choose $rest $goal-class $chosen $procedures $judged $tracks $tables)
             (let* (((Table $class $costs) (gc-agenda-best-table $literal $goal-class $tables))
                    ($cost (gc-agenda-cost $literal $costs))
                    ($procedure (car-atom (filter-atom $procedures $p
                                   (and (gc-agenda-achieves $p $literal)
                                        (and (gc-agenda-admits $class $p $literal $judged $tracks)
                                             (gc-agenda-cheaper (gc-agenda-targets $p) $cost $costs)))))))
               (gc-agenda-choose (append $rest (gc-agenda-targets $procedure)) $goal-class
                                 (append $chosen ((Chose $literal $procedure))) $procedures $judged $tracks $tables))))))

(= (gc-agenda-cheaper $targets $cost $costs)
   (gc-procedure-all (map-atom $targets $t
     (let $c (gc-agenda-cost $t $costs) (if (== $c Unreached) False (< $c $cost))))))

; The first table, in class order, that derives the literal and is componentwise at least the goal's.
(= (gc-agenda-best-table $literal $goal-class $tables)
   (car-atom (filter-atom $tables $t
     (and (gc-agenda-at-least (index-atom $t 1) $goal-class)
          (not (== (gc-agenda-cost $literal (index-atom $t 2)) Unreached))))))

(= (gc-agenda-at-least (Class $tier $ready) (Class $floor-tier $floor-ready))
   (and (gc-agenda-tier-at-least $tier $floor-tier) (gc-agenda-ready-at-least $ready $floor-ready)))
(= (gc-agenda-tier-at-least established $floor) True)
(= (gc-agenda-tier-at-least unestablished unestablished) True)
(= (gc-agenda-tier-at-least unestablished established) False)
(= (gc-agenda-ready-at-least ready $floor) True)
(= (gc-agenda-ready-at-least pending pending) True)
(= (gc-agenda-ready-at-least pending ready) False)

; A literal's class in the answer is the weakest link of what it rests on: the meet of the classes of
; every chosen way beneath it, its own included. A literal's own class can exceed that, because each
; prerequisite chooses by its own class (c-ev-pl-intermediate-class-not-threshold-1018). Meet is
; idempotent, so a prerequisite two ways share counts once. A way's class is its record's tier for the
; literal it is chosen for, and ready only when every When condition holds.
; Time: one walk over at most c choices per choice, c = the choices, so c^2 in all.
; am[implements a-ev-pl-ag-class-goal-threshold-1018@158ba1] am[rests-on c-ev-pl-intermediate-class-not-threshold-1018@5c6b8f]
(= (gc-agenda-weakest-links $chosen $judged $tracks)
   (map-atom $chosen $c
     (let (Chose $literal $procedure) $c
       (Choice $literal (gc-procedure-name $procedure)
         (foldl-atom (gc-agenda-beneath ($literal) () $chosen) (Class established ready) $acc $below
           (gc-agenda-meet $acc (gc-agenda-way-class $below $judged $tracks)))))))

(= (gc-agenda-way-class (Chose $literal (Procedure $name $achieves $when $steps)) $judged $tracks)
   (Class (if (== (gc-agenda-record $name $literal $tracks) Holds) established unestablished)
          (if (gc-procedure-all (map-atom $when $w (== (gc-agenda-status $w $judged) Holds))) ready pending)))

(= (gc-agenda-meet (Class $tier $ready) (Class $other-tier $other-ready))
   (Class (if (and (== $tier established) (== $other-tier established)) established unestablished)
          (if (and (== $ready ready) (== $other-ready ready)) ready pending)))

; The choices reached from the pending literals through the chosen ways' achieve targets, each once.
; A literal that holds has no choice. `or` evaluates both of its arguments, so the empty case is an
; `if`, whose untaken branch is never evaluated, never an `or` beside a car-atom.
(= (gc-agenda-beneath $pending $seen $chosen)
   (if (== $pending ())
       $seen
       (let* ((($literal $rest) (decons-atom $pending))
              ($rows (filter-atom $chosen $c (== (index-atom $c 1) $literal))))
         (if (== $rows ())
             (gc-agenda-beneath $rest $seen $chosen)
             (let $row (car-atom $rows)
               (if (is-member $row $seen)
                   (gc-agenda-beneath $rest $seen $chosen)
                   (let (Chose $l $procedure) $row
                     (gc-agenda-beneath (append $rest (gc-agenda-targets $procedure)) (cons-atom $row $seen) $chosen))))))))

; Why each literal something must bring about, the goal or an achieve target of a relevant
; procedure, has no derivation even in the weakest class while it does not hold: nothing achieves
; it, every procedure that does is excluded by a failing condition or a refuted record, or the
; procedures left need a literal that is itself underivable; a literal whose needs lead back to
; itself is cyclic, a support cycle with no founded entry. A When condition is judged, never
; brought about, so it appears only inside the exclusions that name it.
; am[implements a-ev-pl-ag-class-selection-1017@b0ea0f]
(= (gc-agenda-unsolved $goal $relevant $procedures $judged $tracks $tables)
   (let* (((Table $weakest $costs) (index-atom $tables 3))
          ($targets (unique-atom (cons-atom $goal (gc-procedure-flatten
                      (map-atom (filter-atom $procedures $p (gc-agenda-achieves-any $p $relevant)) $p
                        (gc-agenda-targets $p)))))))
     (map-atom (filter-atom $targets $l (and (not (== (gc-agenda-status $l $judged) Holds))
                                              (== (gc-agenda-cost $l $costs) Unreached))) $l
       (Unsolved $l (gc-agenda-reason $l $procedures $judged $tracks $costs)))))

(= (gc-agenda-reason $literal $procedures $judged $tracks $costs)
   (let* (($ways (filter-atom $procedures $p (gc-agenda-achieves $p $literal)))
          ($open (filter-atom $ways $p (gc-agenda-admits (Class unestablished pending) $p $literal $judged $tracks))))
     (if (== $ways ())
         no-alternative
         (if (== $open ())
             (excluded (map-atom $ways $p (gc-agenda-exclusion $p $literal $judged $tracks)))
             (if (gc-agenda-returns-to $literal $literal () $open $procedures $judged $tracks $costs)
                 cyclic
                 (blocked (map-atom $open $p
                   (Needs (gc-procedure-name $p)
                          (filter-atom (gc-agenda-targets $p) $t (== (gc-agenda-cost $t $costs) Unreached))))))))))

(= (gc-agenda-exclusion (Procedure $name $achieves $when $steps) $literal $judged $tracks)
   (if (== (gc-agenda-record $name $literal $tracks) Fails)
       (Refuted $name)
       (Fails $name (filter-atom $when $w (not (gc-agenda-condition-admitted pending (gc-agenda-status $w $judged)))))))

; Whether an underivable literal's open procedures need, through underivable targets, the literal
; itself. Only open procedures carry a need onward: an excluded one can never be used, so a cycle
; through it is no reason, and the literal it would have served is reported excluded instead.
; Time: each literal visited once, carried in $seen.
(= (gc-agenda-returns-to $origin $literal $seen $open $procedures $judged $tracks $costs)
   (let $needed (unique-atom (gc-procedure-flatten
                  (map-atom $open $p (filter-atom (gc-agenda-targets $p) $t (== (gc-agenda-cost $t $costs) Unreached)))))
     (or (is-member $origin $needed)
         (gc-procedure-any (map-atom (filter-atom $needed $n (not (is-member $n $seen))) $n
           (gc-agenda-returns-to $origin $n (cons-atom $n $seen)
             (filter-atom $procedures $p (and (gc-agenda-achieves $p $n)
                                              (gc-agenda-admits (Class unestablished pending) $p $n $judged $tracks)))
             $procedures $judged $tracks $costs))))))

(= (gc-procedure-any $flags) (foldl-atom $flags False $acc $f (or $acc $f)))
