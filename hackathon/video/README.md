# Generated Video

This folder contains the TypeScript source for the draft hackathon video.

The video is built using Remotion. The current draft is silent and includes
visible placeholders for Ahmad Mesto's voiceover and optional live clips.
If recordings are present in `public/recordings/`, the render command includes
them automatically.

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

## Human-Owned Steps

Use `voiceover_script.md` for narration and `human_handoff.md` for the manual
upload checklist. Do not submit the placeholder draft as the final video.
