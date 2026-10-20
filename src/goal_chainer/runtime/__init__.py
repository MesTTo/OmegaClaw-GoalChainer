"""Purpose: GoalChainer's one pymetta execution boundary. engine hosts the process's engine and the
environment its children start with; budget holds a caller's bounds and runs MeTTa under them;
modules binds libraries and imports MeTTa modules once per process and space; checkouts resolves
the native dependencies GoalChainer runs on; evaluator runs one-answer policies over declared
module groups and reads the engine's answers as Python; numbers reads a caller's number as the finite
float it stands for, for the validators of budgets and SNARS values. Nothing here imports GoalChainer's models,
readers, SNARS or domains, and each name is imported from the module defining it, so it has one
import path."""
