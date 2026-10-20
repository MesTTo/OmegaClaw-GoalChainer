; Purpose: declare the incident example's actions, goals, reading section and defeasible norms.
; am[implements a-integrate-incident-declarations-1018@89a9c1]
; The priorities and norm defaults are the existing incident policy. They are declarations,
; not learned values. Contributions describe predicted coverage, never observed achievement.

(gc-domain "Incident response with individual privacy and collective repair goals")
(gc-policy-version incident-v1)

; The example proposes work. Its host supplies authorization and any execution receipt.
(gc-authority advisory 0 "Recommend an action for the host to review.")
(gc-estimator-ceiling model-proposed advisory)
(gc-estimator-ceiling receipt-calibrated advisory)
(gc-estimator-ceiling measured advisory)
(gc-estimator-ceiling deterministic advisory)
(gc-estimator-ceiling human-asserted advisory)

(gc-action publish_raw_log "Publish raw incident log"
  "Share the full raw log with the whole response channel." (authority advisory))
(gc-action publish_redacted_summary "Publish redacted summary"
  "Share a summary with identifiers removed and enough detail to coordinate." (authority advisory))
(gc-action hold_external_update "Hold external update"
  "Keep information internal until the team checks the evidence." (authority advisory))

(gc-goal preserve_privacy ava individual 0.95
  "Do not expose identifiable user data." (priority-source policy:incident-example))
(gc-goal restore_service ops-team collective 0.9
  "Restore the failing service quickly." (priority-source policy:incident-example))
(gc-goal coordinate_team incident-team collective 0.75
  "Give responders enough shared context to coordinate." (priority-source policy:incident-example))
(gc-goal verify_facts incident-team collective 1.0
  "Verify the incident facts before publishing an update." (priority-source policy:incident-example))

; The reading section: the propositions GoalChainer's semantic reader asks Jev to judge in every text
; it reads for this domain, the answers Jev may give and the evidence direction of each, and the
; question the cross-encoder ranks passages against, in the grammar goal_chainer.domains.readings
; reads. Each proposition declares one of the domain's signals, so its id is the one name its
; gc-reading facts, its SNARS statement (has-property "request" ID) and the rules below use, and the
; domain declares it nowhere else. A change to these forms changes the declaration's digest and so
; the reader revision, and a change to a question's text changes the key of every cached Jev answer
; to it; an id changes no key.
; am[implements a-jev-reading-table-1016] am[implements a-dr-incident-declaration-1018@455a2f]
; am[implements a-jev-decided-nli-1016] am[implements a-dr-sr-incident-file-1018@31f64a]
(gc-reading-domain incident)

; The Jev model every reading is asked of. A versioned ID, never an alias such as jev-latest,
; because an alias moves to a new release and its answers change with it (docs.typesafe.ai
; models.md, "Aliases").
; am[rests-on c-jev-api-shape-1016]
(gc-reading-model "jev-1.13.0")

; The language the propositions are written in, and so the language the reader segments texts in.
(gc-reading-language "en")

; Each proposition is put to Jev as one Choice over these answers: natural language inference's
; entailment, contradiction and neutral. (gc-reading-option NAME DIRECTION DESCRIPTION): DIRECTION is
; the evidence a decided answer gives its proposition, `for`, `against`, or `none` for the text
; staying silent, which is no evidence either way. Everything that reads a reading derives the answer
; set, which answers are decided and what each means from these rows.
; am[rests-on c-orch-three-way-semantics-1016]
; am[implements a-jev-derive-answers-1016]
(gc-reading-instructions
  "Decide whether `text` supports the following proposition, contradicts it, or leaves it unknown. Proposition: ")
(gc-reading-option supported for
  "The text states, or clearly implies, that the proposition is true.")
(gc-reading-option contradicted against
  "The text states, or clearly implies, that the proposition is false.")
(gc-reading-option unknown none
  "The text says nothing that settles whether the proposition is true or false.")

; (gc-reading-proposition ID STATEMENT QUESTION)
; QUESTION is the proposition asked as a question, which the cross-encoder ranks the text's
; passages against to say which one answers. Which propositions the theory treats as sensitive
; categories is the theory's own (sensitive-category ...) facts below, not the reading section's.
; am[implements a-dr-one-name-1018@beba5e]
(gc-reading-proposition sensitive-data
  "The content the text is about includes, or may include, personal or confidential data, such as names, contact details, email addresses, customer or order identifiers, request payloads, credentials, tokens or secrets."
  "Does the content include personal or confidential data such as emails, customer identifiers, payloads, credentials or secrets?")
(gc-reading-proposition public-data
  "The information the text is about is public, holds nothing sensitive, and is safe to share openly with anyone."
  "Is the information public and safe to share openly?")
; Only a stated verification status settles this proposition. An earlier wording gave "the
; investigation is still going on" as an example, and Jev then read "Engineering needs the
; incident room." as unverified facts (0.623 over three draws). The proposition itself stays about
; the facts, and what settles it follows as guidance naming all three outcomes: were "the text
; says so" part of the proposition, its negation would include "the text does not say so", and a
; silent text would read as contradicting it.
; am[implements a-jev-unverified-question-1016@8ecfa0] am[rests-on c-orch-three-way-semantics-1016@b92763]
(gc-reading-proposition unverified
  "The facts of the situation the text describes are not yet verified or confirmed. Only what the text says about verification settles this: saying that the facts are unconfirmed, or that the cause is unknown or still being investigated, supports it; saying that they are verified or confirmed contradicts it; a text that only reports what is happening, or that people are responding to it, leaves it unknown."
  "Does the text say whether the facts are verified, unconfirmed or still being investigated?")
(gc-reading-proposition coordination-needed
  "Responders or teams, such as engineering or support, need shared context to coordinate their work on the incident."
  "Do responders or teams need shared context to coordinate their work?")
(gc-reading-proposition customer-emails
  "The content the text is about includes, or may include, customers' email addresses."
  "Does the content include customer email addresses?")
(gc-reading-proposition order-ids
  "The content the text is about includes, or may include, order identifiers."
  "Does the content include order identifiers?")
(gc-reading-proposition request-payloads
  "The content the text is about includes, or may include, request payloads."
  "Does the content include request payloads?")
(gc-reading-proposition tokens-or-secrets
  "The content the text is about includes, or may include, tokens, secrets, credentials or API keys."
  "Does the content include tokens, secrets, credentials or API keys?")
(gc-reading-proposition full-traces
  "The content the text is about includes, or may include, full stack traces or request traces."
  "Does the content include full stack traces or request traces?")
(gc-reading-proposition raw-logs
  "The content the text is about includes, or may include, raw log lines."
  "Does the content include raw log lines?")

; (gc-reading-choice ID INSTRUCTIONS ((OPTION DESCRIPTION) ...))
; A reading whose answer is one of its own options rather than a proposition's truth.
(gc-reading-choice mood
  "What does `text` mainly do?"
  ((query "It asks a question.")
   (directive "It asks or tells someone to do something.")
   (declarative "It reports or states facts.")))

; The instruction the cross-encoder judges each question and passage pair under, in
; Qwen3-Reranker's <Instruct> slot.
; am[rests-on c-reranker-template-identical-1016]
(gc-ranking-instruction
  "Given a question about an incident, retrieve the passage of the text that answers it")

(given incident)
(given (candidate publish_raw_log))
(given (candidate publish_redacted_summary))
(given (candidate hold_external_update))
(given (sensitive-category customer-emails "customer emails"))
(given (sensitive-category order-ids "order IDs"))
(given (sensitive-category request-payloads "request payloads"))
(given (sensitive-category tokens-or-secrets "tokens or secrets"))
(given (sensitive-category full-traces "full traces"))
(given (sensitive-category raw-logs "raw logs"))

; The generic review supplies (signal ID) or its explicit contrary and queries (do ACTION).
; An unknown supplies neither polarity. The legacy inputs used (supported ID).
; am[rests-on c-dr-deontic-conjunction-1018@051cc4]
(normally rStake (signal sensitive-data) privacyAtStake)
(normally rCategory (and (signal ?category) (sensitive-category ?category ?name)) privacyAtStake)
(normally rPublicDeclared (signal public-data) (not privacyAtStake))
(prefer rPublicDeclared rStake)
(prefer rPublicDeclared rCategory)

; Keep the existing defaults while the operator's D1 and D2 decisions remain open.
; am[related a-ev-in-raw-permit-unknown@f4c33c] am[related a-ev-in-raw-forbid-unless-public@89d5d8]
(normally rRawPermit incident (may (do publish_raw_log)))
(normally rRawForbid privacyAtStake (forbidden (do publish_raw_log)))
(prefer rRawForbid rRawPermit)
; am[related a-ev-in-ready-unknown@4715e7] am[related a-ev-in-hold-unknown@16e474]
(normally rReady incident factsReady)
(normally rUnverified (signal unverified) (not factsReady))
(prefer rUnverified rReady)
(normally rRedPermit incident (may (do publish_redacted_summary)))
(normally rRedOblige factsReady (must (do publish_redacted_summary)))
(normally rHoldPermit incident (may (do hold_external_update)))
(normally rHoldOblige (not factsReady) (must (do hold_external_update)))

; These are the previous appraisal's required goals and coverage, expressed as policy.
; No default action strengths or scalar action scores belong to the declaration.
(given (required preserve_privacy))
(given (required restore_service))
(given (required coordinate_team))
(normally rVerifyRequired (not factsReady) (required verify_facts))
(given (contributes publish_raw_log restore_service positive))
(given (contributes publish_raw_log coordinate_team positive))
(normally rRawPrivacy incident (contributes publish_raw_log preserve_privacy positive))
(except rRawPrivacyRisk privacyAtStake
  (not (contributes publish_raw_log preserve_privacy positive)))
(given (contributes publish_redacted_summary preserve_privacy positive))
(normally rRedRestore factsReady (contributes publish_redacted_summary restore_service positive))
(normally rRedCoordinate factsReady (contributes publish_redacted_summary coordinate_team positive))
(given (contributes hold_external_update preserve_privacy positive))
(normally rHoldVerify (not factsReady) (contributes hold_external_update verify_facts positive))
