Purpose: guide GoalChainer's use of the operator's MeTTa and pymetta implementation.
<!-- am[implements a-integrate-native-reference-instructions-1018@4bcaac] -->

# Native implementation

GoalChainer targets the operator's MeTTa engine that pymetta depends on.
Use pymetta as the Python interface to that engine. MeTTaScript, MeTTa-TS
and other MeTTa implementations are not the target runtime or the authority
for its semantics. Check behavior against pymetta's pinned engine, its source
and its tests; examples from another implementation are only prior art until
their behavior is verified on this engine.

Start with MeTTa and exploit its semantics: atoms and expressions as data,
pattern matching and unification, equations, multiple answers, spaces, and
composition. Read the upstream examples before concluding that the language
cannot express a mechanism.

If a MeTTa-only implementation would constrain a better design, use pymetta.
Custom grounded MeTTa atoms and operations can expose native data structures
and algorithms to MeTTa rules. Consider them alongside ordinary terms,
compiled Python definitions and foreign spaces. They are not restricted to
caches. Keep the rule or operation in one place, using the integration that
preserves its meaning with the least machinery.

For custom matching, inspect `metta.foreign.CustomMatch`: a grounded object's
`match_(other)` can yield binding alternatives through the engine's `(unify ...)`
operation. Python atom equality and host-side `Atom.unify` are separate paths;
check the path the caller actually uses. For stable structural transport,
inspect `metta.convert.register_type` and its explicit value projections.

Check the chosen integration's actual equality, matching, type, effect,
serialization and concurrency contracts. An opaque Python handle has different
semantics from a structural value or a registered type projection; do not
generalize one handle's limitations to every grounded integration. Persist
stable values and explicit provenance where replay requires them. Declare
operation effects and verify speculation and thread isolation on the supported
runtime version.

MDL governs the design: one authoritative representation of each fact, one
implementation of each rule, and derived views rather than independently
maintained copies. Do not recreate a MeTTa evaluator or duplicate reasoning
policy in Python. Ground the mechanisms in established concepts and test the
assumptions that make them apply here.

# Upstream references

The operator's upstream is [MesTTo/MeTTa](https://github.com/MesTTo/MeTTa).
Its local checkout is `/home/user/Dev/PyPeTTa1/PeTTa`. The historical directory
name does not mean GoalChainer targets the separate patham9/PeTTa runtime.
Check the checkout's remote, revision and API against GoalChainer's installed
pymetta version before adopting an example.

Paths below are relative to that upstream checkout.

| Reference | Use |
| --- | --- |
| `extensions/python/llms.txt` | Start here for pymetta's Python API, definitions, atom transport, integration and concurrency. |
| `llms.txt` | MeTTa language and runtime reference. Read the relevant sections alongside source and tests. |
| `extensions/python/examples/README.md` and `extensions/python/examples/` | Executable pymetta examples; `integration/` covers Python objects and foreign spaces, `operations/` covers runtime controls, and `reasoning/` covers reasoning patterns. |
| `extensions/python/examples/language-feature-examples/` | Python counterparts of the MeTTa programs; compare both representations before inventing another adapter. |
| `examples/README.md` and `examples/` | Executable MeTTa examples organized by language construct. |
| `lib/`, especially `lib/lib_thread/` | Existing MeTTa libraries, including threading, before writing replacement infrastructure. |
| `EXTENDING.md`, `CODEC.md`, `KERNEL.md`, `metta/` and `engine/` | Extension, representation and engine contracts; inspect the implementation when a boundary is unclear. |

For matching and rewriting, read examples in chapters 04 and 05. Chapter 06
covers multiple answers; 15 covers transactions and worlds; 17 covers
concurrency; 19 covers custom spaces; 20 covers extensions; 22 covers reasoning.
Use pymetta's native concurrency and the MeTTa threading library according to
their engine ownership, cancellation, effect and budget contracts.

# GoalChainer boundaries

Jev supplies semantic classifications from domain declarations. GoalChainer
reasons over those readings; keyword lists and incident-specific categories do
not belong in the generic core. Examples must exercise the same general
mechanisms as user-supplied domains, with no predetermined plan or outcome.

Keep hypothetical transitions, observed state, proof provenance, uncertainty,
attention, norms and execution authorization distinct. The state rewrite uses
bigraphical reactive systems with actual place and link structure; a chosen
representation must implement that contract, not merely borrow its vocabulary.

