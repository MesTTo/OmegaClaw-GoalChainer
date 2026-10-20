; Purpose: order the deontic statuses once, and derive an action's status from what lib_deontic
; proved about it and whether it left the action in a dilemma as the join of those facts in that
; order.
;
;   (gc-deontic-status (MODE ...) DILEMMA) -> STATUS
;   (gc-status-at-least FLOOR STATUS) -> True when STATUS is FLOOR or above it in the order
;   (gc-statuses) -> (STATUS ...), every status, each once
;
; MODE is F, O or P, the modes of the defeasibly provable conclusions about the action, and
; DILEMMA is True when lib_deontic reports a duty about it it could not resolve. The statuses are
; ordered by how much they settle, and each mode settles its own: F forbidden, O obligated, P
; permitted. In Standard Deontic Logic O implies P, so permitted is below obligated; F p is
; O not-p, so forbidden is comparable with neither and meets them only at conflict, the top; an
; action nothing was proved about is unregulated, the bottom. An action's status is the join of
; its modes' statuses, from the bottom, and a dilemma joins the top: lib_deontic proves neither
; side of an unranked must-versus-forbidden clash and reports it only as a dilemma
; (c-ev-deontic-clash-semantics). The order is N5, a lattice that is not distributive, so the
; status is a join-semilattice fold over what was proved, not a semiring. A host's blocking cut,
; such as the incident example's forbidden and conflict, is the host's own policy, not this
; order's; a test checks that the example's is exactly the statuses at least forbidden
; (c-core-blocking-cut-independent-1017).
; Everything the rule needs is in this file, so it loads alone.
; am[implements a-ev-status-lattice-1017@a862b7] am[implements a-ev-in-dilemma-conflict@9cbf4c]
; am[rests-on c-ev-status-rule-is-a-lattice-join-1017@c5b4d0] am[rests-on c-ev-deontic-clash-semantics@dc6408]

; The order's covers: LOW is directly below HIGH.
(gc-status-cover unregulated permitted)
(gc-status-cover permitted obligated)
(gc-status-cover obligated conflict)
(gc-status-cover unregulated forbidden)
(gc-status-cover forbidden conflict)

; The status each proved mode settles.
(gc-mode-status F forbidden)
(gc-mode-status O obligated)
(gc-mode-status P permitted)

(= (gc-statuses)
   (unique-atom (collapse (match &self (gc-status-cover $low $high) (superpose ($low $high))))))

; Two cover paths can reach one status, unregulated to conflict through permitted or through
; forbidden, and is-member succeeds once per occurrence, so the reached answers are made unique
; before the test: one answer per call.
; Time: at most one walk of each cover chain from FLOOR, h covers deep, h the order's height.
(= (gc-status-at-least $floor $status)
   (if (== $floor $status)
       True
       (is-member True
         (unique-atom
           (collapse (match &self (gc-status-cover $floor $next) (gc-status-at-least $next $status)))))))

; The bottom has no status below it and the top none above it.
(= (gc-status-bottom)
   (car-atom (filter-atom (gc-statuses) $s
     (== () (collapse (match &self (gc-status-cover $below $s) $below))))))
(= (gc-status-top)
   (car-atom (filter-atom (gc-statuses) $s
     (== () (collapse (match &self (gc-status-cover $s $above) $above))))))

; The least upper bound of two statuses: the one upper bound below every other.
; Time: s order tests to find the upper bounds and s^2 to find the least, s = the statuses.
(= (gc-status-join $x $y)
   (let $bounds (filter-atom (gc-statuses) $s (and (gc-status-at-least $x $s) (gc-status-at-least $y $s)))
     (car-atom (filter-atom $bounds $least
       (not (is-member False (map-atom $bounds $other (gc-status-at-least $least $other))))))))

(= (gc-mode-status-of $mode)
   (let $settled (unique-atom (collapse (match &self (gc-mode-status $mode $status) $status)))
     (if (== $settled ()) (Error $mode "lib_deontic proved a mode no status is settled for") (car-atom $settled))))

; One answer per call: the modes are folded, never left as alternatives, and a mode no status is
; settled for answers its Error instead of a status.
; Time: m joins, m = the proved modes.
(= (gc-deontic-status $modes $dilemma)
   (let $settled (map-atom $modes $mode (gc-mode-status-of $mode))
     (let $unsettled (filter-atom $settled $status (not (is-member $status (gc-statuses))))
       (if (== $unsettled ())
           (foldl-atom $settled (if $dilemma (gc-status-top) (gc-status-bottom))
                       $acc $status (gc-status-join $acc $status))
           (car-atom $unsettled)))))
