# GoalChainer film

A ~58s explainer video (Remotion composition id `GoalChainer`), no voiceover.

The headline scene is a **real screen recording**: the captured
`codex_drives_omegaclaw.sh` session embedded as video, with callout cards beside it.
The other scenes reconstruct genuine CLI output as typed terminals and pause to
overlay annotations with arrows pointing at the output. The reconstructed text is
real output from `goalchainer validate`, `goalchainer motivation`, and
`goalchainer solve`.

Structure:
- title, then the problem,
- `omegaclaw` — the headline, a real recording: Codex (model gpt-5.5, reasoning effort xhigh) reads OmegaClaw's skill menu and the incident, reasons, emits `goalchainer-solve` on its own, and OmegaClaw's own registry evaluates it into the verdict and the leak-checked deliverable,
- `validate` — the same code, three requests, three verdicts (input-driven, not a fixed answer),
- `motivation` — individual vs collective goals pulling apart, reconciled by MetaMo's consensus,
- `solve` — real PII in, the redacted deliverable out, leak-checked,
- closing — the seven systems, one runtime.

## The headline recording

`public/recordings/codex-omegaclaw.mp4` is captured live (Codex really runs, so it
needs network and the logged-in Codex path). Regenerate it with:

```bash
cd hackathon/video
bash scripts/record-codex-omegaclaw.sh    # asciinema -> agg -> ffmpeg
```

Recordings are gitignored; the recorder script is the source of truth. After
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
Files: `theme.ts`, `Fonts.tsx`, `Background.tsx`, `Terminal.tsx`, `Annotation.tsx`,
`Cards.tsx`, `scenes.ts` (the real captured output + annotations), `GoalChainerFilm.tsx`.
