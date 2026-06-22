# OmegaClaw GoalChainer

OmegaClaw GoalChainer is a hackathon prototype for agents that reason about
individual and collective goals before acting.

The project combines three local pieces:

- `OmegaClaw-Core`, especially the deontic and directive branches, for norms,
  obligations, prohibitions, and dependency-ordered work.
- `omegaclaw-deontic`, the standalone deontic package and installer.
- `PeTTaChainer`, for πPLN generated-context reasoning over conflicting evidence.

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

## Run

From this repo:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
goalchainer demo --json
pytest
```

Use the local PeTTaChainer runtime when it is available:

```bash
export GOALCHAINER_USE_PETTA=1
export PETTACHAINER_PATH=/home/user/Dev/PeTTaChainer
export PETTA_PATH=/home/user/Dev/PeTTa
export SWIPL_HOME=/home/user/Dev/swipl-9.3.33/build-petta
export PATH="$SWIPL_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$SWIPL_HOME/lib/swipl/lib/x86_64-linux:${LD_LIBRARY_PATH:-}"
export LD_PRELOAD=/home/user/Dev/PeTTa/mork_ffi/target/release/libmork_ffi.so
PYTHONPATH=src /home/user/Dev/PeTTaChainer/.venv/bin/python -m goal_chainer.cli demo --json
```

Use the PeTTaChainer virtualenv for this path because it already contains the
matching `janus_swi` runtime for the local SWI-Prolog build.

The submodule at `external/PeTTaChainer` records the source version used for the
hackathon repo. On this workstation the runnable PeTTaChainer environment lives
at `/home/user/Dev/PeTTaChainer`, so the command above points there.

## Project Links

- Core fork and deontic branches: <https://github.com/MesTTo/OmegaClaw-Core>
- Standalone deontic package: <https://github.com/MesTTo/omegaclaw-deontic>
- PeTTaChainer fork: <https://github.com/MesTTo/PeTTaChainer>
- Hackathon page: <https://deep-projects.ai/hackathon/ai-agents-that-understand-our-individual-and-collective-goals/>

## Repo Layout

- `src/goal_chainer/` contains the prototype engine and optional PeTTaChainer
  bridge.
- `examples/` contains runnable entry points.
- `docs/architecture.md` describes how the pieces fit together.
- `hackathon/submission.md` is the draft project copy for the DEEP Projects page.
- `tests/` checks scoring, norm resolution, and PeTTa output parsing.
