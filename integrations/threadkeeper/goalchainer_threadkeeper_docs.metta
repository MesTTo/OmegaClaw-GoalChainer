;; MeTTa documentation atoms for the GoalChainer ThreadKeeper policy.
;; Import this module with the executable policy when runtime help is needed.

(: gc-thread-compile (-> String %Undefined%))
(: gc-thread-plan (-> String String String %Undefined%))
(: gc-thread-markdown-atoms (-> String %Undefined%))
(: gc-thread-status
  (-> String String String Number Number Number String String %Undefined%))
(: gc-thread-route
  (-> Atom Atom Number Number Number Number Number Bool Bool %Undefined%))
(: gc-thread-release (-> Atom Number Bool %Undefined%))
(: gc-thread-ui (-> String Number %Undefined%))
(: gc-thread-ui-v2 (-> String String String Number %Undefined%))
(: gc-thread-dispatch (-> String Atom Atom Number String %Undefined%))
(: gc-thread-bind-session (-> String String %Undefined%))
(: gc-thread-outcome
  (-> Atom Number Atom Number Number Bool Atom %Undefined%))
(: gc-thread-attempt
  (-> Atom Atom Atom Atom Atom Bool
      Atom Atom Atom Atom Atom Atom
      Number Number Number Number Number Bool %Undefined%))
(: thread-workflow (-> Symbol Symbol Atom))
(: thread-workflow-step (-> Symbol Symbol Number String Atom))
(: thread-mcp-profile (-> Symbol Symbol Atom))
(: thread-spec-v2 (-> Symbol Atom))
(: thread-project (-> Symbol String Atom))
(: thread-agent (-> Symbol Symbol Atom))
(: thread-role (-> Symbol Symbol Symbol Atom))
(: thread-atomspace-link (-> Symbol Symbol Symbol Symbol Atom))

(@doc gc-thread-compile
  (@desc "Validate normalized ThreadKeeper facts and compile the task and workflow graph")
  (@params
    ((@param "MeTTa source containing normalized thread facts")))
  (@return "A goalchainer-thread-v1 or goalchainer-thread-v2 compile protocol record, matching the specification header"))

(@doc gc-thread-plan
  (@desc "Compile validated thread facts into OmegaClaw directive source lines")
  (@params
    ((@param "MeTTa source containing normalized thread facts")
     (@param "Digest of the source specification")
     (@param "Creation date for plan metadata")))
  (@return "A goalchainer-thread-v1 or goalchainer-thread-v2 plan protocol record, matching the specification header"))

(@doc gc-thread-markdown-atoms
  (@desc "Lower a Mettabase Markdown atom tuple into inert actions and diagnostics")
  (@params
    ((@param "MeTTa source containing the output of Mettabase md-atoms")))
  (@return "A goalchainer-thread-v1 markdown protocol record"))

(@doc gc-thread-status
  (@desc "Build a MeTTa Markdown status document from observed orchestration data")
  (@params
    ((@param "Thread title")
     (@param "MeTTa source containing normalized thread facts")
     (@param "MeTTa source containing board rows")
     (@param "Token budget ceiling")
     (@param "Soft token threshold")
     (@param "Tokens spent")
     (@param "MeTTa source containing attempt rows")
     (@param "MeTTa source containing audit rows")))
  (@return "A goalchainer-thread-v1 status protocol record"))

(@doc gc-thread-route
  (@desc "Choose the worker or specialist route under ThreadKeeper budget policy")
  (@params
    ((@param "Task capability requirement")
     (@param "Task stakes")
     (@param "Tokens spent")
     (@param "Token budget ceiling")
     (@param "Soft token threshold")
     (@param "Required local iterations")
     (@param "Completed local iterations")
     (@param "Whether the subproblem is hard")
     (@param "Whether adjudication is available")))
  (@return "A goalchainer-thread-v1 route protocol record"))

(@doc gc-thread-release
  (@desc "Decide whether a dependency-ready task has reached its release time")
  (@params
    ((@param "UTC epoch release constraint, or none")
     (@param "Current UTC epoch")
     (@param "Whether every dependency is ready")))
  (@return "A goalchainer-thread-v1 release protocol record"))

(@doc gc-thread-ui
  (@desc "Derive the Agent Orchestrator task projection from observed task rows")
  (@params
    ((@param "MeTTa source containing ui-task input rows")
     (@param "Current UTC epoch")))
  (@return "A goalchainer-thread-v1 ui protocol record"))

(@doc gc-thread-ui-v2
  (@desc "Derive the project, stable-agent, Atomspace, and session-attempt UI projection")
  (@params
    ((@param "Agent Orchestrator project identifier")
     (@param "MeTTa source containing stable agent registry rows")
     (@param "MeTTa source containing tagged ui-task-v2 rows")
     (@param "Current UTC epoch")))
  (@return "A goalchainer-thread-v2 ui protocol record"))

(@doc gc-thread-dispatch
  (@desc "Select one task role, stable agent key, and visible logical Atomspaces")
  (@params
    ((@param "MeTTa source containing validated thread-spec-v2 facts")
     (@param "Task identifier")
     (@param "MeTTa route target")
     (@param "Positive GoalChainer task-attempt number")
     (@param "MeTTa source containing observed AO agent bindings")))
  (@return "A goalchainer-thread-v2 dispatch protocol record"))

(@doc gc-thread-bind-session
  (@desc "Validate one Agent Orchestrator session observation against its MeTTa dispatch")
  (@params
    ((@param "MeTTa source containing a dispatch record")
     (@param "MeTTa source containing one AO session observation")))
  (@return "A goalchainer-thread-v2 normalized session-attempt record"))

(@doc gc-thread-outcome
  (@desc "Derive the task transition from a worker observation and evaluations")
  (@params
    ((@param "Worker exit reason")
     (@param "Worker exit code")
     (@param "Evaluator verdict")
     (@param "Current attempt number")
     (@param "Maximum retry count")
     (@param "Whether adjudication is required")
     (@param "Adjudicator verdict")))
  (@return "A goalchainer-thread-v1 outcome protocol record"))

(@doc gc-thread-attempt
  (@desc "Run the compatibility host attempt and derive its policy outcome")
  (@params
    ((@param "Encoded worker command")
     (@param "Encoded evaluator command")
     (@param "Encoded adjudicator command")
     (@param "Working directory")
     (@param "Encoded environment")
     (@param "Whether to allocate a pseudo-terminal")
     (@param "Task identifier")
     (@param "Task capability")
     (@param "Acceptance criterion")
     (@param "Task stakes")
     (@param "Evaluator identity")
     (@param "Adjudicator identity")
     (@param "Lease duration")
     (@param "Idle timeout")
     (@param "Wall timeout")
     (@param "Current attempt number")
     (@param "Maximum retry count")
     (@param "Whether adjudication is required")))
  (@return "A goalchainer-thread-v1 attempt protocol record"))

(@doc thread-workflow
  (@desc "Name the guided worker workflow for one thread")
  (@params
    ((@param "Thread identifier")
     (@param "Workflow identifier")))
  (@return "A declarative workflow fact"))

(@doc thread-workflow-step
  (@desc "Add one ordered system instruction to a thread workflow")
  (@params
    ((@param "Thread identifier")
     (@param "Workflow identifier")
     (@param "Positive step order")
     (@param "Worker instruction")))
  (@return "A declarative workflow-step fact"))

(@doc thread-mcp-profile
  (@desc "Select the MCP tool profile installed for every released agent task")
  (@params
    ((@param "Thread identifier")
     (@param "MCP profile identifier. The supported value is oh-my-goals")))
  (@return "A declarative MCP-access fact"))

(@doc thread-spec-v2
  (@desc "Opt into project-scoped stable agents and logical Atomspace links")
  (@params
    ((@param "Thread identifier")))
  (@return "A versioned thread specification header"))

(@doc thread-project
  (@desc "Bind a v2 thread to one Agent Orchestrator project")
  (@params
    ((@param "Thread identifier")
     (@param "Agent Orchestrator project identifier")))
  (@return "A declarative project identity fact"))

(@doc thread-agent
  (@desc "Declare one stable semantic agent key inside a v2 project")
  (@params
    ((@param "Thread identifier")
     (@param "Stable semantic agent key")))
  (@return "A declarative project agent fact"))

(@doc thread-role
  (@desc "Assign one role symbol to an agent key. V2 requires that key in the stable project-agent registry; v1 keeps the existing role identity meaning")
  (@params
    ((@param "Thread identifier")
     (@param "Role. Supported values are control, worker, supervisor, evaluator, specialist, and adjudicator")
     (@param "Agent key assigned to the role")))
  (@return "A declarative role assignment fact"))

(@doc thread-atomspace-link
  (@desc "Declare a logical shared or private Atomspace link without a filesystem path")
  (@params
    ((@param "Thread identifier")
     (@param "Logical link key")
     (@param "Scope. The supported values are shared and private")
     (@param "Owner. Shared links use project; private links use an agent key")))
  (@return "A declarative logical Atomspace link fact"))
