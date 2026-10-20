;;; SNARS module — temporal layer (Mapping 3.1 step 6; SLN 9.3/9.5d).
;;; Import via the snars.metta aggregator; load order lives there.
;;; Opt-in (temporal-cells, default OFF): occ-carrying units land in an EVENT
;;; cell keyed (Event <canon> <occ>) so repeated same-source observations at
;;; different times are NOT receipt-blocked; temporal! then folds each event
;;; cell into the plain (eternal) cell at lambda^(now-t) (project->eternalize->
;;; fuse, SLN 9.3), idempotent via (sn etern <sid> <t>) markers, and closes
;;; gap<=interval-gap occ runs into intervals (oPIEC-lite: Mantenoglou,
;;; Artikis & Paliouras, ECAI 2020 / IJAR 161 2023 -- the support-set
;;; algorithm is the committed upgrade path at p1 scale, SLN 9.5d).

(= (sn config interval-gap) (sn cfg interval-gap 1.0))
(= (sn config temporal-lambda) (sn cfg temporal-lambda 0.9))
(= (sn temporal-cells?) (== 1 (sn cfg temporal-cells 0)))

;; ---- numeric occ aggregation (symbolic occs from t-roles are skipped) ----
;; [perf: insertion sort is O(n^2) MeTTa; the kernel msort/2 is the upgrade
;; path if interval recall grows at p1 scale -- fixture-scale timing shrugs]
(: (sn num-insert) (-> Atom Number Expression))
(= (sn num-insert $xs $x)
   (if (== $xs ())
       ($x)
       (let ($h $t) (decons-atom $xs)
         (if (<= $x $h)
             (cons-atom $x $xs)
             (cons-atom $h (sn num-insert $t $x))))))

(: (sn sort-nums) (-> Atom Expression))
(= (sn sort-nums $xs)
   (if (== $xs ())
       ()
       (let ($h $t) (decons-atom $xs)
         (sn num-insert (sn sort-nums $t) $h))))

(= (sn numeric? $x) (== (get-metatype $x) Grounded))

(= (sn interval! $sid $t1 $t2)
   (with_mutex sn-commit
     (if (== () (collapse (match &self (sn interval $sid $t1 $t2) True)))
         (let $added (add-atom &self (sn interval $sid $t1 $t2)) True)
         False)))

;; oPIEC-lite: runs of occ points with gaps <= interval-gap close into intervals
(: (sn runs!) (-> %Undefined% Number Number Atom Bool))
(= (sn runs! $sid $start $prev $rest)
   (if (== $rest ())
       (if (< $start $prev) (sn interval! $sid $start $prev) True)
       (let ($h $t) (decons-atom $rest)
         (if (<= (- $h $prev) (sn config interval-gap))
             (sn runs! $sid $start $h $t)
             (let $closed (if (< $start $prev) (sn interval! $sid $start $prev) True)
               (sn runs! $sid $h $h $t))))))

(= (sn intervals! $sid)
   (let $ts (sn sort-nums (collapse (match &self (sn occ $sid $t)
                                      (if (sn numeric? $t) $t (empty)))))
     (if (== $ts ())
         False
         (let ($h $t) (decons-atom $ts)
           (sn runs! $sid $h $h $t)))))

;; ---- project -> eternalize -> fuse (SLN 9.3) ----
(= (sn eternalized? $sid $t)
   (not (== () (collapse (match &self (sn etern $sid $t) True)))))

(= (sn eternalize-one! $sid $canon $t $now)
   (if (sn eternalized? $sid $t)
       False
       (let* (($esid (sn sid (Event $canon $t)))
              ((Ev $r $s $a) (sn evidence $esid))
              ($p (pow-math (sn config temporal-lambda) (max 0.0 (- $now $t))))
              ($fused (sn input $sid $r $s (sn config default-rate) "eternal" $p))
              ($marked (with_mutex sn-commit
                         (if (sn eternalized? $sid $t)
                             True
                             (let $a2 (add-atom &self (sn etern $sid $t)) True)))))
         True)))

;; the budgeted step-6 pass: intervals + eternalization over occ-carrying
;; statements; no-op unless temporal-cells mode is on
;; NB: the occ-pair collection is let-bound BEFORE superpose -- superpose takes
;; its tuple as syntax, so a computed collection passed inline is not evaluated
;; (the pinned PeTTa gotcha; the original plan snippet had it inline).
(: (sn temporal!) (-> Number Number Expression))
(= (sn temporal! $budget $now)
   (if (sn temporal-cells?)
       (let $pairs (sn fr-take $budget
                     (collapse (match &self (sn occ $sid $t)
                                 (if (sn numeric? $t) ($sid $t) (empty)))))
         (collapse
           (let $pair (superpose $pairs)
             (let ($sid $t) $pair
               (match &self (sn stmt $sid $canon)
                 (let* (($iv (sn intervals! $sid))
                        ($et (sn eternalize-one! $sid $canon $t $now)))
                   $sid))))))
       ()))

;; convenience control loop: derive cycles + the temporal pass
(= (sn cycle+! $n $now)
   (let* (($d (sn cycles $n))
          ($t (sn temporal! (sn config frontier-cap) $now)))
     ()))
