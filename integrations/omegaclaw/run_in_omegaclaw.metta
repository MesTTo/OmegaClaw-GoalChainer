; A real OmegaClaw Core agent turn. Loads OmegaClaw's own skill registry, loads
; the GoalChainer plugin through the plugin loader exactly as the agent does at
; startup, and then runs the loop's dispatch: the agent emits a command and
; OmegaClaw (eval $command) executes it.
;
; Run from the OmegaClaw-Core checkout the plugin is installed into, which is
; what the relative paths below are resolved against:
;
;   cd <OmegaClaw-Core>
;   PYTHONPATH=<GoalChainer>/src:<PeTTa>/python \
;     swipl -s <PeTTa>/src/main.pl -- \
;       <GoalChainer>/integrations/omegaclaw/run_in_omegaclaw.metta --silent

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

!("===============================================================")
!("OmegaClaw Core  |  loading the GoalChainer plugin")
!("===============================================================")

; The loader imports the plugin and evaluates loadOmegaClawPlugin, which
; registers each command with add-skill. That is what puts the command in
; helper.LLM_COMMANDS, so the loop's UNKNOWN_SKILL_CALL precheck accepts it.
!(loadMettaPlugin "goalchainer" (py-call (posixpath.abspath "plugins/goalchainer")))

!("")
!("agent's skill menu (OmegaClaw getSkills, GoalChainer lines registered):")
!(getSkills)
!("")
!("user> Checkout is down. Engineers want to paste the raw logs with")
!("      customer emails and order IDs into the incident channel.")
!("")
!("agent emits:  goalchainer-decision <request>")
!("OmegaClaw evaluates it:")
!(eval (goalchainer-decision "Checkout is down. Engineers want to paste raw logs with customer emails and order IDs into the incident channel."))
!("")
!("agent emits:  goalchainer-solve <request>")
!("OmegaClaw evaluates it:")
!(eval (goalchainer-solve "Checkout is down, raw logs with customer emails and order IDs"))
