"""Purpose: generate tests/data/bigraph/bigrapher-random.json, BigraphER's reference for the kernel's
random differential: random ground agents and solid rules from bigraph_oracle's generator, restricted to
the fragment on which BigraphER and the kernel share semantics, are written as BigraphER models and run
through `bigrapher full --solver=GBS`; each model whose state space closes within the state bound is kept
with BigraphER's state, transition and occurrence counts and its states read back as kernel terms. With
--check it regenerates into a scratch directory and reports every difference from the committed data.

Usage: python tests/bigraph_bigrapher_reference.py --bigrapher PATH --scratch DIR [--check]"""

from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
from pathlib import Path

import bigraph_oracle as o

DATA = Path(__file__).resolve().parent / "data" / "bigraph" / "bigrapher-random.json"
SEED = 20261018
MODELS = 80
MAX_STATE_INDEX = 20
# The state bound caps how many states BigraphER explores, not how large they grow: a rule copying a
# region into itself doubles a state every step, so each run also stops after this many seconds and
# its model is dropped like one reaching the state bound.
# am[rests-on c-brs-k-bigrapher-size-unbounded-1018]
SECONDS = 10
# The shared fragment: BigraphER keeps a node's ports as a multiset where the kernel keeps them positional,
# so no control has two ports; BigraphER has no passive controls, named nodes or kernel conditions, so the
# models use none; agents have no idle names and redexes no inner names.
# am[rests-on c-integrate-brs-positional-oracle-1018@6f9f3a] am[rests-on c-brs-k-no-passive-controls-1018@9a40f1]
FRAGMENT = {c.name: c for c in (o.Control("A", 0, "active"), o.Control("B", 1, "active"),
                                o.Control("T", 0, "atomic"), o.Control("U", 1, "atomic"))}


# A model the fragment allows: one or two rules, in one priority class or two, each reactum linking every
# outer name of its redex, since BigraphER infers a bigraph's outer face from the names it uses.
# am[implements a-brs-k-bigrapher-1018@994f8c]
def random_model(rng: random.Random) -> tuple[o.Big, list[o.Rule]]:
    agent = o.random_agent(rng, FRAGMENT, max_nodes=7, named=0.0, idle_names=0.0)
    count = rng.choice((1, 1, 2))
    classes = rng.choice((1, 2)) if count == 2 else 1
    rules = []
    for i in range(count):
        while True:
            redex = o.random_redex(rng, FRAGMENT, agent, inner_names=False)
            reactum, eta = o.random_reactum(rng, FRAGMENT, redex)
            used = {l[1] for pt, l in reactum.links.items() if pt[0] == "port" and l[0] == "name"}
            if o.well_formed(reactum, FRAGMENT) and used == set(redex.outer):
                break
        rules.append(o.Rule(f"r{i}", redex, reactum, eta, [], (classes - 1) - min(i, classes - 1)))
    return agent, rules


# The BigraphER expression of B and its sites in textual order: BigraphER numbers sites left to right,
# so SITES[i] is the site of B that BigraphER calls i. Closed edges become closed names zE.
# am[implements a-brs-k-bigrapher-1018@994f8c]
def expression(b: o.Big) -> tuple[str, list[int]]:
    sites: list[int] = []

    def place(p) -> str:
        if isinstance(p, tuple):
            sites.append(p[1])
            return "id"
        control = FRAGMENT[b.controls[p]]
        link = b.links.get(("port", p, 0))
        label = control.name + (f"{{{link[1] if link[0] == 'name' else 'z' + link[1]}}}" if link else "")
        if control.kind == "atomic":
            return label
        kids = [place(c) for c in sorted(b.children(p), key=repr)]
        return f"{label}.({' | '.join(kids)})" if kids else f"{label}.1"

    regions = []
    for j in range(b.roots):
        kids = [place(c) for c in sorted(b.children(("root", j)), key=repr)]
        regions.append("(" + (" | ".join(kids) if kids else "1") + ")")
    body = " || ".join(regions)
    closures = " ".join(f"/z{e}" for e in sorted(b.edges()))
    return (f"{closures} ({body})" if closures else body), sites


# The model text, and the instantiation map remapped to BigraphER's site numbers: entry i names the redex
# site BigraphER numbers as the one the kernel's eta sends reactum site SITES[i] to.
# am[implements a-brs-k-bigrapher-1018@994f8c]
def model_text(agent: o.Big, rules: list[o.Rule]) -> str:
    lines = [f"{'atomic ' if c.kind == 'atomic' else ''}ctrl {c.name} = {c.arity};" for c in FRAGMENT.values()]
    lines.append(f"big s0 = {expression(agent)[0]};")
    for rule in rules:
        redex, redex_sites = expression(rule.redex)
        reactum, reactum_sites = expression(rule.reactum)
        instantiation = ", ".join(str(redex_sites.index(rule.eta[k])) for k in reactum_sites)
        lines.append(f"react {rule.name} = {redex} --> {reactum} @ [{instantiation}];")
    levels = sorted({r.priority for r in rules}, reverse=True)
    classes = ", ".join("{" + ", ".join(r.name for r in rules if r.priority == p) + "}" for p in levels)
    lines += ["begin brs", "  init s0;", f"  rules = [{classes}];", "end"]
    return "\n".join(lines) + "\n"


# A BigraphER JSON state as the oracle's bigraph: node i becomes (new bg i), a link with an outer name
# that name, any other link the closed edge bI; with no control of two ports every port is port 0.
# am[implements a-brs-k-bigrapher-1018@994f8c]
def from_bigrapher(state: dict) -> o.Big:
    places, nodes = state["place_graph"], state["nodes"]
    ids = {i: f"(new bg {i})" for i, _ in nodes}
    b = o.Big(0, (), places["num_regions"], ())
    for i, node in nodes:
        b.controls[ids[i]] = node["ctrl_name"]
    for r, kids in places["rn"]["r_major"]:
        for k in kids:
            b.parent[ids[k]] = ("root", r)
    for p, kids in places["nn"]["r_major"]:
        for k in kids:
            b.parent[ids[k]] = ids[p]
    outer = []
    for e, link in enumerate(state["link_graph"]):
        target = ("name", link["outer"][0]) if link["outer"] else ("edge", f"b{e}")
        if link["outer"]:
            outer.append(link["outer"][0])
        for node, count in link["ports"]:
            assert count == 1, f"a control of the fragment has one port: {link}"
            b.links[("port", ids[node], 0)] = target
    b.outer = tuple(sorted(outer))
    return b


# BigraphER's closure of the model: (states, transitions, occurrences), "bound" when it reaches the state
# bound, or "slow" when it runs past SECONDS.
# am[implements a-brs-k-bigrapher-1018@994f8c]
def run_bigrapher(binary: Path, text: str, scratch: Path, name: str):
    model, ts = scratch / f"{name}.big", scratch / f"{name}-ts.json"
    model.write_text(text)
    try:
        done = subprocess.run([str(binary), "full", "-n", "-M", str(MAX_STATE_INDEX), "--solver=GBS", "-f", "json",
                               "-t", str(ts), str(model)], capture_output=True, text=True, check=False, timeout=SECONDS)
    except subprocess.TimeoutExpired:
        return "slow"
    if done.returncode != 0:
        raise RuntimeError(f"bigrapher failed on {model}: {done.stdout[-2000:]} {done.stderr[-2000:]}")
    if "Maximum number of states reached" in done.stdout:
        return "bound"
    counts = {key: int(re.search(rf"{key}:\s+(\d+)", done.stdout).group(1)) for key in ("States", "Transitions", "Occurrences")}
    graph = json.loads(ts.read_text())
    states = [o.term(from_bigrapher(b)) for _, (_, b) in sorted(graph["v"], key=lambda v: v[1][0])]
    assert len(states) == counts["States"] and len(graph["e"]) == counts["Transitions"], (counts, len(graph["e"]))
    return states, counts["Transitions"], counts["Occurrences"]


# am[implements a-brs-k-bigrapher-1018@994f8c]
def generate(binary: Path, scratch: Path) -> dict:
    rng = random.Random(SEED)
    revision = subprocess.run([str(binary), "--version"], capture_output=True, text=True, check=False).stdout.strip()
    models, candidates, dropped = [], 0, {"bound": 0, "slow": 0}
    while len(models) < MODELS:
        candidates += 1
        agent, rules = random_model(rng)
        text = model_text(agent, rules)
        result = run_bigrapher(binary, text, scratch, f"m{candidates}")
        if isinstance(result, str):
            dropped[result] += 1
            continue
        states, transitions, occurrences = result
        models.append({"name": f"m{candidates}", "model": text, "signature": o.signature_text(FRAGMENT),
                       "agent": o.term(agent), "rules": [o.rule_text(r) for r in rules],
                       "states": states, "transitions": transitions, "occurrences": occurrences})
    return {"bigrapher": revision, "seed": SEED, "max_state_index": MAX_STATE_INDEX, "seconds": SECONDS,
            "candidates": candidates, "dropped": dropped, "models": models}


# am[implements a-brs-k-bigrapher-1018@994f8c]
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--bigrapher", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    args.scratch.mkdir(parents=True, exist_ok=True)
    data = generate(args.bigrapher, args.scratch)
    if args.check:
        committed = json.loads(DATA.read_text())
        different = [m["name"] for m, c in zip(data["models"], committed["models"]) if m != c]
        same_header = {k: data[k] for k in data if k != "models"} == {k: committed[k] for k in committed if k != "models"}
        print("regenerated data matches" if same_header and not different else f"differs: header {not same_header}, models {different}")
        return 0 if same_header and not different else 1
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(data, indent=1) + "\n")
    print(f"{len(data['models'])} models from {data['candidates']} candidates written to {DATA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
