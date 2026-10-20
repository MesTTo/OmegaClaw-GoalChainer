"""Purpose: an independent brute-force oracle of bigraph occurrences, reactions and isomorphism with
positional ports, in plain Python, for the kernel's differential tests. An occurrence is a node map for
which the canonical context and parameter are well-formed bigraphs whose composition with the redex gives
back the agent exactly (Milner 2009); a reaction composes the context, the renamed reactum and the
instantiated parameter; isomorphism tries every permutation of anonymous nodes and closed edges. It also
generates random signatures, agents and solid rules."""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field
from typing import Iterable

# Ids, names and edges are MeTTa text: "h" names an entity, "(new ...)" is anonymous. A place is a node
# id, ("root", j) or ("site", k); a point is ("port", id, k) or ("inner", x); a link ("edge", e) or
# ("name", y).


# am[implements a-brs-k-oracle-1018@f988b3]
@dataclass(frozen=True)
class Control:
    name: str
    arity: int
    kind: str  # atomic | active | passive


# am[implements a-brs-k-oracle-1018@f988b3]
@dataclass
class Big:
    sites: int
    inner: tuple[str, ...]
    roots: int
    outer: tuple[str, ...]
    controls: dict[str, str] = field(default_factory=dict)
    parent: dict[object, object] = field(default_factory=dict)
    links: dict[tuple, tuple] = field(default_factory=dict)

    # am[implements a-brs-k-oracle-1018@f988b3]
    def key(self) -> tuple:
        """The bigraph exactly, ids included, independent of insertion order."""

        return (
            self.sites,
            tuple(sorted(self.inner)),
            self.roots,
            tuple(sorted(self.outer)),
            tuple(sorted(self.controls.items())),
            tuple(sorted(self.parent.items(), key=repr)),
            tuple(sorted(self.links.items(), key=repr)),
        )

    # am[implements a-brs-k-oracle-1018@f988b3]
    def edges(self) -> set[str]:
        return {link[1] for link in self.links.values() if link[0] == "edge"}

    # am[implements a-brs-k-oracle-1018@f988b3]
    def children(self, place: object) -> list[object]:
        return [c for c, p in self.parent.items() if p == place]

    # am[implements a-brs-k-oracle-1018@f988b3]
    def below(self, ids: Iterable[object]) -> set[str]:
        out: set[str] = set()
        stack = [i for i in ids if not isinstance(i, tuple)]
        while stack:
            node = stack.pop()
            if node in out:
                continue
            out.add(node)
            stack.extend(c for c in self.children(node) if not isinstance(c, tuple))
        return out


# am[implements a-brs-k-oracle-1018@f988b3]
def anonymous(node_id: str) -> bool:
    return node_id.startswith("(new ")


# ----- well-formedness -------------------------------------------------------------------------------
# am[implements a-brs-k-oracle-1018@f988b3]
def well_formed(b: Big, sig: dict[str, Control]) -> bool:
    """The contract's section 2.1 conditions, read directly off the definition."""

    if len(set(b.inner)) != len(b.inner) or len(set(b.outer)) != len(b.outer):
        return False
    places = set(b.controls) | {("site", k) for k in range(b.sites)}
    if set(b.parent) != places:
        return False
    for child, parent in b.parent.items():
        if isinstance(parent, tuple):
            if parent[0] != "root" or not 0 <= parent[1] < b.roots:
                return False
        elif parent not in b.controls:
            return False
        elif sig[b.controls[parent]].kind == "atomic":
            return False
    for node in b.controls:  # every node reaches a root
        seen, place = set(), node
        while not isinstance(place, tuple):
            if place in seen:
                return False
            seen.add(place)
            place = b.parent[place]
    expected = {("port", n, k) for n, c in b.controls.items() for k in range(sig[c].arity)}
    expected |= {("inner", x) for x in b.inner}
    if set(b.links) != expected:
        return False
    return all(link[0] == "edge" or (link[0] == "name" and link[1] in b.outer) for link in b.links.values())


# am[implements a-brs-k-oracle-1018@f988b3]
def solid(b: Big) -> bool:
    """BigraphER's solidity plus a port on every closed edge (react.ml is_valid_exn)."""

    if any(not b.children(("root", j)) for j in range(b.roots)):
        return False
    site_parents = [b.parent[("site", k)] for k in range(b.sites)]
    if any(isinstance(p, tuple) for p in site_parents) or len(set(site_parents)) != len(site_parents):
        return False
    port_links = {link for point, link in b.links.items() if point[0] == "port"}
    if any(("name", y) not in port_links for y in b.outer):
        return False
    inner_links = [link for point, link in b.links.items() if point[0] == "inner"]
    if any(link[0] == "name" for link in inner_links) or len(set(inner_links)) != len(inner_links):
        return False
    return all(link in port_links for link in inner_links)


# ----- algebra ---------------------------------------------------------------------------------------
# am[implements a-brs-k-oracle-1018@f988b3]
def compose(f: Big, g: Big) -> Big | None:
    """F o G (Milner 2009, definition 2.7), or None when interfaces or supports clash."""

    if f.sites != g.roots or set(f.inner) != set(g.outer):
        return None
    if set(f.controls) & set(g.controls) or f.edges() & g.edges():
        return None
    site_parent = {child[1]: p for child, p in f.parent.items() if isinstance(child, tuple)}
    inner_link = {point[1]: link for point, link in f.links.items() if point[0] == "inner"}
    parent = {c: p for c, p in f.parent.items() if not isinstance(c, tuple)}
    for c, p in g.parent.items():
        parent[c] = site_parent[p[1]] if isinstance(p, tuple) and p[0] == "root" else p
    links = {pt: link for pt, link in f.links.items() if pt[0] == "port"}
    for pt, link in g.links.items():
        links[pt] = inner_link[link[1]] if link[0] == "name" else link
    return Big(g.sites, g.inner, f.roots, f.outer, {**f.controls, **g.controls}, parent, links)


# am[implements a-brs-k-oracle-1018@f988b3]
def tensor(f: Big, g: Big) -> Big:
    # am[implements a-brs-k-oracle-1018@f988b3]
    def shift(place: object, by_root: int, by_site: int) -> object:
        if isinstance(place, tuple) and place[0] == "root":
            return ("root", place[1] + by_root)
        if isinstance(place, tuple) and place[0] == "site":
            return ("site", place[1] + by_site)
        return place

    parent = dict(f.parent)
    for c, p in g.parent.items():
        parent[shift(c, f.roots, f.sites)] = shift(p, f.roots, f.sites)
    return Big(f.sites + g.sites, f.inner + g.inner, f.roots + g.roots, f.outer + g.outer,
               {**f.controls, **g.controls}, parent, {**f.links, **g.links})


# am[implements a-brs-k-oracle-1018@f988b3]
def identity(places: int, names: Iterable[str]) -> Big:
    names = tuple(names)
    return Big(places, names, places, names, {}, {("site", i): ("root", i) for i in range(places)},
               {("inner", x): ("name", x) for x in names})


# ----- occurrences -----------------------------------------------------------------------------------
# am[implements a-brs-k-oracle-1018@f988b3]
@dataclass(frozen=True)
class Occurrence:
    nodes: tuple       # sorted (redex id, agent id)
    edges: tuple       # sorted (redex edge, agent edge)
    names: tuple       # sorted (outer name, agent link)
    params: tuple      # sorted (site, sorted agent children)


# am[implements a-brs-k-oracle-1018@f988b3]
def decompose(r: Big, g: Big, phi: dict[str, str]):
    """The canonical (C, D, I, edge map, name map, params, passing) for node map PHI, or None where it
    cannot exist, G = C o (R x id) o D with id the identity on PASSING places and the names I. G may
    have sites and inner names: a site under a parameter stays in D, a site in the context passes
    through one identity place, and every inner name of G is a point of D. Whether this is a
    decomposition at all is decided by recomposing it."""

    images = set(phi.values())
    params: dict[int, list] = {}
    for k in range(r.sites):
        u = r.parent[("site", k)]
        params[k] = sorted((c for c in g.children(phi[u]) if c not in images), key=repr)
    par_nodes = g.below(c for kids in params.values() for c in kids)
    ctx_nodes = set(g.controls) - images - par_nodes
    param_roots = {c for kids in params.values() for c in kids}
    par_sites = {("site", i) for i in range(g.sites)
                 if ("site", i) in param_roots or g.parent[("site", i)] in par_nodes}
    ctx_sites = [("site", i) for i in range(g.sites) if ("site", i) not in par_sites]
    region_place: dict[int, object] = {}
    for v, p in r.parent.items():
        if isinstance(v, tuple):
            continue
        if isinstance(p, tuple):
            place = g.parent[phi[v]]
            if region_place.setdefault(p[1], place) != place:
                return None
    edge_map: dict[str, str] = {}
    name_map: dict[str, tuple] = {}
    for (kind, v, k), link in ((pt, l) for pt, l in r.links.items() if pt[0] == "port"):
        agent_link = g.links[("port", phi[v], k)]
        if link[0] == "edge":
            if agent_link[0] != "edge" or edge_map.setdefault(link[1], agent_link[1]) != agent_link[1]:
                return None
        elif name_map.setdefault(link[1], agent_link) != agent_link:
            return None
    edge_images = {("edge", e) for e in edge_map.values()}
    if len(edge_map) != len(set(edge_map.values())):
        return None
    inner_on = {link[1]: pt[1] for pt, link in r.links.items() if pt[0] == "inner"}  # redex edge -> inner name
    inner_of_agent = {("edge", edge_map[e]): x for e, x in inner_on.items() if e in edge_map}
    par_points = {pt: l for pt, l in g.links.items() if pt[0] == "inner" or pt[1] in par_nodes}

    # am[implements a-brs-k-oracle-1018@f988b3]
    def internal(link: tuple) -> bool:
        if link[0] != "edge" or link in edge_images:
            return False
        return all(pt in par_points for pt, l in g.links.items() if l == link)

    vias = sorted({l for l in par_points.values() if l not in edge_images and not internal(l)}, key=repr)
    via_name = {l: f"(Via {'(Edge ' + l[1] + ')' if l[0] == 'edge' else '(Name ' + l[1] + ')'})" for l in vias}
    context = Big(
        r.roots + len(ctx_sites), tuple(r.outer) + tuple(via_name[l] for l in vias), g.roots, g.outer,
        {n: g.controls[n] for n in ctx_nodes},
        {**{n: g.parent[n] for n in ctx_nodes}, **{("site", j): region_place.get(j) for j in range(r.roots)},
         **{("site", r.roots + t): g.parent[s] for t, s in enumerate(ctx_sites)}},
        {**{pt: l for pt, l in g.links.items() if pt[0] == "port" and pt[1] in ctx_nodes},
         **{("inner", y): name_map[y] for y in r.outer if y in name_map},
         **{("inner", via_name[l]): l for l in vias}},
    )
    roots_of = {c: ("root", k) for k, kids in params.items() for c in kids}
    roots_of.update({s: ("root", r.sites + t) for t, s in enumerate(ctx_sites)})
    par_links = {}
    for pt, l in par_points.items():
        if l in edge_images:
            if l not in inner_of_agent:
                return None
            par_links[pt] = ("name", inner_of_agent[l])
        elif internal(l):
            par_links[pt] = l
        else:
            par_links[pt] = ("name", via_name[l])
    parameter = Big(
        g.sites, g.inner, r.sites + len(ctx_sites), tuple(r.inner) + tuple(via_name[l] for l in vias),
        {n: g.controls[n] for n in par_nodes},
        {n: roots_of.get(n, g.parent[n]) for n in par_nodes | par_sites | set(ctx_sites)},
        par_links,
    )
    return context, parameter, tuple(via_name[l] for l in vias), edge_map, name_map, params, len(ctx_sites)


# am[implements a-brs-k-oracle-1018@f988b3]
def redex_image(r: Big, phi: dict[str, str], edge_map: dict[str, str]) -> Big:
    # am[implements a-brs-k-oracle-1018@f988b3]
    def place(p: object) -> object:
        return p if isinstance(p, tuple) else phi[p]

    # am[implements a-brs-k-oracle-1018@f988b3]
    def link(l: tuple) -> tuple:
        return ("edge", edge_map[l[1]]) if l[0] == "edge" else l

    return Big(r.sites, r.inner, r.roots, r.outer, {phi[n]: c for n, c in r.controls.items()},
               {place(c): place(p) for c, p in r.parent.items()},
               {(pt[0], phi[pt[1]], pt[2]) if pt[0] == "port" else pt: link(l) for pt, l in r.links.items()})


# am[implements a-brs-k-oracle-1018@f988b3]
def active_context(context: Big, sig: dict[str, Control], regions: int) -> bool:
    """Whether every place above each of the redex's REGIONS sites of CONTEXT is active."""

    for j in range(regions):
        place = context.parent[("site", j)]
        while not isinstance(place, tuple):
            if sig[context.controls[place]].kind == "passive":
                return False
            place = context.parent[place]
    return True


# am[implements a-brs-k-oracle-1018@f988b3]
def embeddings(sig: dict[str, Control], r: Big, g: Big, *, check_active: bool = True):
    """Every occurrence of the solid redex R in G: brute force over injective control-preserving node
    maps, each kept when its canonical decomposition is well-formed and recomposes to G exactly."""

    rids = sorted(r.controls)
    for image in itertools.permutations(sorted(g.controls), len(rids)):
        phi = dict(zip(rids, image))
        if any(r.controls[v] != g.controls[phi[v]] for v in rids):
            continue
        parts = decompose(r, g, phi)
        if parts is None:
            continue
        context, parameter, vias, edge_map, name_map, params, passing = parts
        if None in context.parent.values():
            continue
        if not (well_formed(context, sig) and well_formed(parameter, sig)):
            continue
        middle = tensor(redex_image(r, phi, edge_map), identity(passing, vias))
        inner = compose(middle, parameter)
        whole = compose(context, inner) if inner is not None else None
        if whole is None or whole.key() != g.key():
            continue
        if check_active and not active_context(context, sig, r.roots):
            continue
        yield Occurrence(tuple(sorted(phi.items())), tuple(sorted(edge_map.items())),
                         tuple(sorted(name_map.items(), key=repr)),
                         tuple(sorted((k, tuple(v)) for k, v in params.items()))), parts


# am[implements a-brs-k-oracle-1018@f988b3]
def occurs(sig: dict[str, Control], pattern: Big, target: Big) -> bool:
    return next(embeddings(sig, pattern, target, check_active=False), None) is not None


# am[implements a-brs-k-oracle-1018@f988b3]
@dataclass
class Rule:
    name: str
    redex: Big
    reactum: Big
    eta: dict[int, int]
    conditions: list = field(default_factory=list)  # (present?, where, pattern), where "ctx" | "param" | k
    priority: int = 0


# am[implements a-brs-k-oracle-1018@f988b3]
def holds(sig: dict[str, Control], rule: Rule, parts) -> bool:
    context, parameter = parts[0], parts[1]
    for present, where, pattern in rule.conditions:
        target = context if where == "ctx" else parameter if where == "param" else component(parameter, where)
        if occurs(sig, pattern, target) != present:
            return False
    return True


# am[implements a-brs-k-oracle-1018@f988b3]
def component(d: Big, k: int) -> Big:
    ids = d.below(d.children(("root", k)))
    ports = {pt: l for pt, l in d.links.items() if pt[0] == "port" and pt[1] in ids}
    leaving = {l for l in ports.values() if l[0] == "edge"
               and any(pt[0] != "port" or pt[1] not in ids for pt, m in d.links.items() if m == l)}
    via = {l: f"(Via (Edge {l[1]}))" for l in leaving}
    return Big(0, (), 1, tuple(d.outer) + tuple(via.values()), {n: d.controls[n] for n in ids},
               {n: ("root", 0) if d.parent[n] == ("root", k) else d.parent[n] for n in ids},
               {pt: ("name", via[l]) if l in via else l for pt, l in ports.items()})


# am[implements a-brs-k-oracle-1018@f988b3]
def occurrences(sig: dict[str, Control], rule: Rule, g: Big):
    return [(occ, parts) for occ, parts in embeddings(sig, rule.redex, g) if holds(sig, rule, parts)]


# ----- reaction --------------------------------------------------------------------------------------
# am[implements a-brs-k-oracle-1018@f988b3]
def fresh(base: str, taken: set[str]) -> str:
    k = 0
    while f"{base} {k})" in taken:
        k += 1
    return f"{base} {k})"


# am[implements a-brs-k-oracle-1018@f988b3]
def react(rule: Rule, g: Big, occ: Occurrence, parts):
    """('refused', named ids) or ('successor', G') for RULE at OCC: C o (R' x id_I) o eta(D)."""

    context, parameter, vias, edge_map, name_map, params, passing = parts
    uses: dict[int, list[int]] = {}
    for k, j in sorted(rule.eta.items()):
        uses.setdefault(j, []).append(k)
    cloned = sorted(n for j, ks in uses.items() if len(ks) > 1 for n in g.below(dict(params)[j]) if not anonymous(n))
    if cloned:
        return ("refused", tuple(cloned))
    phi = dict(occ.nodes)
    taken = set(g.controls)
    node_map = {}
    for t in sorted(rule.reactum.controls):
        if t in phi:
            node_map[t] = phi[t]
        else:
            node_map[t] = fresh(f"(new {rule.name} {t}", taken)
            taken.add(node_map[t])
    edges_taken = set(g.edges())
    edge_rename = {}
    for e in sorted(rule.reactum.edges()):
        if e in edge_map:
            edge_rename[e] = edge_map[e]
        else:
            edge_rename[e] = fresh(f"(new {rule.name} {e}", edges_taken)
            edges_taken.add(edge_rename[e])
    body = redex_image(rule.reactum, node_map, edge_rename)
    pieces_controls, pieces_parent, pieces_links = {}, {}, {}
    for k, j in sorted(rule.eta.items()):
        roots = parameter.children(("root", j))
        ids = sorted(parameter.below(roots))
        first = min(uses[j]) == k
        rename = {}
        for n in ids:
            if first:
                rename[n] = n
            else:
                rename[n] = fresh(f"(new {rule.name} (Copy {k}) {n}", taken)
                taken.add(rename[n])
        for n in ids:
            pieces_controls[rename[n]] = parameter.controls[n]
            pieces_parent[rename[n]] = ("root", k) if n in roots else rename[parameter.parent[n]]
            for (kind, node, port), link in parameter.links.items():
                if node == n:
                    pieces_links[("port", rename[n], port)] = link
    instance = Big(0, (), len(rule.eta), parameter.outer, pieces_controls, pieces_parent, pieces_links)
    middle = tensor(body, identity(passing, vias))
    inner = compose(middle, instance)
    return ("successor", compose(context, inner))


# ----- isomorphism -----------------------------------------------------------------------------------
# am[implements a-brs-k-oracle-1018@f988b3]
def isomorphic(a: Big, b: Big) -> bool:
    """Whether a bijection on anonymous nodes and closed edges, fixing everything else, maps A onto B.
    Every control-preserving permutation of the anonymous nodes is tried; the edge bijection is the one
    the ports then force, and inner names fix the edges they reach."""

    if (a.sites, sorted(a.inner), a.roots, sorted(a.outer)) != (b.sites, sorted(b.inner), b.roots, sorted(b.outer)):
        return False
    named_a = {n: c for n, c in a.controls.items() if not anonymous(n)}
    if named_a != {n: c for n, c in b.controls.items() if not anonymous(n)}:
        return False
    anon_a = sorted(n for n in a.controls if anonymous(n))
    anon_b = sorted(n for n in b.controls if anonymous(n))
    if len(anon_a) != len(anon_b) or len(a.edges()) != len(b.edges()) or len(a.links) != len(b.links):
        return False
    target = b.key()
    for perm in itertools.permutations(anon_b):
        node_map = dict(zip(anon_a, perm))
        if any(a.controls[n] != b.controls[node_map[n]] for n in anon_a):
            continue
        edge_map: dict[str, str] = {}
        consistent = True
        for point, link in a.links.items():
            mapped = (point[0], node_map.get(point[1], point[1]), point[2]) if point[0] == "port" else point
            other = b.links.get(mapped)
            if link[0] == "edge":
                if other is None or other[0] != "edge" or edge_map.setdefault(link[1], other[1]) != other[1]:
                    consistent = False
                    break
        if not consistent or len(set(edge_map.values())) != len(edge_map):
            continue
        if rename(a, node_map, edge_map).key() == target:
            return True
    return False


# am[implements a-brs-k-oracle-1018@f988b3]
def rename(b: Big, node_map: dict[str, str], edge_map: dict[str, str]) -> Big:
    # am[implements a-brs-k-oracle-1018@f988b3]
    def place(p: object) -> object:
        return node_map.get(p, p) if not isinstance(p, tuple) else p

    # am[implements a-brs-k-oracle-1018@f988b3]
    def link(l: tuple) -> tuple:
        return ("edge", edge_map[l[1]]) if l[0] == "edge" else l

    return Big(b.sites, b.inner, b.roots, b.outer, {place(n): c for n, c in b.controls.items()},
               {place(c): place(p) for c, p in b.parent.items()},
               {(pt[0], place(pt[1]), pt[2]) if pt[0] == "port" else pt: link(l) for pt, l in b.links.items()})


# ----- MeTTa text and atoms --------------------------------------------------------------------------
# am[implements a-brs-k-oracle-1018@f988b3]
def place_text(p: object) -> str:
    if isinstance(p, tuple):
        return f"({'Root' if p[0] == 'root' else 'Site'} {p[1]})"
    return str(p)


# am[implements a-brs-k-oracle-1018@f988b3]
def link_text(l: tuple) -> str:
    return f"({'Edge' if l[0] == 'edge' else 'Name'} {l[1]})"


# am[implements a-brs-k-oracle-1018@f988b3]
def term(b: Big) -> str:
    nodes = " ".join(f"(N {n} {c})" for n, c in sorted(b.controls.items()))
    place = " ".join(f"(In {place_text(c)} {place_text(p)})" for c, p in sorted(b.parent.items(), key=repr))
    link = " ".join(
        f"(P {pt[1]} {pt[2]} {link_text(l)})" if pt[0] == "port" else f"(I {pt[1]} {link_text(l)})"
        for pt, l in sorted(b.links.items(), key=repr)
    )
    return (f"(Bigraph (Inner {b.sites} ({' '.join(b.inner)})) (Outer {b.roots} ({' '.join(b.outer)})) "
            f"(Nodes {nodes}) (Place {place}) (Link {link}))")


# am[implements a-brs-k-oracle-1018@f988b3]
def signature_text(sig: dict[str, Control]) -> str:
    return "(Signature " + " ".join(f"(Control {c.name} {c.arity} {c.kind})" for c in sig.values()) + ")"


# am[implements a-brs-k-oracle-1018@f988b3]
def rule_text(rule: Rule) -> str:
    conditions = " ".join(
        f"({'Present' if present else 'Absent'} {'Context' if where == 'ctx' else 'Parameter' if where == 'param' else f'(Parameter {where})'} {term(p)})"
        for present, where, p in rule.conditions
    )
    eta = " ".join(f"({k} {j})" for k, j in sorted(rule.eta.items()))
    return f"(Rule {rule.name} {term(rule.redex)} {term(rule.reactum)} (Eta {eta}) (Conditions {conditions}) (Priority {rule.priority}))"


# am[implements a-brs-k-oracle-1018@f988b3]
def from_atom(atom) -> Big:
    """A kernel Bigraph atom as the oracle's model, every id, name and edge kept as its MeTTa text."""

    inner, outer, nodes, place, link = atom.children[1:]

    # am[implements a-brs-k-oracle-1018@f988b3]
    def parse_place(a) -> object:
        text = repr(a)
        if text.startswith("(Root "):
            return ("root", int(text[6:-1]))
        if text.startswith("(Site "):
            return ("site", int(text[6:-1]))
        return text

    # am[implements a-brs-k-oracle-1018@f988b3]
    def parse_link(a) -> tuple:
        head, value = a.children
        return ("edge" if repr(head) == "Edge" else "name", repr(value))

    b = Big(int(inner.children[1].value), tuple(repr(x) for x in inner.children[2].children),
            int(outer.children[1].value), tuple(repr(y) for y in outer.children[2].children))
    for row in nodes.children[1:]:
        b.controls[repr(row.children[1])] = repr(row.children[2])
    for row in place.children[1:]:
        b.parent[parse_place(row.children[1])] = parse_place(row.children[2])
    for row in link.children[1:]:
        if repr(row.children[0]) == "P":
            b.links[("port", repr(row.children[1]), int(row.children[2].value))] = parse_link(row.children[3])
        else:
            b.links[("inner", repr(row.children[1]))] = parse_link(row.children[2])
    return b


# am[implements a-brs-k-oracle-1018@f988b3]
def occurrence_key(atom) -> Occurrence:
    """A kernel Occurrence atom as the oracle's Occurrence."""

    sections = {repr(s.children[0]): s.children[1:] for s in atom.children[2:]}

    # am[implements a-brs-k-oracle-1018@f988b3]
    def pairs(name):
        return [(repr(row.children[1]), row.children[2]) for row in sections[name]]

    nodes = tuple(sorted((k, repr(v)) for k, v in pairs("Nodes")))
    edges = tuple(sorted((k, repr(v)) for k, v in pairs("Edges")))
    names = tuple(sorted(((k, ("edge" if repr(v.children[0]) == "Edge" else "name", repr(v.children[1]))) for k, v in pairs("Names")), key=repr))
    params = tuple(sorted((int(row.children[1].value), tuple(sorted((repr(c) for c in row.children[2].children), key=repr))) for row in sections["Params"]))
    return Occurrence(nodes, edges, names, tuple((k, tuple(sorted(v, key=repr))) for k, v in params))


# am[implements a-brs-k-oracle-1018@f988b3]
def normal_occurrence(occ: Occurrence) -> Occurrence:
    return Occurrence(occ.nodes, occ.edges, occ.names, tuple((k, tuple(sorted(v, key=repr))) for k, v in occ.params))


# ----- random instances ------------------------------------------------------------------------------
SIGNATURE = {
    c.name: c
    for c in (
        Control("A", 0, "active"), Control("B", 1, "active"), Control("C", 2, "active"),
        Control("K", 2, "passive"), Control("T", 0, "atomic"), Control("U", 1, "atomic"),
    )
}


# am[implements a-brs-k-oracle-1018@f988b3]
def random_agent(rng: random.Random, sig: dict[str, Control], *, max_nodes: int = 6, named: float = 0.3,
                 idle_names: float = 0.2) -> Big:
    """A random ground agent: NAMED is the chance a node names an entity, IDLE_NAMES the chance of an
    outer name no port reaches."""

    roots = rng.randint(1, 2)
    b = Big(0, (), roots, ())
    count = rng.randint(1, max_nodes)
    ids = []
    for i in range(count):
        control = rng.choice(list(sig))
        node = f"n{i}" if rng.random() < named else f"(new g {i})"
        hosts = [n for n in ids if sig[b.controls[n]].kind != "atomic"]
        b.controls[node] = control
        b.parent[node] = rng.choice([("root", j) for j in range(roots)] + hosts)
        ids.append(node)
    names, edges = [], []
    for node in ids:
        for k in range(sig[b.controls[node]].arity):
            choice = rng.random()
            if choice < 0.25 and names:
                link = ("name", rng.choice(names))
            elif choice < 0.4:
                names.append(f"x{len(names)}")
                link = ("name", names[-1])
            elif choice < 0.75 and edges:
                link = ("edge", rng.choice(edges))
            else:
                edges.append(f"e{len(edges)}")
                link = ("edge", edges[-1])
            b.links[("port", node, k)] = link
    b.outer = tuple(names) + (("x9",) if rng.random() < idle_names else ())
    return b


# am[implements a-brs-k-oracle-1018@f988b3]
def random_redex(rng: random.Random, sig: dict[str, Control], agent: Big | None = None, *, inner_names: bool = True) -> Big:
    """A solid redex: from a random part of AGENT when one is given, so that it occurs often, with an
    inner name on a closed edge sometimes when INNER_NAMES."""

    while True:
        r = _redex_candidate(rng, sig, agent, inner_names)
        if r is not None and solid(r) and well_formed(r, sig):
            return r


# am[implements a-brs-k-oracle-1018@f988b3]
def _redex_candidate(rng: random.Random, sig: dict[str, Control], agent: Big | None, inner_names: bool = True) -> Big | None:
    if agent is not None and agent.controls and rng.random() < 0.8:
        start = rng.choice(sorted(agent.controls))
        chosen = [start]
        frontier = [c for c in agent.children(start) if not isinstance(c, tuple)]
        while frontier and len(chosen) < 3 and rng.random() < 0.7:
            nxt = frontier.pop(rng.randrange(len(frontier)))
            chosen.append(nxt)
            frontier.extend(c for c in agent.children(nxt) if not isinstance(c, tuple))
        if len(chosen) < 3 and rng.random() < 0.3:
            others = [n for n in agent.controls if n not in chosen and n not in agent.below(chosen)]
            if others:
                chosen.append(rng.choice(others))
        rename = {n: f"R{i}" for i, n in enumerate(chosen)}
        tops = [n for n in chosen if agent.parent[n] not in rename]
        root_of = {}
        for n in tops:
            root_of[n] = rng.randrange(2) if len(tops) > 1 else 0
        roots = (max(root_of.values()) + 1) if root_of else 1
        if set(range(roots)) != set(root_of.values()):
            return None
        r = Big(0, (), roots, ())
        for n in chosen:
            r.controls[rename[n]] = agent.controls[n]
            r.parent[rename[n]] = ("root", root_of[n]) if n in root_of else rename[agent.parent[n]]
        reaching = _random_redex_links(rng, sig, r, agent, rename)
    else:
        r = Big(0, (), rng.randint(1, 2), ())
        count = rng.randint(r.roots, 3)
        ids = []
        for i in range(count):
            node = f"R{i}"
            hosts = [n for n in ids if sig[r.controls[n]].kind != "atomic"]
            r.controls[node] = rng.choice(list(sig))
            r.parent[node] = ("root", i) if i < r.roots else rng.choice([("root", j) for j in range(r.roots)] + hosts)
            ids.append(node)
        reaching = _random_redex_links(rng, sig, r, None, {})
    for node in sorted(r.controls):
        if sig[r.controls[node]].kind != "atomic" and rng.random() < 0.6:
            r.parent[("site", r.sites)] = node
            r.sites += 1
    edges = sorted(r.edges())
    if inner_names and reaching and rng.random() < 0.7:
        r.inner = ("w",)
        r.links[("inner", "w")] = ("edge", rng.choice(sorted(reaching)))
    elif inner_names and edges and rng.random() < 0.15:
        r.inner = ("w",)
        r.links[("inner", "w")] = ("edge", rng.choice(edges))
    return r


# am[implements a-brs-k-oracle-1018@f988b3]
def _random_redex_links(rng, sig, r: Big, agent: Big | None, rename: dict[str, str]) -> set[str]:
    """Ports of R's nodes: copied from AGENT's links where R came from it, an agent edge every point of
    which is in R or below it becoming a closed edge (marked reachable by an inner name when some point
    is below), others becoming outer names, sometimes two names for one agent link."""

    names: dict[tuple, str] = {}
    reaching: set[str] = set()
    below = agent.below(rename) if agent is not None else set()
    for node in sorted(r.controls):
        original = next((a for a, b in rename.items() if b == node), None)
        for k in range(sig[r.controls[node]].arity):
            if agent is not None and original is not None and rng.random() < 0.85:
                source = agent.links[("port", original, k)]
                inside = [pt for pt, l in agent.links.items() if l == source]
                closed = source[0] == "edge" and all(pt[0] == "port" and pt[1] in rename for pt in inside)
                reached = source[0] == "edge" and not closed and all(pt[0] == "port" and pt[1] in below for pt in inside)
                if closed and rng.random() < 0.8:
                    r.links[("port", node, k)] = ("edge", "f" + source[1])
                elif reached and rng.random() < 0.8:
                    r.links[("port", node, k)] = ("edge", "f" + source[1])
                    reaching.add("f" + source[1])
                elif source in names and rng.random() < 0.2:
                    fresh_name = f"y{len(names) + 10 * k + 7}"
                    r.links[("port", node, k)] = ("name", fresh_name)
                else:
                    names.setdefault(source, f"y{len(names)}")
                    r.links[("port", node, k)] = ("name", names[source])
            elif rng.random() < 0.5:
                r.links[("port", node, k)] = ("name", f"y{len(names) + k}")
                names[("free", node, k)] = f"y{len(names) + k}"
            else:
                r.links[("port", node, k)] = ("edge", f"f{node}{k}")
    r.outer = tuple(sorted({l[1] for l in r.links.values() if l[0] == "name"}))
    return reaching


# am[implements a-brs-k-oracle-1018@f988b3]
def random_condition(rng: random.Random, sig: dict[str, Control], redex: Big) -> tuple:
    """A kernel condition: one node of a random control, its ports on fresh outer names, required
    present or absent in the context, the whole parameter or one site's parameter."""

    control = rng.choice(list(sig))
    pattern = Big(0, (), 1, tuple(f"p{k}" for k in range(sig[control].arity)), {"Q": control}, {"Q": ("root", 0)},
                  {("port", "Q", k): ("name", f"p{k}") for k in range(sig[control].arity)})
    places = ["ctx", "param"] + list(range(redex.sites))
    return (rng.random() < 0.5, rng.choice(places), pattern)


# am[implements a-brs-k-oracle-1018@f988b3]
def random_reactum(rng: random.Random, sig: dict[str, Control], redex: Big) -> tuple[Big, dict[int, int]]:
    """A reactum on the redex's outer face and inner names, and an eta onto the redex's sites."""

    t = Big(0, redex.inner, redex.roots, redex.outer)
    keep = [n for n in sorted(redex.controls) if rng.random() < 0.6]
    ids = []
    for j in range(redex.roots):
        node = keep.pop(0) if keep else f"Z{j}"
        control = redex.controls.get(node) or rng.choice([c for c in sig if sig[c].kind != "atomic"])
        if sig[control].kind == "atomic":
            control = "A"
        t.controls[node] = control
        t.parent[node] = ("root", j)
        ids.append(node)
    for node in keep + ([f"Z{redex.roots}"] if rng.random() < 0.4 else []):
        hosts = [n for n in ids if sig[t.controls[n]].kind != "atomic"]
        t.controls[node] = redex.controls.get(node) or rng.choice(list(sig))
        t.parent[node] = rng.choice([("root", j) for j in range(t.roots)] + hosts)
        ids.append(node)
    links_pool = [("name", y) for y in redex.outer]
    for node in ids:
        for k in range(sig[t.controls[node]].arity):
            if links_pool and rng.random() < 0.6:
                t.links[("port", node, k)] = rng.choice(links_pool)
            else:
                t.links[("port", node, k)] = ("edge", rng.choice(["g0", "g1"] + sorted(redex.edges())))
    for x in t.inner:
        t.links[("inner", x)] = rng.choice(links_pool + [("edge", "g0")]) if links_pool else ("edge", "g0")
        if not any(l == t.links[("inner", x)] for pt, l in t.links.items() if pt[0] == "port"):
            t.links[("inner", x)] = ("edge", "g9")
    hosts = [n for n in ids if sig[t.controls[n]].kind != "atomic"]
    eta: dict[int, int] = {}
    if hosts and redex.sites:
        for k in range(rng.randint(0, 2)):
            t.parent[("site", k)] = rng.choice(hosts)
            eta[k] = rng.randrange(redex.sites)
            t.sites += 1
    return t, eta
