# Errors

`goal_chainer.errors.GoalChainerError` is the failure family the runtime, relevance, the MeTTa engines, SNARS
and the semantic reader share. Its `code` is stable, and the CLI and the OmegaClaw skill report it,
so match on the code rather than the message. `to_dict()` gives the JSON form, `{"code": ...,
"message": ..., "details": {...}}`, and `details` is read-only.

| Class | Code | Raised when |
|---|---|---|
| `GoalChainerError` | `goalchainer_error` | never directly; every failure below is one |
| `DependencyUnavailableError` | `dependency_unavailable` | a runtime, model or checkout GoalChainer needs is missing |
| `MissingAnswerError` | `missing_answer` | the semantic reader has no Jev answer for a text; `details["reason"]` says why |
| `InvalidInputError` | `invalid_input` | a caller's input fails validation, before any reasoning runs |
| `ProtocolError` | `protocol_error` | an engine answers in a shape its protocol does not allow |
| `MettaEngineError` | `engine_error` | the MeTTa engine refuses a program or fails while running it |
| `PersistenceError` | `persistence_error` | an event store, a SNARS session's or a motivation stream's, cannot be read or written, or refuses what it holds |
| `ModuleChanged` | `module_changed` | a module's bytes on disk differ from the bytes this process loaded from it |

A module's own failures subclass these and keep their own codes, such as `budget_exhausted` from
`goal_chainer.runtime.budget` or `deontic_output_error` from `goal_chainer.deontic_engine`.
`goal_chainer.relevance.errors.RelevanceError` also belongs to this family. It keeps its relevance
wire codes, including `invalid-packet`, `review-timeout` and `invalid-motivation`. The request and
motivation commands and the OmegaClaw skill report these failures as JSON with exit status 1.

Public JSON inputs require unique field names in every object and finite floating-point numbers.
Repeated names, including an escaped spelling of the same name, are refused before dispatch.
`NaN`, `Infinity` and decimal exponents that overflow the float range are refused too.
The command keeps its input error code, such as `invalid_input` or `invalid-packet`.

The relevance command reports an invalid or unreadable motivation selection as `invalid-motivation`.
A motivation read stopped by its budget uses `review-timeout` or `review-budget-exceeded`, just as
the review itself does. With `--json`, these are JSON errors; otherwise they appear on standard error.
The generic request, motivation and skill commands retain their shared error codes.

These boundaries raise exceptions outside the family, each documented where it is defined:

- `goal_chainer.domains.model.DomainError`, a `ValueError`: a domain file that cannot be read as a decision
  problem
- `goal_chainer.sexpr.forms.MettaTextError`, a `ValueError`: text a reader cannot split into forms
- `goal_chainer.domains.forms.FormsUnreadable`, a `ValueError`: a declaration file's text that is not
  a sequence of data forms
- `goal_chainer.semantic_artifacts.SleepError`, a `ValueError`: an invalid review, an incomplete
  artifact, a stale evaluation or a refused admission
- `goal_chainer.semantic_capture.UsageError`: a capture command that cannot run as asked

## Migration

These classes lived in `goal_chainer.snars_models` under SNARS names, and the budget failures and
`ModuleChanged` in `goal_chainer.petta_runtime`. Two codes changed with the move: a consumer
matching `petta_execution_error` matches `engine_error` instead, and the base class's
`snars_error`, which nothing raised, is now `goalchainer_error`.

```python
# Before
from goal_chainer.snars_models import SnarsInvalidInputError, SnarsPettaExecutionError

# After
from goal_chainer.errors import InvalidInputError, MettaEngineError
```

| Before | After | Code |
|---|---|---|
| `SnarsError` | `GoalChainerError` | `snars_error` became `goalchainer_error` |
| `SnarsDependencyUnavailableError` | `DependencyUnavailableError` | unchanged |
| `SnarsMissingAnswerError` | `MissingAnswerError` | unchanged |
| `SnarsInvalidInputError` | `InvalidInputError` | unchanged |
| `SnarsProtocolError` | `ProtocolError` | unchanged |
| `SnarsPettaExecutionError` | `MettaEngineError` | `petta_execution_error` became `engine_error` |
| `SnarsPersistenceError` | `PersistenceError` | unchanged |
| `SnarsTimeoutError` | removed with the PeTTa runner, its only raiser | |
| `SnarsUnsupportedCapabilityError` | removed; nothing raised it | |
| `goal_chainer.petta_runtime.ModuleChanged` | `goal_chainer.errors.ModuleChanged` | unchanged |
| `goal_chainer.petta_runtime.BudgetExhausted` | `goal_chainer.runtime.budget.BudgetExhausted` | unchanged |
| `goal_chainer.petta_runtime.InferenceBudgetExceeded` | `goal_chainer.runtime.budget.InferenceBudgetExceeded` | unchanged |
| `goal_chainer.petta_runtime.ReviewTimeout` | `goal_chainer.runtime.budget.ReviewTimeout` | unchanged |
