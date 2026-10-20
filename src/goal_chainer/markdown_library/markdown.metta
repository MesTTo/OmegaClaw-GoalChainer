(@doc md-parse
  (@desc "Parse Markdown text and return the pretty Markdown MeTTa tree as data.")
  (@params ((@param "Markdown text")))
  (@return "Markdown tree atom"))

(@doc md-atoms
  (@desc "Parse Markdown text and return an expression containing the pretty tree followed by side facts.")
  (@params ((@param "Markdown text")
            (@param "Document id symbol")))
  (@return "Expression of Markdown atoms"))

(@doc md-facts
  (@desc "Parse Markdown text and return newline-separated Markdown side facts.")
  (@params ((@param "Markdown text")
            (@param "Document id symbol")))
  (@return "String containing md-* fact atoms"))

(: md-parse (-> String %Undefined%))
(: md-atoms (-> String Symbol Expression))
(: md-facts (-> String Symbol String))
(: md-ir (-> String %Undefined%))
(: md-author-parse (-> String %Undefined%))
(: md-author-atoms (-> String Expression))
(: md-author-facts (-> String String))
(: md-author-markdown (-> String String))
(: md-query (-> %Undefined% %Undefined% %Undefined%))
(: md-editor-atoms (-> %Undefined% Expression))
(: md-space-tables (-> SpaceType %Undefined% %Undefined%))
(: md-space-named (-> SpaceType %Undefined% %Undefined% %Undefined%))
(: md-space-cell (-> SpaceType %Undefined% %Undefined% Number Number %Undefined%))
(: md-space-row (-> SpaceType %Undefined% %Undefined% Number %Undefined%))
(: md-space-col (-> SpaceType %Undefined% %Undefined% Number %Undefined%))
(: md-author-load-into! (-> SpaceType String SpaceType))
(: md-load-into! (-> SpaceType String Symbol SpaceType))
(: md-load! (-> String SpaceType))
(: md-ed-load! (-> SpaceType %Undefined% SpaceType))
(: md-ed-clear! (-> SpaceType %Undefined% SpaceType))
(: md-ed-sync! (-> SpaceType %Undefined% SpaceType))
(: md-ed-set-cell! (-> SpaceType %Undefined% %Undefined% %Undefined% %Undefined%))
(: md-ed-apply! (-> SpaceType %Undefined% Atom %Undefined%))

(= (md-parse $text)
   (sread (py-call (goalchainer_markdown.md_parse $text md1))))

(= (md-atoms $text $doc-id)
   (sread (py-call (goalchainer_markdown.md_atoms $text $doc-id))))

(= (md-facts $text $doc-id)
   ;; repr re-materializes the declared String return (janus yields symbols)
   (repr (py-call (goalchainer_markdown.md_facts $text $doc-id))))

(= (md-ir $text)
   (sread (py-call (goalchainer_markdown.md_ir $text md1))))

(= (md-author-parse $source)
   (sread (py-call (goalchainer_markdown.md_author_parse $source))))

(= (md-author-atoms $source)
   (sread (py-call (goalchainer_markdown.md_author_atoms $source))))

(= (md-author-facts $source)
   ;; repr re-materializes the declared String return (janus yields symbols)
   (repr (py-call (goalchainer_markdown.md_author_facts $source))))

(= (md-author-markdown $source)
   ;; janus hands Python strs back as bare symbols; repr re-materializes the
   ;; declared String return type (typed callers prune symbols otherwise)
   (repr (py-call (goalchainer_markdown.md_author_markdown $source))))

(= (md-query $source $command)
   (sread (py-call (goalchainer_markdown.md_query $source $command md1))))

(= (md-editor-atoms $source)
   (sread (py-call (goalchainer_markdown.md_editor_atoms $source md1))))

(= (md-space-tables $space $doc-id)
   (match $space
     (, (md-child $doc-id $idx $table)
        (md-node $table table))
     $table))

(= (md-space-named $space $doc-id $name)
   (match $space
     (, (md-child $doc-id $idx $node)
        (md-name $node $name))
     $node))

(= (md-space-cell $space $table $section $row $col)
   (match $space
     (, (md-cell-at $table $section $row $col $cell)
        (md-text $cell $value))
     $value))

(= (md-space-row $space $table $section $row)
   (collapse
     (match $space
       (, (md-cell-at $table $section $row $col $cell)
          (md-text $cell $value))
       $value)))

(= (md-space-col $space $table $section $col)
   (collapse
     (match $space
       (, (md-cell-at $table $section $row $col $cell)
          (md-text $cell $value))
       $value)))

(= (md-author-load-into! $space $source)
   (let $atoms (md-author-atoms $source)
        (let $unit (add-atoms $space $atoms)
             $space)))

(= (md-load-into! $space $text $doc-id)
   (let $atoms (md-atoms $text $doc-id)
        (let $unit (add-atoms $space $atoms)
             $space)))

;; The registry anchor linking doc-ids to their loaded spaces. (Previously an
;; undefined (context-space) call — a phantom that "worked" only as an
;; unreduced shared anchor and broke inside compiled bodies.)
(= (context-space) &md-context-space)

(= (md-load! $text)
   (let* (($space (new-space))
          ($loaded (md-load-into! $space $text md1))
          ;; space arguments are taken unevaluated — bind the registry anchor
          ;; through let before handing it to add-atom
          ($registry (context-space))
          ($link (add-atom $registry (md-doc-space md1 $space))))
         $space))

(= (md-ed-load! $space $doc)
   (let $atoms (md-editor-atoms $doc)
        (let $unit (add-atoms $space $atoms)
             $space)))

(= (md-ed-clear! $space $doc-id)
   (let* (($removed-owned
           (collapse
             (match $space (md-ed-owned $doc-id $fact)
               (let* (($r1 (remove-atom $space $fact))
                      ($r2 (remove-atom $space (md-ed-owned $doc-id $fact))))
                     $fact))))
          ($removed-current
           (collapse
             (match $space (md-ed-current $doc-id $doc)
               (remove-atom $space (md-ed-current $doc-id $doc))))))
         $space))

(= (md-ed-sync! $space $doc)
   (let* (($doc-id (index-atom $doc 1))
          ($cleared (md-ed-clear! $space $doc-id))
          ($loaded (md-ed-load! $space $doc)))
         $space))

(= (md-ed-set-cell! $space $doc-id $selector $value)
   (let* (($doc (match $space (md-ed-current $doc-id $d) $d))
          ($result (md-query $doc (edit (find $selector) $value))))
     (case $result
       (((md-edit-ok $new-doc $summary)
          (let $synced (md-ed-sync! $space $new-doc) $new-doc))
        ($error $error)))))

(= (md-ed-apply! $space $doc-id $ops)
   (let* (($doc (match $space (md-ed-current $doc-id $d) $d))
          ($result (md-query $doc (apply $ops))))
     (case $result
       (((md-edit-ok $new-doc $summary)
          (let $synced (md-ed-sync! $space $new-doc) $new-doc))
        ($error $error)))))
