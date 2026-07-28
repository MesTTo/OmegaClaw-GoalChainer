VALID_THREAD_SPEC = """\
# Incident response

The prose is explanatory and is not policy.

```metta
(thread-spec-v1 incident-42)
(thread-title incident-42 "Incident response")
(thread-owner incident-42 responder)
(thread-budget incident-42 120000 60000 1)
(thread-supervision incident-42 30 5 60 2)
(thread-role incident-42 control local-control)
(thread-role incident-42 worker local-worker)
(thread-role incident-42 supervisor thread-supervisor)
(thread-role incident-42 evaluator result-evaluator)
(thread-role incident-42 specialist security-specialist)
(thread-role incident-42 adjudicator security-owner)
(thread-workflow incident-42 research-agent)
(thread-mcp-profile incident-42 oh-my-goals)
(thread-workflow-step incident-42 research-agent 10 "Inspect existing evidence and source material.")
(thread-workflow-step incident-42 research-agent 20 "Implement only the released task and verify its acceptance condition.")
(thread-workflow-step incident-42 research-agent 30 "Report evidence, changed artifacts, and unresolved uncertainty.")
(thread-task incident-42 collect-evidence local evidence-collected normal)
(thread-task incident-42 redact-summary specialist summary-redacted high)
(thread-depends incident-42 redact-summary collect-evidence)
(thread-merge-policy incident-42 none none)
```
"""
