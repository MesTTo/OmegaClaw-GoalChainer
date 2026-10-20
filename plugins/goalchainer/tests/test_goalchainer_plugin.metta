; Purpose: verify plugins/goalchainer registers its skills and prompt extension with the host Omega
; checkout's skill registry, so the agent's loop offers each goalchainer-* skill to the LLM as a tool.
;
; Run from the host Omega root with the omegaclaw-goalchainer package importable; run.sh does both.
; Omega's MeTTa modules import one another through (library Omega ...), so the checkout is registered
; under that alias, and its Python modules are imported under their own names, as Omega's PeTTa
; runtime imports them.
;
; Omega's own loader imports a MeTTa plugin into a space of its own and evaluates the plugin's
; loadOmegaPlugin from &self. PeTTa's rules are global, so that call reaches the plugin; on pymetta a
; function belongs to the space that defines it, the call reaches nothing and the loader answers ()
; with nothing registered. The suite therefore imports the plugin into &self and calls its entry point
; as the loader's evaluation does on PeTTa; the image round trip runs the loader itself on upstream's
; PeTTa.
; am[verifies a-oc-plugin-suite-main-1018@7aee50] am[rests-on c-oc-loader-silent-on-pymetta-1018@f7c367]
!(import! &self (library lib_import))
!(register_metta_library_path Omega (py-call (os.getcwd)))
!(py-call (omega_modules.by_name "src/utils.py"))
!(import! &self (library Omega ./src/utils.metta))
!(py-call (omega_modules.by_name "src/helper.py"))
!(py-call (omega_modules.by_name "src/config.py"))
!(import! &self (library Omega ./src/config.metta))
!(py-call (omega_modules.by_name "src/logger.py"))
!(import! &self (library Omega ./src/log.metta))
!(py-call (omega_modules.by_name "src/providers.py"))
!(import! &self (library Omega ./src/skills.metta))
!(initLogger)

; Before the plugin loads, the registry offers the LLM no goalchainer tool.
; am[verifies a-oc-plugin-suite-main-1018@7aee50]
!(test (py-call (omega_modules.tool_parameters (py-call (providers.getTools (getSkills))) "goalchainer-request"))
       absent)

; The entry point answers () when the plugin reports no error. Its prompt extension is built by
; py-calling gcskill.system_prompt, so a plugin whose GoalChainer cannot answer fails the load here.
; am[verifies a-oc-plugin-entry-1018@3f1f44]
!(import! &self (py-call (posixpath.abspath "plugins/goalchainer/goalchainer")))
!(test (loadOmegaPlugin) ())

; The entry point configured the reader settings: this checkout's install recorded no defaults and
; nothing here overrides them, so each answers empty, leaving the reader to the suite's environment.
; am[verifies a-irp-reader-keys-1018@14bc18]
!(test (py-call (operator.eq (goalchainerModelCache) "")) True)
!(test (py-call (operator.eq (goalchainerJevCache) "")) True)
!(test (py-call (operator.eq (goalchainerJevOffline) "")) True)
!(test (py-call (operator.eq (goalchainerJevUrl) "")) True)

; Every registered skill reaches the LLM as a tool taking the one JSON request argument.
; am[verifies a-integrate-domain-surface-1018@759698] am[verifies a-oc-plugin-suite-main-1018@7aee50]
!(test (py-call (omega_modules.tool_parameters (py-call (providers.getTools (getSkills))) "goalchainer-request"))
       json_request)
!(test (py-call (omega_modules.tool_parameters (py-call (providers.getTools (getSkills))) "goalchainer-directive-dispatch"))
       json_request)
!(test (py-call (omega_modules.tool_parameters (py-call (providers.getTools (getSkills))) "goalchainer-snars-dispatch"))
       json_request)
; am[verifies a-v2-cli-skill-surface-1020@6f755c]
!(test (py-call (omega_modules.tool_parameters (py-call (providers.getTools (getSkills))) "goalchainer-motivation-dispatch"))
       json_request)

; A name the plugin never registered is still no tool, so the checks above discriminate.
!(test (py-call (omega_modules.tool_parameters (py-call (providers.getTools (getSkills))) "goalchainer-not-a-skill"))
       absent)

; The registry keeps each skill's description beside its function and arguments. The row is matched
; rather than written out, since written out it is a two-argument call of the one-argument skill.
; am[verifies a-integrate-domain-surface-1018@759698]
!(test (collapse (match &self (dynamic-skill goalchainer-request ($function $description $arguments))
                   ($description $arguments)))
       (("Review, plan or check a current step against a selected domain; include explicit inference and time limits"
         (json_request))))

; GoalChainer's required pipeline reaches the agent as prompt context rather than as a skill it has
; to remember to call, and that context names the request skill.
; am[verifies a-integrate-domain-surface-1018@759698]
!(test (collapse (match &self (= (prompt-extension goalchainer) $text) found)) (found))
!(test (py-call (operator.contains (prompt-extension goalchainer) "goalchainer-request")) True)
; am[verifies a-v2-cli-skill-surface-1020@6f755c]
!(test (py-call (operator.contains (prompt-extension goalchainer) "a review never records an attempt")) True)

!(println! test-goalchainer-plugin-done)
