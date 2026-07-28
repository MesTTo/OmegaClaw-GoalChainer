# Native SNARS migration and rollback

## Behavior change

The primary decision path used to grade action belief through PeTTaChainer and
project its STV into an approximate Subjective Logic opinion. The scorer then
multiplied strength by confidence.

Native mode now:

1. parses request text into Mettabase SH trees,
2. ingests those trees through `sn ingest!`,
3. derives action beliefs through registered SNARS rules,
4. uses `opinion.expectation` once,
5. retains evidence counts, receipts, trust, proof stamps, and proof trees.

The legacy `snars_query.py` two-premise wrapper has been removed.

## Data compatibility

Persistent stores record the exact Mettabase commit. Opening a store against a
different commit fails before replay. Keep the old checkout available until a
planned migration has been tested against a copied database.

The current event schema is append-only version 1. There is no silent schema or
commit migration.

## Runtime rollback

Use explicit offline mode to return to the older deterministic extractor and
PeTTaChainer projection:

```bash
goalchainer demo --mode offline
goalchainer solve --mode offline
```

Offline responses say:

```json
{
  "mode": "offline",
  "native_snars_ran": false
}
```

Offline mode does not read or update the SNARS database. It is a runtime rollback,
not a conversion of native event data.

To roll the code back, revert the GoalChainer native integration commits and reset
the `external/mettabase` submodule to the prior pin. Do not open a newer event
store from the older code. Keep a copy until the rollback has been exercised.

## Failure behavior

Native dependency, parser, timeout, PeTTa, protocol, and persistence failures
return a stable error object and a nonzero CLI exit. They do not activate offline
mode. Select offline mode before the request when native execution is not wanted.
