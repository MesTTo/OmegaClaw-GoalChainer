% SNARS v0 evidence kernel: the mutable region behind unchanged (sn ...) heads.
% Evidence cells, the logical tick, activation cells, and the trust ledger are
% dynamic predicates guarded by the sn-commit mutex. The Rust kernel later
% replaces this file, not its callers.
%
% Loaded by snars/kernel.metta via import_prolog_functions_from_file; the
% MeTTa-visible functions return their last argument.

:- dynamic sn_ev/4.
:- dynamic sn_sup/2.

% Fuse one discounted observation into a statement's evidence cell. The pre-fuse
% projection P(x)=(R0+2A)/(R0+S0+2) IS the step-5 prediction (the hole eval);
% KL(Bernoulli(Ppost) || Bernoulli(Ppre)) is the surprise = curriculum weight,
% computed in place on the hot path and stored per sid (a mutable number, never
% a space fact -- Mapping 3.0c). No extra janus round-trip.
sn_ev_add(Sid, R, S, A, P, Sid) :-
    with_mutex('sn-commit',
               (   ( retract(sn_ev(Sid, R0, S0, _)) -> true ; ( R0 = 0.0, S0 = 0.0 ) ),
                   R1 is R0 + P*R,
                   S1 is S0 + P*S,
                   assertz(sn_ev(Sid, R1, S1, A)),
                   % E1: exact Bayesian surprise = KL(Beta_post || Beta_pre), the
                   % cell's Beta posteriors before/after this observation (J 3.7:
                   % alpha=r+aW, beta=s+(1-a)W, W=2). Supersedes the Bernoulli-
                   % projection KL (which collapsed the Beta to its mean P and so
                   % under-counted movement that changes confidence at fixed P).
                   % A is clamped off {0,1} (the aclamp doctrine) so a dogmatic
                   % base rate -- e.g. a goal cell at desire 1.0 -- cannot push a
                   % Beta parameter to 0 (lgamma(0)/digamma(0) = float overflow).
                   Ac is max(0.001, min(0.999, A)),
                   APre is R0 + 2*Ac, BPre is S0 + 2*(1-Ac),
                   APost is R1 + 2*Ac, BPost is S1 + 2*(1-Ac),
                   sn_kl_beta(APost, BPost, APre, BPre, KL),
                   retractall(sn_sup(Sid, _)),
                   assertz(sn_sup(Sid, KL))
               )).

% digamma psi(x) (no SWI builtin): recurrence psi(x)=psi(x+1)-1/x up to x>=6,
% then the standard asymptotic series. Accurate to ~1e-8 over the cell range.
sn_digamma(X, P) :-
    ( X < 6.0
    -> X1 is X + 1.0, sn_digamma(X1, P1), P is P1 - 1.0/X
    ;  X2 is X*X, X4 is X2*X2, X6 is X4*X2,
       P is log(X) - 0.5/X - 1.0/(12.0*X2) + 1.0/(120.0*X4) - 1.0/(252.0*X6)
    ).

% KL(Beta(A1,B1) || Beta(A2,B2)) -- P=posterior(A1,B1), Q=prior(A2,B2).
% = ln[B(A2,B2)/B(A1,B1)] + (A1-A2)psi(A1) + (B1-B2)psi(B1) + (A2-A1+B2-B1)psi(A1+B1)
% with ln B(a,b) = lgamma(a)+lgamma(b)-lgamma(a+b). Exact Beta-Beta KL.
sn_kl_beta(A1, B1, A2, B2, KL) :-
    LnB is (lgamma(A2)+lgamma(B2)-lgamma(A2+B2)) - (lgamma(A1)+lgamma(B1)-lgamma(A1+B1)),
    sn_digamma(A1, PsiA1), sn_digamma(B1, PsiB1),
    S1 is A1 + B1, sn_digamma(S1, PsiS1),
    KL is LnB + (A1-A2)*PsiA1 + (B1-B2)*PsiB1 + (A2-A1+B2-B1)*PsiS1.

% Surprise reader; an unseen sid has never been fused, so it reads zero.
sn_surprise(Sid, Sup) :- ( sn_sup(Sid, Sup) -> true ; Sup = 0.0 ).

% ---- E2: per-(sid, source) contribution ledger (SLN 9.2 substrate) ----
% Written alongside every fuse so re-assertion can later remove exactly one
% source's evidence (J Def 13.1: unfusion in evidence space is subtraction).
:- dynamic sn_src/4.

sn_ev_add_src(Sid, Sigma, R, S, A, P, Sid) :-
    with_mutex('sn-commit',
               (   sn_ev_add(Sid, R, S, A, P, Sid),
                   ( retract(sn_src(Sid, Sigma, Rc0, Sc0)) -> true ; ( Rc0 = 0.0, Sc0 = 0.0 ) ),
                   Rc is Rc0 + P*R,
                   Sc is Sc0 + P*S,
                   assertz(sn_src(Sid, Sigma, Rc, Sc))
               )).

% SLN 9.2 re-assertion = unfuse + average + refuse, textbook-exact: unfuse
% sigma's prior contribution (J Def 13.1 -- evidence subtraction), average it
% with the repeated unit (J Def 12.7 via Theorem 12.3 -- evidence-parameter
% averaging (r_old+r_new)/2), re-fuse (addition). Net cell delta =
% (u_old+u_new)/2 - u_old, on sigma's contribution only; idempotent on
% identical repeats, other sources untouched.
sn_ev_reassert(Sid, Sigma, R, S, A, P, Sid) :-
    with_mutex('sn-commit',
               (   ( sn_src(Sid, Sigma, Rc0, Sc0) -> true ; ( Rc0 = 0.0, Sc0 = 0.0 ) ),
                   Ra is (Rc0 + P*R)/2,
                   Sa is (Sc0 + P*S)/2,
                   DR is Ra - Rc0,
                   DS is Sa - Sc0,
                   ( retract(sn_ev(Sid, R0, S0, A0)) -> true ; ( R0 = 0.0, S0 = 0.0, A0 = A ) ),
                   R1 is max(0.0, R0 + DR),
                   S1 is max(0.0, S0 + DS),
                   assertz(sn_ev(Sid, R1, S1, A0)),
                   retractall(sn_src(Sid, Sigma, _, _)),
                   assertz(sn_src(Sid, Sigma, Ra, Sa))
               )).

% ---- E2: P^2 streaming quantile estimator (SLN 9.7 governance) ----
% The P-square algorithm (Jain & Chlamtac 1985): track the P-quantile in O(1)
% memory with five markers, no stored sample buffer. Supersedes the cap-256
% sorted list. State: init(SortedBuf) for the first <5 samples, then
% run(Heights, Positions, DesiredPositions, Increments) (each a 5-list).
:- dynamic sn_p2/3.

% add observation V to Key's estimator for the P-quantile (P fixed per key).
sn_q_add(Key, P, V, V) :-
    with_mutex('sn-commit',
               (   ( retract(sn_p2(Key, _, St0)) -> true ; St0 = init([]) ),
                   sn_p2_add(St0, P, V, St1),
                   assertz(sn_p2(Key, P, St1))
               )).

% read Key's current P-quantile estimate: q3 once running; empirical quantile of
% the <5 buffered samples otherwise; 1e9 when empty (the conservative "no data,
% don't gate" sentinel, matching the old buffer's behaviour).
sn_q_at(Key, X) :-
    ( sn_p2(Key, P, St) -> sn_p2_q(St, P, X) ; X = 1.0e9 ).

% init phase: buffer until five samples, then build the markers.
sn_p2_add(init(L0), P, V, St) :-
    msort([V|L0], L),
    (   L = [A,B,C,D,E]
    ->  NP2 is 1 + 2*P, NP3 is 1 + 4*P, NP4 is 3 + 2*P,
        DN2 is P/2, DN3 is P, DN4 is (1.0+P)/2,
        St = run([A,B,C,D,E], [1,2,3,4,5], [1,NP2,NP3,NP4,5], [0,DN2,DN3,DN4,1])
    ;   St = init(L)
    ).
% running phase: one P^2 update.
sn_p2_add(run(Qs, Ns, NPs, DNs), _, V, run(Qs2, Ns2, NPs2, DNs)) :-
    sn_p2_cell(Qs, V, K, Qs1),
    sn_p2_incn(Ns, K, Ns1),
    sn_p2_addv(NPs, DNs, NPs2),
    sn_p2_adjust(Qs1, Ns1, NPs2, Qs2, Ns2).

sn_p2_q(init(L), P, X) :-
    ( L = [] -> X = 1.0e9 ; length(L,N), I is max(1,min(N,round(P*N))), nth1(I,L,X) ).
sn_p2_q(run(Qs, _, _, _), _, X) :- nth1(3, Qs, X).

% locate the cell k with q_k =< V < q_{k+1}; extend the min/max marker if outside.
sn_p2_cell([Q1,Q2,Q3,Q4,Q5], V, K, [R1,Q2,Q3,Q4,R5]) :-
    ( V < Q1   -> K = 1, R1 = V,  R5 = Q5
    ; V < Q2   -> K = 1, R1 = Q1, R5 = Q5
    ; V < Q3   -> K = 2, R1 = Q1, R5 = Q5
    ; V < Q4   -> K = 3, R1 = Q1, R5 = Q5
    ; V =< Q5  -> K = 4, R1 = Q1, R5 = Q5
    ;             K = 4, R1 = Q1, R5 = V ).

% positions: n_i += 1 for i > k (n1 fixed at 1, n5 = running count).
sn_p2_incn([N1,N2,N3,N4,N5], K, [N1,O2,O3,O4,O5]) :-
    ( K < 2 -> O2 is N2+1 ; O2 = N2 ),
    ( K < 3 -> O3 is N3+1 ; O3 = N3 ),
    ( K < 4 -> O4 is N4+1 ; O4 = N4 ),
    O5 is N5+1.

sn_p2_addv([A1,A2,A3,A4,A5], [D1,D2,D3,D4,D5], [O1,O2,O3,O4,O5]) :-
    O1 is A1+D1, O2 is A2+D2, O3 is A3+D3, O4 is A4+D4, O5 is A5+D5.

% adjust the three interior markers (2,3,4), threading the updated left neighbour.
sn_p2_adjust([Q1,Q2,Q3,Q4,Q5], [N1,N2,N3,N4,N5], [_,NP2,NP3,NP4,_], [Q1,Q2b,Q3b,Q4b,Q5], [N1,N2b,N3b,N4b,N5]) :-
    sn_p2_one(Q1, Q2, Q3, N1, N2, N3, NP2, Q2b, N2b),
    sn_p2_one(Q2b, Q3, Q4, N2b, N3, N4, NP3, Q3b, N3b),
    sn_p2_one(Q3b, Q4, Q5, N3b, N4, N5, NP4, Q4b, N4b).

% one marker: if its desired position is >=1 off (and a real gap exists), shift
% it by +/-1 via the parabolic (P^2) prediction, falling back to linear if the
% parabola breaks marker ordering.
sn_p2_one(Qm, Qi, Qp, Nm, Ni, Np, NPi, Qo, No) :-
    Diff is NPi - Ni,
    (   ( Diff >= 1, Np - Ni > 1 )
    ->  sn_p2_move(Qm, Qi, Qp, Nm, Ni, Np, 1, Qo, No)
    ;   ( Diff =< -1, Nm - Ni < -1 )
    ->  sn_p2_move(Qm, Qi, Qp, Nm, Ni, Np, -1, Qo, No)
    ;   ( Qo = Qi, No = Ni ) ).

sn_p2_move(Qm, Qi, Qp, Nm, Ni, Np, D, Qo, No) :-
    No is Ni + D,
    QPar is Qi + (D / (Np - Nm)) *
            ( (Ni - Nm + D) * (Qp - Qi) / (Np - Ni)
            + (Np - Ni - D) * (Qi - Qm) / (Ni - Nm) ),
    (   ( Qm < QPar, QPar < Qp )
    ->  Qo = QPar
    ;   ( D =:= 1 -> Qd = Qp, Nd = Np ; Qd = Qm, Nd = Nm ),
        Qo is Qi + D * (Qd - Qi) / (Nd - Ni) ).

% Read a cell; unseen cells are vacuous at the 0.5 prior.
sn_ev_view(Sid, ['Ev', R, S, A]) :-
    with_mutex('sn-commit',
               ( sn_ev(Sid, R, S, A) -> true ; ( R = 0.0, S = 0.0, A = 0.5 ) )).

sn_clock(T) :-
    statistics(walltime, [T|_]).

sn_ev_count(N) :-
    (   predicate_property(sn_ev(_, _, _, _), number_of_clauses(N))
    ->  true
    ;   N = 0
    ).

% Logical tick for activation decay (ALANN-style, no wall clock).
:- dynamic sn_tick_v/1.
sn_tick_v(0).

sn_tick(T) :-
    with_mutex('sn-commit',
               ( retract(sn_tick_v(T0)), T is T0 + 1, assertz(sn_tick_v(T)) )).

sn_tick_now(T) :-
    sn_tick_v(T).

% Control cells: the forward chainer's frontier, working set and residual
% queue, one value per name (derive.metta). A dynamic predicate like every
% store above, so a call run under snapshot/1 discards its writes with the
% evidence cells, where an engine state cell could not be written at all.
:- dynamic sn_cell_v/2.

sn_cell_put(Name, Value, true) :-
    with_mutex('sn-commit',
               ( retractall(sn_cell_v(Name, _)), assertz(sn_cell_v(Name, Value)) )).

sn_cell_get(Name, Value) :-
    sn_cell_v(Name, Value).

% Activation cells: estimate A + residual R, lazily decayed by Lambda^(Now-T0).
:- dynamic sn_act_c/4.

sn_act_fold(Key, Lambda, Now, A, R) :-
    (   retract(sn_act_c(Key, A0, R0, T0))
    ->  F is Lambda**(Now - T0),
        A is A0*F,
        R is R0*F
    ;   ( A = 0.0, R = 0.0 )
    ).

sn_act_res(Key, W, Lambda, Now, R1) :-
    with_mutex('sn-commit',
               (   sn_act_fold(Key, Lambda, Now, A, R),
                   R1 is R + W,
                   assertz(sn_act_c(Key, A, R1, Now))
               )).

sn_act_push(Key, Alpha, Lambda, Now, Spread) :-
    with_mutex('sn-commit',
               (   sn_act_fold(Key, Lambda, Now, A, R),
                   A1 is A + Alpha*R,
                   Spread is (1.0 - Alpha)*R,
                   assertz(sn_act_c(Key, A1, 0.0, Now))
               )).

sn_act_val(Key, Lambda, Now, A) :-
    (   sn_act_c(Key, A0, _, T0)
    ->  A is A0*Lambda**(Now - T0)
    ;   A = 0.0
    ).

% Trust ledger: rule/source reliability as Beta evidence (Josang & Ismail 2002).
:- dynamic sn_tr/4.

sn_tr_add(K1, K2, Q, NQ, K2) :-
    with_mutex('sn-commit',
               (   ( retract(sn_tr(K1, K2, R0, S0)) -> true ; ( R0 = 0.0, S0 = 0.0 ) ),
                   R1 is R0 + Q,
                   S1 is S0 + NQ,
                   assertz(sn_tr(K1, K2, R1, S1))
               )).

sn_tr_p(K1, K2, A, P) :-
    (   sn_tr(K1, K2, R, S)
    ->  P is (R + 2*A)/(R + S + 2)
    ;   P = A
    ).

% K2: the raw (r,s) of a trust cell as a 2-list, for Thompson sampling the
% rule-reliability Beta instead of reading only its mean (sn_tr_p).
sn_tr_rs(K1, K2, [R, S]) :-
    ( sn_tr(K1, K2, R, S) -> true ; ( R = 0.0, S = 0.0 ) ).

sn_tr_u(K1, K2, U) :-
    (   sn_tr(K1, K2, R, S)
    ->  U is 2/(R + S + 2)
    ;   U = 1.0
    ).

sn_tr_rho(K1, K2, A, Rho) :-
    sn_tr_p(K1, K2, A, P),
    Rho is P/A.

% Sid memo: content-addressed ids are pure functions of ground canonical
% trees, so cache them behind the ONE Python hasher (term_hash keeps lookup
% indexed; the tree is re-verified on hit against hash collisions).
:- dynamic sn_sid_c/3.

sn_sid_get(Tree, R) :-
    term_hash(Tree, H),
    (   sn_sid_c(H, Tree, Sid)
    ->  R = ['SidHit', Sid]
    ;   R = 'SidMiss'
    ).

sn_sid_put(Tree, Sid, Sid) :-
    term_hash(Tree, H),
    with_mutex('sn-commit',
               ( sn_sid_c(H, Tree, Sid) -> true ; assertz(sn_sid_c(H, Tree, Sid)) )).

:- ( nb_current(sn_frozen, _) -> true ; nb_setval(sn_frozen, 0) ).

sn_ev_del(Sid, Sid) :-
    with_mutex('sn-commit',
               ( retractall(sn_ev(Sid, _, _, _)),
                 retractall(sn_src(Sid, _, _, _)) )).

% membership/unifiability check for view clauses (M3): PeTTa's 4-arg
% atom-form unify does not reduce (probe 2026-06-12) -- one Prolog line is
% the sanctioned escape. Succeeds with 'True' iff A and B unify (no bindings
% leak: double negation). Returns lowercase true/false: PeTTa maps MeTTa
% True <-> Prolog true (parser.pl) -- capitalized 'True' would print right
% but never compare/branch (probe 2026-06-13).
sn_unifiable(A, B, R) :- ( \+ A \= B -> R = true ; R = false ).

% canonical order for symmetric-shaped conclusions (standard order of terms;
% R0). Lowercase true/false: PeTTa booleans (probe 2026-06-13).
sn_key_le(A, B, R) :- ( A @=< B -> R = true ; R = false ).

% ---- K1: transactional counterfactuals (what-if!) ----
% The chess-game envision/reset pattern (move_piece/reset_pieces over ~1500
% lines, one missed reversal corrupts state) collapsed to ONE safe kernel op.
% Inside SWI snapshot/1: assert the hypothesis with 'believe!'/3 (interns it,
% adds its cell) into the LIVE world, then prove the query against the augmented
% world with the pure backward chainer sn(prove,...), collecting every proof
% triple. snapshot/1 then rolls back ALL dynamic predicates -- evidence cells,
% the space's (sn stmt ...) / index facts, the sid memo -- in one scope, so the
% KB is bit-identical afterward; only the Results binding survives the rollback
% (snapshot/1 keeps bindings, discards the trail of dynamic changes).
%
% Why this clears the prior K1 blocker: the deduce-and-graft sweep interned new
% conclusions inside the sandbox, and each intern is a janus py-call (sid hash)
% that re-enters Prolog under the snapshot transaction -- the re-entrancy that
% failed. The consolidated chainer is PURE (reads cells via sn_ev_view, never
% grafts), so it interns nothing during the sweep; the only py-call is the ONE
% hypothesis intern, and direct (non-deductive) counterfactuals were already
% verified to work in snapshot. catch/3 keeps a malformed hypothesis from
% aborting the whole op (fail-open: the query then simply proves over the
% unchanged world). believe! and (sn prove ...) are MeTTa functions defined by the
% modules loaded after this file, so they are called through the engine's eval/2,
% which runs a function in the module its space compiled it into: pymetta compiles
% each space's equations into that space's own module, where a direct call to
% sn/4 from this file raised "Unknown procedure: sn/4", and PeTTa's eval/2 calls
% the same predicates the direct call did.
sn_what_if(HypTree, HypOpts, QueryGoal, Budget, Results) :-
    snapshot(( catch(eval(['believe!', HypTree, HypOpts], _), _, true),
               findall(R, eval([sn, prove, QueryGoal, Budget], R), Results) )).
