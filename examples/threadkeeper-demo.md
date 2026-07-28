# ThreadKeeper orchestration demo

The semantic facts below define the plan and worker workflow. Mettabase parses
the fence. MeTTaScript validates and compiles it.

```metta
(thread-spec-v1 threadkeeper-demo)
(thread-title threadkeeper-demo "ThreadKeeper orchestration demo")
(thread-owner threadkeeper-demo demo-owner)
(thread-budget threadkeeper-demo 1000 500 1)
(thread-supervision threadkeeper-demo 1 2 5 2)
(thread-role threadkeeper-demo control demo-control)
(thread-role threadkeeper-demo worker demo-worker)
(thread-role threadkeeper-demo supervisor demo-supervisor)
(thread-role threadkeeper-demo evaluator demo-evaluator)
(thread-role threadkeeper-demo specialist demo-specialist)
(thread-role threadkeeper-demo adjudicator demo-adjudicator)
(thread-workflow threadkeeper-demo guided-research)
(thread-workflow-step threadkeeper-demo guided-research 10 "Inspect the repository, task dependencies, and available evidence.")
(thread-workflow-step threadkeeper-demo guided-research 20 "Perform only the released task and check its acceptance condition.")
(thread-workflow-step threadkeeper-demo guided-research 30 "Report the result, verification evidence, and unresolved uncertainty.")
(thread-task threadkeeper-demo collect-evidence local evidence-collected normal)
(thread-task threadkeeper-demo redact-summary specialist summary-redacted high)
(thread-task threadkeeper-demo retry-check local retry-accepted normal)
(thread-task threadkeeper-demo permanent-failure local failure-observed normal)
(thread-task threadkeeper-demo blocked-child local child-never-runs normal)
(thread-task threadkeeper-demo budget-denied specialist budget-denial-observed normal)
(thread-depends threadkeeper-demo redact-summary collect-evidence)
(thread-depends threadkeeper-demo retry-check redact-summary)
(thread-depends threadkeeper-demo permanent-failure retry-check)
(thread-depends threadkeeper-demo blocked-child permanent-failure)
(thread-merge-policy threadkeeper-demo none none)
```
