; Purpose: register bounded domain, motivation, directive and SNARS requests with the Omega
; agent, formerly OmegaClaw, through its plugin API, with the reader's paths as Omega configuration.
; The installer writes goalchainer_host.py with GoalChainer's interpreter. Each skill passes JSON
; through gcskill to that process. The domain request preserves the user's text in reading.text.
; am[implements a-integrate-domain-surface-1018@759698]

; The interpreter the installer recorded, read from the generated goalchainer_host.py beside this file.
; Omega's loader puts the plugin's directory on sys.path, so the module is found on both engines,
; while a relative import! of a MeTTa file resolves against this file on pymetta but against the
; agent's top-level program on PeTTa, and fails silently there.
; am[implements a-oc-plugin-host-module-1018@180dc9] am[rests-on c-oc-petta-import-working-dir-1018@cec2fd]
(= (goalchainer-python) (py-call (goalchainer_host.python)))

; The reader's settings, declared as every Omega tunable is, (= (name) (empty)), and bound by configure
; in loadOmegaPlugin: a key=value argument to the agent, an OMEGA_<name> variable or config/config.yaml
; overrides the default the install recorded. The declaration is what lets PeTTa compile a call to one
; as a call, where it hands a py-call an undeclared one unevaluated.
; am[implements a-irp-reader-keys-1018@14bc18] am[rests-on c-irp-plugin-configure-supported-1018@289b90]
(= (goalchainerModelCache) (empty))
(= (goalchainerJevCache) (empty))
(= (goalchainerJevOffline) (empty))
(= (goalchainerJevUrl) (empty))

; Registration and the prompt extension expose the same callable commands. Omega's plugin loader
; calls loadOmegaPlugin, the entry point its plugin API names, and offers each added skill to the LLM
; as a tool whose parameters are the skill's argument names. The reader settings go to gcskill once,
; before the prompt extension starts the first skill process.
; am[implements a-integrate-domain-surface-1018@759698] am[implements a-oc-plugin-entry-1018@3f1f44]
; am[rests-on c-oc-plugin-api-1018@14ec52] am[rests-on c-oc-tool-call-interface-1018@ac35f0]
; am[implements a-irp-reader-keys-1018@14bc18]
; am[implements a-v2-cli-skill-surface-1020@6f755c]
(= (loadOmegaPlugin)
   (progn
     (log INFO "goalchainer-plugin" "Adding the GoalChainer skills")
     (configure goalchainerModelCache (py-call (goalchainer_host.reader_default "goalchainerModelCache")))
     (configure goalchainerJevCache (py-call (goalchainer_host.reader_default "goalchainerJevCache")))
     (configure goalchainerJevOffline (py-call (goalchainer_host.reader_default "goalchainerJevOffline")))
     (configure goalchainerJevUrl (py-call (goalchainer_host.reader_default "goalchainerJevUrl")))
     (py-call (gcskill.configure_reader (goalchainerModelCache) (goalchainerJevCache)
                                        (goalchainerJevOffline) (goalchainerJevUrl)))
     (add-skill goalchainer-request
        "Review, plan or check a current step against a selected domain; include explicit inference and time limits"
        (json_request))
     (add-skill goalchainer-directive-dispatch
        "Inspect or change a durable directive plan through a typed operation with explicit resource limits"
        (json_request))
     (add-skill goalchainer-snars-dispatch
        "Query evidence, proofs, conditions, obligations, counterfactuals or trust through a bounded SNARS session"
        (json_request))
     (add-skill goalchainer-motivation-dispatch
        "Record attributed need observations or host attempts, or inspect a motivation stream, with explicit resource limits"
        (json_request))
     (add-prompt-extension goalchainer (goalchainer-system-prompt))
     ()))

; am[implements a-integrate-domain-surface-1018@759698]
(= (goalchainer-request $request)
   (py-call (gcskill.request (goalchainer-python) $request)))

; am[implements a-integrate-domain-surface-1018@759698]
(= (goalchainer-directive-dispatch $request)
   (py-call (gcskill.directive_dispatch (goalchainer-python) $request)))

; am[implements a-integrate-domain-surface-1018@759698]
(= (goalchainer-snars-dispatch $request)
   (py-call (gcskill.dispatch (goalchainer-python) $request)))

; am[implements a-v2-cli-skill-surface-1020@6f755c]
(= (goalchainer-motivation-dispatch $request)
   (py-call (gcskill.motivation_dispatch (goalchainer-python) $request)))

; am[implements a-integrate-domain-surface-1018@759698]
(= (goalchainer-system-prompt)
   (py-call (gcskill.system_prompt (goalchainer-python))))
