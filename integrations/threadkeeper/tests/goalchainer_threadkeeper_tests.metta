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
