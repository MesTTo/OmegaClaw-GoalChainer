; Purpose: a fixture for tests/metta_scope_lint.py: bad-pair binds $other in two case patterns of one
; clause, which pymetta 0.9.4 compiles to one Prolog variable; good-pair binds it only inside lambdas.
(= (bad-pair $a $b) ((case $a (((Site $k) site) ($other $other))) (case $b (((Root $j) root) ($other $other)))))
(= (good-pair $xs) (map-atom $xs $x (case $x (((Site $k) site) ($other $other)))))
