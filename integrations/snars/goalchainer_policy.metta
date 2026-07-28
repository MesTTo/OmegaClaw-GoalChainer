;;; GoalChainer incident policy expressed as inspectable SNARS knowledge.
;;;
;;; Request evidence arrives as parsed `(hb tree ...)` facts and is ingested by
;;; Mettabase before these rules run. The policy adds stable action facts and
;;; registered rewrite rules. It never inserts an acceptable or forbidden
;;; conclusion for a specific request.

(= (gc concept $name) (sn c $name))
(= (gc action-property $action $property)
   (sn p so "has-property"
     ((arg s (gc concept $action)) (arg o (gc concept $property)))))

;;; Walk the complete typed SH trees emitted by HyperBase. Surface labels remain
;;; useful evidence here even when SNARS canonicalization uses AMR identifiers.
(= (gc tree-label (sh-atom $tag $label)) $label)
(= (gc tree-label (sh $tag $label $args)) $label)
(= (gc tree-label (sh $tag $label (args $args)))
   (gc arg-labels $args))
(= (gc tree-label (sh-conn $connector $args))
   (gc tree-label $connector))
(= (gc tree-label (sh-conn $connector $args))
   (gc arg-labels $args))

(= (gc arg-labels $args)
   (if (== $args ())
       (empty)
       (let ($head $tail) (decons-atom $args)
         (superpose ((gc arg-label $head) (gc arg-labels $tail))))))
(= (gc arg-label (arg $role $tree)) (gc tree-label $tree))

(= (gc negated-tree? $tree)
   (case $tree
     (((sh-conn (sh $tag "not" $args) $outer-args) True)
      ($_ False))))

(= (gc observed-label $label)
   (match &self (hb tree $edge $tree)
     (if (gc negated-tree? $tree)
         (empty)
         (gc tree-label $tree))))

(= (gc one-of $value $values)
   (if (== $values ())
       False
       (let ($head $tail) (decons-atom $values)
         (if (== $value $head) True (gc one-of $value $tail)))))

(= (gc any-label? $labels)
   (not (== ()
     (collapse
       (let $label (gc observed-label $label)
         (if (gc one-of $label $labels) True (empty)))))))

(= (gc sensitive?)
   (gc any-label?
     ("email" "emails" "payload" "payloads" "token" "tokens"
      "secret" "secrets" "credential" "credentials" "customer"
      "personal" "identifier" "identifiers" "pii")))

(= (gc public?)
   (gc any-label?
     ("public" "publicly" "safe" "publishable" "non-sensitive")))

(= (gc unverified?)
   (gc any-label?
     ("unverified" "unknown" "investigating" "unconfirmed")))

(= (gc coordination?)
   (gc any-label?
     ("engineering" "support" "responders" "team" "incident")))

(= (gc request-source)
   (match &self (sn receipt $sid $source $hash)
     (if (or (== $source "goalchainer:policy-actions")
             (== $source "structural"))
         (empty)
         $source)))

(= (gc first-request-source)
   (case (collapse (once (gc request-source)))
     ((() "user")
      ($sources (car-atom $sources)))))

;;; Turn parser observations into ordinary SNARS evidence. Stable sources make
;;; replay receipt-deduplicating.
(= (gc assert-request-context!)
   (let* (($source (gc first-request-source))
          ($sensitive
            (if (gc sensitive?)
                (believe! (gc action-property "request" "sensitive-data")
                  ((evidence 8.0 0.0) (source $source)))
                ()))
          ($public
            (if (gc public?)
                (believe! (gc action-property "request" "public-data")
                  ((evidence 8.0 0.0) (source $source)))
                ()))
          ($unverified
            (if (gc unverified?)
                (believe! (gc action-property "request" "unverified")
                  ((evidence 8.0 0.0) (source $source)))
                ()))
          ($coordination
            (if (gc coordination?)
                (believe! (gc action-property "request" "coordination-needed")
                  ((evidence 8.0 0.0) (source $source)))
                ())))
     True))

;;; Stable action properties.
(= (gc init-policy!)
   (let* (($raw-exposes
            (believe! (gc action-property "publish_raw_log" "exposes-sensitive-data")
              ((evidence 8.0 0.0) (source "goalchainer:policy-actions"))))
          ($raw-coordinates
            (believe! (gc action-property "publish_raw_log" "supports-coordination")
              ((evidence 8.0 0.0) (source "goalchainer:policy-actions"))))
          ($redacted
            (believe! (gc action-property "publish_redacted_summary" "redacted")
              ((evidence 8.0 0.0) (source "goalchainer:policy-actions"))))
          ($redacted-protects
            (believe! (gc action-property "publish_redacted_summary" "protects-privacy")
              ((evidence 8.0 0.0) (source "goalchainer:policy-actions"))))
          ($redacted-coordinates
            (believe! (gc action-property "publish_redacted_summary" "supports-coordination")
              ((evidence 8.0 0.0) (source "goalchainer:policy-actions"))))
          ($hold-protects
            (believe! (gc action-property "hold_external_update" "protects-privacy")
              ((evidence 8.0 0.0) (source "goalchainer:policy-actions"))))
          ($hold-internal
            (believe! (gc action-property "hold_external_update" "internal")
              ((evidence 8.0 0.0) (source "goalchainer:policy-actions")))))
     True))

;;; Policy rules carry stable registry names. The source and trust identity for
;;; registered rules remain inspectable through the SNARS rule trust ledger.
(sn rw gc-raw-risk ded-shape
  (sh (tag P d so ()) "has-property"
    (args ((arg s (sh-atom (tag C c NoRoles ()) "publish_raw_log"))
           (arg o (sh-atom (tag C c NoRoles ()) "exposes-sensitive-data")))))
  (sh (tag P d so ()) "has-property"
    (args ((arg s (sh-atom (tag C c NoRoles ()) "request"))
           (arg o (sh-atom (tag C c NoRoles ()) "sensitive-data")))))
  (sh (tag P d so ()) "has-property"
    (args ((arg s (sh-atom (tag C c NoRoles ()) "publish_raw_log"))
           (arg o (sh-atom (tag C c NoRoles ()) "risky"))))))

(sn rw gc-risk-forbidden ded-shape
  (sh (tag P d so ()) "has-property"
    (args ((arg s $action)
           (arg o (sh-atom (tag C c NoRoles ()) "risky")))))
  (sh (tag P d so ()) "has-property"
    (args ((arg s (sh-atom (tag C c NoRoles ()) "request"))
           (arg o (sh-atom (tag C c NoRoles ()) "sensitive-data")))))
  (sh (tag P d so ()) "has-property"
    (args ((arg s $action)
           (arg o (sh-atom (tag C c NoRoles ()) "forbidden"))))))

(sn rw gc-redacted-acceptable ded-shape
  (sh (tag P d so ()) "has-property"
    (args ((arg s $action)
           (arg o (sh-atom (tag C c NoRoles ()) "redacted")))))
  (sh (tag P d so ()) "has-property"
    (args ((arg s $action)
           (arg o (sh-atom (tag C c NoRoles ()) "protects-privacy")))))
  (sh (tag P d so ()) "has-property"
    (args ((arg s $action)
           (arg o (sh-atom (tag C c NoRoles ()) "acceptable"))))))

(sn rw gc-safe-coordination-acceptable ded-shape
  (sh (tag P d so ()) "has-property"
    (args ((arg s $action)
           (arg o (sh-atom (tag C c NoRoles ()) "supports-coordination")))))
  (sh (tag P d so ()) "has-property"
    (args ((arg s (sh-atom (tag C c NoRoles ()) "request"))
           (arg o (sh-atom (tag C c NoRoles ()) "public-data")))))
  (sh (tag P d so ()) "has-property"
    (args ((arg s $action)
           (arg o (sh-atom (tag C c NoRoles ()) "acceptable"))))))

(sn rw gc-hold-unverified-acceptable ded-shape
  (sh (tag P d so ()) "has-property"
    (args ((arg s $action)
           (arg o (sh-atom (tag C c NoRoles ()) "internal")))))
  (sh (tag P d so ()) "has-property"
    (args ((arg s (sh-atom (tag C c NoRoles ()) "request"))
           (arg o (sh-atom (tag C c NoRoles ()) "unverified")))))
  (sh (tag P d so ()) "has-property"
    (args ((arg s $action)
           (arg o (sh-atom (tag C c NoRoles ()) "acceptable"))))))

(sn rw gc-protection-acceptable ded-shape
  (sh (tag P d so ()) "has-property"
    (args ((arg s $action)
           (arg o (sh-atom (tag C c NoRoles ()) "protects-privacy")))))
  (sh (tag P d so ()) "has-property"
    (args ((arg s (sh-atom (tag C c NoRoles ()) "request"))
           (arg o (sh-atom (tag C c NoRoles ()) "sensitive-data")))))
  (sh (tag P d so ()) "has-property"
    (args ((arg s $action)
           (arg o (sh-atom (tag C c NoRoles ()) "acceptable"))))))
