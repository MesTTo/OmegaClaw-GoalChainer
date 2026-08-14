; The plugin seam: loading plugins/goalchainer through the real plugin loader
; must both advertise each skill to the LLM and register it as a dispatchable
; command.
;
; The second half is the half that matters. src/loop.metta prechecks every
; parsed command with (HandleError UNKNOWN_SKILL_CALL $s $s), and
; balance_parentheses in src/helper.py raises that error for any command whose
; head is not in LLM_COMMANDS. That set is seeded from STATIC_LLM_COMMANDS and
; extended only by helper.add_llm_command, which add-skill calls. The bridge
; this plugin replaces only advertised its commands, so on this OmegaClaw every
; goalchainer-* call the agent made would come back UNKNOWN_SKILL_CALL. These
; tests ask helper.starts_command_line, the same predicate the parser applies.
;
; Run from the host OmegaClaw-Core root, with the omegaclaw-goalchainer package
; importable; run.sh does both. The core modules are reached by absolute path
; rather than through a (library OmegaClaw-Core ...) import, so the suite needs
; no library registration and does not depend on what the host checkout is
; named. This plugin only py-calls, so it imports no MeTTa library of its own.
!(import! &self (py-call (posixpath.abspath "src/utils")))
!(import! &self (py-call (posixpath.abspath "src/logger.py")))
!(import! &self (py-call (posixpath.abspath "src/log")))
!(import! &self (py-call (posixpath.abspath "src/helper.py")))
!(import! &self (py-call (posixpath.abspath "src/config.py")))
!(import! &self (py-call (posixpath.abspath "src/config")))
!(import! &self (py-call (posixpath.abspath "src/skills")))
!(import! &self (py-call (posixpath.abspath "src/plugin.py")))
!(import! &self (py-call (posixpath.abspath "src/plugin")))

!(initLogger)

; Before the plugin loads, the parser does not know these commands.
!(test (py-call (helper.starts_command_line "goalchainer-decision x")) False)
!(test (py-call (helper.starts_command_line "goalchainer-thread-dispatch x")) False)

; The loader imports the plugin into its own space and evaluates
; loadOmegaClawPlugin, returning () when the plugin reports no error. This also
; proves the Python side resolves: the prompt extension is built by py-calling
; gcskill.system_prompt, so a missing package fails the load here.
;
; loadMettaPlugin rather than (loadPlugin (metta ...)): the dispatcher tags its
; MeTTa case with a two-argument `metta` term and src/skills defines the
; one-argument `metta` skill, so with both loaded the specializer rejects the
; tag. This is the same code path minus the tag.
; An absolute location, which is what plugin.listPlugins hands the loader in
; production once it expands {REPO}. A relative one resolves against the
; importing file's directory on PeTTa import-overhaul, not the working directory.
!(test (loadMettaPlugin "goalchainer" (py-call (posixpath.abspath "plugins/goalchainer"))) ())

; ...and after it loads, every registered skill passes that precheck.
!(test (py-call (helper.starts_command_line "goalchainer-decision x")) True)
!(test (py-call (helper.starts_command_line "goalchainer-solve x")) True)
!(test (py-call (helper.starts_command_line "goalchainer-motivation x")) True)
!(test (py-call (helper.starts_command_line "goalchainer-directive x")) True)
!(test (py-call (helper.starts_command_line "goalchainer-directive-dispatch x")) True)
!(test (py-call (helper.starts_command_line "goalchainer-snars x")) True)
!(test (py-call (helper.starts_command_line "goalchainer-snars-dispatch x")) True)
!(test (py-call (helper.starts_command_line "goalchainer-thread-dispatch x")) True)

; An unregistered command still fails, so the check above is discriminating
; rather than accepting everything.
!(test (py-call (helper.starts_command_line "goalchainer-not-a-skill x")) False)

; The catalogue the LLM reads carries the registered lines.
!(test (is-member
          "- Run the native SNARS decision summary: goalchainer-snars request"
          (getSkills)) True)
!(test (is-member
          "- Create and claim an OmegaClaw directive plan from an incident decision: goalchainer-directive request"
          (getSkills)) True)

; GoalChainer's required pipeline reaches the agent as prompt context rather
; than as a skill it has to remember to call.
!(test (== (collapse (prompt-extension goalchainer)) ()) False)

!(println! test-goalchainer-plugin-done)
