# SNARS persistence and privacy

Persistence is opt-in. A command without `--database` uses SQLite in memory and
discards the event stream when the session closes.

## Stored data

A persistent event can contain:

- parser-generated HyperBase facts
- the original request
- evidence source names and trust
- authored statements
- goals and their metadata
- temporal ticks
- observed outcomes

Requests can contain personal or operational data. Choose a database path with the
same care as an incident log.

## File controls

GoalChainer rejects symbolic-link database paths. It creates the database with
mode `0600`, enables SQLite `secure_delete`, foreign keys, WAL, and a five-second
busy timeout. Each row includes a content hash, schema version, and exact
Mettabase commit.

The WAL and shared-memory files live next to the database while it is open. Protect
the containing directory as well as the main file.

## Redaction

The Python API accepts a redactor when a persistent session is created:

```python
from goal_chainer.snars_reasoner import SnarsSession

def redact(kind, payload):
    if kind != "ingest_text":
        return payload
    return {
        **payload,
        "text": "[redacted]",
        "facts": redact_hyperbase_facts(payload["facts"]),
    }

session = SnarsSession.persistent(runtime, "state.sqlite3", redactor=redact)
```

The redactor receives the whole event before replay or persistence. Redacting only
the `text` field is insufficient because parser facts can retain the same content.
GoalChainer executes and appends the prepared redacted payload, so private and
replayed state cannot diverge.

## Retention and deletion

Set a retention period based on the incident-data policy. Close the session before
deleting its files. Remove the database, `-wal`, and `-shm` files together.
Filesystem deletion is the supported full-stream deletion operation because the
event table is append-only.

Counterfactual hypotheses are never written. GoalChainer verifies both the SNARS
state tree and persistent event digest after every counterfactual.
