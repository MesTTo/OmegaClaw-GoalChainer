; Purpose: review a companion's suggestions against an observed target band, with the host choosing
; and reporting any action and outcome. The numeric expectations are illustrative inputs.
; am[implements a-v2-examples-1019@2d047f]

(gc-domain "Companion with an observed need")
(gc-policy-version companion-v2)
(gc-authority advisory 0 "A suggestion for the host to consider.")
(gc-estimator-ceiling deterministic advisory)
(gc-estimator-ceiling measured advisory)
(gc-estimator-ceiling human-asserted advisory)
(gc-estimator-ceiling model-proposed advisory)
(gc-estimator-ceiling receipt-calibrated advisory)

(gc-action guide_breath "Offer a breathing exercise" "Ask whether a breathing exercise would help." (authority advisory))
(gc-action stimulate "Suggest an active topic" "Offer a stimulating conversation topic." (authority advisory))
(gc-action stay_silent "Leave space" "Let the person choose whether to continue." (authority advisory))
(gc-goal comfort person individual 1 "Keep reported activation in the person's chosen band."
  (priority-source human:participant))
(gc-signal review_open "the host requests a review")
(normally rBreath (signal review_open) (candidate guide_breath))
(normally rTopic (signal review_open) (candidate stimulate))
(normally rSilence (signal review_open) (candidate stay_silent))
(normally rPermit (candidate ?a) (may (do ?a)))

; The ordinary band appraisal remains useful to the need-less control in the example test.
; For this regulated goal the observed reduction supplies the path value instead.
(normally rGeneral (signal review_open) (contributes guide_breath comfort positive))
(gc-need activation comfort (scale 0 1) (band 0.4 0.6) (drive 1) (need-source human:participant))
(gc-need-expectation guide_breath activation -0.4 human-asserted (expectation-source human:demo-designer))
(gc-need-expectation stimulate activation 0.1 human-asserted (expectation-source human:demo-designer))
(gc-need-expectation stay_silent activation 0 human-asserted (expectation-source human:demo-designer))
