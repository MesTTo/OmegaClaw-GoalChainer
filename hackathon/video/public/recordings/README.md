# Recordings

Real terminal recordings the videos embed. The files themselves are gitignored;
the recorder scripts under `../../scripts` are the source of truth, so anyone can
regenerate them.

## The film (GoalChainer composition)

- `codex-omegaclaw-loop.mp4`: the headline. The real `codex_omegaclaw_loop.sh`
  session, Codex driving OmegaClaw Core through the GoalChainer skill across six
  agent cycles (pin, SNARS, MetaMo, decision, solve, send). Capture it with
  `bash scripts/record-codex-omegaclaw-loop.sh` (Codex really runs across cycles,
  so this needs network and the logged-in Codex path), then `npm run render:film`.
- `codex-omegaclaw.mp4`: the single-shot variant (one command), from
  `bash scripts/record-codex-omegaclaw.sh`. Not used by the current film.

## The draft (OmegaClawHackathon composition)

These fill the draft's clip slots; `npm run prepare:media` detects them and writes
`src/video/media.generated.ts`, then `npm run render:clean` embeds them.

- `codex-auth-selftest.mp4`: the Codex provider self-test.
- `codebase-repair-demo.mp4`: the regenerated repo, failing tests, the patch, the
  generated git log, passing tests. Preferred over `goalchainer-demo.mp4`.
- `goalchainer-demo.mp4`: the GoalChainer run or the PeTTaChainer proof audit.
- `voiceover.wav`: narration.
