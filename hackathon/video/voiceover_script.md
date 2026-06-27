# OmegaClaw GoalChainer Voiceover Script

Target length: 2 minutes.

## 0:00 to 0:10

I am showing OmegaClaw GoalChainer, a decision layer for agents that need to
reason about individual and collective goals before they act.

## 0:10 to 0:30

The problem is that a useful action can still violate a goal. In incident
response, raw logs help the team coordinate, but they may expose customer data.

GoalChainer keeps privacy, service repair, coordination, and deontic norms
visible instead of hiding them in one prompt.

## 0:30 to 0:48

The Codex provider removes setup friction. OmegaClaw can use the logged-in Codex
path, so the demo focuses on the reasoning loop rather than credential setup.

## 0:48 to 1:26

The main demo is a generated codebase repair task.

The user gives a normal bug report: the checkout status repo is leaking customer
data in incident updates. GoalChainer regenerates a local repo with docs, tests,
and a seeded implementation bug, then runs the tests before patching.

It reads the policy contract from Markdown, inspects the Python function with
AST, and emits structured propositions: the policy forbids restricted fields,
the tests reject restricted values, and the code returns `raw_log` unchanged.

It also shows counterfactuals. Returning `raw_log` is blocked. Deleting all
diagnostics is weak. Redacting restricted fields while keeping allowed
diagnostics is selected.

## 1:26 to 1:48

The patch is shown as a real diff. It redacts customer emails, order IDs, request
payloads, tokens, and traces before the external update is built.

After the patch, the repo is inspected again. The returned fields now match the
documented customer update contract, `raw_log` is no longer passed through, tests
pass, and the fix is committed locally.

## 1:48 to 2:00

The point is concrete: the user does not need to know the formal terms. They ask
a normal operational question, and the agent answers with goals, norms, source
evidence, counterfactuals, a patch, tests, and a local proof trail.
