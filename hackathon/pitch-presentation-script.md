# GoalChainer — pitch script (spoken over `pitch-presentation.html`)

How to use this. Open `pitch-presentation.html` and press **F** for fullscreen.
Each `[SPACE]` below is one press of the spacebar: it either reveals the next line
on the slide or moves to the next slide. The bold lines are what is on the screen;
the plain text is what you say, and it carries detail that is not on the slide.
Target length about three minutes at a normal speaking pace. Slow down on the
causal chain and the demo.

---

## Slide 1 — title

Hi, I'm Ahmad. This is OmegaClaw GoalChainer. The one-line version: it gives an
agent ethics it can actually prove, and it now runs in pure TypeScript. Let me
show you why that matters.

`[SPACE]`

## Slide 2 — the stakes

**Checkout is down. The fastest fix leaks your customers.**

Picture a real incident. The service is down and the on-call engineers want to
paste the raw production logs into the public channel so everyone can debug.

`[SPACE]` Those logs carry customer emails, order IDs, live access tokens.

`[SPACE]` So two goals collide. The collective goal wants to share everything and
coordinate. The individual's goal, privacy, wants to protect them. And there is a
norm that forbids it.

`[SPACE]` Here is the thing. A normal agent optimizes the task it was given, and it
leaks the data, and it looks competent while doing it. The interesting question is
not what the agent *can* do. It is what it *should* do.

`[SPACE]`

## Slide 3 — the idea

**What if ethics were math?**

Our answer is a branch of formal logic most people have never heard of. Deontic
logic, the logic of obligation, goes back to von Wright in 1951. It is what legal
and normative reasoning is built on.

`[SPACE]` `[SPACE]` `[SPACE]` `[SPACE]` It has three words. Forbidden, must not
happen. Obligated, must happen. Permitted, allowed but not required.

`[SPACE]` And that is the pitch in one line. Norms you can read, rules that fire,
and a verdict you can prove. Not a vibe, not a content filter, not a hope that the
model behaves. It may be the most precise and auditable way we have to give a
machine ethics.

`[SPACE]`

## Slide 4 — the pipeline

**From plain English to a provable verdict.**

So how does a sentence become a verdict? Watch the trajectory. I'll build it one
step at a time.

`[SPACE]` It starts as natural language, the messy request. `[SPACE]` `[SPACE]` We
rewrite it into structured propositions, one claim per sentence. `[SPACE]` `[SPACE]`
Those become MeTTa atoms, a small knowledge graph the machine can query. `[SPACE]`
`[SPACE]` Then four reasoning systems run over it. `[SPACE]` `[SPACE]` They produce
one ranked verdict, gated by the norms. `[SPACE]` `[SPACE]` And then it actually
executes the chosen action and checks the result. Real data in, safe data out.
Let me show you each piece for real.

`[SPACE]`

## Slide 5 — translation

**Natural text becomes something a machine can reason over.**

This is the actual request. `[SPACE]` And this is what it compiles to: real MeTTa
atoms. `given risky publish_raw_log`, plus the hypergraph edges for the entities
it found. No keyword matching, it reads the meaning. Now we can reason.

`[SPACE]`

## Slide 6 — the norms

**A defeasible rule fires the verdict.**

The norms are defeasible, which is a precise idea. A "normally" rule holds unless
something stronger overrides it, exactly like real-world policy.

`[SPACE]` The agent reads the risk, and the rule fires: a risky raw log is a
forbidden action. `[SPACE]` And forbidden dominates obligated dominates permitted,
so the raw log is out before any number is even computed. The prohibition is a
hard gate.

`[SPACE]`

## Slide 7 — graded belief, PLN

**How strongly should it believe each option?**

Forbidding is not enough, you also need to grade the good options. For that we run
PeTTaChainer, which is a full implementation of PLN, Probabilistic Logic Networks,
from Goertzel, Iklé, Goertzel and Heljakka. The key idea is that every belief
carries two numbers, not one: strength, how true it is, and confidence, how
settled the evidence is.

`[SPACE]` It chains the rules and the facts with two operators, deduce and revise,
and the redacted summary lands at strength 0.93, confidence 0.98, with a full
proof term you can inspect.

`[SPACE]` And we cross-check it. A second engine, SNARS, built on subjective
logic, returns the same call as an opinion: belief 0.669, projected expectation
0.834, with provenance for every premise. Two independent uncertainty calculi,
same answer.

`[SPACE]`

## Slide 8 — whose goal wins, MetaMo

**Reconciling the individual and the collective.**

Now the goals layer, and this is the heart of the hackathon theme.

`[SPACE]` `[SPACE]` We model each goal owner as its own motivation subsystem. The
individual pulls toward the redacted summary. The collective pulls toward the raw
log, because the raw log has the most detail.

`[SPACE]` `[SPACE]` MetaMo scores each action by how much both subsystems can
agree. The action both can accept wins, and an option one side loves and the other
hates is penalized for the gap. That quarter-times-the-disagreement term is a
fairness floor.

`[SPACE]` The winner is the redacted summary, the action that serves the team
without sacrificing the person.

`[SPACE]`

## Slide 9 — the verdict

**One ranked decision, gated by the norms.**

So here is the output. `[SPACE]` The redacted summary is recommended at 0.987.
`[SPACE]` Holding is a weaker candidate at 0.516. `[SPACE]` And the raw log is
blocked at minus one. `[SPACE]` That minus one is the deontic gate. No amount of
usefulness can buy a forbidden action back. That is the whole point.

`[SPACE]`

## Slide 10 — it solves it

**Real data in, a safe deliverable out.**

And it does not stop at a recommendation. It runs the chosen action on the real
incident log. `[SPACE]` Here is the real input: a customer email, an order ID, a
live token. `[SPACE]` Here is exactly what gets sent: every restricted value
replaced with redacted, and the operational error code kept so the update is still
useful. `[SPACE]` Then a leak check scans the output for every secret. Nothing
survives. Safe, leaked nothing. A problem actually solved, not a decision table.

`[SPACE]`

## Slide 11 — see it run

**Codex drives the live OmegaClaw loop.**

And this is all of it running for real. `[SPACE]` That is Codex, GPT 5.5, driving
the actual OmegaClaw agent loop across six cycles, calling GoalChainer as a skill,
on the live runtime. `[SPACE]` You can watch the reasoning and the output go by:
the SNARS belief, the verdict blocking the raw log, the solve step leaking nothing.

`[SPACE]`

## Slide 12 — the headline, MeTTa-TS

**And all of this now runs in pure TypeScript.**

Here is the part I'm most excited about. `[SPACE]` All of this reasoning now runs
on MeTTa-TS, a pure-TypeScript MeTTa interpreter. No Prolog, no Python, no native
addon. It runs in a browser, on the edge, and inside a TypeScript agent, which
also means it can reach the entire JavaScript and MCP tooling ecosystem.

`[SPACE]` And it is correct. It passes all 270 assertions of Hyperon's oracle, and
it is cross-checked against a machine-checked Lean 4 semantics. `[SPACE]` We
proved it reproduces the original engines value for value, down to the last digit:
the same strength, the same 0.986774. Not approximately. Bit for bit.

`[SPACE]`

## Slide 13 — close

**Real reasoning. Input-driven. Verified.**

So that is GoalChainer. It weighs whose goal is helped, whose is harmed, and which
norm forbids it, before it acts. The reasoning is real, it changes with the input,
and every step is verified. Thank you.

---

## If you are short on time (60 seconds)

Run slides 2, 4, 9, 11, 12. "Checkout is down and the fast fix leaks customer
data. GoalChainer turns the request into MeTTa atoms, then reasons over it with
deontic norms, PLN belief, a subjective-logic cross-check, and an individual-versus
-collective consensus. It blocks the raw log at minus one, recommends the redacted
summary at 0.987, and the leak check proves nothing sensitive ships. Here it is
running for real under Codex. And all of it now runs in pure TypeScript, proven
bit-for-bit against the original."

## Likely questions

- **Is it hardcoded?** No. The same code blocks the raw log under PII and permits
  it when the data is declared public, proven by a differential battery.
- **Does Codex really drive it?** Yes, the recording is the real run; Codex emits
  each command and OmegaClaw evaluates it.
- **What is novel?** The combination: defeasible deontic norms, PLN belief, a
  subjective-logic opinion, and an individual-versus-collective consensus, fused
  into one ranked, proof-backed, leak-checked decision, exposed as an agent skill,
  and now portable to pure TypeScript.
