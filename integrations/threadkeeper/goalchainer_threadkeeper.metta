; MeTTa policy and compilation layer for ThreadKeeper orchestration.
; Mettabase parses Markdown. This file validates its normalized data facts,
; derives routing and attempt outcomes, and returns versioned records.

!(import_prolog_function atomic_list_concat)

(= (gc-thread-ok $operation $payload)
   (goalchainer-thread-v1 $operation ok $payload))

(= (tk-row-head $row)
   (if (== (get-metatype $row) Expression)
       (if (> (size-atom $row) 0) (index-atom $row 0) invalid)
       invalid))

(= (tk-expected-arity $head)
   (case $head
     ((thread-spec-v1 2)
      (thread-title 3)
      (thread-owner 3)
      (thread-budget 5)
      (thread-supervision 6)
      (thread-role 4)
      (thread-task 6)
      (thread-depends 4)
      (thread-merge-policy 4)
      ($other -1))))

(= (tk-rows $facts $head)
   (filter-atom $facts $row (== (tk-row-head $row) $head)))

(= (tk-count $facts $head)
   (size-atom (tk-rows $facts $head)))

(= (tk-single-error $facts $head $missing $duplicate)
   (let $count (tk-count $facts $head)
     (if (== $count 0) $missing
         (if (> $count 1) $duplicate none))))

(= (tk-bad-arity $facts)
   (filter-atom $facts $row
     (not (== (size-atom $row) (tk-expected-arity (tk-row-head $row))))))

(= (tk-values-at $rows $index)
   (map-atom $rows $row (index-atom $row $index)))

; Thread dependency cycles use the same native MeTTa transitive-closure
; algorithm as OmegaClaw's directive analyzer, applied to specification edges.
(= (tk-dependency-edges $dependencies)
   (unique-atom
     (map-atom $dependencies $row
       ((index-atom $row 2) (index-atom $row 3)))))

(= (tk-tc-step $edges $relation)
   (unique-atom
     (union-atom $relation
       (collapse
         (let* ((($a $b) (superpose $relation))
                (($c $d) (superpose $edges)))
           (if (== $b $c) ($a $d) (empty)))))))

(= (tk-tc-fix $edges $relation)
   (let $next (tk-tc-step $edges $relation)
     (if (== (size-atom $next) (size-atom $relation))
         $relation
         (tk-tc-fix $edges $next))))

(= (tk-cyclic-tasks $dependencies)
   (let* (($edges (tk-dependency-edges $dependencies))
          ($reach (tk-tc-fix $edges $edges)))
     (unique-atom
       (collapse
         (let ($source $target) (superpose $reach)
           (if (== $source $target) $source (empty)))))))

(= (tk-symbol? $value)
   (== (get-metatype $value) Symbol))

(= (tk-positive-number? $value)
   (if (== (get-metatype $value) Grounded)
       (> $value 0)
       False))

(= (tk-nonnegative-number? $value)
   (if (== (get-metatype $value) Grounded)
       (>= $value 0)
       False))

(= (tk-required-role-error $facts $role $missing $duplicate)
   (let $count (size-atom
                 (filter-atom (tk-rows $facts thread-role) $row
                   (== (index-atom $row 2) $role)))
     (if (== $count 0) $missing
         (if (> $count 1) $duplicate none))))

(= (tk-role-value $facts $role)
   (index-atom
     (index-atom
       (filter-atom (tk-rows $facts thread-role) $row
         (== (index-atom $row 2) $role))
       0)
     3))

(= (tk-optional-role-value $facts $role)
   (let $rows (filter-atom (tk-rows $facts thread-role) $row
                 (== (index-atom $row 2) $role))
     (if (== $rows ()) none (index-atom (index-atom $rows 0) 3))))

(= (tk-role-key-valid? $key)
   (or (== $key control)
   (or (== $key worker)
   (or (== $key supervisor)
   (or (== $key evaluator)
   (or (== $key specialist)
       (== $key adjudicator)))))))

(= (tk-capability-valid? $capability)
   (or (== $capability local)
   (or (== $capability specialist)
       (== $capability either))))

(= (tk-stakes-valid? $stakes)
   (or (== $stakes normal) (== $stakes high)))

(= (tk-merge-valid? $row)
   (let* (($mode (index-atom $row 2))
          ($branch (index-atom $row 3)))
     (or (and (== $mode none) (== $branch none))
         (and (== $mode integration-branch) (tk-symbol? $branch)))))

(= (tk-budget-valid? $row)
   (let* (($ceiling (index-atom $row 2))
          ($soft (index-atom $row 3))
          ($min-local (index-atom $row 4)))
     (if (tk-positive-number? $ceiling)
         (if (tk-nonnegative-number? $soft)
             (if (tk-nonnegative-number? $min-local)
                 (<= $soft $ceiling)
                 False)
             False)
         False)))

(= (tk-supervision-valid? $row)
   (let* (($lease (index-atom $row 2))
          ($idle (index-atom $row 3))
          ($wall (index-atom $row 4))
          ($retries (index-atom $row 5)))
     (if (tk-positive-number? $lease)
         (if (tk-positive-number? $idle)
             (if (tk-positive-number? $wall)
                 (if (tk-nonnegative-number? $retries)
                     (<= $idle $wall)
                     False)
                 False)
             False)
         False)))

(= (tk-structural-errors $facts)
   (let $bad-arity (tk-bad-arity $facts)
     (if (not (== $bad-arity ()))
         (invalid-arity)
         (filter-atom
           ((tk-single-error $facts thread-spec-v1 missing-spec duplicate-spec)
            (tk-single-error $facts thread-title missing-title duplicate-title)
            (tk-single-error $facts thread-owner missing-owner duplicate-owner)
            (tk-single-error $facts thread-budget missing-budget duplicate-budget)
            (tk-single-error $facts thread-supervision missing-supervision duplicate-supervision)
            (tk-single-error $facts thread-merge-policy missing-merge-policy duplicate-merge-policy)
            (tk-required-role-error $facts control missing-control-role duplicate-control-role)
            (tk-required-role-error $facts worker missing-worker-role duplicate-worker-role)
            (tk-required-role-error $facts supervisor missing-supervisor-role duplicate-supervisor-role)
            (tk-required-role-error $facts evaluator missing-evaluator-role duplicate-evaluator-role)
            (tk-required-role-error $facts specialist missing-specialist-role duplicate-specialist-role)
            (if (== (tk-count $facts thread-task) 0) missing-task none))
           $error (not (== $error none))))))

(= (tk-semantic-errors $facts)
   (let* (($thread-ids
            (unique-atom (tk-values-at $facts 1)))
          ($roles (tk-rows $facts thread-role))
          ($role-keys (tk-values-at $roles 2))
          ($role-identities (tk-values-at $roles 3))
          ($tasks (tk-rows $facts thread-task))
          ($task-ids (tk-values-at $tasks 2))
          ($dependencies (tk-rows $facts thread-depends))
          ($dependency-sources (tk-values-at $dependencies 2))
          ($dependency-targets (tk-values-at $dependencies 3))
          ($missing-task-refs
            (union-atom
              (subtraction-atom $dependency-sources $task-ids)
              (subtraction-atom $dependency-targets $task-ids)))
          ($self-dependencies
            (filter-atom $dependencies $row
              (== (index-atom $row 2) (index-atom $row 3))))
          ($cyclic-tasks (tk-cyclic-tasks $dependencies))
          ($bad-role-keys
            (filter-atom $role-keys $key (not (tk-role-key-valid? $key))))
          ($bad-capabilities
            (filter-atom $tasks $row
              (not (tk-capability-valid? (index-atom $row 3)))))
          ($bad-stakes
            (filter-atom $tasks $row
              (not (tk-stakes-valid? (index-atom $row 5)))))
          ($budget-row (index-atom (tk-rows $facts thread-budget) 0))
          ($supervision-row (index-atom (tk-rows $facts thread-supervision) 0))
          ($merge-row (index-atom (tk-rows $facts thread-merge-policy) 0)))
     (filter-atom
       ((if (not (== (size-atom $thread-ids) 1)) mixed-thread-id none)
        (if (not (== (size-atom $task-ids)
                     (size-atom (unique-atom $task-ids))))
            duplicate-task none)
        (if (not (== (size-atom $dependencies)
                     (size-atom (unique-atom $dependencies))))
            duplicate-dependency none)
        (if (not (== $missing-task-refs ())) missing-dependency none)
        (if (not (== $self-dependencies ())) self-dependency none)
        (if (not (== $cyclic-tasks ())) dependency-cycle none)
        (if (not (== $bad-role-keys ())) invalid-role none)
        (if (not (== (size-atom $role-identities)
                     (size-atom (unique-atom $role-identities))))
            duplicate-role-identity none)
        (if (not (== $bad-capabilities ())) invalid-capability none)
        (if (not (== $bad-stakes ())) invalid-stakes none)
        (if (not (tk-budget-valid? $budget-row)) invalid-budget none)
        (if (not (tk-supervision-valid? $supervision-row))
            invalid-supervision none)
        (if (not (tk-merge-valid? $merge-row)) invalid-merge-policy none))
       $error (not (== $error none)))))

(= (tk-validation-errors $facts)
   (let $structural (tk-structural-errors $facts)
     (if (== $structural ())
         (tk-semantic-errors $facts)
         $structural)))

(= (tk-dependencies-for $facts $task)
   (sort-atom
     (map-atom
       (filter-atom (tk-rows $facts thread-depends) $row
         (== (index-atom $row 2) $task))
       $row (index-atom $row 3))))

(= (tk-compiled-task $facts $row)
   (let (thread-task $thread $task $capability $acceptance $stakes) $row
     (task $task $capability $acceptance $stakes
       (depends (tk-dependencies-for $facts $task)))))

(= (tk-compilation $facts)
   (let $errors (tk-validation-errors $facts)
     (if (not (== $errors ()))
         (compilation (valid False) (errors $errors))
         (let* (((thread-spec-v1 $thread)
                  (index-atom (tk-rows $facts thread-spec-v1) 0))
                ((thread-title $_ $title)
                  (index-atom (tk-rows $facts thread-title) 0))
                ((thread-owner $_ $owner)
                  (index-atom (tk-rows $facts thread-owner) 0))
                ((thread-budget $_ $ceiling $soft $min-local)
                  (index-atom (tk-rows $facts thread-budget) 0))
                ((thread-supervision $_ $lease $idle $wall $retries)
                  (index-atom (tk-rows $facts thread-supervision) 0))
                ((thread-merge-policy $_ $merge-mode $integration-branch)
                  (index-atom (tk-rows $facts thread-merge-policy) 0)))
           (compilation
             (valid True)
             (errors ())
             (thread $thread $title $owner)
             (budget $ceiling $soft $min-local)
             (supervision $lease $idle $wall $retries)
             (roles
               (tk-role-value $facts control)
               (tk-role-value $facts worker)
               (tk-role-value $facts supervisor)
               (tk-role-value $facts evaluator)
               (tk-role-value $facts specialist)
               (tk-optional-role-value $facts adjudicator))
             (tasks
               (map-atom (tk-rows $facts thread-task) $row
                 (tk-compiled-task $facts $row)))
             (merge-policy $merge-mode $integration-branch))))))

(= (gc-thread-compile $facts-source)
   (gc-thread-ok compile (tk-compilation (sread $facts-source))))

; Compile the validated thread graph into native OmegaClaw directive atoms.
; Python supplies the date and persists the resulting text. MeTTa owns every
; task symbol, dependency conjunction, and assignment clause.
(= (tk-atom-concat $left $right)
   (atomic_list_concat ($left $right)))

(= (tk-conjunction $terms)
   (if (== (size-atom $terms) 1)
       (car-atom $terms)
       (cons-atom and
         ((car-atom $terms) (tk-conjunction (cdr-atom $terms))))))

(= (tk-prefixed-values $prefix $values)
   (map-atom $values $value (tk-atom-concat $prefix $value)))

(= (tk-assigned-agent $facts $capability)
   (if (== $capability specialist)
       (tk-role-value $facts specialist)
       (tk-role-value $facts worker)))

(= (tk-task-plan-lines $facts $row)
   (let (thread-task $thread $task $capability $acceptance $stakes) $row
     (let* (($task-symbol (tk-atom-concat task- $task))
            ($ready-symbol (tk-atom-concat ready- $task))
            ($dependencies (tk-dependencies-for $facts $task))
            ($completed
              (tk-prefixed-values completed- $dependencies))
            ($agent (tk-assigned-agent $facts $capability))
            ($agent-symbol
              (tk-atom-concat "agent-"
                (tk-atom-concat $agent "-available")))
            ($assignment
              (tk-atom-concat "assign-to-"
                (tk-atom-concat $task
                  (tk-atom-concat "-" $agent))))
            ($readiness
              (if (== $dependencies ())
                  (tk-conjunction
                    ($task-symbol (tk-atom-concat "no-deps-" $task)))
                  (tk-conjunction
                    (cons-atom $task-symbol $completed)))))
       (if (== $dependencies ())
           ((cons-atom given ($task-symbol))
            (cons-atom given ((tk-atom-concat "no-deps-" $task)))
            (cons-atom normally
              ($ready-symbol $readiness $ready-symbol))
            (cons-atom normally
              ($assignment
               (tk-conjunction ($ready-symbol $agent-symbol))
               $assignment)))
           ((cons-atom given ($task-symbol))
            (cons-atom normally
              ($ready-symbol $readiness $ready-symbol))
            (cons-atom normally
              ($assignment
               (tk-conjunction ($ready-symbol $agent-symbol))
               $assignment)))))))

(= (tk-task-plan-lines-all $facts $rows)
   (if (== $rows ())
       ()
       (union-atom
         (tk-task-plan-lines $facts (car-atom $rows))
         (tk-task-plan-lines-all $facts (cdr-atom $rows)))))

(= (tk-plan-lines $facts $digest $created)
   (let* (((thread-spec-v1 $thread)
            (index-atom (tk-rows $facts thread-spec-v1) 0))
          ((thread-title $_ $title)
            (index-atom (tk-rows $facts thread-title) 0))
          ((thread-owner $_ $owner)
            (index-atom (tk-rows $facts thread-owner) 0))
          ($agents
            (sort-atom
              (unique-atom
                ((tk-role-value $facts worker)
                 (tk-role-value $facts specialist)))))
          ($metadata
            (cons-atom meta
              (plan
               (cons-atom id ((repr $thread)))
               (cons-atom title ($title))
               (cons-atom version ("thread-spec-v1"))
               (cons-atom status ("active"))
               (cons-atom created ($created))
               (cons-atom author
                 ((repr (tk-atom-concat agent: $owner))))
               (cons-atom source-digest ($digest)))))
          ($availability
            (map-atom $agents $agent
              (cons-atom given
                ((tk-atom-concat "agent-"
                   (tk-atom-concat $agent "-available"))))))
          ($tasks
            (tk-task-plan-lines-all
              $facts (tk-rows $facts thread-task))))
     (cons-atom $metadata (union-atom $availability $tasks))))

(= (gc-thread-plan $facts-source $digest $created)
   (let $facts (sread $facts-source)
     (let $errors (tk-validation-errors $facts)
       (if (== $errors ())
           (gc-thread-ok plan
             (plan
               (lines
                 (map-atom
                   (tk-plan-lines $facts $digest $created)
                   $line
                   (repr $line)))))
           (goalchainer-thread-v1 plan error
             (validation $errors))))))

; Mettabase's MeTTa facade owns Markdown parsing. Thread facts remain quoted
; data throughout this path, so source fences cannot execute host effects.
(= (tk-md-action $block $entry)
   (case $entry
     (((md-add $index $atom)
       (action $block add (+ $index 1) (repr $atom)))
      ((md-eval $index $atom)
       (action $block eval (+ $index 1) (repr $atom)))
      ($_ (empty)))))

(= (tk-md-code-actions $block $quoted)
   (map-atom (cdr-atom $quoted) $entry (tk-md-action $block $entry)))

(= (tk-md-actions-walk $facts)
   (if (== (size-atom $facts) 0)
       ()
       (let* (($row (car-atom $facts))
              ($rest (tk-md-actions-walk (cdr-atom $facts))))
         (case $row
           (((md-metta-code $block $quoted)
             (union-atom
               (tk-md-code-actions $block $quoted)
               $rest))
            ($_ $rest))))))

(= (tk-md-diagnostics-walk $facts)
   (if (== (size-atom $facts) 0)
       ()
       (let* (($row (car-atom $facts))
              ($rest (tk-md-diagnostics-walk (cdr-atom $facts))))
         (case $row
           (((md-diagnostic $block metta-parse-failed $message)
             (union-atom ((diagnostic $block $message)) $rest))
            ($_ $rest))))))

(= (tk-md-sources-walk $facts)
   (if (== (size-atom $facts) 0)
       ()
       (let* (($row (car-atom $facts))
              ($rest (tk-md-sources-walk (cdr-atom $facts))))
         (case $row
           (((md-source $block $source)
             (union-atom ((source $block $source)) $rest))
            ($_ $rest))))))

(= (gc-thread-markdown $source)
   (let* (($atoms (md-atoms $source thread-spec))
          ($facts (cdr-atom $atoms)))
     (gc-thread-ok markdown
       (markdown
         (actions (tk-md-actions-walk $facts))
         (diagnostics (tk-md-diagnostics-walk $facts))
         (sources (tk-md-sources-walk $facts))))))

; Build the status document as Mettabase's authoring AST. Python observes the
; filesystem-backed board and audit log, then passes data rows to this function.
(= (tk-status-table $name $headings $rows)
   (cons-atom table
     (cons-atom
       (cons-atom id ($name))
       (cons-atom
         (cons-atom align
           (map-atom $headings $heading none))
         (cons-atom
           (cons-atom head $headings)
           $rows)))))

(= (tk-status-budget-rows $ceiling $soft $spent)
   ((cons-atom row ("Ceiling" (repr $ceiling)))
    (cons-atom row ("Soft threshold" (repr $soft)))
    (cons-atom row ("Spent" (repr $spent)))
    (cons-atom row
      ("Remaining" (repr (max 0 (- $ceiling $spent)))))))

(= (tk-status-specification $facts)
   (cons-atom metta
     (map-atom $facts $fact (cons-atom add ($fact)))))

(= (tk-status-document $title $facts $board $ceiling $soft $spent
                        $attempts $audit)
   (cons-atom md
     (goalchainer-thread-status
      (cons-atom h1 ($title))
      (cons-atom p
        ("OmegaClaw owns task state. PeTTa owns routing and attempt policy."))
      (cons-atom h2 ("Board"))
      (tk-status-table
        thread-board ("Task" "State") $board)
      (cons-atom h2 ("Budget"))
      (tk-status-table
        thread-budget
        ("Measure" "Tokens")
        (tk-status-budget-rows $ceiling $soft $spent))
      (cons-atom h2 ("Attempts"))
      (tk-status-table
        thread-attempts
        ("Task" "Attempt" "Exit" "Evaluation" "Outcome")
        $attempts)
      (cons-atom h2 ("Audit chain"))
      (tk-status-table
        thread-audit
        ("Sequence" "Timestamp" "Event" "Actor" "Hash")
        $audit)
      (cons-atom h2 ("MeTTa Markdown specification"))
      (tk-status-specification $facts))))

(= (gc-thread-status $title $facts-source $board-source
                     $ceiling $soft $spent
                     $attempts-source $audit-source)
   (gc-thread-ok status
     (status-document
       (document
         (repr
           (tk-status-document
             $title
             (sread $facts-source)
             (sread $board-source)
             $ceiling $soft $spent
             (sread $attempts-source)
             (sread $audit-source)))))))

; ThreadKeeper's budget gate. The local-iteration guard precedes the budget
; ceiling to retain the public ThreadKeeper branch behavior exactly.
(= (tk-escalate $spent $ceiling $soft $min-local $iterations $hard)
   (if (< $iterations $min-local) (deny "iterate cheaply first")
   (if (>= $spent $ceiling) (deny "budget exhausted")
   (if (< $spent $soft) (allow "under soft threshold")
   (if (== $hard True) (allow "subproblem flagged hard")
                         (deny "not hard enough to justify spend"))))))

(= (tk-route $capability $stakes $spent $ceiling $soft $min-local
             $iterations $hard $adjudicator-enabled)
   (if (== $capability local)
       (route worker True "local task" False)
       (if (and (== $capability either) (== $hard False))
           (route worker True "local path sufficient" False)
           (let ($verdict $reason)
                (tk-escalate $spent $ceiling $soft $min-local $iterations $hard)
             (if (== $verdict allow)
                 (route specialist True $reason
                   (and (== $stakes high) (== $adjudicator-enabled True)))
                 (route denied False $reason False))))))

(= (gc-thread-route $capability $stakes $spent $ceiling $soft $min-local
                    $iterations $hard $adjudicator-enabled)
   (gc-thread-ok route
     (tk-route $capability $stakes $spent $ceiling $soft $min-local
               $iterations $hard $adjudicator-enabled)))

(= (tk-attempt-failure-reason $exit-reason $exit-code $evaluator
                              $adjudication-required $adjudicator)
   (if (== $exit-reason idle-timeout) "worker idle timeout"
   (if (== $exit-reason wall-timeout) "worker wall timeout"
   (if (not (== $exit-code 0)) "worker exited with nonzero status"
   (if (not (== $evaluator accept)) "evaluator rejected result"
   (if (and (== $adjudication-required True)
            (not (== $adjudicator accept)))
       "adjudicator rejected result"
       "attempt rejected"))))))

(= (tk-outcome $exit-reason $exit-code $evaluator $attempt $max-retries
               $adjudication-required $adjudicator)
   (if (and (== $exit-reason process-exited)
            (and (== $exit-code 0)
                 (and (== $evaluator accept)
                      (or (== $adjudication-required False)
                          (== $adjudicator accept)))))
       (outcome complete "accepted by evaluator")
       (let $reason
            (tk-attempt-failure-reason
              $exit-reason $exit-code $evaluator
              $adjudication-required $adjudicator)
         (if (<= $attempt $max-retries)
             (outcome retry $reason)
             (outcome permanent-failure $reason)))))

(= (gc-thread-outcome $exit-reason $exit-code $evaluator $attempt $max-retries
                      $adjudication-required $adjudicator)
   (gc-thread-ok outcome
     (tk-outcome $exit-reason $exit-code $evaluator $attempt $max-retries
                 $adjudication-required $adjudicator)))

; PeTTa owns one complete worker attempt. Python atoms provide the two effects
; MeTTa cannot perform itself: bounded process execution and evaluator process
; invocation. Observation, gating, adjudication, and outcome stay in MeTTa.
(= (tk-host-process $command $cwd $lease $idle $wall $environment $pty)
   (sread
     (py-call
       (goalchainer_thread_atoms.run_process
         $command $cwd $lease $idle $wall $environment $pty))))

(= (tk-host-verdict $command $cwd $task $capability $acceptance $stakes
                     $observation $lease $idle $wall)
   (let (observation $exit-reason $exit-code $output $output-bytes
                     $duration $activity $renewals)
        $observation
     (sread
       (py-call
         (goalchainer_thread_atoms.evaluate
           $command $cwd $task $capability $acceptance $stakes
           $exit-reason $exit-code $output $output-bytes
           $duration $activity $renewals $lease $idle $wall)))))

(= (tk-evaluate-attempt $identity $command $cwd $task $capability
                         $acceptance $stakes $observation $lease $idle $wall)
   (let (observation $exit-reason $exit-code $output $output-bytes
                     $duration $activity $renewals)
        $observation
     (if (or (not (== $exit-reason process-exited))
             (not (== $exit-code 0)))
         (evaluation $identity reject
           b64_d29ya2VyIGRpZCBub3QgZXhpdCBzdWNjZXNzZnVsbHk=)
         (let $host-verdict
              (tk-host-verdict
                $command $cwd $task $capability $acceptance $stakes
                $observation $lease $idle $wall)
           (evaluation
             $identity
             (index-atom $host-verdict 1)
             (index-atom $host-verdict 2))))))

(= (tk-adjudicate-attempt $required $identity $command $cwd $task
                           $capability $acceptance $stakes $observation
                           $lease $idle $wall)
   (if (== $required False)
       (evaluation none not-required
         b64_YWRqdWRpY2F0aW9uIG5vdCByZXF1aXJlZA==)
       (if (== $command b64_W10=)
           (evaluation $identity reject
             b64_YWRqdWRpY2F0b3IgaW1wbGVtZW50YXRpb24gd2FzIG5vdCBzdXBwbGllZA==)
           (tk-evaluate-attempt
             $identity $command $cwd $task $capability $acceptance $stakes
             $observation $lease $idle $wall))))

(= (tk-evaluation-verdict $evaluation)
   (let (evaluation $identity $verdict $reason) $evaluation $verdict))

(= (gc-thread-attempt
      $worker-command $evaluator-command $adjudicator-command
      $cwd $environment $pty
      $task $capability $acceptance $stakes
      $evaluator-identity $adjudicator-identity
      $lease $idle $wall $attempt $max-retries $adjudication-required)
   (let* (($observation
            (tk-host-process
              $worker-command $cwd $lease $idle $wall $environment $pty))
          ($evaluation
            (tk-evaluate-attempt
              $evaluator-identity $evaluator-command $cwd
              $task $capability $acceptance $stakes
              $observation $lease $idle $wall))
          ($adjudication
            (tk-adjudicate-attempt
              $adjudication-required $adjudicator-identity
              $adjudicator-command $cwd
              $task $capability $acceptance $stakes
              $observation $lease $idle $wall))
          ((observation $exit-reason $exit-code $output $output-bytes
                        $duration $activity $renewals)
            $observation)
          ($outcome
            (tk-outcome
              $exit-reason $exit-code
              (tk-evaluation-verdict $evaluation)
              $attempt $max-retries $adjudication-required
              (tk-evaluation-verdict $adjudication))))
     (gc-thread-ok attempt
       (attempt-result
         $observation
         $evaluation
         $adjudication
         $outcome))))
