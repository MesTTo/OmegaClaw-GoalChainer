# OmegaClaw GoalChainer

OmegaClaw GoalChainer is a hackathon prototype for agents that reason about
individual and collective goals before acting.

The project combines three local pieces:

- `OmegaClaw-Core`, especially the deontic and directive branches, for norms,
  obligations, prohibitions, and dependency-ordered work.
- `omegaclaw-deontic`, the standalone deontic package and installer.
- `PeTTaChainer`, for πPLN generated-context reasoning over conflicting evidence.
- `mettabase` and COLORE, for ontology context and HyperBase-ready structured
  propositions.

Those repos are linked as submodules under `external/`:

```bash
git submodule update --init --recursive
```

The first demo is an incident-response planning problem. One person needs privacy,
the team needs enough detail to coordinate, and the service needs a fix. The
agent ranks candidate actions by checking:

- which individual and collective goals each action satisfies,
- whether a norm permits, obligates, forbids, or conflicts on the action,
- what contextual evidence says once exceptions are considered.

The PeTTaChainer bridge is optional. Without it, the demo uses deterministic
scenario scores so the repo stays easy to test. With the local PeTTaChainer
checkout and SWI runtime configured, the same action evidence can be scored by
`contextual_query`.

The ontology bridge is read-only. It loads the local COLORE fixture from
`/home/user/Dev/mettabase/tests/petta/data-colore.metta` when that file is
available, summarizes the selected timepoints and kinship axioms, and emits
HyperBase-style `(hb ...)` facts for clear incident propositions. This gives the
agent a parseable proposition layer without requiring the user to know HyperBase
notation.

The stronger demo is a generated codebase repair task. GoalChainer regenerates a
small checkout-status repo with a seeded leak, runs its failing tests, reads the
repo docs and implementation, emits HyperBase-ready propositions about the
policy/test/code conflict, patches the bug, reruns tests, and commits the repair
inside the generated repo. The generated repo stays under `artifacts/` unless
`--repo-path` or `GOALCHAINER_CODEBASE_DEMO_REPO` points somewhere else.

## Run

From this repo:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
goalchainer demo --json
goalchainer-skill goalchainer-ontology-context --request "checkout logs include customer emails"
goalchainer codebase-demo --request "read the repo docs and tests, then fix the checkout update leak"
goalchainer-skill goalchainer-codebase-demo --request "debug the checkout status repo"
pytest
```

Use the local PeTTaChainer runtime when it is available:

```bash
export GOALCHAINER_USE_PETTA=1
export PETTACHAINER_PATH=/home/user/Dev/PeTTaChainer
export PETTA_PATH=/home/user/Dev/PeTTa-upstream-clean
export SWIPL_HOME=/home/user/Dev/swipl-9.3.33/build-petta
export PATH="$SWIPL_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$SWIPL_HOME/lib/swipl/lib/x86_64-linux:${LD_LIBRARY_PATH:-}"
PYTHONPATH=src /home/user/Dev/PeTTaChainer/.venv/bin/python -m goal_chainer.cli demo --json
```

Use the PeTTaChainer virtualenv for this path because it already contains the
matching `janus_swi` runtime for the local SWI-Prolog build.

The submodule at `external/PeTTaChainer` records the source version used for the
hackathon repo. On this workstation the runnable PeTTaChainer environment lives
at `/home/user/Dev/PeTTaChainer`, so the command above points there.

The command uses `/home/user/Dev/PeTTa-upstream-clean`, a clean checkout of
`trueagi-io/PeTTa`, so the demo does not depend on local custom PeTTa edits.

## Pitch Video

The TypeScript pitch-video source lives in `hackathon/video/`.

```bash
cd hackathon/video
npm install
npm run render:clean
```

The render command creates `out/omegaclaw-goalchainer-draft-clean.mp4`. The
current draft has placeholders for Ahmad Mesto's voiceover and optional terminal
clips. Put recordings in `hackathon/video/public/recordings/` using the names in
that folder's README, then rerun `npm run render:clean`.

## Project Links

- Core fork and deontic branches: <https://github.com/MesTTo/OmegaClaw-Core>
- Standalone deontic package: <https://github.com/MesTTo/omegaclaw-deontic>
- PeTTaChainer fork: <https://github.com/MesTTo/PeTTaChainer>
- Hackathon page: <https://deep-projects.ai/hackathon/ai-agents-that-understand-our-individual-and-collective-goals/>

## Repo Layout

- `src/goal_chainer/` contains the prototype engine, optional PeTTaChainer
  bridge, COLORE loader, and HyperBase proposition renderer.
- `examples/` contains runnable entry points.
- `docs/architecture.md` describes how the pieces fit together.
- `hackathon/submission.md` is the draft project copy for the DEEP Projects page.
- `hackathon/video/` contains the scripted TypeScript video render.
- `tests/` checks scoring, norm resolution, PeTTa output parsing, COLORE
  context loading, and HyperBase proposition facts.
