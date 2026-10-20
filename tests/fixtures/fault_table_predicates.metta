; Purpose: predicates for the fault-table reader's tests: one that always holds, one that never
; does, one that checks its term is positive, one that answers nothing and one that answers twice.

(= (gc-ft-test-holds $context $term) True)
(= (gc-ft-test-fails $context $term) False)
(= (gc-ft-test-positive $context $term) (> $term 0))
(= (gc-ft-test-silent $context $term) (empty))
(= (gc-ft-test-twice $context $term) (superpose (True False)))
