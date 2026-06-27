# Recording Placeholders

The draft video renders without media files. Use this folder for human-owned
recordings when replacing the placeholder panels.

Suggested filenames:

- `codex-auth-selftest.mp4`: a short terminal or browser clip showing the Codex
  provider self-test.
- `codebase-repair-demo.mp4`: a terminal clip showing the regenerated repo,
  failing tests, symbolic reasoning trace, patch, generated git log, and passing
  tests. This is preferred over `goalchainer-demo.mp4` when present.
- `goalchainer-demo.mp4`: a short clip showing the GoalChainer JSON run or the
  PeTTaChainer proof audit.
- `voiceover.wav`: Ahmad Mesto's narration.

After recording, run `npm run render:clean`. The render script detects these
files and includes them automatically.
