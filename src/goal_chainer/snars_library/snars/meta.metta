;;; SNARS module — metadata format v2: option normalization, clause readers,
;;; residue channel, assembled views (plan: 2026-06-12 metadata-format).
;;; Import via the snars.metta aggregator; load order lives there.

;; ---- F5: the keyword->clause-head map is data; flat-form recognition is
;; closed over this table (extensions use clause form) ----
(sn kw :evidence evidence) (sn kw :rate rate) (sn kw :source source)
(sn kw :trust trust) (sn kw :domain domain) (sn kw :kind kind)
(sn kw :occ occ) (sn kw :claim claim) (sn kw :desire desire)
(sn kw :quantifier quant) (sn kw :hedge hedge)

(= (sn kw-of $x)
   (case (collapse (match &self (sn kw $x $name) $name))
     ((() NoKw)
      (($n) $n))))

;; collect a flat keyword's values: everything until the next registered keyword
(: (sn kw-vals) (-> Atom Expression))
(= (sn kw-vals $opts)
   (if (== $opts ())
       (() ())
       (let ($h $t) (decons-atom $opts)
         (if (and (== (get-metatype $h) Symbol) (not (== (sn kw-of $h) NoKw)))
             (() $opts)
             (let ($vs $rest) (sn kw-vals $t)
               ((cons-atom $h $vs) $rest))))))

;; ---- ONE normalizer: clause groups pass through; flat :keys become clauses;
;; stray non-keyword atoms in flat position are preserved as (unknown-opt x) ----
(: (sn opts-norm) (-> Atom Expression))
(= (sn opts-norm $opts)
   (if (== $opts ())
       ()
       (let ($h $t) (decons-atom $opts)
         (if (== (get-metatype $h) Expression)
             (cons-atom $h (sn opts-norm $t))
             (let $name (sn kw-of $h)
               (if (== $name NoKw)
                   (cons-atom (unknown-opt $h) (sn opts-norm $t))
                   (let ($vs $rest) (sn kw-vals $t)
                     (cons-atom (cons-atom $name $vs) (sn opts-norm $rest)))))))))

;; ---- clause readers (the opt family over normalized clauses; extra clause
;; tail elements are tolerated, first value(s) win). opt-c is documented for
;; arity>=1 heads only; opt?-c is for flags (decons-atom on a zero-value
;; clause like (claim) yields (claim ())) ----
(: (sn opt-c) (-> Atom %Undefined% %Undefined% %Undefined%))
(= (sn opt-c $clauses $head $default)
   (if (== $clauses ())
       $default
       (let ($h $t) (decons-atom $clauses)
         (let ($ch $vals) (decons-atom $h)
           (if (== $ch $head)
               (car-atom $vals)
               (sn opt-c $t $head $default))))))

(: (sn opt2-c) (-> Atom %Undefined% Atom Expression))
(= (sn opt2-c $clauses $head $defaults)
   (if (== $clauses ())
       $defaults
       (let ($h $t) (decons-atom $clauses)
         (let ($ch $vals) (decons-atom $h)
           (if (== $ch $head)
               (let ($v1 $vr) (decons-atom $vals)
                 ($v1 (car-atom $vr)))
               (sn opt2-c $t $head $defaults))))))

(: (sn opt?-c) (-> Atom %Undefined% Bool))
(= (sn opt?-c $clauses $head)
   (if (== $clauses ())
       False
       (let ($h $t) (decons-atom $clauses)
         (let ($ch $vals) (decons-atom $h)
           (if (== $ch $head)
               True
               (sn opt?-c $t $head))))))

;; ---- F4: the open channel. Heads consumed by the kernel never land here;
;; everything else is an extension's per-statement metadata, verbatim ----
(sn opt-known evidence) (sn opt-known rate) (sn opt-known source)
(sn opt-known trust) (sn opt-known domain) (sn opt-known kind)
(sn opt-known occ) (sn opt-known claim) (sn opt-known desire)
(sn opt-known quant) (sn opt-known hedge)

(= (sn opt-known? $h)
   (not (== () (collapse (once (match &self (sn opt-known $h) True))))))

(: (sn meta-residue!) (-> %Undefined% %Undefined% Atom Bool))
(= (sn meta-residue! $sid $sigma $clauses)
   (if (== $clauses ())
       True
       (let ($h $t) (decons-atom $clauses)
         (let ($ch $vals) (decons-atom $h)
           (let $w (if (sn opt-known? $ch)
                       ()
                       (if (== () (collapse (once (match &self (sn meta $sid $sigma $h) True))))
                           (add-atom &self (sn meta $sid $sigma $h))
                           ()))
             (sn meta-residue! $sid $sigma $t))))))

;; ---- F6: the assembled view (inspection surface; rules match fact families) ----
(: (sn meta-view) (-> %Undefined% Expression))
(= (sn meta-view $sid)
   (collapse (superpose (
     (match &self (sn stmt $sid $t) (tree $t))
     (let (Ev $r $s $a) (sn evidence $sid) (ev $r $s $a))
     (match &self (sn domain $sid $d) (domain $d))
     (match &self (sn kind $sid $k) (kind $k))
     (match &self (sn occ $sid $t) (occ $t))
     (match &self (sn from $sid $e) (from $e))
     (match &self (sn receipt $sid $g $h) (src $g))
     (match &self (sn proof $sid $p) (proof $p))
     (match &self (sn q $sid $g $q) (q $g $q))
     (match &self (sn hedged $sid $g $h) (hedge $g $h))
     (match &self (sn att $sid $g $c) (att $g $c))
     (match &self (sn deixis $sid $g $d) (deixis $g $d))
     (match &self (sn ctx $sid $c) (ctx $c))
     (match &self (sn predicted $sid) (predicted))
     (match &self (sn meta $sid $g $c) (meta $g $c))))))

;; membership test over the view. PeTTa's 4-arg atom-form unify does NOT
;; reduce (probe 2026-06-12 -- returns as data); the check rides the one-line
;; kernel helper sn_unifiable/3 instead (which returns PeTTa-native booleans:
;; lowercase Prolog true/false -- probe 2026-06-13). The view tuple is
;; let-bound before superpose (superpose's tuple is taken as data).
(: (sn meta?) (-> %Undefined% %Undefined% Bool))
(= (sn meta? $sid $pat)
   (not (== () (collapse
     (let $vs (sn meta-view $sid)
       (let $c (superpose $vs)
         (if (sn_unifiable $c $pat) ok (empty))))))))
