# Motivation snapshot cost

<!-- am[implements a-v2m-snapshot-sweep-1020@fefbd6] -->
<!-- am[related a-v2-review-package-1020@940ccf] -->
Every review of a domain with needs computes a motivation snapshot of the host's stream, and the
stream of a persistent agent grows every turn. `benchmarks/motivation.py` measures how the
snapshot's cost grows with the stream. Each stream holds m attempts, cycling through the companion
test domain's actions, each between a baseline observation of one need and the outcome observation
it produced, so every attempt gives one sample.

From a provisioned checkout:

```sh
PYTHONPATH=src:tests python -m benchmarks.motivation \
  --attempts 10 20 40 80 160 320 640 1280 2560 5120 > ai-tmp/motivation-cost.jsonl
```

The first line names the engine, the revision, the Python and the SHA-256 of the motivation policy
file measured. Each following line gives one stream size: the policy's inferences and seconds on
the stream held in memory, and the seconds to read the same stream back from a store file written
beforehand. The first snapshot in a process prepares the policy, which no review is charged for,
so a warm-up stream runs first and is not reported.

## Recorded measurements

<!-- am[rests-on c-v2m-snapshot-cost-measured-1020@eace58] am[rests-on c-v2m-flatten-once-quadratic-1020@98063a] -->
[The sweep's rows](results/motivation-snapshot-20261020.jsonl) and
[the rows of the policy before it](results/motivation-snapshot-37a75695-20261020.jsonl), at
`37a75695`, come from the same command on one machine:

| Attempts | Inferences before | Seconds before | Inferences after | Seconds after | Store read seconds |
| --- | --- | --- | --- | --- | --- |
| 10 | 91,010 | 0.013 | 23,204 | 0.005 | 0.001 |
| 80 | 1,653,279 | 0.119 | 136,744 | 0.016 | 0.003 |
| 320 | 20,718,519 | 1.29 | 526,024 | 0.060 | 0.014 |
| 1,280 | 336,339,479 | 19.6 | 2,083,144 | 0.274 | 0.055 |
| 5,120 | | | 8,311,624 | 1.96 | 0.350 |

The after rows measure policy digest
`f7c6bf315301610f12c84adee7d92c714e226ca23d4d951d10ce34c70202bb8e`,
recorded in the first line of the results file. That policy spends exactly
6,984 + 1,622 m inferences on every size measured. msort, which sorts
each list, counts as one inference however many comparisons it makes, so the count shows the
linear folds and not the m log m comparisons inside the five sorts. The seconds roughly double
with m; on this loaded machine repeated runs at 5,120 attempts took between 1.5 and 2.2 seconds.
Before the sweep each attempt rescanned the stream, and flatten-once and sort-by copied or
partitioned growing lists, so the inferences grew with the square of m.

Reading the stream back from its store is linear in its records and took between 18% and 28% of
the policy's seconds at every size. A longer stream therefore still costs more to review, in
proportion to its length: the sweep removes the square, not the stream.

<!-- am[related a-v2r-exact-sign-1020] am[related a-v2r-stable-magnitude-1020] -->
With each reduction's sign decided exactly and its magnitude evaluated from the exact gaps,
[the same command's rows](results/motivation-snapshot-exact-sign-20261020.jsonl), policy
`sha256:4750c1e764dc03f0697fadc713d148b7f568dd9d5268d1908c2d3ad2a0d921c9`, spend exactly
21,331 + 1,622 m inferences on every size measured: the same 1,622 for each attempt, and 14,347
more for each snapshot, spent on the reductions and the levels' urgencies, which grow with the
domain's actions and needs and not with the stream. At 5,120 attempts the policy took 1.44 seconds and the store read 0.26.
