# GoalChainer film

A ~111s explainer video (Remotion composition id `GoalChainer`), no voiceover.

The headline scene is a **real screen recording**: the captured
`codex_omegaclaw_loop.sh` session embedded as video. Codex is the provider in
OmegaClaw's loop and works the incident across six cycles, one command per turn,
while a step caption narrates whichever cycle is on screen. The other scenes
reconstruct genuine CLI output as typed terminals and pause to overlay annotations
with arrows pointing at the output. The reconstructed text is real output from
`goalchainer validate`, `goalchainer motivation`, and `goalchainer solve`.

Structure:
- title, then the problem,
- `omegaclaw` — the headline, a real recording: Codex (gpt-5.5, reasoning effort xhigh) drives OmegaClaw across cycles — pin, SNARS, MetaMo, the ranked decision, solve, then a grounded send — each evaluated by OmegaClaw's own registry,
- `validate` — the same code, three requests, three verdicts (input-driven, not a fixed answer),
- `motivation` — individual vs collective goals pulling apart, reconciled by MetaMo's consensus,
- `solve` — real PII in, the redacted deliverable out, leak-checked,
- closing — the seven systems, one runtime.

## The headline recording

`public/recordings/codex-omegaclaw-loop.mp4` is captured live (Codex really runs
across cycles, so it needs network and the logged-in Codex path). Regenerate it with:

```bash
cd hackathon/video
bash scripts/record-codex-omegaclaw-loop.sh    # asciinema -> agg -> ffmpeg
```

Recordings are gitignored; the recorder script is the source of truth. The clip is
played at `playbackRate` 0.85 in the film so each cycle is readable. After
recording, `npm run render:film` embeds it.

## Render

```bash
cd hackathon/video
npm install              # if node_modules is absent
npm run preview          # remotion studio; pick the GoalChainer composition
npm run render:film      # -> out/goalchainer-film-clean.mp4 (1920x1080, h264, metadata stripped)
```

Fonts (IBM Plex Mono, Fraunces, IBM Plex Sans) are committed under
`public/fonts/*.woff2` and loaded via `@font-face`, so the render needs no network.
Files: `theme.ts`, `Fonts.tsx`, `Background.tsx`, `Panel.tsx` (shared window chrome),
`Terminal.tsx` (reconstructed terminals), `Clip.tsx` (the embedded recording + step
captions), `Card.tsx` (shared card + connector), `Annotation.tsx` (line-pointing
arrows), `Cards.tsx` (title/problem/closing), `scenes.ts`, `GoalChainerFilm.tsx`.
