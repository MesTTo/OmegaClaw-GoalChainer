# OmegaClaw GoalChainer

OmegaClaw GoalChainer is a hackathon prototype for agents that reason about
individual and collective goals before acting.

The project combines three local pieces:

- `OmegaClaw-Core`, especially `lib_nal.metta` plus the deontic and directive
  branches, for native NAL truth rules, norms, obligations, prohibitions, and
  dependency-ordered work.
- `omegaclaw-deontic`, the standalone deontic package and installer.
- `PeTTaChainer`, for proof-audit and replay artifacts around generated-context
  reasoning.
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

The incident demo uses a required native reasoning path. The user can speak in
plain language. The system prompt asks Codex to rewrite the situation as clear
structured English propositions. GoalChainer renders those propositions as
HyperBase-style `(hb ...)` facts and typed `(sh ...)` trees, projects them into
NAL premises, and runs OmegaClaw Core's `lib_nal.metta` with the local MeTTa
runtime. If the MeTTa binary or NAL library is missing, the command fails.

The ontology bridge is read-only. It loads the local COLORE fixture from
`/home/user/Dev/mettabase/tests/petta/data-colore.metta` when that file is
available and summarizes selected timepoints and kinship axioms as named
projection licenses.

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
goalchainer-skill goalchainer-system-prompt
goalchainer-skill goalchainer-ontology-context --request "checkout logs include customer emails"
goalchainer codebase-demo --request "read the repo docs and tests, then fix the checkout update leak"
goalchainer-skill goalchainer-codebase-demo --request "debug the checkout status repo"
pytest
```

The native path expects the local MeTTa binary and OmegaClaw NAL library:

```bash
export GOALCHAINER_METTA_BIN=/home/user/Dev/mettabase/hyperbase/.venv/bin/metta
export GOALCHAINER_NAL_LIB=/home/user/Dev/OmegaClaw-Core/lib_nal.metta
PYTHONPATH=src python3 -m goal_chainer.cli demo --json
```

The submodule at `external/PeTTaChainer` records the source version used for the
hackathon repo. On this workstation the runnable PeTTaChainer environment lives
at `/home/user/Dev/PeTTaChainer`; the proof-audit skill reads its sealed
showcase artifacts and verifier output.

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

- `src/goal_chainer/` contains the prototype engine, native MeTTa/NAL evidence
  bridge, COLORE loader, and HyperBase proposition renderer.
- `examples/` contains runnable entry points.
- `docs/architecture.md` describes how the pieces fit together.
- `hackathon/submission.md` is the draft project copy for the DEEP Projects page.
- `hackathon/video/` contains the scripted TypeScript video render.
- `tests/` checks scoring, norm resolution, PeTTa output parsing, native
  MeTTa/NAL reasoning, COLORE context loading, and HyperBase proposition facts.
