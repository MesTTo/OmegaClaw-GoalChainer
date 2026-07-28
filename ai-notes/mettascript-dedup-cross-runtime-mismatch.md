# MeTTaScript deduplication cross-runtime mismatch

## Status

Resolved in the MeTTa policy and verified through both runtimes.

## What changed

MeTTaLSP's `deduplicate` command found repeated nested `tk-keep-error` calls in `integrations/threadkeeper/goalchainer_threadkeeper.metta`. The first refactor replaced those calls with:

```metta
(= (tk-keep-errors $errors)
   (filter-atom $errors $error (not (== $error none))))
```

Structural and semantic validation then supplied one expression containing the computed error values.

## Runtime difference

The native `metta` command continued to pass the focused MeTTa test file:

```text
npm run test:metta
13 focused assertions passed
```

MeTTaScript 2.7 did not preserve the same result when `tk-keep-errors` received the computed structural-error tuple. The Python-to-MeTTaScript boundary returned:

```metta
(Error NotReducible NoReturn)
```

The failure propagated through `gc-thread-compile`, so the versioned `goalchainer-thread-v1` record was absent. Nine Agent Orchestrator integration tests failed while compiling the shared valid thread fixture.

The mismatch is on the actual authority path:

```text
ThreadRuntime.compile
  -> MeTTaScriptRuntime.run_batch
  -> integrations/mettascript/runner.mjs
  -> @mettascript/node 2.7
  -> gc-thread-compile
```

The retained PeTTa compatibility runtime was not involved in this failure.

## Reproducer

With the valid thread fixture from `tests/thread_spec_fixture.py`, the MeTTaScript runner currently reports:

```text
(tk-structural-errors FACTS) => (Error NotReducible NoReturn)
(tk-semantic-errors FACTS)   => ()
(tk-validation-errors FACTS) => (Error NotReducible NoReturn)
(tk-thread-header FACTS)     => (thread incident-42 "Incident response" responder)
(tk-compilation FACTS)       => (Error NotReducible NoReturn)
```

The recursive error collector behaves correctly for literal values:

```text
(tk-keep-errors ())                              => ()
(tk-keep-errors (none))                          => ()
(tk-keep-errors (none missing-title))            => (missing-title)
(tk-keep-errors (missing-title none))            => (missing-title)
(tk-keep-errors (missing-title duplicate-title)) => (missing-title duplicate-title)
```

The remaining failure was isolated to the extracted `tk-role-rows` helper. Its
`filter-atom` iterator variable appeared only in the helper body. Native MeTTa
treated the variable as the filter binder, while MeTTaScript returned
`NoReturn` when the helper was called.

## Resolution

`tk-role-rows-walk` now traverses the role rows through explicit `car-atom`,
`cdr-atom`, and `cons-atom` rewrites. The iterator is represented by an
ordinary `let*` binding at each graph step. No free higher-order binder crosses
the rewrite boundary.

The repaired MeTTaScript path returns:

```text
(tk-role-rows FACTS control)         => ((thread-role incident-42 control local-control))
(tk-required-role-error ...)         => none
(tk-structural-errors FACTS)         => ()
(tk-validation-errors FACTS)         => ()
(tk-compilation FACTS)               => (compilation (valid True) ...)
```

Verification after the repair:

```text
npm run test:metta
13 focused assertions passed

pytest tests/test_thread_runtime.py tests/test_ao_ui.py
50 passed

pytest
334 passed, 3 skipped

metta-lsp deduplicate integrations/threadkeeper --min-atoms 12 --min-lines 2
6 intentional matches, 1.76% duplicate atoms, 1.25% duplicate lines
```

MeTTaLSP reports no diagnostics. The six practical-threshold matches are four
mirrored declarations needed by the inert documentation module, one repeated
`ui-task` graph shape, and one evaluator call shared by direct evaluation and
adjudication.

## Required acceptance checks

- `gc-thread-compile` returns one `goalchainer-thread-v1 compile` record through MeTTaScript 2.7.
- The same valid and invalid specifications return equivalent results through the native focused MeTTa tests.
- MeTTaLSP diagnostics remain empty after any intentional false-positive suppression.
- `tests/test_thread_runtime.py` passes through the Python-to-MeTTaScript boundary.
- `tests/test_ao_ui.py` passes through the same compilation path.
- The complete GoalChainer suite passes before the deduplication is accepted.

## Design constraint

The repair must remain MeTTa-native. Python may transport the source and parse the versioned result, but Python must not reconstruct structural validation or choose its errors.
