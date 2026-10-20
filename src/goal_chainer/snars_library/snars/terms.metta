;;; SNARS module — split from the snars.metta monolith (2026-06-12).
;;; Import via the snars.metta aggregator; load order lives there.

;; ---- term constructors: typed SH trees with canonical string labels ----
(: (sn str) (-> %Undefined% %Undefined%))
(= (sn str $x)
   (case (get-metatype $x)
     ((Symbol (repr $x))
      ($_ $x))))

(: (sn c) (-> %Undefined% %Undefined%))
(= (sn c $label) (sh-atom (tag C c NoRoles ()) (sn str $label)))

(: (sn cp) (-> %Undefined% %Undefined%))
(= (sn cp $label) (sh-atom (tag C p NoRoles ()) (sn str $label)))

;; aliased pred labels normalize to the canonical identity-bearing label
;; BEFORE sid (R1 ruling: "<->" canonical, "alike" sugar -- one sid, two
;; spellings); alias ROWS live with their packs (runtime match), only this
;; resolver must compile before its callers (eval-timing law)
(= (sn pred-canon $lbl)
   (case (collapse (once (match &self (sn pred-alias $lbl $c) $c)))
     ((() $lbl)
      (($c) $c))))

(: (sn p) (-> %Undefined% %Undefined% Atom %Undefined%))
(= (sn p $roles $label $args) (sh (tag P d $roles ()) (sn str (sn pred-canon $label)) (args $args)))

;; F7: author a predicate without the roles string -- canon derives it
;; (probe-verified 2026-06-12: canonicalize rebuilds roles, sids identical)
(: (sn p*) (-> %Undefined% Atom %Undefined%))
(= (sn p* $label $args) (sn p so $label $args))

;; ---- Python gateways: ONE canonicalizer and ONE hash for all paths ----
(= (sn canon $tree) (sread (py-call (goalchainer_snars.snars_canonical $tree))))
(= (sn peel $tree) (sread (py-call (goalchainer_snars.snars_peel $tree))))
;; sid is a pure function of a ground canonical tree and sits on the rule-firing
;; hot path — memoize through the kernel cache so repeat trees skip the
;; janus round-trip and the sread re-parse. PeTTa tabling cannot memoize
;; py-call bodies (verified 2026-06-12), hence the explicit cache.
(= (sn sid $tree)
   (case (sn_sid_get $tree)
     (((SidHit $sid) $sid)
      ($_ (sn_sid_put $tree (sread (py-call (goalchainer_snars.snars_sid $tree))))))))
(= (sn rh $sid $sigma) (sread (py-call (goalchainer_snars.snars_receipt_hash $sid $sigma))))
(= (sn labels $tree) (sread (py-call (goalchainer_snars.snars_labels $tree))))

;; native pattern canonicalization (variable-safe: holes never reach py-call):
;; sense atoms replace labels where the AMR slot is filled; P subtypes normalize
(: (sn pat) (-> %Undefined% %Undefined%))
(= (sn pat $n)
   (if (== (get-metatype $n) Expression)
       (sn pat-x $n)
       $n))

(= (sn pat-x $n)
   (case $n
     (((sh-atom $tag $label)
       (sh-atom (sn pat-tag $tag) (sn pat-label $tag $label)))
      ((sh $tag $label (args $items))
       (sh (sn pat-tag $tag) (sn pat-label $tag $label) (args (sn pat-args $items))))
      ((sh-conn $conn (args $items))
       (sh-conn (sn pat $conn) (args (sn pat-args $items))))
      ($other $other))))

(= (sn pat-tag $tag)
   (case $tag
     (((tag P $sub $roles $amr) (tag P d $roles $amr))
      ($other $other))))

(= (sn pat-label $tag $label)
   (case $tag
     (((tag $t $s $r (amr $c)) $c)
      ($other $label))))

(: (sn pat-args) (-> Atom Expression))
(= (sn pat-args $items)
   (if (== $items ())
       ()
       (let ($head $tail) (decons-atom $items)
         (let $rebuilt (case $head
                         (((arg $role $child) (arg $role (sn pat $child)))
                          ($other (sn pat $other))))
           (cons-atom $rebuilt (sn pat-args $tail))))))

;; surface strings are display-only (sn label) facts; the model is over sense atoms
(: (sn label-all!) (-> Atom Bool))
(= (sn label-all! $pairs)
   (if (== $pairs ())
       True
       (let ($head $tail) (decons-atom $pairs)
         (let ($concept $surface) $head
           (let* (($recorded (if (== () (collapse (match &self (sn label $concept $s) True)))
                                 (add-atom &self (sn label $concept $surface))
                                 ()))
                  ($rest (sn label-all! $tail)))
             True)))))

