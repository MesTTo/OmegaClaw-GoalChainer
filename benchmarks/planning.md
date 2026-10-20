# Planning outcomes and computation

<!-- am[implements a-integrate-planning-utility-eval-1017@879c87] -->
This experiment measures the current planner and the last experimental backward composer on
the same generated domains, procedure libraries, observations and runtime. The comparator is
the unchanged policy at `0a7ef56a5e3226c090c575799fb7b54c2cc223c6`, preserved as a fixture.
It was a work-in-progress prototype, never a shipped, budgeted planner. These measurements
are not a production before-and-after performance claim.

<!-- am[implements a-integrate-plan-eval-generator-1019@ed9341] -->
Each task starts with a chain of procedures. A procedure needs its predecessor's result and
then performs an action. Graph transformations add an alternative with the same prerequisites
but fewer actions, remove the chain's foundation, close it into a cycle, or require an observed
condition. The condition is independently unknown, true or false. Each task has one declared
entity. Names carry no policy meaning.

<!-- am[implements a-integrate-plan-eval-harness-1019@88aa3d] -->
The current planner returns a schedule, an inquiry or no plan. The old composer returns selected
procedures and their evidence class. It supplies no schedule. For these monotone graph tasks,
the harness simulates each selected procedure at most once, taking only transitions the
independent acceptance model enables. Both outcomes are checked by that model. An inquiry or
a pending selection is not counted as a reached goal. No host action runs, and an achieved
goal in the model does not establish a real-world outcome.
The arms have different output contracts, so their planning costs do not compare equivalent
end-to-end services.

Both arms pay for the current domain and procedure readers, then their own planning call,
under one inference allowance and deadline. Wall time includes Python construction and decoding.
Native inference counts do not measure Python work. Model validation happens afterwards and
has a separate elapsed-time field. Module loading and a first call of each arm are reported as
preparation, outside the warm-query measurements. These are not cold command-line timings.

The result rows retain each complete answer, simulated actions and model transitions separately
from inferences and seconds. There is no conversion from these quantities to a scalar utility or value of computation.
Budget exhaustion has its own status and no goal outcome. Unexpected failures stop the run.

<!-- am[implements a-integrate-plan-eval-verify-1019@791c8b] -->
From a checkout provisioned by `scripts/gate.sh`, run:

```sh
PYTHONPATH=src:tests .venv/bin/python -m benchmarks.planning \
  --lengths 1 2 3 --budgets 10000 1000000 10000000 \
  --seeds 17 23 --seconds 30 > ai-tmp/planning-grid.jsonl
```

The command needs the development dependencies because it reuses the acceptance suite's
domain renderer and independent model. The first row identifies the runtime, module hashes,
historical source blob, harness, renderer and oracle. Every task is written with its content
digest. Each query names that digest, its arm, limits and ordering seed. Seeds shuffle the
paired arm order without changing a task's evidence. The fixed grid has 21 tasks and 252 queries.

The comparison covers the declared finite graph family. It does not measure free-text reading,
host execution, outcome calibration, receipt promotion, multi-entity matching, or user workloads.

## Recorded grids

<!-- am[implements a-integrate-final-planning-grid-report-1019@e7e7c2] -->
The [soundness-repaired grid](results/planning-grid-soundness-20261019.jsonl) ran at
`9a34d007f9c05af26840701cee62cb105b51609c` with the command above. It contains all
252 distinct task, arm, budget and seed combinations. Every successful answer passed
the independent model's checks. Each budget has 42 queries per arm.

| Inference allowance | Prototype answers | Current answers | Prototype simulated goals | Current simulated goals |
| --- | ---: | ---: | ---: | ---: |
| 10,000 | 0 | 0 | 0 | 0 |
| 1,000,000 | 42 | 10 | 18 | 4 |
| 10,000,000 | 42 | 38 | 18 | 16 |

Every unanswered query exhausted its inference allowance. At ten million, the current
planner exhausts the limit for the length-3 alternative and unknown-condition tasks under
both ordering seeds. Both arms reach every chain and true-condition goal. Neither reaches
a missing, cyclic, unknown-condition or false-condition goal. For the two shorter
unknown-condition tasks, the current planner returns an inquiry; the prototype returns
a pending selection.

For the length-1 and length-2 alternatives, the current plan performs one fewer action:
1 and 2 actions against the prototype's 2 and 3. The alternatives have identical
prerequisites. The length-3 current query gives no answer within the measured allowances,
so this run establishes no action saving for it. For length 2 and ordering seed 17 at
ten million, the current planner spends 4,789,285 inferences against 607,335 for the prototype.
Across that allowance's 42 queries, including exhausted queries, measured query wall time
totals 9.961 seconds and 3.553 seconds respectively. Preparation takes another 5.506 seconds
for both arms together. Those timings belong to this machine and run.

The [earlier grid](results/planning-grid-20261019.jsonl), at
`87efba3707eaca5c0498c64972e5e9850de1cdc1`, predates the soundness and consistency repairs.
It answered 42 current-planner queries at ten million. Keep it as historical evidence;
the table above reports the repaired planner's lower completion count under that same limit.

These results establish a computation versus simulated-action tradeoff. They establish neither
an overall performance benefit nor that one saved action is worth its extra planning cost.
