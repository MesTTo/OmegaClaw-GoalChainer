"""Purpose: resolve a caller's path to a declaration file and read its text, refusing a path or file that cannot be read as UTF-8 text with the caller's own error, read a caller's input text from a file or from standard input's bytes as UTF-8 alike, whatever the process locale, and read declaration text as data forms: each top-level form's exact text with the atom pymetta parses from it, refusing a directive or any text outside a form.

The domain loader and every section reader take their forms from here, so a section reader never
imports the loader that calls it (c-rel-pj-loader-imports-section-readers-1018).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..runtime.budget import RunBudget
from ..runtime.engine import shared_evaluation
from ..sexpr.forms import MettaTextError, TopLevelForm, top_level_forms


# am[implements a-rel-nd-pymetta-atoms-1018@f047df]
class FormsUnreadable(ValueError):
    """Text that is not a sequence of data forms: `problem` says why, `index` is where in the text,
    and `form` is the text of the form at fault, empty when no one form is."""

    def __init__(self, problem: str, index: int, form: str = "") -> None:
        super().__init__(problem)
        self.problem, self.index, self.form = problem, index, form


# Every loader of a declaration file, the domain loader and the procedure library's among them,
# and input_text for the commands' JSON files resolve the caller's path and read its text here, so
# each way a path or file can fail to be text is the caller's own error in one wording and nothing
# escapes: a path that cannot be resolved, such as one holding a NUL byte (ValueError) or naming an
# unknown user's home (RuntimeError), and a file that is missing, a directory, unreadable or not UTF-8.
# am[implements a-integrate-domain-file-failures-1018@359226] am[implements a-rel-file-text-normalizes-1018@2afe58]
# am[related a-rel-cli-reader-unreadable-1018@cbbab6]
def file_text(path: str | Path, refuse: Callable[[str], Exception]) -> tuple[Path, str]:
    """The resolved path of `path`, a user's home expanded, and its UTF-8 text, read as
    Path.read_text reads it, or `refuse(message)` raised with the path and the cause."""

    try:
        source = Path(path).expanduser().resolve()
    except (ValueError, RuntimeError, OSError) as error:
        raise refuse(f"{str(path)!r}: cannot be read as UTF-8 text: it is no usable path ({error})") from None
    try:
        return source, source.read_text(encoding="utf-8")
    except FileNotFoundError:
        cause = "no such file"
    except IsADirectoryError:
        cause = "it is a directory"
    except UnicodeDecodeError as error:
        cause = f"{error.reason} at byte {error.start}"
    except OSError as error:
        cause = error.strerror or str(error)
    raise refuse(f"{source}: cannot be read as UTF-8 text: {cause}")


# A caller's input text from a file, by file_text, or for "-" from standard input, read as UTF-8
# whatever the process locale; the shared CLI's reader and the relevance commands' read through it.
# The process decodes sys.stdin's text by its locale: under LC_ALL=C, UTF-8 mode or a
# surrogateescape PYTHONIOENCODING a byte that is no UTF-8 becomes a lone surrogate, and under
# latin-1 another character. So standard input is read as bytes and decoded as UTF-8, as file_text
# decodes a file, and refused in file_text's words with standard input for the path. A standard
# input that is no byte stream, absent as when fd 0 is closed or replaced by text alone, is refused
# alike, and so is one whose byte stream cannot be read: a failing read raises OSError, and a closed
# stream's read ValueError, which is no OSError.
# Time and space: linear in the input's length.
# am[implements a-sc-shared-input-text-1018@3ec800] am[implements a-integrate-cli-stdin-repair-1018@a5f985]
# am[rests-on c-rel-stdin-decodes-by-locale-1018@0bfd89] am[implements a-integrate-input-text-closed-buffer-1018@7d108d]
# am[related a-sc-relevance-reads-input-text-1018@0fe1b8]
def input_text(source: str, refuse: Callable[[str], Exception]) -> str:
    """The UTF-8 text of the file `source`, or of standard input's bytes when `source` is "-", or
    `refuse(message)` raised naming the source and the cause."""

    if source != "-":
        return file_text(source, refuse)[1]
    stream = getattr(sys.stdin, "buffer", None)
    if stream is None:
        raise refuse("standard input: cannot be read as UTF-8 text: it is no byte stream")
    try:
        data = stream.read()
    except (OSError, ValueError) as error:
        cause = (error.strerror if isinstance(error, OSError) else None) or error
        raise refuse(f"standard input: cannot be read as UTF-8 text: {cause}") from None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise refuse(f"standard input: cannot be read as UTF-8 text: {error.reason} at byte {error.start}") from None


# goal_chainer.sexpr.forms scans the top-level forms, which tells a directive from data and keeps
# each form's exact text, and pymetta parses each form's atoms, so a string means what MeTTa reads
# it as, escapes included. A file read this way only declares, so a directive or any text outside
# every form is refused; an unclosed directive is reported at its !, the first text outside a form.
# Every caller maps FormsUnreadable to its own error (c-rel-agrees-dr-pymetta-atoms-1018).
# pymetta's parse runs on the engine, so the forms are parsed as shared engine work: beside running
# evaluations, once no load holds the engine alone. A request reads its domain, procedures and rows
# here, so none of them waits for another request's evaluation (a-integrate-admit-concurrency-1018),
# and a request's read waits for a load or a pool worker only until its budget's deadline; None is for
# a read outside any request. Literal vocabulary tables use the pure text reader instead.
# The budget has no default, so every
# caller says which it is (a-ev-rb-pipeline-budget-1018's rule: no unbudgeted default).
# Time: one scan of the text and one parse per form; the first parse in a process boots pymetta's
# runtime (c-rel-nd-parse-boots-runtime-1018).
# am[implements a-rel-nd-pymetta-atoms-1018@f047df] am[implements a-rt-metta-forms-shared-1017@db105c]
# am[rests-on c-rel-agrees-dr-pymetta-atoms-1018@552f9f] am[rests-on c-rel-nd-parse-boots-runtime-1018@bce664]
# am[implements a-rel-nd-replay-1018@32519e] am[rests-on c-rel-pj-loader-imports-section-readers-1018@4e1a4e]
# am[implements a-integrate-admit-concurrency-1018@b0a4e3] am[implements a-integrate-runtime-wait-deadline-1018@a74406]
# am[implements a-rt-parse-budget-required-1018@f73dbd]
# am[related a-integrate-vocab-pure-read-1019@745f98]
def parsed_forms(text: str, *, budget: RunBudget | None) -> list[tuple[TopLevelForm, Any]]:
    """Each top-level form of a declaration file's text, with the atom pymetta parses from it.

    `budget` is the request's: waiting for the engine ends at its deadline with its
    ReviewTimeout. None is for a read outside any request, which waits as long as it takes."""

    try:
        scanned = list(top_level_forms(text))
    except MettaTextError as error:
        if error.kind == "stray" or error.character == "!":
            raise FormsUnreadable(f"text outside a form: {error.character!r}", error.index) from error
        raise FormsUnreadable(error.kind, error.index) from error
    for form in scanned:
        if form.directive:
            raise FormsUnreadable("text outside a form: '!'", form.index, form.text)

    from metta import MettaError, parse  # noqa: PLC0415 (pymetta, the pinned engine, loads its runtime here)

    def read(engine: Any) -> list[tuple[TopLevelForm, Any]]:
        parsed = []
        for form in scanned:
            try:
                parsed.append((form, parse(form.text)))
            except MettaError as error:
                raise FormsUnreadable(f"pymetta cannot read the form: {error}", form.index, form.text) from error
        return parsed

    return shared_evaluation(read, budget=budget)
