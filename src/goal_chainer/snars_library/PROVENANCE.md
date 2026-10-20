<!--
Purpose: say where GoalChainer's SNARS library comes from, what was taken and left, what changed
since and under which licence, for the files beside this one and src/goalchainer_snars.py.
am[implements a-rt-fr-follow-sub-rows-1017@03dff0] am[rests-on c-integrate-conditional-frontier-omission-1017@ba61de]
am[rests-on c-rt-fr-shared-key-namespace-1017@a9dc19]
am[implements a-rt-sp-boundary-1017@5b3a0e] am[implements a-rt-sp-consumers-1017@a7097b]
am[implements a-integrate-snars-supported-premises-1017@5186a3] am[implements a-rt-miner-supported-statements-1017@1e8790]
am[rests-on c-rt-sp-producers-complete-1017@05a20d] am[rests-on c-rt-support-is-receipt-or-proof-1017@6c065e]
am[implements a-rt-conditional-enumeration-commit-1017@9831fa] am[implements a-rt-fr-admit-abductive-mp-1017@1889cf]
am[implements a-rt-derive-sweep-conditional-partners-1017@4b66c3] am[rests-on c-integrate-conditional-enumerators-scope-1017@87de90]
am[implements a-integrate-frontier-order-hook-1017@dab0ee]
am[implements a-rt-ob-core-1017@26b526] am[implements a-rt-ob-condition-1017@dc8180]
am[implements a-rt-ob-negation-track-1017@a1a80d]
am[rests-on c-rt-pm-interface-shape-v6-1017@ec7b8c] am[rests-on c-integrate-condition-projection-endpoints-1017@364ddb]
-->

# SNARS library provenance

This directory is SNARS, the subjective-logic reasoner GoalChainer's native decisions run on,
taken from Mettabase. GoalChainer registers this directory as the MeTTa library `snars` on its
in-process pymetta engine, so `(library snars snars/kernel.pl)` resolves to `snars/kernel.pl` here.

| | |
|---|---|
| Source | https://github.com/MesTTo/mettabase |
| Commit | `c079c894f3d97421242299f26db76c9de89b2438` |
| Licences | Mettabase's MIT notice in `LICENSE`; the chaining portion of `snars/sbc.metta` also carries the GPLv3 terms described below; sCASP has its own Apache-2.0 notice |

<!-- am[implements a-v2-public-license-notice-1020@fedb58] -->
`snars/sbc.metta` identifies its recursion as the trueagi `chaining` skeleton.
That upstream is GPLv3 at
[`bc9beb2672953e07971b3abecc1fe67651ecddc4`](https://github.com/trueagi-io/chaining/tree/bc9beb2672953e07971b3abecc1fe67651ecddc4).
Its unary and binary chaining structure comes from the probabilistic backward
chainer, with SNARS opinion operators replacing probability multiplication;
its sized recursion follows the upstream consume-and-pass structure.
The upstream GPL version 3 text is copied verbatim in
[`chaining/LICENSE`](chaining/LICENSE). This distribution retains those terms
for `snars/sbc.metta` and its modifications; the Mettabase MIT notice does not
replace them. The package metadata includes `GPL-3.0-only`, and the complete
modified source is included in the repository, source distribution and wheel.
The other files retain their respective notices.

Adding this notice and licence changes the SNARS tree identity. Restart running
processes and start a new SNARS store when upgrading from the earlier private
build; existing stores remain tied to their original identity.

Taken:

- `lib/mettabase/snars.metta`, the aggregator, as `snars.metta`
- `lib/mettabase/snars/`, its 21 modules and the Prolog kernel `kernel.pl`, as `snars/`
- `lib/mettabase/snars-guard.metta`, the optional sCASP guard, as `snars-guard.metta`
- `src/mettabase/core/sexpr.py`, `src/mettabase/snars/tnf.py` and
  `src/mettabase/hyperbase/render.py`, the SH-term English renderer the proof drawing uses, as
  `../sexpr/syntax.py`, `../snars_python/tnf.py` and `../snars_python/english.py`: packages of
  their own, so this directory holds no Python and no bytecode cache changes its tree digest.
  `sexpr.py` was `../snars_python/sexpr.py` until it moved to GoalChainer's MeTTa text package,
  below SNARS, with its bytes unchanged
- the `snars_*` py-call wrappers from `src/mettabase/petta/extension.py` and `atom_text` from
  `src/mettabase/ops/fuzzy.py`, as the top-level module `src/goalchainer_snars.py`

Left in the source, because nothing GoalChainer runs loads them: HyperBase's parser and ingestion
pipeline, the other Mettabase libraries, `mettabase_petta.py` and the rest of `extension.py`, the
`snars_statement_facts` wrapper, and Mettabase's tests and benchmarks. Its SNARS PeTTa suites
import its `assertions` library and most of them its HyperBase library, so GoalChainer tests this
library through its own SNARS tests instead, among them a scripted session over every operation
whose answers must equal those PeTTa gave before GoalChainer retired it
(`tests/data/snars-executor-petta.json`).

Every file was byte-identical to its source path when it was taken. GoalChainer changed these
since:

- **Control cells.** `snars/derive.metta` kept its frontier, working set and residual queue in
  three engine state cells, which pymetta refuses to write inside `speculate`. They live in
  `kernel.pl`'s dynamic predicate `sn_cell_v/2`, read and written through `sn_cell_get` and
  `sn_cell_put` under the `sn-commit` mutex, which `snars/kernel.metta` imports; `(sn frontier)`
  reads the frontier. A speculation now discards them with every other kernel store.
- **What-if.** `kernel.pl`'s `sn_what_if` called `believe!` and `(sn prove ...)` as the Prolog
  predicates PeTTa compiles them to, which pymetta does not define where the kernel runs. It calls
  them through `eval/2`, which both engines define.
- **Guard.** `snars-guard.metta` loaded its sCASP program from a string through
  `translatePredicate`'s `load_files`, which on pymetta defined none of its predicates. The program
  is `snars/guard.pl`, imported with `import_prolog_functions_from_file` the way the kernel is, and
  the `(sn guard-inject ...)` equation is gone. It loads sCASP from `scasp/` beside it, a copy of
  sCASP 1.1.4 under its own Apache-2.0 licence that `scasp/PROVENANCE.md` describes, where the
  source loaded whichever sCASP pack the SWI-Prolog running it had installed.
- **Library imports.** `snars/kernel.metta` and `snars-guard.metta` import their Prolog files as
  `(library snars snars/kernel.pl)` and `(library snars snars/guard.pl)`, where the source imported
  the kernel from the process's working directory.
- **py-call module.** The modules call `goalchainer_snars.snars_*` where they called
  `mettabase_petta.snars_*`; `tnf.py` and `goalchainer_snars.py` import the S-expression module as
  `goal_chainer.sexpr.syntax`.
- **Frontier comparison.** `snars/derive.metta` exposes `(sn fr-before ITEM KEY ITEM KEY)`
  for optional worlds to replace during preparation. Its default is the original strict `>`.
  Insertion passes raw keys, and selection passes decayed keys after the original sentinel
  bound is met. Equal keys keep their original order. Insertion also controls which pending
  computations the frontier cap discards; it removes no statements, receipts or proofs.
- **Obligations and conditions.** `snars/sbc.metta` adds `(sn obligations GOAL HYP SIZE THETA)`:
  the size-bounded chainer over the live generator plus one open-leaf row, answering every
  structural route to GOAL with each leaf's condition and the opinion GOAL would hold were each
  open premise to carry HYP, with that scenario's cut. Nothing is interned or written.
  `snars/truth.metta` adds `(sn condition OPINION THETA)`, one cut of the computed interval
  `[b, b + u]`; `(sn literal-view SID pos|neg)`, a statement's view or its complement for the
  literal (Not S); and `(sn condition-of SID POLARITY THETA)`, which leaves a statement without
  support Undecided. `(sn opinion ...)` now reads its cell through `(sn ev-op ...)`, the same
  arithmetic an obligation's hypothesis and a track record's counts go through. No existing
  operation answers differently.
- Comments naming `lib/mettabase/` paths name this directory's.

With these changes the library answers every recorded SNARS batch of GoalChainer's test suite,
101 before and 101 after the switch to Jev readings, as unmodified c079c89 does on PeTTa, and the
same in-process on pymetta inside `speculate`, every run leaving the engine as it found it.

Two later changes make the library answer differently from c079c89, by design:

- **Conditional candidates.** `snars/derive.metta` enumerated no pair of a statement and a `==>`
  edge, the pairs both conditional rules take: modus ponens on the edge's antecedent and abductive
  modus ponens on its consequent. `(sn fr-touch! ...)` looked for an antecedent's edges in `rk`
  rows, which `index!` writes only for statements with more than two roles, while a `==>` edge is
  binary and is filed as a `sub` row under its antecedent's sid and an `obj` row under its
  consequent's; `(sn derive!)` keys partners by the labels of a binary statement's fillers, which
  never reach an edge's ends. So `(sn focus! ...)` and `(sn cycles ...)` fired neither rule, though
  `(sn derive-pair! ...)` proves both. A touched statement now pairs with each edge filed under its
  sid whose `s` or `o` filler is the typed `(sn-ref ...)` the rules match, so a concept whose label
  is the sid's symbol, which shares the key, stays out; a touched edge pairs with the statements
  its fillers name, so a pair reaches the frontier whichever arrives last; and `(sn derive!)` pairs
  each such edge with both of them, whatever their arity; the support check below decides which
  of those pairs fire. The pair's value, the rules, receipts and trust are as they were. A batch
  without a conditional edge, as each recorded batch above is, answers as before;
  `tests/test_snars_conditional_candidates.py` runs batches with one.
- **Supported premises.** Every rule checked its premises for stamp disjointness, domain and
  licence and nothing else, so a statement the library interns without asserting it, a
  conditional's endpoint, a parsed query, a believe-channel claim or its content, fired as a
  premise on its base rate alone: it has no stamp, so it shares none. `(sn supported? ...)` in
  `snars/intern.metta` holds for a statement with a receipt row, observed, or a proof row, derived,
  and the commits that write proofs, `derived!`, `weak-quantum-d!`, `graft-into!` and `graft!`,
  refuse a premise without one. The frontier's `fr-push!`, the backward chainer's facts and
  conditional rules in `snars/sbc.metta`, `ask!` in `snars/authoring.metta`, and the rule miner's
  pattern support, chains, closing edges and copulas in `snars/miner.metta` read the same
  predicate. An authored statement counts whatever its evidence, negative and vacuous included;
  values, rules, receipts and trust are as they were. Each recorded batch above answers as before;
  `tests/test_snars_supported_premises.py` runs batches with statements that are only interned.

Other later changes appear in this repository's history.

<!-- am[implements a-integrate-guard-metta-build-1019@e688cb] -->
The guard now takes quoted MeTTa expressions instead of Prolog text. Its small
adapter maps nested expressions to the solver's compound terms while retaining
variable sharing; s(CASP) itself is unchanged. Queries use s(CASP)'s `model/1`
option and return its first witness. They no longer enumerate every witness or
catch solver exceptions as failure. The protocol derives its Boolean and model
from that single query and echoes a structured goal. The historical PeTTa fixture
remains unchanged; the differential test explicitly accounts for the changed goal
notation when comparing its guard record. Restart processes and create new stores
after this SNARS identity change; the store schema remains version 3.
