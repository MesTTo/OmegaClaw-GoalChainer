# Hence lifecycle compatibility

The SPL block is the reference plan for Hence at
`81b8cac24013073f9b72f8886d2538df0ee8888b`. The MeTTa block declares the same
two-task graph for GoalChainer.

```spl
(given agent-coder-available)
(given task-evidence)
(given task-summary)
(given no-deps-evidence)
(normally ready-evidence
  (and task-evidence no-deps-evidence)
  ready-evidence)
(normally ready-summary
  completed-evidence
  ready-summary)
(normally assign-evidence
  (and ready-evidence agent-coder-available)
  assign-to-evidence-coder)
(normally assign-summary
  (and ready-summary agent-coder-available)
  assign-to-summary-coder)
```

```metta
(thread-spec-v1 hence-compatibility)
(thread-title hence-compatibility "Hence lifecycle compatibility")
(thread-owner hence-compatibility test-owner)
(thread-budget hence-compatibility 1000 500 1)
(thread-supervision hence-compatibility 2 2 4 1)
(thread-role hence-compatibility control test-control)
(thread-role hence-compatibility worker coder)
(thread-role hence-compatibility supervisor test-supervisor)
(thread-role hence-compatibility evaluator test-evaluator)
(thread-role hence-compatibility specialist test-specialist)
(thread-task hence-compatibility evidence local evidence-accepted normal)
(thread-task hence-compatibility summary local summary-accepted normal)
(thread-depends hence-compatibility summary evidence)
(thread-merge-policy hence-compatibility none none)
```
