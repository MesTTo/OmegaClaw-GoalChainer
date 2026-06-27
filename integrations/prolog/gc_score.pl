% GoalChainer: the decision's combined score, as a Prolog relation loaded into
% PeTTa and called as a MeTTa function. The motivation path (used whenever the
% MetaMo consensus is available) is computed natively here rather than in Python:
%   forbidden/conflict -> -1.0 (the deontic hard gate)
%   otherwise          -> 0.54*Motivation + 0.38*(Strength*Confidence) + bonus
% where bonus = 0.1 for an obligated action, else 0.0.
gc_score(forbidden, _, _, _, R) :- !, R = -1.0.
gc_score(conflict,  _, _, _, R) :- !, R = -1.0.
gc_score(Deontic, Strength, Confidence, Motivation, Score) :-
    ( Deontic == obligated -> Bonus = 0.1 ; Bonus = 0.0 ),
    Evidence is Strength * Confidence,
    Score is 0.54 * Motivation + 0.38 * Evidence + Bonus.

% Decision status from the deontic verdict, the score, and whether any required
% goal is missing (HasMissing is 1 or 0). Same thresholds as the Python.
gc_decision_status(forbidden, _, _, blocked) :- !.
gc_decision_status(conflict,  _, _, blocked) :- !.
gc_decision_status(_, Score, 0, recommended) :- Score >= 0.72, !.
gc_decision_status(_, Score, _, candidate) :- Score >= 0.5, !.
gc_decision_status(_, _, _, weak).

% The whole final verdict in one call: returns the list (Score Status).
gc_decide(Deontic, Strength, Confidence, Motivation, HasMissing, [Score, Status]) :-
    gc_score(Deontic, Strength, Confidence, Motivation, Score),
    gc_decision_status(Deontic, Score, HasMissing, Status).
