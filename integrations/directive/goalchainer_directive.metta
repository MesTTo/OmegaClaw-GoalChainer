; GoalChainer's machine-readable adapter over OmegaClaw's directive runtime.
; The plan remains the source of truth. These functions only package native
; directive values in a versioned record for Python and OmegaClaw callers.

!(import! &self (library OmegaClaw-Core plugins/deontic/lib_directive))

(= (gc-directive-ok $operation $payload)
   (goalchainer-directive-v1 $operation ok $payload))

; Deontic conclusions become directive states before a plan is written.
(= (gc-task-state forbidden) blocked)
(= (gc-task-state obligated) ready)
(= (gc-task-state permitted) backlog)
(= (gc-task-state unregulated) backlog)

(= (gc-directive-classify $rows)
   (gc-directive-ok classify
     (classification
       (map-atom $rows $row
         (let ($task $deontic) $row
           (task $task $deontic (gc-task-state $deontic)))))))

; Read every queryable coordination view after one reasoning pass.
(= (gc-directive-snapshot-value $path)
   (let* (($conclusions (dl-run $path))
          ($names (directive-pos-names))
          ($tasks (directive-tasks $names))
          ($ready (directive-ready $names))
          ($claimed (directive-claimed $names))
          ($blocked (directive-blocked $names))
          ($upstream (directive-upstream $names))
          ($completed (directive-completed $names))
          ($assignments (sort-atom (directive-assignments $names)))
          ($next (sort-atom (directive-next-actions $names)))
          ($total (size-atom $tasks))
          ($done (size-atom (tasks-in-state $tasks $names done))))
     (snapshot
       (status
         (tasks (sort-atom $tasks))
         (ready (sort-atom $ready))
         (claimed (sort-atom $claimed))
         (blocked (sort-atom $blocked))
         (upstream-blocked (sort-atom $upstream))
         (completed (sort-atom $completed)))
       (next-actions $next)
       (board
         (backlog (tasks-in-state $tasks $names backlog))
         (ready (tasks-in-state $tasks $names ready))
         (in-progress (tasks-in-state $tasks $names in-progress))
         (blocked
           (sort-atom
             (union-atom
               (tasks-in-state $tasks $names blocked)
               (tasks-in-state $tasks $names upstream-blocked))))
         (done (tasks-in-state $tasks $names done)))
       (summary
         (total $total)
         (backlog (size-atom (tasks-in-state $tasks $names backlog)))
         (ready (size-atom (tasks-in-state $tasks $names ready)))
         (in-progress (size-atom (tasks-in-state $tasks $names in-progress)))
         (blocked
           (+ (size-atom (tasks-in-state $tasks $names blocked))
              (size-atom (tasks-in-state $tasks $names upstream-blocked))))
         (done $done)
         (progress-pct (mm_pct $done $total)))
       (info (plan-meta-kvs))
       (assignments $assignments)
       (analysis
         (cycles (plan-cycle-groups))
         (consistent (plan-consistent-cs? $conclusions))))))

(= (gc-directive-snapshot $path)
   (gc-directive-ok snapshot (gc-directive-snapshot-value $path)))

(= (gc-directive-task-state $path $task)
   (let* (($_ (dl-run $path))
          ($names (directive-pos-names)))
     (gc-directive-ok task-state
       (task-state $task (directive-task-state $task $names)))))

; The native validation and trace functions print their detailed reports.
; Their return values are wrapped while the caller retains the other output lines.
(= (gc-directive-validate $path $strict)
   (let $valid (directive-validate $path $strict)
     (gc-directive-ok validate
       (validation (valid $valid) (strict $strict)))))

(= (gc-directive-analyze $path)
   (let* (($rendered (directive-analyze $path))
          ($cycles (plan-cycles $path))
          ($consistent (plan-consistent? $path)))
     (gc-directive-ok analyze
       (analysis
         (rendered $rendered)
         (cycles $cycles)
         (consistent $consistent)))))

(= (gc-directive-trace $path)
   (let $rendered (directive-trace $path)
     (gc-directive-ok trace (trace (rendered $rendered)))))

; Mettabase's existing MeTTa Markdown library renders the authored audit tree.
(= (gc-directive-markdown $source)
   (gc-directive-ok markdown
     (markdown (md-author-markdown $source))))

; Mutations append the native superiority-ranked lifecycle block, then return
; the resulting plan snapshot from a fresh reasoning pass.
(= (gc-directive-mutation $kind $result $path)
   (gc-directive-ok lifecycle
     (lifecycle
       (kind $kind)
       (result $result)
       (snapshot (gc-directive-snapshot-value $path)))))

(= (gc-directive-claim $path $task $agent $force)
   (gc-directive-mutation claim
     (directive-claim $path $task $agent $force)
     $path))

(= (gc-directive-unclaim $path $task $agent)
   (gc-directive-mutation unclaim
     (directive-unclaim $path $task $agent)
     $path))

(= (gc-directive-complete $path $task $agent)
   (gc-directive-mutation complete
     (directive-complete $path $task $agent)
     $path))

(= (gc-directive-block $path $task $agent)
   (gc-directive-mutation block
     (directive-block $path $task $agent)
     $path))

(= (gc-directive-unblock $path $task $agent)
   (gc-directive-mutation unblock
     (directive-unblock $path $task $agent)
     $path))
