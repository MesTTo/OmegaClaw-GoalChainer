;; MeTTaScript policy and compilation layer for ThreadKeeper orchestration.
;; Mettabase parses Markdown. This file validates its normalized data facts,
;; derives scheduling, routing, projection, and attempt outcomes, and returns
;; versioned records. PeTTa can still evaluate the same compatibility surface.

(= (gc-thread-ok $operation $payload)
   (goalchainer-thread-v1 $operation ok $payload))

(= (tk-row-head $row)
   (if (== (get-mettatype $row) Expression)
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
      (thread-not-before 4)
      (thread-workflow 3)
      (thread-workflow-step 5)
      (thread-merge-policy 4)
      ($other -1))))

(= (tk-rows $facts $head)
   (filter-atom $facts $row (== (tk-row-head $row) $head)))

(= (tk-count $facts $head)
   (size-atom (tk-rows $facts $head)))

(= (tk-count-error $count $missing $duplicate)
   (if (== $count 0) $missing
       (if (> $count 1) $duplicate none)))

(= (tk-single-error $facts $head $missing $duplicate)
   (tk-count-error (tk-count $facts $head) $missing $duplicate))

(= (tk-bad-arity $facts)
   (filter-atom $facts $row
     (not (== (size-atom $row) (tk-expected-arity (tk-row-head $row))))))

(= (tk-values-at $rows $index)
   (map-atom $rows $row (index-atom $row $index)))

;; Dependency traversal is deterministic. It does not depend on Empty values
;; produced by a collapsed nondeterministic branch, which differ between
;; MeTTaScript and PeTTa.
(= (tk-dependency-edges $dependencies)
   (unique-atom
     (map-atom $dependencies $row
       ((index-atom $row 2) (index-atom $row 3)))))

(= (tk-neighbors $edges $task)
   (let $matching
        (filter-atom $edges $edge
          (== (index-atom $edge 0) $task))
     (map-atom $matching $edge (index-atom $edge 1))))

(= (tk-member? $values $value)
   (not (== (intersection-atom $values ($value)) ())))

(= (tk-any-reaches? $edges $neighbors $target $visited)
   (if (== $neighbors ())
       False
       (let* (($next (car-atom $neighbors))
              ($rest (cdr-atom $neighbors)))
         (if (== $next $target)
             True
             (if (tk-reaches? $edges $next $target $visited)
                 True
                 (tk-any-reaches? $edges $rest $target $visited))))))

(= (tk-reaches? $edges $task $target $visited)
   (if (tk-member? $visited $task)
       False
       (tk-any-reaches?
         $edges
         (tk-neighbors $edges $task)
         $target
         (cons-atom $task $visited))))

(= (tk-cyclic-tasks-walk $edges $tasks)
   (if (== $tasks ())
       ()
       (let* (($task (car-atom $tasks))
              ($rest (tk-cyclic-tasks-walk $edges (cdr-atom $tasks))))
         (if (tk-reaches? $edges $task $task ())
             (cons-atom $task $rest)
             $rest))))

(= (tk-cyclic-tasks $dependencies)
   (let* (($edges (tk-dependency-edges $dependencies))
          ($tasks
            (unique-atom
              (union-atom
                (tk-values-at $edges 0)
                (tk-values-at $edges 1)))))
     (tk-cyclic-tasks-walk $edges $tasks)))

(= (tk-symbol? $value)
   (== (get-mettatype $value) Symbol))

(= (tk-string? $value)
   (== (get-type $value) String))

(= (tk-positive-number? $value)
   (if (== (get-mettatype $value) Grounded)
       (> $value 0)
       False))

(= (tk-nonnegative-number? $value)
   (if (== (get-mettatype $value) Grounded)
       (>= $value 0)
       False))

(= (tk-role-rows-walk $rows $role)
   (if (== $rows ())
       ()
       (let* (($row (car-atom $rows))
              ($rest (tk-role-rows-walk (cdr-atom $rows) $role)))
         (if (== (index-atom $row 2) $role)
             (cons-atom $row $rest)
             $rest))))

(= (tk-role-rows $facts $role)
   (tk-role-rows-walk (tk-rows $facts thread-role) $role))

(= (tk-required-role-error $facts $role $missing $duplicate)
   (tk-count-error
     (size-atom (tk-role-rows $facts $role))
     $missing
     $duplicate))

(= (tk-role-value $facts $role)
   (index-atom (index-atom (tk-role-rows $facts $role) 0) 3))

(= (tk-optional-role-value $facts $role)
   (let $rows (tk-role-rows $facts $role)
     (if (== $rows ()) none (index-atom (index-atom $rows 0) 3))))

(= (tk-has-duplicates? $values)
   (not
     (== (size-atom $values)
         (size-atom (unique-atom $values)))))

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

(= (tk-keep-errors $errors)
   (if (== $errors ())
       ()
       (let* (($error (car-atom $errors))
              ($rest (tk-keep-errors (cdr-atom $errors))))
         (if (== $error none)
             $rest
             (cons-atom $error $rest)))))

(= (tk-structural-errors $facts)
   (let $bad-arity (tk-bad-arity $facts)
     (if (not (== $bad-arity ()))
         (invalid-arity)
         (let* (($spec
                  (tk-single-error
                    $facts thread-spec-v1 missing-spec duplicate-spec))
                ($title
                  (tk-single-error
                    $facts thread-title missing-title duplicate-title))
                ($owner
                  (tk-single-error
                    $facts thread-owner missing-owner duplicate-owner))
                ($budget
                  (tk-single-error
                    $facts thread-budget missing-budget duplicate-budget))
                ($supervision
                  (tk-single-error
                    $facts thread-supervision
                    missing-supervision duplicate-supervision))
                ($merge
                  (tk-single-error
                    $facts thread-merge-policy
                    missing-merge-policy duplicate-merge-policy))
                ($workflow
                  (tk-single-error
                    $facts thread-workflow none duplicate-workflow))
                ($control
                  (tk-required-role-error
                    $facts control
                    missing-control-role duplicate-control-role))
                ($worker
                  (tk-required-role-error
                    $facts worker
                    missing-worker-role duplicate-worker-role))
                ($supervisor
                  (tk-required-role-error
                    $facts supervisor
                    missing-supervisor-role duplicate-supervisor-role))
                ($evaluator
                  (tk-required-role-error
                    $facts evaluator
                    missing-evaluator-role duplicate-evaluator-role))
                ($specialist
                  (tk-required-role-error
                    $facts specialist
                    missing-specialist-role duplicate-specialist-role))
                ($task
                  (if (== (tk-count $facts thread-task) 0)
                      missing-task
                      none)))
           (tk-keep-errors
             ($spec $title $owner $budget $supervision $merge $workflow
              $control $worker $supervisor $evaluator $specialist $task))))))

(= (tk-semantic-errors $facts)
   (let* (($thread-ids
            (unique-atom (tk-values-at $facts 1)))
          ($roles (tk-rows $facts thread-role))
          ($role-keys (tk-values-at $roles 2))
          ($role-identities (tk-values-at $roles 3))
          ($tasks (tk-rows $facts thread-task))
          ($task-ids (tk-values-at $tasks 2))
          ($dependencies (tk-rows $facts thread-depends))
          ($schedules (tk-rows $facts thread-not-before))
          ($schedule-tasks (tk-values-at $schedules 2))
          ($workflows (tk-rows $facts thread-workflow))
          ($workflow-steps (tk-rows $facts thread-workflow-step))
          ($workflow-ids (tk-values-at $workflows 2))
          ($step-workflow-ids (tk-values-at $workflow-steps 2))
          ($step-orders (tk-values-at $workflow-steps 3))
          ($dependency-sources (tk-values-at $dependencies 2))
          ($dependency-targets (tk-values-at $dependencies 3))
          ($missing-task-refs
            (union-atom
              (subtraction-atom $dependency-sources $task-ids)
              (subtraction-atom $dependency-targets $task-ids)))
          ($missing-schedule-refs
            (subtraction-atom $schedule-tasks $task-ids))
          ($bad-schedules
            (filter-atom $schedules $row
              (not (tk-nonnegative-number? (index-atom $row 3)))))
          ($bad-workflow-steps
            (filter-atom $workflow-steps $row
              (or (not (tk-positive-number? (index-atom $row 3)))
                  (not (tk-string? (index-atom $row 4))))))
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
          ($merge-row (index-atom (tk-rows $facts thread-merge-policy) 0))
          ($mixed-thread
            (if (not (== (size-atom $thread-ids) 1))
                mixed-thread-id none))
          ($duplicate-task
            (if (tk-has-duplicates? $task-ids)
                duplicate-task none))
          ($duplicate-dependency
            (if (tk-has-duplicates? $dependencies)
                duplicate-dependency none))
          ($missing-dependency
            (if (not (== $missing-task-refs ()))
                missing-dependency none))
          ($missing-schedule
            (if (not (== $missing-schedule-refs ()))
                missing-scheduled-task none))
          ($duplicate-schedule
            (if (tk-has-duplicates? $schedule-tasks)
                duplicate-task-schedule none))
          ($invalid-schedule
            (if (not (== $bad-schedules ()))
                invalid-task-schedule none))
          ($missing-workflow
            (if (and (== $workflows ())
                     (not (== $workflow-steps ())))
                missing-workflow none))
          ($invalid-workflow
            (if (or (tk-has-duplicates? $workflow-ids)
                    (not (== (subtraction-atom
                               (unique-atom $step-workflow-ids)
                               $workflow-ids)
                             ())))
                invalid-workflow-reference none))
          ($duplicate-workflow-step
            (if (tk-has-duplicates? $step-orders)
                duplicate-workflow-step-order none))
          ($invalid-workflow-step
            (if (not (== $bad-workflow-steps ()))
                invalid-workflow-step none))
          ($self-dependency
            (if (not (== $self-dependencies ()))
                self-dependency none))
          ($cycle
            (if (not (== $cyclic-tasks ()))
                dependency-cycle none))
          ($invalid-role
            (if (not (== $bad-role-keys ())) invalid-role none))
          ($duplicate-identity
            (if (tk-has-duplicates? $role-identities)
                duplicate-role-identity none))
          ($invalid-capability
            (if (not (== $bad-capabilities ()))
                invalid-capability none))
          ($invalid-stakes
            (if (not (== $bad-stakes ())) invalid-stakes none))
          ($invalid-budget
            (if (not (tk-budget-valid? $budget-row))
                invalid-budget none))
          ($invalid-supervision
            (if (not (tk-supervision-valid? $supervision-row))
                invalid-supervision none))
          ($invalid-merge
            (if (not (tk-merge-valid? $merge-row))
                invalid-merge-policy none)))
     (tk-keep-errors
       ($mixed-thread $duplicate-task $duplicate-dependency
        $missing-dependency $missing-schedule $duplicate-schedule
        $invalid-schedule $missing-workflow $invalid-workflow
        $duplicate-workflow-step $invalid-workflow-step $self-dependency
        $cycle $invalid-role $duplicate-identity $invalid-capability
        $invalid-stakes $invalid-budget $invalid-supervision
        $invalid-merge))))

(= (tk-validation-errors $facts)
   (let $structural (tk-structural-errors $facts)
     (if (== $structural ())
         (tk-semantic-errors $facts)
         $structural)))

(= (tk-task-rows $rows $task)
   (filter-atom $rows $row (== (index-atom $row 2) $task)))

(= (tk-dependencies-for $facts $task)
   (let* (($matching
            (tk-task-rows (tk-rows $facts thread-depends) $task))
          ($values
            (map-atom $matching $row (index-atom $row 3))))
     (sort-atom $values)))

(= (tk-not-before-for $facts $task)
   (let $rows (tk-task-rows (tk-rows $facts thread-not-before) $task)
     (if (== $rows ())
         none
         (index-atom (index-atom $rows 0) 3))))

(= (tk-compiled-task $facts $row)
   (let (thread-task $thread $task $capability $acceptance $stakes) $row
     (task $task $capability $acceptance $stakes
       (depends (tk-dependencies-for $facts $task))
       (not-before (tk-not-before-for $facts $task)))))

(= (tk-compiled-tasks-walk $facts $rows)
   (if (== $rows ())
       ()
       (let* (($task (tk-compiled-task $facts (car-atom $rows)))
              ($rest (tk-compiled-tasks-walk $facts (cdr-atom $rows))))
         (cons-atom $task $rest))))

(= (tk-workflow-steps $facts)
   (let $rows (tk-rows $facts thread-workflow-step)
     (sort-atom
       (map-atom $rows $step-row
         (step (index-atom $step-row 3)
               (index-atom $step-row 4))))))

(= (tk-compiled-workflow $facts)
   (let $workflows (tk-rows $facts thread-workflow)
     (if (== $workflows ())
         (workflow goalchainer-default
           ((step 10
              "Inspect the task context, repository guidance, and existing work before changing anything.")
            (step 20
              "Complete only the released task and verify its acceptance condition with concrete evidence.")
            (step 30
              "Report changed artifacts, checks run, remaining uncertainty, and any follow-up work.")))
         (let* (($workflow-row (index-atom $workflows 0))
                ($workflow (index-atom $workflow-row 2)))
           (workflow $workflow
             (tk-workflow-steps $facts))))))

(= (tk-thread-header $facts)
   (let* (((thread-spec-v1 $thread)
            (index-atom (tk-rows $facts thread-spec-v1) 0))
          ((thread-title $_ $title)
            (index-atom (tk-rows $facts thread-title) 0))
          ((thread-owner $_ $owner)
            (index-atom (tk-rows $facts thread-owner) 0)))
     (thread $thread $title $owner)))

(= (tk-compilation $facts)
   (let $errors (tk-validation-errors $facts)
     (if (not (== $errors ()))
         (compilation (valid False) (errors $errors))
         (let* (((thread $thread $title $owner)
                  (tk-thread-header $facts))
                ((thread-budget $_ $ceiling $soft $min-local)
                  (index-atom (tk-rows $facts thread-budget) 0))
                ((thread-supervision $_ $lease $idle $wall $retries)
                  (index-atom (tk-rows $facts thread-supervision) 0))
                ((thread-merge-policy $_ $merge-mode $integration-branch)
                  (index-atom (tk-rows $facts thread-merge-policy) 0))
                ($task-rows (tk-rows $facts thread-task))
                ($tasks (tk-compiled-tasks-walk $facts $task-rows)))
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
             (tk-compiled-workflow $facts)
             (tasks $tasks)
             (merge-policy $merge-mode $integration-branch))))))

(: gc-thread-compile (-> String %Undefined%))

(= (gc-thread-compile $facts-source)
   (gc-thread-ok compile (tk-compilation (sread $facts-source))))

;; Compile the validated thread graph into native OmegaClaw directive atoms.
;; The host supplies the date and persists the resulting text. MeTTa owns every
;; task symbol, dependency conjunction, and assignment clause.
(= (tk-atom-concat $left $right)
   (atom_concat $left $right))

(= (tk-conjunction-text $terms)
   (let $head (car-atom $terms)
     (if (== (size-atom $terms) 1)
         (repr $head)
         (let* (($tail (cdr-atom $terms))
                ($tail-source (tk-conjunction-text $tail))
                ($tail-condition (sread $tail-source))
                ($condition (cons-atom and ($head $tail-condition))))
           (repr $condition)))))

(= (tk-prefixed-values $prefix $values)
   (map-atom $values $value (tk-atom-concat $prefix $value)))

(= (tk-assigned-agent $facts $capability)
   (if (== $capability specialist)
       (tk-role-value $facts specialist)
       (tk-role-value $facts worker)))

(= (tk-given-line $symbol)
   (let $line (cons-atom given ($symbol))
     (repr $line)))

(= (tk-normally-line $name $condition-source)
   (let* (($condition (sread $condition-source))
          ($line (cons-atom normally ($name $condition $name))))
     (repr $line)))

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
            ($readiness-source
              (if (== $dependencies ())
                  (tk-conjunction-text
                    ($task-symbol (tk-atom-concat "no-deps-" $task)))
                  (tk-conjunction-text
                    (cons-atom $task-symbol $completed))))
            ($given-task (tk-given-line $task-symbol))
            ($ready-line
              (tk-normally-line $ready-symbol $readiness-source))
            ($assignment-condition-source
              (tk-conjunction-text ($ready-symbol $agent-symbol)))
            ($assignment-line
              (tk-normally-line
                $assignment $assignment-condition-source)))
       (if (== $dependencies ())
           (let $given-no-deps
                (tk-given-line (tk-atom-concat "no-deps-" $task))
             ($given-task $given-no-deps $ready-line $assignment-line))
           ($given-task $ready-line $assignment-line)))))

(= (tk-task-plan-lines-all $facts $rows)
   (if (== $rows ())
       ()
       (union-atom
         (tk-task-plan-lines $facts (car-atom $rows))
         (tk-task-plan-lines-all $facts (cdr-atom $rows)))))

(= (tk-plan-metadata $thread $title $owner $digest $created)
   (let* (($thread-text (repr $thread))
          ($agent (tk-atom-concat agent: $owner))
          ($agent-text (repr $agent))
          ($id-row (cons-atom id ($thread-text)))
          ($title-row (cons-atom title ($title)))
          ($version-row (cons-atom version ("thread-spec-v1")))
          ($status-row (cons-atom status ("active")))
          ($created-row (cons-atom created ($created)))
          ($author-row (cons-atom author ($agent-text)))
          ($digest-row (cons-atom source-digest ($digest)))
          ($line
            (cons-atom meta
              (plan
               $id-row
               $title-row
               $version-row
               $status-row
               $created-row
               $author-row
               $digest-row))))
     (repr $line)))

(= (tk-agent-availability-line $agent)
   (let* (($suffix (tk-atom-concat $agent "-available"))
          ($symbol (tk-atom-concat "agent-" $suffix)))
     (tk-given-line $symbol)))

(= (tk-plan-lines $facts $digest $created)
   (let* (((thread $thread $title $owner)
            (tk-thread-header $facts))
          ($agents
            (sort-atom
              (unique-atom
                ((tk-role-value $facts worker)
                 (tk-role-value $facts specialist)))))
          ($metadata
            (tk-plan-metadata $thread $title $owner $digest $created))
          ($availability
            (map-atom $agents $agent
              (tk-agent-availability-line $agent)))
          ($tasks
            (tk-task-plan-lines-all
              $facts (tk-rows $facts thread-task)))
          ($body (union-atom $availability $tasks)))
     (cons-atom $metadata $body)))

(: gc-thread-plan (-> String String String %Undefined%))

(= (gc-thread-plan $facts-source $digest $created)
   (let $facts (sread $facts-source)
     (let $errors (tk-validation-errors $facts)
       (if (== $errors ())
           (gc-thread-ok plan
             (plan
               (lines
                 (let $plan-lines
                      (tk-plan-lines $facts $digest $created)
                   $plan-lines))))
           (goalchainer-thread-v1 plan error
             (validation $errors))))))

;; Mettabase's MeTTa facade owns Markdown parsing. Thread facts remain quoted
;; data throughout this path, so source fences cannot execute host effects.
(= (tk-md-action $block $entry)
   (case $entry
     (((md-add $index $atom)
       (action $block add (+ $index 1) (repr $atom)))
      ((md-eval $index $atom)
       (action $block eval (+ $index 1) (repr $atom)))
      ($_ (empty)))))

(= (tk-md-code-actions-loop $block $entries $reversed)
   (if (== $entries ())
       (reverse $reversed)
       (let* (($action (tk-md-action $block (car-atom $entries)))
              ($remaining (cdr-atom $entries))
              ($next (cons-atom $action $reversed)))
         (tk-md-code-actions-loop $block $remaining $next))))

(= (tk-md-code-actions $block $quoted)
   (let $entries (cdr-atom $quoted)
     (tk-md-code-actions-loop $block $entries ())))

(= (tk-space-from-rows $rows)
   (let $space (new-space)
     (foldl-atom
       $rows
       $space
       $current
       $row
       (let $_ (add-atom $current $row) $current))))

;; collapse returns a comma-headed tuple. The protocol carries the matched
;; graph values, not the evaluator's comma marker.
(= (tk-collapse-values $collapsed)
   (let ($_ $values) (decons-atom $collapsed) $values))

(= (tk-basic-md-action $block $kind $index $source)
   ;; Mettabase action is a data constructor, not MetaMo's executable symbol.
   ;; @suppress symbol.needsImport
   (action $block $kind (+ $index 1) $source))

(= (tk-md-action-row $block $kind $index $source)
   (if (== $kind add)
       (let $quoted (sread $source)
         (case $quoted
           (((quote
               (goalchainer-thread-specification $facts))
             (let $actions
                  (map-atom $facts $fact
                    (let* (($quoted-fact (cons-atom quote ($fact)))
                           ($fact-source (repr $quoted-fact)))
                      (action
                        $block add (+ $index 1) $fact-source)))
               (superpose $actions)))
            ($_ (tk-basic-md-action $block $kind $index $source)))))
       (tk-basic-md-action $block $kind $index $source)))

(= (tk-md-action-from-row $row)
   (case $row
     (((md-action $block $kind $index $source)
       (tk-md-action-row $block $kind $index $source))
      ((md-metta-code $block $quoted)
       (let $actions (tk-md-code-actions $block $quoted)
         (superpose $actions)))
      ($_ (empty)))))

(= (tk-md-actions-in $space)
   (match $space $row (tk-md-action-from-row $row)))

(= (tk-md-diagnostics-in $space)
   (match $space
     (md-diagnostic $block metta-parse-failed $message)
     (diagnostic $block $message)))

(= (tk-md-sources-in $space)
   (match $space
     (md-source $block $source)
     (source $block $source)))

(: gc-thread-markdown-atoms (-> String %Undefined%))

(= (tk-thread-markdown $atoms)
   (let* (($space (tk-space-from-rows $atoms))
          ($actions
            (tk-collapse-values (collapse (tk-md-actions-in $space))))
          ($diagnostics
            (tk-collapse-values (collapse (tk-md-diagnostics-in $space))))
          ($sources
            (tk-collapse-values (collapse (tk-md-sources-in $space))))
          ($actions-row (cons-atom actions ($actions)))
          ($diagnostics-row (cons-atom diagnostics ($diagnostics)))
          ($sources-row (cons-atom sources ($sources)))
          ($payload
            (cons-atom markdown
              ($actions-row $diagnostics-row $sources-row)))
          ($record
            (cons-atom goalchainer-thread-v1
              (markdown ok $payload))))
     $record))

(= (gc-thread-markdown-atoms $atoms-source)
   (let $atoms (sread $atoms-source)
     (tk-thread-markdown $atoms)))

;; Build the status document as Mettabase's authoring AST. The host observes the
;; filesystem-backed board and audit log, then passes data rows to this function.
(= (tk-status-table $name $headings $rows)
   (let* (($alignments (map-atom $headings $heading none))
          ($id-row (cons-atom id ($name)))
          ($align-row (cons-atom align $alignments))
          ($head-row (cons-atom head $headings))
          ($table-rows (cons-atom $head-row $rows))
          ($table-body (cons-atom $align-row $table-rows))
          ($table-attributes (cons-atom $id-row $table-body)))
     (cons-atom table $table-attributes)))

(= (tk-status-budget-rows $ceiling $soft $spent)
   (let* (($ceiling-text (repr $ceiling))
          ($soft-text (repr $soft))
          ($spent-text (repr $spent))
          ($remaining (max 0 (- $ceiling $spent)))
          ($remaining-text (repr $remaining))
          ($ceiling-row (cons-atom row ("Ceiling" $ceiling-text)))
          ($soft-row (cons-atom row ("Soft threshold" $soft-text)))
          ($spent-row (cons-atom row ("Spent" $spent-text)))
          ($remaining-row (cons-atom row ("Remaining" $remaining-text))))
     ($ceiling-row $soft-row $spent-row $remaining-row)))

(= (tk-status-document $title $facts $board $ceiling $soft $spent
                        $attempts $audit)
   (let* (($title-block (cons-atom h1 ($title)))
          ($authority-block
            (cons-atom p
              ("OmegaClaw owns task state. MeTTaScript owns routing and attempt policy.")))
          ($board-heading (cons-atom h2 ("Board")))
          ($board-table
            (tk-status-table
              thread-board ("Task" "State") $board))
          ($budget-heading (cons-atom h2 ("Budget")))
          ($budget-rows
            (tk-status-budget-rows $ceiling $soft $spent))
          ($budget-table
            (tk-status-table
              thread-budget ("Measure" "Tokens") $budget-rows))
          ($attempts-heading (cons-atom h2 ("Attempts")))
          ($attempts-table
            (tk-status-table
              thread-attempts
              ("Task" "Attempt" "Exit" "Evaluation" "Outcome")
              $attempts))
          ($audit-heading (cons-atom h2 ("Audit chain")))
          ($audit-table
            (tk-status-table
              thread-audit
              ("Sequence" "Timestamp" "Event" "Actor" "Hash")
              $audit))
          ($specification-heading
            (cons-atom h2 ("MeTTa Markdown specification")))
          ($space (new-space))
          ($_stored
            (add-atom $space
              (md
                goalchainer-thread-status
                $title-block
                $authority-block
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
                    (goalchainer-thread-specification $facts)))))))
     (match $space $document (repr $document))))

(: gc-thread-status
  (-> String String String Number Number Number String String %Undefined%))

(= (gc-thread-status $title $facts-source $board-source
                     $ceiling $soft $spent
                     $attempts-source $audit-source)
   (let* (($facts (sread $facts-source))
          ($board (sread $board-source))
          ($attempts (sread $attempts-source))
          ($audit (sread $audit-source))
          ($document-source
            (tk-status-document
              $title $facts $board
              $ceiling $soft $spent
              $attempts $audit)))
     (gc-thread-ok status
       (status-document
         (document $document-source)))))

;; ThreadKeeper's budget gate. The local-iteration guard precedes the budget
;; ceiling to retain the public ThreadKeeper branch behavior exactly.
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

(: gc-thread-route
  (-> Atom Atom Number Number Number Number Number Bool Bool %Undefined%))

(= (gc-thread-route $capability $stakes $spent $ceiling $soft $min-local
                    $iterations $hard $adjudicator-enabled)
   (gc-thread-ok route
     (tk-route $capability $stakes $spent $ceiling $soft $min-local
               $iterations $hard $adjudicator-enabled)))

;; Scheduling is a release constraint, not a calendar entry. The host supplies
;; the current UTC epoch. MeTTaScript decides whether a dependency-ready task
;; may run.
(= (tk-release $not-before $now $dependency-ready)
   (if (== $dependency-ready False)
       (release False "dependencies not ready")
       (if (== $not-before none)
           (release True "no release constraint")
           (if (< $now $not-before)
               (release False "not-before constraint has not elapsed")
               (release True "not-before constraint elapsed")))))

(: gc-thread-release (-> Atom Number Bool %Undefined%))

(= (gc-thread-release $not-before $now $dependency-ready)
   (gc-thread-ok release
     (tk-release $not-before $now $dependency-ready)))

;; Derive the exclusive Agent Orchestrator board projection from observed
;; OmegaClaw state. The host supplies rows and the current UTC epoch. MeTTa owns
;; the scheduled versus ready decision and every summary count.
(: gc-thread-ui (-> String Number %Undefined%))

(= (tk-ui-effective-state $state $not-before $now)
   (if (== $state ready)
       (let (release $allowed $reason)
            (tk-release $not-before $now True)
         (if (== $allowed True) ready scheduled))
       $state))

(= (tk-ui-release-reason $state $not-before $now)
   (if (== $state ready)
       (let (release $allowed $reason)
            (tk-release $not-before $now True)
         $reason)
       ""))

(= (tk-ui-project-row $now $row)
   (let
     (ui-task
       $task $capability $acceptance $stakes $dependencies
       $state $upstream-blocked $agent $attempts $session $not-before)
     $row
     (let* (($effective-state
              (tk-ui-effective-state $state $not-before $now))
            ($release-reason
              (tk-ui-release-reason $state $not-before $now)))
       (ui-task
         $task $capability $acceptance $stakes $dependencies
         $effective-state $upstream-blocked $agent $attempts $session
         $not-before $release-reason))))

(= (tk-ui-project-in $space $now)
   (match $space
     (ui-task
       $task $capability $acceptance $stakes $dependencies
       $state $upstream-blocked $agent $attempts $session $not-before)
     (tk-ui-project-row $now
       (ui-task
         $task $capability $acceptance $stakes $dependencies
         $state $upstream-blocked $agent $attempts $session $not-before))))

(= (tk-ui-task-state $task)
   (let
     (ui-task
       $id $capability $acceptance $stakes $dependencies
       $state $upstream-blocked $agent $attempts $session
       $not-before $release-reason)
     $task
     $state))

(= (tk-ui-count $tasks $state)
   (size-atom
     (filter-atom $tasks $task
       (== (tk-ui-task-state $task) $state))))

(= (tk-ui-progress $done $total)
   (if (== $total 0)
       0
       (floor-math (/ (* $done 100) $total))))

(= (tk-ui-projection $space $now)
   (let* (($tasks
            (tk-collapse-values
              (collapse (tk-ui-project-in $space $now))))
          ($total (size-atom $tasks))
          ($scheduled (tk-ui-count $tasks scheduled))
          ($backlog (tk-ui-count $tasks backlog))
          ($ready (tk-ui-count $tasks ready))
          ($in-progress (tk-ui-count $tasks in-progress))
          ($blocked (tk-ui-count $tasks blocked))
          ($done (tk-ui-count $tasks done))
          ($progress (tk-ui-progress $done $total)))
     (ui-projection
       (summary
         $total $scheduled $backlog $ready
         $in-progress $blocked $done $progress)
       (tasks $tasks))))

(= (gc-thread-ui $rows-source $now)
   (let* (($rows (sread $rows-source))
          ($space (tk-space-from-rows $rows)))
     (gc-thread-ok ui
       (tk-ui-projection $space $now))))

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

(: gc-thread-outcome
  (-> Atom Number Atom Number Number Bool Atom %Undefined%))

(= (gc-thread-outcome $exit-reason $exit-code $evaluator $attempt $max-retries
                      $adjudication-required $adjudicator)
   (gc-thread-ok outcome
     (tk-outcome $exit-reason $exit-code $evaluator $attempt $max-retries
                 $adjudication-required $adjudicator)))

;; The compatibility attempt surface keeps the existing Python atoms for
;; bounded process execution and evaluator invocation. The primary
;; MeTTaScript path runs those host effects outside the policy space and asks
;; gc-thread-outcome for the transition decision.
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

(: gc-thread-attempt
  (-> Atom Atom Atom Atom Atom Bool
      Atom Atom Atom Atom Atom Atom
      Number Number Number Number Number Bool %Undefined%))

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
