% GoalChainer: deontic status -> directive task state.
% A Prolog relation loaded into PeTTa and called as a MeTTa function
% ((gc_task_state obligated) -> ready). Preferred over asserting the rows
% from Python: the mapping lives as data in a real Prolog file.
gc_task_state(forbidden,   blocked).
gc_task_state(obligated,   ready).
gc_task_state(permitted,   backlog).
gc_task_state(unregulated, backlog).
