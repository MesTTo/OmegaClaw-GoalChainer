# GoalChainer film

A ~62s explainer video (Remotion composition id `GoalChainer`). The terminal runs
the real commands, then pauses to overlay editorial annotations with arrows that
point at the output, no voiceover. All the terminal text is genuine captured output:
the OmegaClaw scene is the real `codex_drives_omegaclaw.sh` session, the rest is from
`goalchainer validate`, `goalchainer motivation`, and `goalchainer solve`.

Structure:
- title, then the problem,
- `omegaclaw` — the headline: GoalChainer runs as a real OmegaClaw Core skill, and a real agent (Codex) reads the skill menu and the incident and emits `goalchainer-solve` on its own; OmegaClaw's own registry evaluates it,
- `validate` — the same code, three requests, three verdicts (input-driven, not a fixed answer),
- `motivation` — individual vs collective goals pulling apart, reconciled by MetaMo's consensus,
- `solve` — real PII in, the redacted deliverable out, leak-checked,
- closing — the seven systems, one runtime.

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
