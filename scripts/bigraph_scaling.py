"""Purpose: measure the bigraph kernel's cost against state size on a warm pymetta engine and write one
JSON row per size and operation: faults, every occurrence, one rewrite, isomorphism against a renamed
copy, the bucket, successors and transitions, each the fastest of REPEATS runs with its inferences, every
run on states renamed afresh so that no engine cache answers a repeat. Each program reduces its answer
to a size or a Boolean inside the engine, so a row times the kernel rather than the conversion of 128
states to Python, which took 60% of successors' time at 256 nodes.

Usage: python scripts/bigraph_scaling.py [--kernel PATH] --sizes 8,16,32 --out ROWS.jsonl [--repeats 3]
       [--ops iso,bucket]
       python scripts/bigraph_scaling.py --fit ROWS.jsonl...

--fit reads rows and prints, per kernel and operation, the cost class that fits them best.

The states hold n/4 rooms under one root, each room holding a host that shares a closed edge with it and
holds two items; every id is anonymous. The rule turns one item of a host online, so a state of n nodes
has n/2 occurrences, and a renamed copy of the state is isomorphic to it."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from collections import defaultdict
from pathlib import Path

KERNEL = Path(__file__).resolve().parents[1] / "src" / "goal_chainer" / "bigraph" / "kernel.metta"
SIG = ("(Signature (Control Room 1 active) (Control Host 1 active) (Control Item 0 atomic) "
       "(Control Online 0 atomic) (Control Cell 0 passive))")
REDEX = ("(Bigraph (Inner 1 ()) (Outer 1 ()) (Nodes (N R Room) (N H Host) (N I Item)) "
         "(Place (In R (Root 0)) (In H R) (In I H) (In (Site 0) H)) (Link (P R 0 (Edge e)) (P H 0 (Edge e))))")
REACTUM = ("(Bigraph (Inner 1 ()) (Outer 1 ()) (Nodes (N R Room) (N H Host) (N O Online)) "
           "(Place (In R (Root 0)) (In H R) (In O H) (In (Site 0) H)) (Link (P R 0 (Edge e)) (P H 0 (Edge e))))")
RULE = f"(Rule use {REDEX} {REACTUM} (Eta (0 0)) (Conditions) (Priority 0))"
# The program of each operation on a state S and a renamed copy T, answering a number or a Boolean that
# the row records: no faults, n/2 occurrences and successors, a four-part (Successor NAME OCC G'), True, a
# four-part bucket, and one transition, since every successor of a scaling state is isomorphic to every
# other.
OPS = {
    "faults": "!(size-atom (bg-faults {sig} {s}))",
    "occurrences": "!(size-atom (collapse (bg-occurrence {sig} {rule} {s})))",
    "apply-one": "!(size-atom (let $o (once (bg-occurrence {sig} {rule} {s})) (bg-apply {sig} {rule} {s} $o)))",
    "iso": "!(bg-iso {s} {t})",
    "bucket": "!(size-atom (bg-bucket {s}))",
    "successors": "!(size-atom (bg-successors {sig} ({rule}) {s}))",
    "transitions": "!(size-atom (bg-transitions {sig} ({rule}) {s}))",
}
# The classes rows are fitted against, each as seconds = a + c * f(n): a is the fixed cost of one engine
# run, which dominates the small sizes, and c the cost per unit of f.
CLASSES = {
    "log n": math.log2,
    "n": float,
    "n log n": lambda n: n * math.log2(n),
    "n^2": lambda n: float(n * n),
    "n^2 log n": lambda n: n * n * math.log2(n),
    "n^3": lambda n: float(n) ** 3,
}


# am[implements a-brs-k-st-scaling-1018@fe09da]
def state(n: int, tag: str) -> str:
    nodes, place, link = [], [], []
    for r in range(max(1, n // 4)):
        room, host = f"(new {tag} r{r})", f"(new {tag} h{r})"
        nodes += [f"(N {room} Room)", f"(N {host} Host)"]
        place += [f"(In {room} (Root 0))", f"(In {host} {room})"]
        link += [f"(P {room} 0 (Edge (e{tag} {r})))", f"(P {host} 0 (Edge (e{tag} {r})))"]
        for i in range(2):
            item = f"(new {tag} i{r} {i})"
            nodes.append(f"(N {item} Item)")
            place.append(f"(In {item} {host})")
    return (f"(Bigraph (Inner 0 ()) (Outer 1 ()) (Nodes {' '.join(nodes)}) (Place {' '.join(place)}) "
            f"(Link {' '.join(link)}))")


# The fastest of REPEATS runs, so another process's load inflates no row. Each run gets states under
# fresh ids: pymetta memoizes some recursive functions and keeps compiled queries, so a repeat of the same
# text could be answered from a cache.
# am[implements a-brs-k-st-scaling-1018@fe09da]
def measure(m, op: str, n: int, repeats: int):
    best = None
    for k in range(repeats):
        code = OPS[op].format(sig=SIG, rule=RULE, s=state(n, f"a{k}"), t=state(n, f"b{k}"))
        with m.stats() as spent:
            started = time.perf_counter()
            result = m.self.run(code)
            seconds = time.perf_counter() - started
        if best is None or seconds < best[1]:
            best = (spent.inferences, seconds, result)
    return best


# Least squares of seconds = a + c * f(n) over the rows, each residual relative to its row's seconds so
# that the small sizes count as much as the large, with a and c kept non-negative; answers (a, c, RSS).
# Time: one pass over the rows.
# am[implements a-brs-k-st-scaling-1018@fe09da]
def fit_class(points: list[tuple[int, float]], f) -> tuple[float, float, float]:
    sw = sx = sxx = st = sxt = 0.0
    for n, t in points:
        w, x = 1 / (t * t), f(n)
        sw, sx, sxx, st, sxt = sw + w, sx + w * x, sxx + w * x * x, st + w * t, sxt + w * x * t
    det = sw * sxx - sx * sx
    a, c = ((sxx * st - sx * sxt) / det, (sw * sxt - sx * st) / det) if det > 0 else (-1.0, 0.0)
    if a < 0:
        a, c = 0.0, sxt / sxx
    if c < 0:
        a, c = st / sw, 0.0
    return a, c, sum(((t - a - c * f(n)) / t) ** 2 for n, t in points)


# Per kernel and operation, the class with the least Akaike information criterion: every class has the
# same two parameters, so this is the least residual, and the margin to the runner-up says how clearly
# the rows separate the two.
# Time: K classes times one pass over the rows.
# am[implements a-brs-k-st-scaling-1018@fe09da]
def fit(paths: list[Path]) -> None:
    groups: dict[tuple[str, str], list[tuple[int, float]]] = defaultdict(list)
    for path in paths:
        for line in path.read_text().splitlines():
            row = json.loads(line)
            groups[row["kernel"], row["op"]].append((row["nodes"], row["seconds"]))
    for (kernel, op), points in sorted(groups.items()):
        if len(points) < 3:
            print(f"{kernel} {op}: {len(points)} sizes, too few to separate classes")
            continue
        ranked = sorted((len(points) * math.log(max(rss, 1e-300) / len(points)) + 4, name, a, c)
                        for name, f in CLASSES.items() for a, c, rss in [fit_class(points, f)])
        (best, name, a, c), (runner, runner_name, _, _) = ranked[0], ranked[1]
        sizes = sorted(n for n, _ in points)
        print(f"{kernel} {op}: {name}, {1e3 * a:.2f} ms + {c:.3g} s x f(n) over n = {sizes[0]}..{sizes[-1]}, "
              f"AIC {best - runner:.1f} below {runner_name}")


# am[implements a-brs-k-st-scaling-1018@fe09da]
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--kernel", type=Path, default=KERNEL)
    parser.add_argument("--sizes")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--ops", default=",".join(OPS), help="operations to measure, of " + ", ".join(OPS))
    parser.add_argument("--fit", type=Path, nargs="+", help="rows to fit instead of measuring")
    args = parser.parse_args()
    if args.fit:
        fit(args.fit)
        return
    if not (args.sizes and args.out):
        parser.error("measuring needs --sizes and --out")
    ops = args.ops.split(",")
    unknown = sorted(set(ops) - set(OPS))
    if unknown:
        parser.error(f"unknown operations {unknown}; known: {list(OPS)}")
    # Imported here so that --fit runs where pymetta is not installed.
    from metta import MeTTa

    source = args.kernel.read_text()
    digest = hashlib.sha256(source.encode()).hexdigest()[:12]
    with MeTTa() as m, args.out.open("w") as out:
        m.self.run(source)
        for program in OPS.values():  # compiles every operation once
            m.self.run(program.format(sig=SIG, rule=RULE, s=state(8, "w"), t=state(8, "v")))
        for n in (int(s) for s in args.sizes.split(",")):
            for name in ops:
                inferences, seconds, result = measure(m, name, n, args.repeats)
                row = {"kernel": digest, "nodes": state(n, "a").count("(N "), "op": name, "inferences": inferences,
                       "seconds": round(seconds, 4), "answer": result[0][0].value}
                out.write(json.dumps(row) + "\n")
                out.flush()
                print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
