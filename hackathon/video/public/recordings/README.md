# Recordings

Terminal recordings the videos embed. The files are gitignored and stay local.
A recording script replaces a file here only when its recorded run and both renders succeeded.
Each MP4 it publishes keeps its cast and GIF in
`out/live-casts/<the directory its path owns>/<sha256 of the MP4>/`,
written and synced before the MP4's rename makes the new capture current, so a recording or publication
that fails before that rename exits with the failure's status and leaves every current capture
as it was. An interrupt leaves the capture as it was too, or the new one current when it comes
after the rename. If the new MP4's directory then cannot be synced to disk, the script fails too and
keeps the capture the new one replaced beside it. Each MP4 path owns its own directory there,
named by a hash of the path and the MP4's file name, and publishing removes only the other
captures in it, so an MP4 at another path keeps its own even when it holds the same bytes, and two
publications of one MP4 take turns. Besides those captures, a publication removes only what an
earlier one stopped part-way left: a capture set aside there as `.<digest>.<token>.removing` and a
copy of the MP4 staged beside it as `.<the MP4's name>.<token>.staged`. Any other file kept in
either place, a `.gitkeep` or notes, stays.
The captures kept here were recorded on 27 and 28 June 2026, before GoalChainer's
domain-request migration, and the compositions that embed them are labelled
historical. The recorder scripts under `../../scripts` now record different
sessions under the same file names, so recording one replaces its historical
capture.

## The films (GoalChainer and GoalChainerExplainer compositions)

- `codex-omegaclaw-loop.mp4`: the headline. The kept capture is a six-cycle run of
  the retired skills: pin, SNARS, MetaMo, decision, solve, send.
  `bash scripts/record-codex-omegaclaw-loop.sh` now records Codex driving Omega,
  formerly OmegaClaw, through the GoalChainer plugin's tools, one tool call per agent cycle: it
  pins the task, sends the run's explicit incident review through
  `goalchainer-request`, then answers, and the host delivers the answer nowhere.
  Codex really runs, so a capture needs network, the logged-in Codex path and the
  operator's authorization.
- `codex-omegaclaw.mp4`: the single-shot variant, one Codex turn whose
  GoalChainer tool calls Omega evaluates, from
  `bash scripts/record-codex-omegaclaw.sh`. The films do not use it.

## The draft (OmegaClawHackathon composition)

These fill the draft's clip slots; `npm run prepare:media` detects them and writes
`src/video/media.generated.ts`, then `npm run render:clean` embeds them.

- `codex-auth-selftest.mp4`: the kept capture is the self-test of the Codex provider in a
  Codex-auth fork of OmegaClaw-Core. `bash scripts/record-demo-clips.sh` now records the stock
  path's self-test under this name, with no hosted call: the Codex CLI's version and login and the
  skills the installed GoalChainer plugin registers in Omega. The live terminal demo
  (`npm run record:terminal`, written to `out/`) opens with the same self-test.
- `goalchainer-demo.mp4`: the kept capture shows PeTTaChainer's showcase verifier
  and its earlier audit verdict. `bash scripts/record-demo-clips.sh` now records the
  GoalChainer incident review and its recorded provenance under this name, with
  the self-test.
- `codebase-repair-demo.mp4`: the retired codebase repair demo's capture, which the
  draft no longer embeds.
- `voiceover.wav`: narration.
