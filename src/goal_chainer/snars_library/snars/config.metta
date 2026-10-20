;;; SNARS module — split from the snars.metta monolith (2026-06-12).
;;; Import via the snars.metta aggregator; load order lives there.

;; ---- configuration (lib_nars config idiom) ----
;; values are overridable for benchmark sweeps: (add-atom &self (sn cfg-set KEY V))
;; wins over the default. match on a data atom -> single-valued, janus-free.
(= (sn cfg $key $default)
   (case (collapse (match &self (sn cfg-set $key $v) $v))
     ((() $default)
      (($v) $v))))
(= (sn config default-rate) 0.5)
(= (sn config default-trust) 1.0)
(= (sn config u-min) 0.001)
(= (sn config a-clamp) 0.001)
(= (sn config k-eps) 0.000001)
(= (sn config claimer-trust) 0.8)
;; know-class skips the claimer haircut (O5 "boosted truth-port"; factive
;; presupposition -- Kiparsky & Kiparsky 1970; FactBank is the calibration
;; corpus when this graduates from a design call to data)
(= (sn config know-trust) 1.0)
;; structural-truth prior b_struct (3.7 discount ruling; R3 ordering uses it)
(= (sn config structural-b) (sn cfg structural-b 0.9))
;; subgoal registration threshold (R2; control-side, SLN 3.9 caveat)
(= (sn config decision-threshold) (sn cfg decision-threshold 0.6))
;; E2 governance flags (default OFF; calibration leaves them off until priced)
(= (sn config reassert-avg) (sn cfg reassert-avg 0))
(= (sn config gates) (sn cfg gates 0))
(= (sn config push-q) (sn cfg push-q 0.9))
(= (sn config structural-r) 9.0)
(= (sn config structural-a) 0.9)
(= (sn config trust-prior-src) 0.9)
(= (sn config trust-floor-c) (sn cfg trust-floor-c 0.1))
(= (sn config dc-threshold) (sn cfg dc-threshold 0.5))
(= (sn config forget-act) (sn cfg forget-act 0.01))
;; the trust ledger A/B switch (v2 P2): a presence flag in the space. The
;; harness adds `(sn frozen-flag)` for the frozen arm; match on a data atom is
;; the single-valued, janus-free mechanism (no config redef, no integer unify).
(= (sn frozen?) (not (== () (collapse (once (match &self (sn frozen-flag) True))))))
(= (sn freeze!) (if (sn frozen?) True (let $a (add-atom &self (sn frozen-flag)) True)))

