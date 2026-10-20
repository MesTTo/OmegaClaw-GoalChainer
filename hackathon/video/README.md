# Generated Video

## Historical

<!-- am[implements a-fh-label-1018@2f54e2] -->
The three compositions here, `GoalChainerExplainer`, `GoalChainer` and
`OmegaClawHackathon`, show GoalChainer in June 2026, before its domain-request
migration. The skills, verdicts, PeTTaChainer audit and delivery they show are
retired. Every frame carries a HISTORICAL label (`src/HistoricalLabel.tsx`), and
the compositions embed the captures recorded on 27 and 28 June 2026
(`public/recordings/README.md`).

<!-- am[related a-od-film-recapture-1018@51ae8c] -->
A new live capture runs Codex through its hosted service, so it waits for the
operator's authorization.

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

## Human-Owned Steps

Use `voiceover_script.md` for narration and `human_handoff.md` for the manual
upload checklist. Do not submit the placeholder draft as the final video.
