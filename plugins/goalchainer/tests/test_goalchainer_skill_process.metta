; Purpose: verify the installed plugin's domain request, typed failures and child environment.
; Run from the Omega root with the plugin installed. The installer records the child
; interpreter in goalchainer_host.py; the request loads its declared domain and reviews its Jev
; readings.
; am[verifies a-rt-skill-process-boundary-1016@a36729]
; am[verifies a-integrate-domain-surface-1018@759698]
!(import! &self (py-call (posixpath.abspath "plugins/goalchainer/goalchainer")))

; The returned record is computed by the same public adapter the CLI calls.
; am[verifies a-integrate-domain-surface-1018@759698]
!(test (py-call (operator.contains
                  (goalchainer-request "{\"operation\":\"review\",\"domain\":{\"packaged\":\"incident\"},\"context\":{\"review_id\":\"plugin-example\",\"subject\":\"checkout\",\"trigger\":\"incident-report\",\"as_of\":\"2026-10-16T09:00:00+00:00\",\"authority\":\"advisory\",\"policy_version\":\"incident-v1\",\"readings\":[]},\"reading\":{\"text\":\"Checkout is down. Raw logs include customer emails. Engineering needs the incident room.\",\"observed_at\":\"2026-10-16T09:00:00+00:00\",\"valid_until\":null},\"inference_budget\":1000000000,\"timeout_seconds\":600}")
                  "goalchainer-request-v1"))
       True)

; A malformed request keeps its typed error across the process boundary.
; am[verifies a-rt-skill-process-boundary-1016@a36729]
!(test (py-call (skill_probe.failure_code (goalchainer-python) "goalchainer-snars-dispatch" "not json"))
       invalid_input)
; am[verifies a-v2-cli-skill-surface-1020@6f755c]
!(test (py-call (skill_probe.failure_code (goalchainer-python) "goalchainer-motivation-dispatch" "not json"))
       invalid_input)

; Host runtime variables must not affect the child's own interpreter configuration.
; am[verifies a-rt-skill-process-boundary-1016@a36729]
; am[verifies a-integrate-domain-surface-1018@759698]
!(test (py-call (operator.contains
                  (py-call (skill_probe.request_under_host_settings (goalchainer-python)
                             "{\"operation\":\"review\",\"domain\":{\"packaged\":\"incident\"},\"context\":{\"review_id\":\"plugin-example\",\"subject\":\"checkout\",\"trigger\":\"incident-report\",\"as_of\":\"2026-10-16T09:00:00+00:00\",\"authority\":\"advisory\",\"policy_version\":\"incident-v1\",\"readings\":[]},\"reading\":{\"text\":\"Checkout is down. Raw logs include customer emails. Engineering needs the incident room.\",\"observed_at\":\"2026-10-16T09:00:00+00:00\",\"valid_until\":null},\"inference_budget\":1000000000,\"timeout_seconds\":600}"))
                  "goalchainer-request-v1"))
       True)

!(println! test-goalchainer-skill-process-done)
