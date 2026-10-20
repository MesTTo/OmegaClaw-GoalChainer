Purpose: hold the Jev answers GoalChainer's tests replay offline.

Each `<sha256>.json` file is one answer Jev gave to one reading question about one text, named by
the SHA-256 of the model, the state and the question (`goal_chainer.semantic_reader.AnswerCache`).
Every answer here was captured from the live service by
`python -m goal_chainer.semantic_capture capture`, never written by hand, so a test that replays
one is a replay of what Jev answered. A file holding `refused` records that Jev refused the text as
too long. See docs/semantic-reader.md.
