"""Purpose: score the semantic reader against a frozen, labelled reading corpus for one reading
declaration. For each declared proposition, choice and binding it reports the confusion of
labels against decided answers, accuracy and per-class recall with Wilson 95% intervals, and the
Brier score and the calibration gap (mean top probability minus accuracy) with seeded bootstrap 95%
intervals. It makes no global calibration claim and changes nothing the reader or the policy does.

Usage, from the checkout:
    uv run --frozen --extra dev --extra semantic python -m goal_chainer.semantic_evaluation \
        --inference-budget N --timeout-seconds S [--corpus tests/data/reading-corpus/corpus.json] \
        [--domain-file PATH] [--json report.json]

The corpus is labelled for one domain's reading section: the packaged incident domain's, or that of
the domain file --domain-file names.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .domains.loader import load_domain
from .domains.readings import ReadingDeclaration
from .runtime.budget import RunBudget
from .semantic_reader import DRAWS, SURE, JevClient, SemanticReader, default_reader
from .errors import InvalidInputError

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = REPO_ROOT / "tests" / "data" / "reading-corpus" / "corpus.json"
# Keys a corpus text holds besides its choices' labels, which sit beside them under each choice's id;
# "bindings" holds each binding's label under its signal and then its control.
RESERVED_KEYS = frozenset({"id", "text", "labels", "bindings"})
# The two-sided 95% normal quantile.
Z95 = 1.959963984540054
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 20261017


# am[implements a-corpus-evaluation-1017@33cd3d]
@dataclass(frozen=True, slots=True)
class Label:
    """One judgement of one text, or None for an abstention, with the clause that justifies it."""

    answer: str | None
    why: str


# am[implements a-corpus-evaluation-1017@33cd3d]
@dataclass(frozen=True, slots=True)
class CorpusText:
    id: str
    text: str
    labels: Mapping[str, Label]
    choices: Mapping[str, Label]
    bindings: Mapping[str, Label]


# am[implements a-corpus-evaluation-1017@33cd3d]
@dataclass(frozen=True, slots=True)
class Corpus:
    version: int
    labelled_by: str
    digest: str
    texts: tuple[CorpusText, ...]


# Every declared proposition is labelled on every text, under "labels", with one of the declared
# answers, every declared choice, under its own id, with one of its options, and every declared
# binding, under "bindings" by its signal and then its control, with one of the entities it offers
# or no match, each with a nonempty justification, and nothing else is labelled. A label abstains with
# null in place of its answer: an option is a string, so no option's name, abstain included, can be
# read as abstaining (c-integrate-binding-abstain-collision-1019). Nothing names a particular
# domain's readings.
# am[implements a-corpus-evaluation-1017@33cd3d] am[implements a-dr-evaluation-generic-1018@120a4c]
# am[implements a-bnd-evaluation-1019@f82299] am[implements a-integrate-binding-abstain-repair-1019@bf5ccd]
# am[rests-on c-integrate-binding-abstain-collision-1019@8304fc]
def load_corpus(declaration: ReadingDeclaration, path: Path = CORPUS_PATH) -> Corpus:
    raw = path.read_bytes()
    data = json.loads(raw)
    propositions = {p.id for p in declaration.propositions}
    answers = set(declaration.answers)
    clashing = sorted(c.id for c in declaration.choices if c.id in RESERVED_KEYS)
    if clashing:
        raise InvalidInputError("A choice id is a key the corpus format reserves.",
                                     details={"choices": clashing, "reserved": sorted(RESERVED_KEYS)})

    def label(value: Any, allowed: set[str], where: str) -> Label:
        if not (isinstance(value, list) and len(value) == 2 and (value[0] is None or isinstance(value[0], str))
                and isinstance(value[1], str)):
            raise InvalidInputError("A corpus label is an answer and its justification, the answer null to abstain.",
                                    details={"at": where})
        answer, why = value
        if answer is not None and answer not in allowed:
            raise InvalidInputError("A corpus label names no option.", details={"at": where, "label": answer})
        if not why.strip():
            raise InvalidInputError("A corpus label has no justification.", details={"at": where})
        return Label(answer, why)

    declared_bindings = {(b.signal, b.control) for b in declaration.bindings}

    def bindings(entry: Any, where: str) -> dict[str, Label]:
        given = entry.get("bindings", {})
        if not isinstance(given, dict) or not all(isinstance(controls, dict) for controls in given.values()):
            raise InvalidInputError("A corpus text's bindings map each signal to its controls' labels.", details={"at": where})
        labelled = {(signal, control) for signal, controls in given.items() for control in controls}
        if labelled != declared_bindings:
            raise InvalidInputError(
                "A corpus text must label every binding and nothing else.",
                details={"at": where, "differs": sorted(" ".join(pair) for pair in labelled ^ declared_bindings)},
            )
        return {b.question_id: label(given[b.signal][b.control], set(b.options), f"{where}/{b.signal}/{b.control}")
                for b in declaration.bindings}

    texts = []
    for entry in data["texts"]:
        where = entry["id"]
        if set(entry["labels"]) != propositions:
            raise InvalidInputError(
                "A corpus text must label every reading proposition.",
                details={"at": where, "differs": sorted(set(entry["labels"]) ^ propositions)},
            )
        texts.append(
            CorpusText(
                id=entry["id"],
                text=entry["text"],
                labels={p: label(v, answers, f"{where}/{p}") for p, v in entry["labels"].items()},
                choices={
                    c.id: label(entry.get(c.id), {option for option, _ in c.options}, f"{where}/{c.id}")
                    for c in declaration.choices
                },
                bindings=bindings(entry, where),
            )
        )
    if len({t.id for t in texts}) != len(texts):
        raise InvalidInputError("Corpus text ids repeat.")
    return Corpus(
        version=int(data["version"]),
        labelled_by=str(data["labelled_by"]),
        digest=hashlib.sha256(raw).hexdigest(),
        texts=tuple(texts),
    )


# Wilson's score interval (Wilson 1927; Newcombe 1998, method 3), which stays inside [0, 1] and
# keeps its coverage near the nominal level at the small counts a corpus of this size gives, where
# the normal (Wald) interval does not.
# am[implements a-corpus-evaluation-1017@33cd3d]
def wilson(successes: int, trials: int, z: float = Z95) -> tuple[float, float] | None:
    if trials == 0:
        return None
    p = successes / trials
    denominator = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denominator
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))


# The multi-class Brier score (Brier 1950): squared distance between the answer distribution and
# the label's one-hot vector, 0 for a certain right answer and 2 for a certain wrong one.
# am[implements a-corpus-evaluation-1017@33cd3d]
def brier(probabilities: Mapping[str, float], label: str, options: Sequence[str]) -> float:
    return sum((probabilities.get(o, 0.0) - (1.0 if o == label else 0.0)) ** 2 for o in options)


# A percentile bootstrap over items, seeded, so a report regenerates byte for byte.
# Time: resamples x len(items) statistic evaluations.
# am[implements a-corpus-evaluation-1017@33cd3d]
def bootstrap(
    items: Sequence[Any], statistic: Callable[[Sequence[Any]], float], *, resamples: int = BOOTSTRAP_RESAMPLES
) -> tuple[float, float] | None:
    if not items:
        return None
    rng = random.Random(BOOTSTRAP_SEED)
    values = sorted(
        statistic([items[rng.randrange(len(items))] for _ in items]) for _ in range(resamples)
    )
    return (values[int(0.025 * (resamples - 1))], values[int(0.975 * (resamples - 1))])


# Four decimals keep a regenerated report byte-identical across platforms' last-bit differences.
# am[implements a-corpus-evaluation-1017@33cd3d]
def _rounded(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, (list, tuple)):
        return [_rounded(v) for v in value]
    if isinstance(value, dict):
        return {k: _rounded(v) for k, v in value.items()}
    return value


# One target's scores over its scored items, each (label, answer, probabilities).
# am[implements a-corpus-evaluation-1017@33cd3d]
def score(items: Sequence[tuple[str, str, Mapping[str, float]]], options: Sequence[str]) -> dict[str, Any]:
    confusion = {label: {answer: 0 for answer in options} for label in options}
    for label, answer, _ in items:
        confusion[label][answer] += 1
    correct = sum(1 for label, answer, _ in items if label == answer)
    recall = {}
    for label in options:
        total = sum(confusion[label].values())
        recall[label] = {
            "n": total,
            "recall": confusion[label][label] / total if total else None,
            "wilson95": wilson(confusion[label][label], total),
        }

    def mean_brier(sample: Sequence[Any]) -> float:
        return sum(brier(p, label, options) for label, _, p in sample) / len(sample)

    def gap(sample: Sequence[Any]) -> float:
        top = sum(max(p.values()) for _, _, p in sample) / len(sample)
        return top - sum(1 for label, answer, _ in sample if label == answer) / len(sample)

    return _rounded(
        {
            "n": len(items),
            "confusion": confusion,
            "accuracy": correct / len(items) if items else None,
            "accuracy_wilson95": wilson(correct, len(items)),
            "recall": recall,
            "brier": mean_brier(items) if items else None,
            "brier_bootstrap95": bootstrap(items, mean_brier),
            "calibration_gap": gap(items) if items else None,
            "calibration_gap_bootstrap95": bootstrap(items, gap),
        }
    )


# The scores need only Jev's settled answers, which a full read takes unchanged and then grounds with
# the cross-encoder, so settling alone scores identically while skipping the grounding that took
# about ten minutes of a run's eleven (c-native-test-grounding-dominates-1017). The report names the
# declaration by domain and digest, since that, with the model, fixes every question asked, and the
# settlement, the top probability under which a question is re-drawn and the draws then averaged,
# since that fixes which probabilities were scored. An evaluation runs outside any request, under
# the limits its caller gives, which bound every Jev request it makes.
# Time: one settle per corpus text, replayed from the answer cache when offline.
# am[implements a-corpus-evaluation-1017@33cd3d] am[implements a-dr-evaluation-generic-1018@120a4c]
# am[addresses i-corpus-report-settlement-provenance-1017@8c1d5e] am[implements a-dr-reader-budget-required-1018@0b0cce]
# am[implements a-dr-sr-tool-budgets-1018@e4d351] am[implements a-bnd-evaluation-1019@f82299]
# am[rests-on c-bnd-evaluation-asks-every-question-1019@f98330]
def evaluate(
    corpus: Corpus, declaration: ReadingDeclaration, jev: JevClient | None = None, *, budget: RunBudget
) -> dict[str, Any]:
    jev = jev or SemanticReader(declaration=declaration).jev
    questions = declaration.questions()
    settled = [(text, jev.settle(text.text, questions, budget=budget)) for text in corpus.texts]
    labelled = {p.id: (lambda text, p=p: text.labels[p.id]) for p in declaration.propositions}
    labelled.update({c.id: (lambda text, c=c: text.choices[c.id]) for c in declaration.choices})
    labelled.update({b.question_id: (lambda text, b=b: text.bindings[b.question_id]) for b in declaration.bindings})
    targets: dict[str, list[tuple[str, str, Mapping[str, float]]]] = {target: [] for target in labelled}
    abstained = {target: 0 for target in targets}
    for text, answers in settled:
        for target, label_of in labelled.items():
            label = label_of(text).answer
            if label is None:
                abstained[target] += 1
                continue
            got = answers[target].answer
            targets[target].append((label, got.decided(), dict(got.probabilities)))
    options = {p.id: list(declaration.answers) for p in declaration.propositions}
    options.update({c.id: [option for option, _ in c.options] for c in declaration.choices})
    options.update({b.question_id: list(b.options) for b in declaration.bindings})
    models = {settle.answer.model for _, answers in settled for settle in answers.values()}
    return {
        "corpus": {"version": corpus.version, "sha256": corpus.digest, "texts": len(corpus.texts)},
        "model": sorted(models),
        "declaration": {"domain": declaration.name, "digest": declaration.digest},
        "settlement": {"sure": SURE, "draws": DRAWS},
        "targets": {
            target: {**score(items, options[target]), "abstained": abstained[target]}
            for target, items in targets.items()
        },
    }


# am[implements a-corpus-evaluation-1017@33cd3d]
def _interval(pair: Any) -> str:
    return "n/a" if pair is None else f"{pair[0]:.2f} to {pair[1]:.2f}"


# A metric a target lacks, every one of its labels having abstained, is written n/a, as an absent
# interval is, and a present one in the given format.
# am[implements a-integrate-binding-empty-score-render-1019@aa4d95]
def _metric(value: Any, spec: str) -> str:
    return "n/a" if value is None else format(value, spec)


# am[implements a-corpus-evaluation-1017@33cd3d]
# am[implements a-integrate-binding-empty-score-render-1019@aa4d95]
def markdown(report: Mapping[str, Any]) -> str:
    """One row per target: its scored labels, accuracy, recall per answer, Brier score and gap."""

    lines = [
        f"Corpus version {report['corpus']['version']}, {report['corpus']['texts']} texts, "
        f"sha256 {report['corpus']['sha256'][:12]}; {report['declaration']['domain']} declaration "
        f"{report['declaration']['digest'][:12]}; model {', '.join(report['model'])}.",
        "",
        "| target | n | accuracy (95%) | recall by label | Brier (95%) | gap (95%) |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for target, s in report["targets"].items():
        recall = "; ".join(
            f"{label} {r['recall']:.2f} of {r['n']}" for label, r in s["recall"].items() if r["n"]
        )
        lines.append(
            f"| {target} | {s['n']} | {_metric(s['accuracy'], '.2f')} ({_interval(s['accuracy_wilson95'])}) | {recall} | "
            f"{_metric(s['brier'], '.3f')} ({_interval(s['brier_bootstrap95'])}) | "
            f"{_metric(s['calibration_gap'], '+.2f')} ({_interval(s['calibration_gap_bootstrap95'])}) |"
        )
    return "\n".join(lines) + "\n"


# The command reads the declaration it scores from the packaged incident domain, or from the domain
# file it is given, under its own limits, which also bound every Jev request.
# am[implements a-corpus-evaluation-1017@33cd3d] am[implements a-dr-sr-tool-budgets-1018@e4d351]
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m goal_chainer.semantic_evaluation")
    parser.add_argument("--corpus", type=Path, default=CORPUS_PATH)
    parser.add_argument("--domain-file", type=Path,
                        help="a domain file whose reading section the corpus is labelled for; "
                             "default the packaged incident domain")
    parser.add_argument("--json", type=Path, help="also write the report as JSON here")
    parser.add_argument("--inference-budget", type=int, required=True,
                        help="maximum engine inferences for the evaluation")
    parser.add_argument("--timeout-seconds", type=float, required=True,
                        help="wall-clock limit for the evaluation")
    args = parser.parse_args(argv)
    budget = RunBudget(inference_budget=args.inference_budget, timeout_seconds=args.timeout_seconds)
    if args.domain_file is None:
        declaration = default_reader(budget=budget).declaration
    else:
        declaration = load_domain(args.domain_file, budget=budget).readings
        if declaration is None:
            raise InvalidInputError("The domain file declares no reading section to evaluate.",
                                    details={"domain_file": str(args.domain_file)})
    report = evaluate(load_corpus(declaration, args.corpus), declaration, budget=budget)
    if args.json:
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sys.stdout.write(markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
