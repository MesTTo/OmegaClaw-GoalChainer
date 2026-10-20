# GoalChainer film

A ~111s explainer video (Remotion composition id `GoalChainer`), no voiceover.
It is historical: it shows GoalChainer in June 2026, before its domain-request
migration, and every frame says so (`../HistoricalLabel.tsx`).

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

`public/recordings/codex-omegaclaw-loop.mp4` is the capture of 28 June 2026: Codex
driving OmegaClaw across six cycles of the retired skills (pin, SNARS, MetaMo,
decision, solve, send). The headline steps in `scenes.ts` and the callouts in
`ExplainerFilm.tsx` narrate that capture. Recordings are gitignored and stay
local. The clip is played at `playbackRate` 0.85 so each cycle is readable, and
`npm run render:film` embeds it.

<!-- am[related i-od-film-narrates-earlier-capture-1018@d02bd3] am[related a-od-film-recapture-1018@51ae8c] -->
`bash scripts/record-codex-omegaclaw-loop.sh` now records a different session
under the same name: the pin, the run's explicit incident review through
`goalchainer-request`, and the answer, which the host delivers nowhere. Recording
it replaces the kept capture, so the steps and callouts would need rewriting and
re-timing. It runs Codex through its hosted service, so it waits for the
operator's authorization.

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
