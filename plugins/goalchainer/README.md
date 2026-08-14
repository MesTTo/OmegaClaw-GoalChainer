# GoalChainer plugin

Adds goal-aware decision support to the agent: given a request, GoalChainer
parses it into Semantic-Hypergraph propositions, ingests them as SNARS evidence,
gates the candidate actions through `lib_deontic`, ranks what survives with
MetaMo's motivation consensus, and can execute the winner and leak-check the
result before it goes out.

## Skills

| Skill | What it does |
| --- | --- |
| `goalchainer-decision request` | Decide what to send, from parsed SH evidence, SNARS beliefs and proofs, `lib_deontic` and MetaMo |
| `goalchainer-solve request` | Decide **and** execute: run the recommended action and return the leak-checked deliverable |
| `goalchainer-motivation request` | Reconcile individual against collective goals with MetaMo's consensus |
| `goalchainer-directive request` | Create and claim a directive plan from a decision |
| `goalchainer-directive-dispatch json_request` | Inspect or mutate a durable plan from typed JSON |
| `goalchainer-snars request` | The native SNARS decision summary |
| `goalchainer-snars-dispatch json_request` | Evidence, explanation, counterfactual, goal-temporal and trust-discovery operations |
| `goalchainer-thread-dispatch json_request` | Compile, inspect, route, run or render MeTTa Markdown thread orchestration |

GoalChainer's required pipeline reaches the agent through
`add-prompt-extension`, so it is context the model already has rather than a
skill it must remember to call.

Registration goes through `add-skill`, which appends the catalogue line **and**
calls `helper.add_llm_command`. The second half is what makes a skill callable:
`src/loop.metta` prechecks every parsed command with
`(HandleError UNKNOWN_SKILL_CALL $s $s)`, and `balance_parentheses` in
`src/helper.py` raises that for any command whose head is not in
`LLM_COMMANDS`. The bridge this plugin replaces only advertised its commands, so
on a current OmegaClaw every `goalchainer-*` call came back rejected.

## Requirements

- The **deontic plugin**, which supplies `lib_deontic` and `lib_directive`.
- The **`omegaclaw-goalchainer` package** on the agent's `PYTHONPATH`. The
  plugin only `py-call`s into it; `py-call` resolves exactly one dot, so the
  callable surface is the single top-level `gcskill` module rather than
  `goal_chainer.omegaclaw_skill` directly.

## Install

Copy this directory into the OmegaClaw-Core checkout and add one entry to
`config/plugins.yaml`:

```yaml
- name: goalchainer
  loader: metta
  location: "{REPO}/plugins/goalchainer"
```

No core file is edited.

## Tests

```sh
OMEGACLAW_DIR=<the checkout> plugins/goalchainer/tests/run.sh
```

`test_goalchainer_plugin.metta` covers the seam. It asks
`helper.starts_command_line` — the predicate the parser applies — before and
after loading the plugin through the real `loadMettaPlugin`, so it pins that
each command goes from rejected to dispatchable and that an unregistered name is
still rejected. Loading also proves the Python side resolves, because the prompt
extension is built by `py-call`ing `gcskill.system_prompt`.
