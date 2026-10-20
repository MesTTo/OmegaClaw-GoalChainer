; Purpose: review research actions against observed evidence coverage, keeping a prohibition ahead
; of the largest predicted improvement. The numeric expectations are illustrative inputs.
; am[implements a-v2-examples-1019@2d047f]

(gc-domain "Research with an observed need")
(gc-policy-version research-v2)
(gc-authority advisory 0 "A suggestion for the researcher to consider.")
(gc-estimator-ceiling deterministic advisory)
(gc-estimator-ceiling measured advisory)
(gc-estimator-ceiling human-asserted advisory)
(gc-estimator-ceiling model-proposed advisory)
(gc-estimator-ceiling receipt-calibrated advisory)

(gc-action gather_evidence "Gather public evidence" "Query a public source for the missing evidence." (authority advisory))
(gc-action write_summary "Write a summary" "Summarize the evidence already available." (authority advisory))
(gc-action read_private "Read private notes" "Read another person's private notes." (authority advisory))
(gc-goal coverage researcher individual 1 "Cover the declared research questions with inspected sources."
  (priority-source human:researcher))
(gc-signal review_open "the host requests a review")
(normally rGather (signal review_open) (candidate gather_evidence))
(normally rSummary (signal review_open) (candidate write_summary))
(normally rPrivate (signal review_open) (candidate read_private))
(normally rPermit (candidate ?a) (may (do ?a)))
(always rPrivacy (signal review_open) (forbidden (do read_private)))
(normally rGeneral (signal review_open) (contributes gather_evidence coverage positive))
(gc-need evidence_coverage coverage (scale 0 1) (band 0.8 1) (drive 2) (need-source human:researcher))
(gc-need-expectation gather_evidence evidence_coverage 0.5 human-asserted (expectation-source human:demo-designer))
(gc-need-expectation write_summary evidence_coverage 0.1 human-asserted (expectation-source human:demo-designer))
(gc-need-expectation read_private evidence_coverage 0.8 human-asserted (expectation-source human:demo-designer))
