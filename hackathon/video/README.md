# Generated Video

This folder contains the TypeScript source for the draft hackathon video.

The video is built using Remotion. The current draft is silent until Ahmad
Mesto's voiceover is added. If recordings are present in `public/recordings/`,
the render command includes them automatically.

The main composition is timed to 2:00.

## Commands

```bash
npm install
npm run render:clean
```

The clean draft renders to:

```text
out/omegaclaw-goalchainer-draft-clean.mp4
```

For an intermediate render without the metadata strip:

```bash
npm run render
```

That writes:

```text
out/omegaclaw-goalchainer-draft.mp4
```

For a faster proof render:

```bash
npm run render:low
```

To record only the stronger codebase repair terminal clip:

```bash
npm run record:codebase
```

That writes `public/recordings/codebase-repair-demo.mp4`. The render step will
use it in the GoalChainer clip slot when it is present.

## Human-Owned Steps

Use `voiceover_script.md` for narration and `human_handoff.md` for the manual
upload checklist. Do not submit the placeholder draft as the final video.
