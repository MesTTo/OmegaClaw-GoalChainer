; Purpose: settle the incident example host's execution step from its primitives: what each
; execution condition says and which raw-log fields are restricted.
;
;   (gc-settle-conditions NORM (Authorization GRANTED REASON) ARTIFACT) -> (Conditions CONDITION ...)
;   (gc-settle-field-classes ("FIELD" ...)) -> ((Field "FIELD" CLASS) ...)
;
; ARTIFACT is NoArtifact, or (Artifact VERDICT) with VERDICT NoRestrictedValues or
; RestrictedValuesFound, the host's containment check of what it prepared. A CONDITION is
; (Condition NAME STATUS REASON) with STATUS True, False or Unknown; Unknown means nothing observed
; settles the facet, never that it is false, after Kubernetes status conditions.
; am[implements a-ev-mr-settle@e40f9f] am[rests-on c-integrate-user-metta-policy-1016@9eb3d0]
;
; Each entry Python calls declares its type, as goal_chainer.runtime.evaluator requires: a scalar
; parameter its own type, structured data Atom so hole data stays inert, and a result that may be a
; symbol or an expression %Undefined%.
; am[implements a-rt-rb-migrate-evidence-1018@4fa74b] am[rests-on c-ev-rb-precise-param-types-1018@6b8293]

; The host's blocking cut: exactly forbidden and conflict. It is a policy of its own, not read off
; the deontic status order, though today it is exactly the statuses at least forbidden, which a test
; checks (c-core-blocking-cut-independent-1017). It came here from the retired scorer, its only
; other reader.
; am[implements a-ie-s2a-blocking-cut-home-1018@dd66bf] am[rests-on c-core-blocking-cut-independent-1017@b1b8b4]
(= (gc blocking-status? $deontic)
   (or (== $deontic forbidden) (== $deontic conflict)))

; Whether a step under NORM may be authorized: it may unless NORM is in the blocking cut above. The
; Admissible condition reads it, and the host asks it before it prepares anything for a step it
; authorized.
; am[implements a-ie-s5-incident-host-1018@53176a] am[rests-on c-ie-host-keeps-explicit-cut-1018@7116c5]
; am[implements a-integrate-example-host-inputs-1018@f0d0fa] am[implements a-ie-s2a-blocking-cut-home-1018@dd66bf]
(: gc-settle-admissible (-> Atom Bool))
(= (gc-settle-admissible $norm) (not (gc blocking-status? $norm)))

; Every facet is derived from the norm, the authorization and the artifact, so no two can disagree.
; GoalChainer performs no host effect, so EffectConfirmed is never True: only a host receipt can
; confirm it.
; am[implements a-ie-s5-incident-host-1018@53176a] am[implements a-integrate-example-host-inputs-1018@f0d0fa]
(: gc-settle-conditions (-> Atom Atom Atom Expression))
(= (gc-settle-conditions $norm (Authorization $granted $reason) $artifact)
   (Conditions
     (Condition Admissible (gc-settle-admissible $norm) (Norm $norm))
     (Condition Authorized $granted $reason)
     (gc-settle-prepared $artifact)
     (gc-settle-privacy $artifact)
     (gc-settle-release $artifact)
     (gc-settle-effect $artifact)))

(= (gc-settle-prepared NoArtifact) (Condition ArtifactPrepared False NotAttempted))
(= (gc-settle-prepared (Artifact $verdict)) (Condition ArtifactPrepared True Prepared))
(= (gc-settle-privacy NoArtifact) (Condition PrivacyVerified Unknown NotAttempted))
(= (gc-settle-privacy (Artifact NoRestrictedValues)) (Condition PrivacyVerified True NoRestrictedValues))
(= (gc-settle-privacy (Artifact RestrictedValuesFound)) (Condition PrivacyVerified False RestrictedValuesFound))
(= (gc-settle-release NoArtifact) (Condition ReleaseEligible False NotAttempted))
(= (gc-settle-release (Artifact NoRestrictedValues)) (Condition ReleaseEligible True PrivacyVerified))
(= (gc-settle-release (Artifact RestrictedValuesFound)) (Condition ReleaseEligible False PrivacyCheckFailed))
(= (gc-settle-effect NoArtifact) (Condition EffectConfirmed Unknown NoEffectExpected))
(= (gc-settle-effect (Artifact NoRestrictedValues)) (Condition EffectConfirmed Unknown AwaitingHostReceipt))
(= (gc-settle-effect (Artifact RestrictedValuesFound)) (Condition EffectConfirmed Unknown NoEffectExpected))

; Only fields declared safe for coordination keep their values; every other raw-log field is
; restricted, so a field nobody listed is redacted and searched for, never released.
; am[implements a-ev-mr-privacy-classes@d79884] am[addresses i-ev-privacy-denylist@9fa13e]
(= (gc-settle-diagnostic-fields) ("error_code" "failure_mode" "affected_surface"))
(: gc-settle-field-classes (-> Atom Expression))
(= (gc-settle-field-classes $fields)
   (map-atom $fields $field
     (Field $field (if (is-member $field (gc-settle-diagnostic-fields)) diagnostic restricted))))
