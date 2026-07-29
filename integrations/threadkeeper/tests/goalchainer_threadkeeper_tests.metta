;; Native MeTTa contract tests for GoalChainer policy.

!(import! &self ../goalchainer_threadkeeper)

!(assertEqual
  (gc-thread-release 200 199 True)
  (goalchainer-thread-v1 release ok
    (release False "not-before constraint has not elapsed")))

!(assertEqual
  (gc-thread-release 200 200 True)
  (goalchainer-thread-v1 release ok
    (release True "not-before constraint elapsed")))

!(assertEqual
  (gc-thread-route specialist high 0 120000 60000 1 1 True True)
  (goalchainer-thread-v1 route ok
    (route specialist True "under soft threshold" True)))

!(assertEqual
  (gc-thread-outcome process-exited 0 accept 1 2 False not-required)
  (goalchainer-thread-v1 outcome ok
    (outcome complete "accepted by evaluator")))

!(assertEqual
  (tk-compiled-workflow
    ((thread-workflow demo guided-research)
     (thread-workflow-step demo guided-research 20 "Verify acceptance.")
     (thread-workflow-step demo guided-research 10 "Inspect existing work.")))
  (workflow guided-research
    ((step 10 "Inspect existing work.")
     (step 20 "Verify acceptance."))))

!(assertEqual
  (tk-compiled-mcp-access ())
  (mcp-access oh-my-goals
    (remember query solve revise forget explain
     find_papers ingest_paper add_claim citations review check_retractions)))

!(assertEqual
  (tk-compiled-mcp-access
    ((thread-mcp-profile demo oh-my-goals)))
  (tk-compiled-mcp-access ()))

!(assertEqual
  (gc-thread-markdown-atoms
    "((md-source cb \"```metta\\n(foo)\\n```\")
      (md-action cb add 0 \"(quote (foo))\"))")
  (goalchainer-thread-v1 markdown ok
    (markdown
      (actions ((action cb add 1 "(quote (foo))")))
      (diagnostics ())
      (sources ((source cb "```metta\n(foo)\n```"))))))

!(assertEqual
  (gc-thread-markdown-atoms
    "((md-source cb \"```metta\\n(goalchainer-thread-specification ((thread-spec-v1 demo) (thread-owner demo owner)))\\n```\")
      (md-action cb add 0 \"(quote (goalchainer-thread-specification ((thread-spec-v1 demo) (thread-owner demo owner))))\"))")
  (goalchainer-thread-v1 markdown ok
    (markdown
      (actions
        ((action cb add 1 "(quote (thread-spec-v1 demo))")
         (action cb add 1 "(quote (thread-owner demo owner))")))
      (diagnostics ())
      (sources
        ((source cb
           "```metta\n(goalchainer-thread-specification ((thread-spec-v1 demo) (thread-owner demo owner)))\n```"))))))

!(assertEqual
  (gc-thread-ui
    "((ui-task collect local accept normal () ready False worker 0 none 200)
      (ui-task publish local published normal (collect) done False worker 1 session-7 none))"
    199)
  (goalchainer-thread-v1 ui ok
    (ui-projection
      (summary 2 1 0 0 0 0 1 50)
      (tasks
        ((ui-task collect local accept normal () scheduled False
           worker 0 none 200 "not-before constraint has not elapsed")
         (ui-task publish local published normal (collect) done False
           worker 1 session-7 none ""))))))

(= (test-v2-facts)
  ((thread-spec-v2 demo)
   (thread-project demo "project-demo")
   (thread-title demo "Demo")
   (thread-owner demo owner)
   (thread-budget demo 1000 500 0)
   (thread-supervision demo 30 5 60 2)
   (thread-agent demo control-agent)
   (thread-agent demo worker-agent)
   (thread-agent demo supervisor-agent)
   (thread-agent demo evaluator-agent)
   (thread-agent demo specialist-agent)
   (thread-role demo control control-agent)
   (thread-role demo worker worker-agent)
   (thread-role demo supervisor supervisor-agent)
   (thread-role demo evaluator evaluator-agent)
   (thread-role demo specialist specialist-agent)
   (thread-task demo collect local collected normal)
   (thread-task demo research either researched high)
   (thread-atomspace-link demo project-shared shared project)
   (thread-atomspace-link demo control-private private control-agent)
   (thread-atomspace-link demo worker-private private worker-agent)
   (thread-atomspace-link demo supervisor-private private supervisor-agent)
   (thread-atomspace-link demo evaluator-private private evaluator-agent)
   (thread-atomspace-link demo specialist-private private specialist-agent)
   (thread-merge-policy demo none none)))

!(assertEqual
  (tk-v2-validation-errors (test-v2-facts))
  ())

!(assertEqual
  (tk-v2-bad-agent-keys (worker-agent "invalid-agent-key"))
  ("invalid-agent-key"))

!(assertEqual
  (gc-thread-dispatch
    (repr (test-v2-facts))
    research specialist 1
    "((ao-agent-binding \"project-demo\" specialist-agent \"11111111-1111-4111-8111-111111111111\"))")
  (goalchainer-thread-v2 dispatch ok
    (dispatch
      (valid True)
      (errors ())
      (project "project-demo")
      (attempt-key demo research 1)
      (assignment specialist specialist-agent "11111111-1111-4111-8111-111111111111")
      (atomspace-links
        ((atomspace-link project-shared shared project)
         (atomspace-link specialist-private private specialist-agent)))
      (mcp-access oh-my-goals
        (remember query solve revise forget explain
         find_papers ingest_paper add_claim citations review check_retractions))
      (workflow goalchainer-default
        ((step 10
           "Inspect the task context, repository guidance, and existing work before changing anything.")
         (step 20
           "Complete only the released task and verify its acceptance condition with concrete evidence.")
         (step 30
           "Report changed artifacts, checks run, remaining uncertainty, and any follow-up work."))))))

!(assertEqual
  (gc-thread-bind-session
    "(dispatch
       (valid True)
       (errors ())
       (project \"project-demo\")
       (attempt-key demo research 1)
       (assignment specialist specialist-agent \"11111111-1111-4111-8111-111111111111\")
       (atomspace-links
         ((atomspace-link project-shared shared project)
          (atomspace-link specialist-private private specialist-agent)))
       (mcp-access oh-my-goals (remember))
       (workflow guided ((step 10 \"Inspect.\"))))"
    "(ao-session-observation
       (attempt-key demo research 1)
       \"project-demo\" specialist-agent
       \"11111111-1111-4111-8111-111111111111\" 4 \"session-7\"
       \"running\" \"active\" False \"2026-07-29T00:00:00Z\")")
  (goalchainer-thread-v2 session ok
    (session
      (valid True)
      (errors ())
      (session-attempt
        (attempt-key demo research 1)
        (project "project-demo")
        (assignment specialist specialist-agent "11111111-1111-4111-8111-111111111111")
        (agent-attempt 4)
        (session-id "session-7")
        (state "running" "active" False)
        (updated-at "2026-07-29T00:00:00Z")))))

!(assertEqual
  (gc-thread-ui-v2
    "project-demo"
    "((agent worker-agent worker \"22222222-2222-4222-8222-222222222222\"))"
    "((ui-task-v2
       (task collect local collected normal ())
       (execution ready False 200)
       (assignment worker worker-agent \"22222222-2222-4222-8222-222222222222\")
       (attempts 0 none ())
       (atomspace-links
         ((atomspace-link project-shared shared project)
          (atomspace-link worker-private private worker-agent)))))"
    199)
  (goalchainer-thread-v2 ui ok
    (ui-projection-v2
      (project "project-demo")
      (agents ((agent worker-agent worker "22222222-2222-4222-8222-222222222222")))
      (summary 1 1 0 0 0 0 0 0)
      (tasks
        ((ui-task-v2
           (task collect local collected normal ())
           (execution scheduled False 200
             "not-before constraint has not elapsed")
           (assignment worker worker-agent "22222222-2222-4222-8222-222222222222")
           (attempts 0 none ())
           (atomspace-links
             ((atomspace-link project-shared shared project)
              (atomspace-link worker-private private worker-agent)))))))))

!(assertEqual
  (let* (($source
            (tk-status-document
              "Demo"
              ((fact value))
              ((row "task" "ready"))
              10 5 1 () ()))
          ($document (sread $source))
          ($space (new-space))
          ($_stored (add-atom $space $document)))
    (match $space
      (md
        goalchainer-thread-status
        $title
        $authority
        $board-heading
        $board-table
        $budget-heading
        $budget-table
        $attempts-heading
        $attempts-table
        $audit-heading
        $audit-table
        $specification-heading
        (metta
          (add
            (goalchainer-thread-specification ((fact value))))))
      True))
  True)

;; Load documentation after policy assertions so docs remain inert metadata.
!(import! &self ../goalchainer_threadkeeper_docs)

!(assertEqual
  (get-doc gc-thread-release)
  (@doc-formal
    (@item gc-thread-release)
    (@kind function)
    (@type (-> Atom Number Bool %Undefined%))
    (@desc "Decide whether a dependency-ready task has reached its release time")
    (@params
      ((@param
         (@type Atom)
         (@desc "UTC epoch release constraint, or none"))
       (@param
         (@type Number)
         (@desc "Current UTC epoch"))
       (@param
         (@type Bool)
         (@desc "Whether every dependency is ready"))))
    (@return
      (@type %Undefined%)
      (@desc "A goalchainer-thread-v1 release protocol record"))))

!(assertEqual
  (get-doc thread-workflow-step)
  (@doc-formal
    (@item thread-workflow-step)
    (@kind function)
    (@type (-> Symbol Symbol Number String Atom))
    (@desc "Add one ordered system instruction to a thread workflow")
    (@params
      ((@param (@type Symbol) (@desc "Thread identifier"))
       (@param (@type Symbol) (@desc "Workflow identifier"))
       (@param (@type Number) (@desc "Positive step order"))
       (@param (@type String) (@desc "Worker instruction"))))
    (@return (@type Atom) (@desc "A declarative workflow-step fact"))))

!(assertEqual
  (get-doc thread-mcp-profile)
  (@doc-formal
    (@item thread-mcp-profile)
    (@kind function)
    (@type (-> Symbol Symbol Atom))
    (@desc "Select the MCP tool profile installed for every released agent task")
    (@params
      ((@param (@type Symbol) (@desc "Thread identifier"))
       (@param
         (@type Symbol)
         (@desc "MCP profile identifier. The supported value is oh-my-goals"))))
    (@return (@type Atom) (@desc "A declarative MCP-access fact"))))

!(assertEqual
  (get-doc thread-project)
  (@doc-formal
    (@item thread-project)
    (@kind function)
    (@type (-> Symbol String Atom))
    (@desc "Bind a v2 thread to one Agent Orchestrator project")
    (@params
      ((@param (@type Symbol) (@desc "Thread identifier"))
       (@param
         (@type String)
         (@desc "Agent Orchestrator project identifier"))))
    (@return
      (@type Atom)
      (@desc "A declarative project identity fact"))))

!(assertEqual
  (get-doc thread-role)
  (@doc-formal
    (@item thread-role)
    (@kind function)
    (@type (-> Symbol Symbol Symbol Atom))
    (@desc "Assign one role symbol to an agent key. V2 requires that key in the stable project-agent registry; v1 keeps the existing role identity meaning")
    (@params
      ((@param (@type Symbol) (@desc "Thread identifier"))
       (@param
         (@type Symbol)
         (@desc "Role. Supported values are control, worker, supervisor, evaluator, specialist, and adjudicator"))
       (@param (@type Symbol) (@desc "Agent key assigned to the role"))))
    (@return
      (@type Atom)
      (@desc "A declarative role assignment fact"))))
