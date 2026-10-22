<!-- Purpose: give the exact spoken path and visual cues for the GoalChainer pitch presentation. -->
<!-- am[implements a-semantic-motion-scenes@5a3658] -->
# GoalChainer: pitch script (spoken over `pitch-presentation.html`)

How to use this. Open `pitch-presentation.html` and press **F** for fullscreen.
Each `[SPACE]` below is one press of the spacebar: it either reveals the next line
on the slide or moves to the next slide. The bold lines are what is on the screen;
the plain text is what you say, and it carries detail that is not on the slide.
Target length about three minutes at a normal speaking pace. Slow down on the
causal chain and the demo.

---

## Slide 1: title

Hi, I'm Ahmad. This is OmegaClaw GoalChainer. The one-line version: it makes an
agent weigh competing goals under explicit norms before it acts. The diagram is
the whole story. The two goals pull in different directions, the norm rules one
route out, and one action remains acceptable to both.

`[SPACE]`

## Slide 2: the stakes

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

## Slide 3: the idea

**Norms become rules the agent can query.**

Our answer uses deontic logic, the logic of obligation. It separates an action's
status from its usefulness, so a useful action can still be forbidden.

`[SPACE]` `[SPACE]` `[SPACE]` `[SPACE]` It has three words. Forbidden, must not
happen. Obligated, must happen. Permitted, allowed but not required.

`[SPACE]` The action enters as a proposition, the rule stays visible, and the
status leaves with its reason. The agent can inspect that result before acting.

`[SPACE]`

## Slide 4: the pipeline

**Follow one claim from request to action.**

So how does a sentence become a verdict? Follow the moving token. Its identity
does not disappear at a hidden handoff.

The request becomes a reading, then MeTTa facts and rules. The reasoning layer
adds the norm, belief, and goal conclusions. The verdict chooses an allowed
action. The host executes it and checks the result. Each boundary is explicit:
host code transports and executes; MeTTa policy decides the route.

`[SPACE]`

## Slide 5: translation

**Natural text becomes something a machine can reason over.**

This is the actual request. `[SPACE]` And this is what it compiles to: real MeTTa
atoms. `given risky publish_raw_log`, plus the hypergraph edges for the entities
it found. No keyword matching, it reads the meaning. Now we can reason.

`[SPACE]`

## Slide 6: the norms

**A defeasible rule fires the verdict.**

The norms are defeasible. A normal rule holds unless something stronger defeats
it, which lets policy express exceptions without silently dropping the default.

`[SPACE]` Watch the risk fact move into the stable rule. The rule emits a
forbidden conclusion with its derivation. `[SPACE]` The prohibition is a hard
gate. Usefulness can rank allowed actions, but no score can revive this one.

`[SPACE]`

## Slide 7: graded belief, PLN

**How strongly should it believe each option?**

Forbidding is not enough, you also need to grade the good options. For that we run
PeTTaChainer, which is a full implementation of PLN, Probabilistic Logic Networks,
from Goertzel, Iklé, Goertzel and Heljakka. The key idea is that every belief
carries two numbers, not one: strength, how true it is, and confidence, how
settled the evidence is.

`[SPACE]` The fact and rule stay visible while their support paths converge.
Deduction composes evidence, revision combines independent support, and the
redacted summary lands at strength 0.93, confidence 0.98, with an inspectable
proof term.

`[SPACE]` And we cross-check it. A second engine, SNARS, built on subjective
logic, returns the same call as an opinion: belief 0.669, projected expectation
0.834, with provenance for every premise. Two independent uncertainty calculi,
same answer.

`[SPACE]`

## Slide 8: whose goal wins, MetaMo

**Reconciling the individual and the collective.**

Now the goals layer, and this is the heart of the hackathon theme.

`[SPACE]` `[SPACE]` We model each goal owner as its own motivation subsystem. The
arrows keep those directions visible. The individual pulls toward privacy. The
collective pulls toward useful operational detail.

`[SPACE]` `[SPACE]` MetaMo scores each action by how much both subsystems can
agree. The action both can accept wins, and an option one side loves and the other
hates is penalized for the gap. That quarter-times-the-disagreement term is a
fairness floor.

`[SPACE]` The consensus marker settles on the redacted summary, the action that
serves the team without sacrificing the person.

`[SPACE]`

## Slide 9: the verdict

**One ranked decision, gated by the norms.**

The bars show the ranking grow. `[SPACE]` The redacted summary reaches 0.987.
`[SPACE]` Holding reaches 0.516. `[SPACE]` The raw log may score as useful, but
the independent norm gate clamps it to minus one. `[SPACE]` No amount of
usefulness can buy a forbidden action back.

`[SPACE]`

## Slide 10: it solves it

**Real data in, a safe deliverable out.**

And it does not stop at a recommendation. The scan crosses the actual incident
record. `[SPACE]` Here is the real input: a customer email, an order ID, a live
token. `[SPACE]` Restricted values disappear into redacted placeholders while
the operational error code persists. `[SPACE]` The final leak check searches the
output for every original secret. Nothing survives. Safe, leaked nothing.

`[SPACE]`

## Slide 11: see it run

**Codex drives the live OmegaClaw loop.**

And this is all of it running for real. `[SPACE]` That is Codex, GPT 5.5, driving
the actual OmegaClaw agent loop across six cycles, calling GoalChainer as a skill,
on the live runtime. `[SPACE]` You can watch the reasoning and the output go by:
the SNARS belief, the verdict blocking the raw log, the solve step leaking nothing.

`[SPACE]`

## Slide 12: the semantic boundary

**Verify the program where it actually runs.**

The moving token now shows the acceptance boundary. `[SPACE]` The policy is MeTTa.
GoalChainer targets the pinned native engine through pymetta. The engine's actual
behavior, not an editor's approximation, decides whether the program works.

`[SPACE]` Acceptance comes from behavioral evidence: changing the input changes
the verdict, exact counterexamples stay as regressions, and execution produces a
leak-checked artifact. `[SPACE]` MeTTaLSP diagnostics are useful editor feedback,
but they are not semantic proof here because that implementation has different
semantics.

`[SPACE]`

## Slide 13: close

**Real reasoning. Input-driven. Verified.**

So that is GoalChainer. It weighs whose goal is helped, whose is harmed, and which
norm forbids it, before it acts. The reasoning is real, it changes with the input,
and every step is verified. Thank you.

---

## If you are short on time (60 seconds)

Run slides 2, 4, 9, 11, 12. "Checkout is down and the fast fix leaks customer
data. GoalChainer turns the request into MeTTa atoms, then reasons over it with
deontic norms, PLN belief, a subjective-logic cross-check, and an
individual-versus-collective consensus. It blocks the raw log at minus one,
recommends the redacted summary at 0.987, and the leak check proves nothing
sensitive ships. Here it is running for real under Codex. The MeTTa policy is
accepted against GoalChainer's
pinned pymetta runtime and the end-to-end behavior, not editor diagnostics."

## Likely questions

- **Is it hardcoded?** No. The same code blocks the raw log under PII and permits
  it when the data is declared public, proven by a differential battery.
- **Does Codex really drive it?** Yes, the recording is the real run; Codex emits
  each command and OmegaClaw evaluates it.
- **What is novel?** The combination: defeasible deontic norms, PLN belief, a
  subjective-logic opinion, and an individual-versus-collective consensus, fused
  into one ranked, proof-backed, leak-checked decision, exposed as an agent skill,
  with MeTTa policy remaining authoritative over the decision.
