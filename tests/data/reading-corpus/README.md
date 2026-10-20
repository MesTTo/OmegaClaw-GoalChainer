# Reading parity corpus

Purpose: a frozen, held-out set of short incident texts, each labelled on every proposition and
choice the incident reading declaration asks. `python -m goal_chainer.semantic_evaluation` scores
the semantic reader's replayed answers against the labels.

`corpus.json` holds 40 texts written for this corpus. None is taken from the tests, and none was
used to shape a reading question. Each label is one of the declaration's answers for a
proposition, under `labels`, or one of a choice's options, under the choice's own id (here `mood`).
A corpus for a declaration with bindings labels each binding under `bindings`, by its signal and
then its control, with an entity it offers or `no match`; the incident declaration declares none.
Each carries the clause of the text that justifies it. A label abstains with `null` in place of its
answer, never with a word, since an option may be named anything, `abstain` included. The judgement
follows the declaration's own answer descriptions:

| label | the text |
| --- | --- |
| `supported` | states, or clearly implies, that the proposition is true |
| `contradicted` | states, or clearly implies, that the proposition is false |
| `unknown` | says nothing that settles either |
| `null` (abstain) | could be read either way by a careful reader; never scored |

The sensitive-data and sensitive-category propositions are about content that "includes, or may
include", the data, so a stated possibility supports them.

All labels are by `labelled_by`, written from the texts alone before any Jev answer for them existed.
Version 1's SHA-256 was recorded in the project's reasoning record (`c-corpus-frozen-1017`) before
its first capture; its guideline sentence was later reworded, every text and label unchanged. Version
2 (`c-bnd-corpus-v2-1019`) writes version 1's abstentions as `null`, every other label, text and key
unchanged. A changed label or text is a new version of the corpus, never an edit of this one.

The texts are asked of Jev in file order. If the request cap stops a capture, the scored corpus is
the leading texts whose answers are all captured. That rule was fixed before any answer was seen.

The report gives, per proposition and for the mood:
- the confusion of labels against decided answers, with abstentions left out;
- accuracy and per-class recall, each with a Wilson 95% interval;
- the Brier score and the gap between mean top probability and accuracy, each with a seeded
  bootstrap 95% interval.

About 40 labels per proposition are too few for a binned reliability curve. The report makes no
global calibration claim, and nothing in it changes how evidence is valued or what any model is
trained on.
