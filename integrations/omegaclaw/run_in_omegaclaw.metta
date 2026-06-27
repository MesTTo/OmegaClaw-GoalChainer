; A real OmegaClaw Core agent turn. Loads OmegaClaw's own skill registry
; (src/skills), registers GoalChainer beside it, and runs the loop's dispatch:
; the agent emits a command, OmegaClaw (eval $command) executes it.
;
;   PYTHONPATH=<GoalChainer>/src:<PeTTa>/python \
;     swipl -s <PeTTa>/src/main.pl -- integrations/omegaclaw/run_in_omegaclaw.metta silent

!(import! &self (library OmegaClaw-Core src/skills))
!(import! &self goalchainer_skill)

!("===============================================================")
!("OmegaClaw Core  |  skill registry: OmegaClaw + GoalChainer")
!("===============================================================")
!("user> Checkout is down. Engineers want to paste the raw logs with")
!("      customer emails and order IDs into the incident channel.")
!("")
!("agent's GoalChainer skill menu (added to OmegaClaw getSkills):")
!(goalchainer-skill-docs)
!("")
!("agent emits:  goalchainer-decision <request>")
!("OmegaClaw evaluates it:")
!(eval (goalchainer-decision "Checkout is down. Engineers want to paste raw logs with customer emails and order IDs into the incident channel."))
!("")
!("agent emits:  goalchainer-solve <request>")
!("OmegaClaw evaluates it:")
!(eval (goalchainer-solve "Checkout is down, raw logs with customer emails and order IDs"))
