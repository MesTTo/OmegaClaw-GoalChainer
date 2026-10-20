% Purpose: translate held MeTTa expressions into s(CASP) clauses and queries.
% The sCASP clauses behind the (sn guard...) heads of snars-guard.metta,
% which imports them with import_prolog_functions_from_file the way kernel.metta imports
% kernel.pl. The MeTTa-visible functions return their last argument.
%
% It was Prolog text that snars-guard.metta loaded from a string through translatePredicate's
% load_files; on pymetta that door loaded nothing, so sn_guard_assert was undefined, while the
% same text loaded as a file defines all three. A file keeps the guard's own file id, which is
% why the text was not given to injectPrologCode: that loads as file `user`, and a second call
% would reconsult and wipe the first program.
%
% sCASP is the copy that ships beside this library, in ../scasp/, loaded by a path relative to this
% file, so the guard needs no SWI-Prolog pack and every engine runs the same solver.
% am[implements a-rt-scasp-vendor-1017@5bec02]
:- use_module('../scasp/prolog/scasp', [scasp/2, scasp_assert/1]).

% am[implements a-integrate-guard-metta-build-1019@e688cb]
sn_guard_assert(Expression, true) :-
    sn_guard_expression(Expression, C),
    scasp_assert(C).

sn_guard_fact2(P, X, Y, true) :-
    G =.. [P, X, Y],
    scasp_assert(G).

% A witness establishes possibility. Solver errors must remain errors.
% am[implements a-integrate-guard-metta-build-1019@e688cb]
sn_guard_check(Expression, Result) :-
    sn_guard_expression(Expression, Goal),
    copy_term(Goal, Query),
    (   scasp(Query, [model(Model)])
    ->  term_string(Model, Result)
    ;   Result = "no"
    ).

% Time and space: O(n), n = the number of nodes in the expression.
% pymetta gives Atom arguments as nested lists sharing their Prolog variables.
% am[implements a-integrate-guard-metta-build-1019@e688cb]
sn_guard_expression(Expression, Term) :-
    (   nonvar(Expression), Expression = [Name|Arguments], atom(Name), is_list(Arguments)
    ->  maplist(sn_guard_argument, Arguments, Converted),
        Term =.. [Name|Converted]
    ;   throw(error(type_error(guard_expression, Expression), sn_guard_expression/2))
    ).

% am[implements a-integrate-guard-metta-build-1019@e688cb]
sn_guard_argument(Value, Term) :-
    (   var(Value)
    ->  Term = Value
    ;   is_list(Value)
    ->  sn_guard_expression(Value, Term)
    ;   atomic(Value)
    ->  Term = Value
    ;   throw(error(type_error(guard_argument, Value), sn_guard_argument/2))
    ).
