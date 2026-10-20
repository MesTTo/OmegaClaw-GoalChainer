"""Purpose: GoalChainer's MeTTa text layer, below every engine, reader and domain: syntax holds
Mettabase's S-expression atoms with parse and emit, codec builds checked atoms over it, protocol
reads versioned protocol records and forms scans program text into top-level forms. Importing the
package pins syntax, so whichever module imports it first, its compile reads one copy of the file,
the copy SNARS's world identity digests, since SNARS's py-calls run it."""

from pathlib import Path

from .. import pinned

# am[implements a-rt-rb-codec-1018@e3e552] am[rests-on c-rt-codec-decision-kept-1018@5b65d4]
pinned.pin({f"{__name__}.syntax": Path(__file__).resolve().parent / "syntax.py"})
