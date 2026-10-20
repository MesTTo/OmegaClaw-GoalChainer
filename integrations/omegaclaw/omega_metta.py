"""Purpose: answer what the Codex drivers offer their agent and what its reply does the way upstream
Omega's loop does, in process on pymetta. A registry session holds Omega's skill registry with the
installed GoalChainer plugin loaded by its own loadOmegaPlugin, and prints the plugin's skills, the
tools Omega offers an LLM for named skills, the skill rules and prompt extensions of Omega's context,
or the loop's result for one plugin call, its arguments a JSON list on standard input. A reader
session holds Omega's provider module and prints the calls Omega reads in a reply on standard input.
The reply schema the offered tools give Codex needs no session.

Run it with the interpreter the plugin's install recorded, for example
`printf '%s' '["{...}"]' | python omega_metta.py --omega external/OmegaClaw-Core eval goalchainer-request`."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

# Omega's Python modules import one another by name (providers.py runs `import config`), and its
# PeTTa runtime imports each under that name, so each is imported here under its own name too, with
# its directory after the installed packages; each MeTTa module comes through the Omega alias. The
# registry is what the plugin suite loads before the plugin: the skill registry, its logging, and
# helper.normalize_string, which the loop's evaluation calls, with Omega's plugin listing. The reader
# is what reading a reply needs: the provider module and the utils that import sread. Neither runs
# initLogger, which would send every INFO line to standard error.
# am[implements a-op-session-self-1018@bd8329] am[rests-on c-rt-oc-py-module-identity-1018@5e410a]
# am[rests-on c-oc-loader-silent-on-pymetta-1018@f7c367]
REGISTRY = ("src/utils.py", "src/utils.metta", "src/helper.py", "src/config.py", "src/config.metta",
            "src/logger.py", "src/log.metta", "src/providers.py", "src/skills.metta", "src/plugin.py")
READER = ("src/utils.py", "src/utils.metta", "src/config.py", "src/providers.py")
# The plugin's name in config/plugins.yaml, the record scripts/install_plugin.py writes.
PLUGIN = "goalchainer"
# The name this host registers Codex under in Omega's provider registry.
PROVIDER = "Codex"
# eval's exit status when the loop's result is an alert, so a driver can tell a call that was refused
# or failed from a host that could not run it.
ALERT_STATUS = 3


# am[implements a-op-session-self-1018@bd8329]
@dataclass(frozen=True)
class Session:
    """A pymetta session over an Omega checkout, the Python modules it imported by name, and the
    skills the plugin's loader added, empty for a session that loaded no plugin."""

    m: Any
    modules: dict[str, ModuleType]
    plugin: tuple[str, ...] = ()


# lib_import comes first, since Omega's modules import Prolog predicates through it, then the
# checkout as the Omega library, then each module in order.
# Time: one pymetta boot and the imports.
# am[implements a-op-session-self-1018@bd8329] am[implements a-rt-oh-pymetta-run-1018@ace6fb]
def _boot(omega: Path, imports: tuple[str, ...]) -> Session:
    from metta import MeTTa  # noqa: PLC0415 (only the plugin's recorded interpreter has pymetta)

    m = MeTTa()
    m.run("!(import! &self (library lib_import))")
    m.run("!(register_metta_library_path Omega {path})", path=str(omega))
    modules = {}
    for relative in imports:
        path = omega / relative
        if path.suffix == ".py":
            if str(path.parent) not in sys.path:
                sys.path.append(str(path.parent))
            modules[path.stem] = importlib.import_module(path.stem)
        else:
            m.run(f"!(import! &self (library Omega ./{relative}))")
    return Session(m, modules)


# The plugin loads as Omega's loadMettaPlugin loads one (src/plugin.metta at 1a7624e): its record in
# config/plugins.yaml through plugin.listPlugins, its folder put on sys.path by
# plugin.addLocationToPath so it can py-call its own Python files, then its file imported and its
# loadOmegaPlugin evaluated. That loader imports a plugin into a space of its own and answers () on
# pymetta with nothing registered, so here the plugin is imported into the session's space, as the
# plugin suite does; its skills are those getSkills names after the entry point and not before.
# Time: the boot, and the entry point, whose prompt extension starts the plugin's skill process once.
# am[implements a-op-session-self-1018@bd8329] am[rests-on c-op-session-skills-diff-1018@b3d1e6]
# am[rests-on c-op-upstream-plugin-loader-1018@5095b9]
def registry(omega: Path) -> Session:
    """A session holding Omega's skill registry with the installed plugin loaded. Raises SystemExit
    when config/plugins.yaml lists no MeTTa plugin of that name or its entry point answers anything
    but ()."""

    session = _boot(omega, REGISTRY)
    plugins = session.modules["plugin"]
    listed = [(loader, location) for loader, name, location in plugins.listPlugins() if name == PLUGIN]
    if [loader for loader, _ in listed] != ["metta"]:
        raise SystemExit(f"{omega / 'config' / 'plugins.yaml'} lists no one MeTTa plugin {PLUGIN}: {listed}")
    [(_, location)] = listed
    plugins.addLocationToPath(location)
    before = {name for name, _, _ in skills(session.m)}
    session.m.run("!(import! &self {path})", path=str(Path(location) / PLUGIN))
    answers = session.m.run("!(loadOmegaPlugin)")
    if [[str(answer) for answer in group] for group in answers] != [["()"]]:
        raise SystemExit(f"the GoalChainer plugin's loadOmegaPlugin answered {answers}, not ()")
    added = tuple(name for name, _, _ in skills(session.m) if name not in before)
    return Session(session.m, session.modules, added)


# am[implements a-op-calls-1018@94747e]
def reader(omega: Path) -> Session:
    """A session holding Omega's provider module and its reader."""

    return _boot(omega, READER)


# am[implements a-op-session-self-1018@bd8329]
def _text(atom: Any) -> str:
    value = getattr(atom, "value", None)
    return value if isinstance(value, str) else str(atom)


# A three-part expression under `head`: (Error $cmd $msg), the shape the loop's HandleError matches
# (src/loop.metta:52-60 at 1a7624e), or the (python_error Class Exception) catch puts inside one.
# am[implements a-op-calls-1018@94747e]
def _headed(atom: Any, head: str) -> bool:
    from metta import Expression  # noqa: PLC0415

    return isinstance(atom, Expression) and len(atom.children) == 3 and str(atom.children[0]) == head


# getSkills answers (name description params) triples, which the loop hands to providers.getTools.
# am[implements a-op-session-self-1018@bd8329]
def skills(m: Any) -> list[tuple[str, str, list[str]]]:
    """Every registered skill as getSkills answers it, in its order."""

    [[found]] = m.run("!(getSkills)")
    return [(str(name), _text(description), [str(parameter) for parameter in parameters.children])
            for name, description, parameters in (triple.children for triple in found.children)]


# am[implements a-op-reply-schema-1018@d51383] am[rests-on c-op-upstream-tool-render-1018@edc11f]
# am[rests-on c-op-lib-llm-ext-imports-openai-1018@0f401a]
def offered(tool: Any) -> dict[str, Any]:
    """The LLMTool as upstream's AIProvider.convert_tool sends it to an LLM: a strict function whose
    parameters are all required strings (providers/lib_llm_ext.py:323-337 at 1a7624e)."""

    return {"type": "function", "function": {
        "name": tool.name, "description": tool.description, "strict": True,
        "parameters": {"type": "object",
                       "properties": {parameter.name: {"type": "string"} for parameter in tool.parameters},
                       "required": [parameter.name for parameter in tool.parameters],
                       "additionalProperties": False}}}


# Upstream's loop offers every skill (collectTools); a driver may name the ones it serves.
# am[implements a-op-reply-schema-1018@d51383] am[implements a-op-drivers-tools-1018@a61ed7]
def tools(session: Session, names: list[str]) -> list[dict[str, Any]]:
    """The tools Omega offers an LLM for the named skills, or for every skill when none is named, in
    getSkills order. Raises SystemExit naming a skill the registry does not hold."""

    registered = skills(session.m)
    missing = sorted(set(names) - {name for name, _, _ in registered})
    if missing:
        raise SystemExit(f"Omega's registry holds no skill {', '.join(missing)}")
    chosen = [skill for skill in registered if not names or skill[0] in names]
    return [offered(tool) for tool in session.modules["providers"].getTools(chosen)]


# Codex has no custom function tools, so its final message carries the calls, under a schema that
# admits only an offered tool's name with that tool's parameters. Codex sends the schema strict
# (Responses API structured outputs: every object closed and every property required, anyOf below the
# root). An empty list stays admissible, as upstream's llmProviderChat answers it with its own error.
# am[implements a-op-reply-schema-1018@d51383] am[rests-on c-op-codex-output-schema-strict-1018@139d03]
def reply_schema(offer: list[dict[str, Any]]) -> dict[str, Any]:
    """The JSON schema of Codex's reply, {"tool_calls": [{"name": NAME, "arguments": {...}}, ...]}.
    Raises SystemExit for an offer of no tools, which no schema of calls can admit."""

    if not offer:
        raise SystemExit("no tool is offered, so no reply can call one")
    calls = [{"type": "object", "description": function["description"],
              "properties": {"name": {"type": "string", "enum": [function["name"]]},
                             "arguments": function["parameters"]},
              "required": ["name", "arguments"], "additionalProperties": False}
             for function in (tool["function"] for tool in offer)]
    return {"type": "object", "properties": {"tool_calls": {"type": "array", "items": {"anyOf": calls}}},
            "required": ["tool_calls"], "additionalProperties": False}


# Codex's reply as an upstream provider answers: one LLMToolCall per call, with an id of its own,
# as upstream's scripted LLM builds them, and an error call for arguments that are no JSON object,
# as its AIProvider does. A reply that is no object of calls is the response's error, never a raise:
# llmProviderChat answers a raising provider with no calls and no error.
# Time: linear in the reply's length.
# am[implements a-op-calls-1018@94747e] am[rests-on c-op-mock-agent-reply-shape-1018@9a293a]
# am[rests-on c-op-upstream-tool-render-1018@edc11f] am[rests-on c-op-provider-exception-empty-1018@45b986]
def response(providers: ModuleType, reply: str) -> Any:
    """The LLMResponse Codex's reply makes, before upstream validates it."""

    try:
        message = json.loads(reply)
    except json.JSONDecodeError as error:
        return providers.LLMResponse().with_error(f"Codex's reply is not JSON: {error}")
    entries = message.get("tool_calls") if isinstance(message, dict) else None
    if not isinstance(entries, list):
        return providers.LLMResponse().with_error("Codex's reply is no JSON object with a tool_calls list")
    answered = providers.LLMResponse()
    for number, entry in enumerate(entries, 1):
        call = providers.LLMToolCall().with_id(f"call_{number}")
        if not isinstance(entry, dict):
            answered.add_tool_call(call.with_error("A tool call must be a JSON object"))
            continue
        call.with_name(entry.get("name"))
        arguments = entry.get("arguments")
        answered.add_tool_call(call.with_arguments(arguments) if isinstance(arguments, dict)
                               else call.with_error("Tool arguments must be a JSON object"))
    return answered


# am[implements a-op-calls-1018@94747e]
def _provider(providers: ModuleType, reply: str) -> Any:
    class Codex(providers.LLMProvider):
        """Codex as an Omega provider: the reply it already gave answers the chat."""

        def chat(self, request: Any) -> Any:
            return response(providers, reply)

    return Codex()


# The MeTTa text swrite gives a String. Only Strings cross into the engine here: an atom passed as a
# parameter is evaluated where it stands as an argument, and a call would run again.
# am[implements a-op-calls-1018@94747e] am[rests-on c-op-pymetta-params-evaluated-1018@a0ea7d]
def _written(m: Any, value: str) -> str:
    [[text]] = m.run("!(swrite {value})", value=value)
    return text.value


# A symbol swrite can write is one whose name the engine's own reader reads back as that symbol.
# am[implements a-op-calls-1018@94747e]
def _reads_back(m: Any, name: str) -> bool:
    from metta import Symbol  # noqa: PLC0415

    [[read]] = m.run("!(catch (sread {name}))", name=name)
    return isinstance(read, Symbol) and str(read) == name


# swrite writes an atom only when each of its leaves reads back as itself (pymetta's
# metta_text_writable, _runtime/engine/parser.pl:1424-1483), and refuses the live objects catch holds
# for a Python exception and the symbol a parse error names its unreadable text by. This writes an
# atom as swrite does, each such leaf as the String of its text.
# Time: one engine round trip per String or symbol leaf.
# am[implements a-op-calls-1018@94747e] am[rests-on c-op-swrite-refuses-host-objects-1018@925639]
def _metta_text(m: Any, atom: Any) -> str:
    from metta import Expression, Symbol, Variable  # noqa: PLC0415

    if isinstance(atom, Expression):
        return "(" + " ".join(_metta_text(m, child) for child in atom.children) + ")"
    value = getattr(atom, "value", None)
    if isinstance(value, str):
        return _written(m, value)
    if isinstance(atom, Variable) or isinstance(value, (bool, int, float)) or (
            isinstance(atom, Symbol) and _reads_back(m, str(atom))):
        return str(atom)
    return _written(m, str(atom) if value is None else str(value))


# The loop's alert, "ALERT_FAILED" and the error's MeTTa text (HandleError, src/loop.metta:52-60 at
# 1a7624e). A skill's Python exception, which catch holds with its live exception and traceback, is
# written in the shape pymetta documents for one: its class, its message and the failing call.
# am[implements a-op-calls-1018@94747e] am[rests-on c-op-pymetta-catch-documented-shape-1018@860ec0]
def alert(m: Any, error: Any, call: str | None = None) -> str:
    """The loop's alert for an (Error ...) result; `call` is the failing call's MeTTa text."""

    formal = error.children[1]
    if call is not None and _headed(formal, "python_error") and isinstance(getattr(formal.children[2], "value", None), BaseException):
        return f"ALERT_FAILED(Error (python_error {formal.children[1]} {_written(m, str(formal.children[2].value))}) {call})"
    return "ALERT_FAILED" + _metta_text(m, error)


# The loop's reading of a reply (src/loop.metta:105-110 at 1a7624e): the provider's response,
# validated by llmProviderChat against the offered tools, rendered by llmResponseToSExpr and read by
# catch over sread. A response the reader refuses whole, (Error () message), is one alert; each call
# is its name and string arguments as sread read them, with its alert when upstream refused it.
# Only the request's tools bear on validation, so its system message is empty.
# Time: linear in the reply's length, plus the session.
# am[implements a-op-calls-1018@94747e] am[rests-on c-op-upstream-tool-path-1018@c66038]
# am[rests-on c-op-reader-roundtrip-1018@23c186]
def calls(session: Session, offer: list[dict[str, Any]], reply: str) -> list[dict[str, Any]]:
    """One object a call, {"id", "command", "arguments", "alert"}; a reply refused whole is one
    object with no id or command. Raises SystemExit when the provider raised, which llmProviderChat
    answers with no calls and no error."""

    providers = session.modules["providers"]
    providers.registerLLMProvider(PROVIDER, _provider(providers, reply))
    providers.llmProviderStart(PROVIDER)
    functions = [tool["function"] for tool in offer]
    request = providers.llmRequest(providers.llmRequestMessage("system", ""), [], None, None,
                                   providers.getTools([(function["name"], function["description"],
                                                        function["parameters"]["required"]) for function in functions]))
    validated = providers.llmProviderChat(request)
    if not validated.calls and not validated.is_error():
        raise SystemExit("the provider raised, so Omega's llmProviderChat answered no calls; its log names the error")
    [[read]] = session.m.run("!(catch (sread {text}))", text=providers.llmResponseToSExpr(validated))
    if _headed(read, "Error"):
        return [{"id": None, "command": None, "arguments": [], "alert": alert(session.m, read)}]
    found = []
    for callid, call in (pair.children for pair in read.children):
        if _headed(call, "Error"):
            named = call.children[1].children
            found.append({"id": str(callid), "command": str(named[0]) if named else None,
                          "arguments": [_text(argument) for argument in named[1:]], "alert": alert(session.m, call)})
        else:
            found.append({"id": str(callid), "command": str(call.children[0]),
                          "arguments": [_text(argument) for argument in call.children[1:]], "alert": None})
    return found


# The loop's evaluation of one call (src/loop.metta:123-124 at 1a7624e): catch over the collapsed
# answers through helper.normalize_string, then SUCCESS with them or the alert. Each argument enters
# as one String atom, as sread reads a call's arguments, so quotes and backslashes need no escaping.
# Only the plugin's own skills are evaluated.
# Time: the skill's own work, plus the session.
# am[implements a-op-calls-1018@94747e] am[implements a-rt-oh-request-review-1018@4f055a]
# am[rests-on c-op-loop-result-string-1018@421a49]
def evaluate(session: Session, command: str, arguments: list[str]) -> tuple[str, bool]:
    """The loop's result for (COMMAND ARGUMENT ...) and whether it is a success. Raises SystemExit
    naming a command the plugin did not register."""

    if command not in session.plugin:
        raise SystemExit(f"{command} is no skill the GoalChainer plugin registered.")
    values = {f"a{index}": argument for index, argument in enumerate(arguments)}
    holes = "".join(f" {{{name}}}" for name in values)
    [[result]] = session.m.run(
        f"!(catch (let $R (collapse (eval ({command}{holes}))) (py-call (helper.normalize_string $R))))", **values)
    if not _headed(result, "Error"):
        return f"SUCCESS, RETURN: {_text(result)}", True
    call = "(" + " ".join([command, *(_written(session.m, argument) for argument in arguments)]) + ")"
    return alert(session.m, result, call), False


# am[implements a-op-calls-1018@94747e]
def _arguments(text: str) -> list[str]:
    arguments = json.loads(text)
    if not isinstance(arguments, list) or not all(isinstance(argument, str) for argument in arguments):
        raise SystemExit("eval's arguments must be a JSON list of strings")
    return arguments


# am[implements a-rt-oh-pymetta-run-1018@ace6fb] am[implements a-op-drivers-tools-1018@a61ed7]
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0].removeprefix("Purpose: "))
    parser.add_argument("--omega", type=Path, required=True, help="the Omega checkout the plugin is installed in")
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("registered", help="print the skills the plugin's loader registered, one per line")
    offer = actions.add_parser("tools", help="print as one JSON list the tools Omega offers an LLM for NAMES, or for every skill")
    offer.add_argument("names", nargs="*")
    actions.add_parser("rules", help="print the skill rules of Omega's context, one per line")
    actions.add_parser("extensions", help="print the plugin's prompt extensions")
    actions.add_parser("schema", help="print the reply schema for the tools on standard input")
    read = actions.add_parser("calls", help="print the calls Omega reads in the reply on standard input, one JSON object a line")
    read.add_argument("tools", help="the offered tools, as the tools action printed them")
    run = actions.add_parser("eval", help="print the loop's result for COMMAND, its arguments a JSON list on standard input")
    run.add_argument("command")
    arguments = parser.parse_args(argv)
    omega = arguments.omega.resolve()
    if arguments.action == "schema":
        print(json.dumps(reply_schema(json.loads(sys.stdin.read()))))
        return 0
    if arguments.action == "calls":
        found = calls(reader(omega), json.loads(arguments.tools), sys.stdin.read())
        print("\n".join(json.dumps(call) for call in found))
        return 0
    session = registry(omega)
    if arguments.action == "eval":
        result, succeeded = evaluate(session, arguments.command, _arguments(sys.stdin.read()))
        print(result)
        return 0 if succeeded else ALERT_STATUS
    if arguments.action == "tools":
        print(json.dumps(tools(session, arguments.names)))
    elif arguments.action == "registered":
        print("\n".join(session.plugin))
    elif arguments.action == "rules":
        [[rules]] = session.m.run("!(getSkillRules)")
        print("\n".join(_text(rule) for rule in rules.children))
    else:
        [[added]] = session.m.run("!(collapse (prompt-extension $_))")
        print("\n".join(_text(text) for text in added.children))
    return 0


if __name__ == "__main__":
    sys.exit(main())
