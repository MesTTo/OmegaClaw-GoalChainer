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
