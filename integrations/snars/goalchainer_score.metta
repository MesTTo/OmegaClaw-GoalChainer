;;; Native GoalChainer scoring over SNARS expectation.
;;;
;;; Input row:
;;;   (ActionScore id order deontic expectation goal individual collective
;;;                motivation missing-count)
;;; where motivation is `(Motivation value)` or `(NoMotivation)`.

(= (gc score-value
      $deontic $expectation $goal $individual $collective
      (Motivation $motivation))
   (if (or (== $deontic forbidden) (== $deontic conflict))
       -1.0
       (+ (+ (* 0.54 $motivation) (* 0.38 $expectation))
          (if (== $deontic obligated) 0.1 0.0))))

(= (gc score-value
      $deontic $expectation $goal $individual $collective
      (NoMotivation))
   (if (or (== $deontic forbidden) (== $deontic conflict))
       -1.0
       (+ (+ (+ (* 0.42 $goal) (* 0.38 $expectation))
               (* 0.12 (min $individual $collective)))
             (if (== $deontic obligated) 0.1 0.0))))

(= (gc decision-status $deontic $score $missing-count)
   (if (or (== $deontic forbidden) (== $deontic conflict))
       blocked
       (if (and (>= $score 0.72) (== $missing-count 0))
           recommended
           (if (>= $score 0.5) candidate weak))))

(= (gc score-row
      (ActionScore $action $order $deontic $expectation
                   $goal $individual $collective $motivation $missing-count))
   (let* (($score
            (gc score-value $deontic $expectation $goal
                            $individual $collective $motivation))
          ($status (gc decision-status $deontic $score $missing-count))
          ($formula
            (case $motivation
              (((Motivation $value) motivation-expectation)
               ((NoMotivation) coverage-expectation)))))
     (DecisionRow $action $order $score $status $deontic $expectation
                  $goal $individual $collective $missing-count $formula)))

(= (gc score-rows $rows)
   (if (== $rows ())
       ()
       (let ($head $tail) (decons-atom $rows)
         (cons-atom (gc score-row $head) (gc score-rows $tail)))))

(= (gc decision-key
      (DecisionRow $action $order $score $status $deontic $expectation
                   $goal $individual $collective $missing $formula))
   (DecisionKey (- 0.0 $score) $order
     (DecisionRow $action $order $score $status $deontic $expectation
                  $goal $individual $collective $missing $formula)))

(= (gc decision-keys $rows)
   (if (== $rows ())
       ()
       (let ($head $tail) (decons-atom $rows)
         (cons-atom (gc decision-key $head) (gc decision-keys $tail)))))

(= (gc unwrap-keys $keys)
   (if (== $keys ())
       ()
       (let ($head $tail) (decons-atom $keys)
         (let (DecisionKey $negative $order $row) $head
           (cons-atom $row (gc unwrap-keys $tail))))))

(= (gc tied-actions $rows $best-score $epsilon)
   (if (== $rows ())
       ()
       (let ($head $tail) (decons-atom $rows)
         (let (DecisionRow $action $order $score $status $deontic $expectation
                          $goal $individual $collective $missing $formula) $head
           (if (<= (abs-math (- $score $best-score)) $epsilon)
               (cons-atom $action
                          (gc tied-actions $tail $best-score $epsilon))
               (gc tied-actions $tail $best-score $epsilon))))))

(= (gc score-record $input-rows $epsilon)
   (let* (($scored (gc score-rows $input-rows))
          ($ranked (gc unwrap-keys (msort (gc decision-keys $scored))))
          (($best $tail) (decons-atom $ranked))
          ((DecisionRow $action $order $score $status $deontic $expectation
                        $goal $individual $collective $missing $formula) $best)
          ($tied (gc tied-actions $ranked $score $epsilon))
          ($automatic
            (and (== $status recommended) (== (size-atom $tied) 1))))
     (goalchainer-snars-v1 score ok
       (ranking $ranked (tied $tied) (automatic $automatic)))))
