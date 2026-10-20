# Attention scheduling experiment

<!-- am[implements a-integrate-planning-utility-eval-1017@879c87] -->
For the paired planner experiment, see [Planning outcomes and computation](planning.md).

<!-- am[implements a-integrate-cairn-harness-1018@4ba2ae] -->
Run the same frozen evidence through native SNARS ordering, ECAN ordering and seeded
random pair ordering. Every arm uses the production inference rules, support checks,
frontier capacity and forward-query stopping condition. The experiment runs on the
operator's MeTTa engine through pymetta.

From a provisioned checkout:

```sh
PYTHONPATH=src python -m benchmarks.attention \
  --lengths 1 3 --distractors 0 4 \
  --budgets 1000000 10000000 100000000 --seeds 17 23 \
  --seconds 180 > ai-tmp/attention-budget-curves.jsonl
```

Each workload contains a chain and independent distractor chains. A companion workload
removes one required edge. A three-edge chain tests an internal link whose endpoints are
absent from the query. Evidence is eight positive units per edge, with one source per
edge. These are declared experimental inputs, not production classification rules.

The first JSON line identifies the engine, loaded module digests, Python version and
harness digest. It reports module preparation separately. Each workload is emitted with
its digest; each query row names that digest, schedule, seed, resource limits, actual
inferences, elapsed seconds and result. Seeded arm order reduces systematic order bias.

<!-- am[implements a-integrate-benchmark-hold-budget-1018@1bd14c] -->
A query's budget includes evidence replay, frontier admission, attention graph construction
and diffusion where used, proof search, and receipt/trust invariant checks. Wall time also
includes host-side construction and decoding. The deadline covers the query's wait for the
engine too, so a query that cannot get the engine in time stops with `ReviewTimeout`.
Compilation of the shared benchmark world is startup work outside these warm-query
measurements. They do not measure cold CLI latency.
The random arm pays for its Python priority calculation, just as ECAN pays for graph work.
Inference counts measure engine work; seconds include grounded Python work as well.

`Witness` means the forward query returned a supported opinion and proof. It does not mean
the opinion passes a decision threshold or represents a true host observation. `Incomplete`
means the admitted frontier emptied without a witness. A bounded, lossy frontier is not a
complete theorem prover, so that result is not a proof of impossibility. Budget exhaustion
has its own status and no partial answer. Unexpected engine or protocol failures stop the
experiment.

All query mutations are speculative. The experiment checks that search preserves authored
receipt identities and source trust. Different schedules may find different proofs and
opinions; those answers are retained in the output rather than forced equal.

<!-- am[rests-on c-integrate-cairn-three-arm-source-1017@f0bd45] -->
The experimental structure follows CAIRN's full, attention and random arms at
[`c2c9c31`](https://github.com/trueagi-io/CAIRN/blob/c2c9c31e06a679f650a0d5bcf2cabe8760efc59a/bridge/steering.metta).
GoalChainer changes scheduling without filtering away evidence. Compare witness rates
at each common budget and inspect the returned proofs. Results on these generated chains
alone cannot establish a benefit on users' workloads, or expected value of computation.

## Recorded measurements

<!-- am[rests-on c-integrate-attention-curves-3577a38-1018@e2f27a] -->
The [initial grid](results/attention-grid-20261018.jsonl) contains 144 queries from
snapshot `3577a38dc7b346a031f8a40e361a7882ca5fc1f3`. Reproduce its inputs with:

```sh
PYTHONPATH=src python -m benchmarks.attention \
  --lengths 1 3 --distractors 0 2 \
  --budgets 100000 1000000 10000000 --seeds 17 23 --seconds 30
```

All three schedules have the same result counts at each budget. At 100,000 and
1,000,000 inferences, all 16 queries per schedule exhaust the budget. At 10,000,000,
each schedule returns six witnesses, eight incomplete searches and two budget stops.

The [larger-budget follow-up](results/attention-bridge-20261018.jsonl) isolates the
three-edge chain with two distractor chains, using `--lengths 3 --distractors 2
--budgets 20000000 --seeds 17 23 --seconds 30`. Every schedule finds a witness when
the bridge is present and returns Incomplete when its middle edge is absent.

| Schedule | Search steps, seeds 17 / 23 | Engine inferences, seeds 17 / 23 |
| --- | --- | --- |
| Native | 3 / 3 | 11,071,675 / 11,071,610 |
| ECAN | 2 / 2 | 11,162,236 / 11,162,234 |
| Random | 7 / 10 | 11,094,514 / 11,104,203 |

ECAN selects a shorter search on this fixture, but its total engine work exceeds
native ordering. These measurements establish neither a budget advantage nor a
benefit on user workloads. The raw rows retain proofs, opinions, module identities
and elapsed times for further comparison.
