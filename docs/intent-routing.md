# NexusOne intent classifier and route contract

The main orchestrator uses the versioned `nexusone-intent-contract-v1` contract and
`nexusone-intent-classifier-v1` marker. `app/agents/orchestrator/intent_classifier.py`
contains the only provider classifier boundary; `routing.py` only maps validated
finite labels to graph routes and does not inspect message keywords.

## Intent labels

`casual`, `general_question`, `knowledge_lookup`, `structured_lookup`,
`combined_lookup`, `ticket_create`, `ticket_status`, `history_lookup`, `feedback`,
`clarification`, and `unsupported` are the complete classifier label set.

`general_question` includes basic questions and ticket-creation guidance. Guidance
such as “I can create a ticket … please provide …” is not a command and must not
invoke the ticket action. `ticket_create` requires an explicit user request to
create, submit, raise, open, or generate a ticket.

The server maps these labels as follows:

- casual -> `CASUAL` deterministic response
- general_question -> `GENERAL_KNOWLEDGE` safe composer path
- knowledge_lookup -> permission-filtered RAG
- structured_lookup or ticket_status -> constrained SQL subgraph
- combined_lookup -> SQL followed by permission-filtered RAG
- ticket_create -> validated ticket action service
- feedback -> direct feedback guidance (the explicit feedback endpoint remains the write path)
- clarification -> clarifying response with no tool call
- unsupported -> supported-options explanation with no tool call
- history_lookup -> bounded server-owned short-term history response; an empty conversation returns a safe unsupported response

A ticket-status label is never treated as ticket creation. A ticket-create label may
carry missing context; the existing ticket service then asks for department,
category, or description without writing a partial ticket. The authenticated
conversation store supplies at most the bounded recent user-message context used
for history lookup and follow-up classification; it does not grant authorization,
retrieval, SQL, or action authority.

## Public response additions

Existing fields (`status`, `reason_code`, `route`, `message`, profile, citations,
rows, and trace) remain compatible. Responses now also include:

- `intent`: validated label or `null` when authorization/input ended before classification
- `intent_confidence`: bounded 0..1 score or `null`
- `needs_clarification`: boolean
- `clarification_question`: bounded question or `null`
- `missing_context`: bounded field labels
- `intent_contract_version` and `intent_classifier_version`: safe constants

Safe classifier failures use `status=needs_clarification`, `route=clarification`,
and a reason such as `INTENT_CLASSIFIER_UNAVAILABLE`,
`INTENT_PROVIDER_UNAVAILABLE`, `INTENT_CLASSIFIER_ERROR_<TYPE>`,
`INTENT_CONFIDENCE_TOO_LOW`, or `INTENT_INPUT_TOO_LARGE`. They do not fall back to
keyword routing and do not call retrieval, SQL, or actions. Unsupported responses
use `UNSUPPORTED_REQUEST`; history responses use `SHORT_TERM_MEMORY` when bounded
prior turns are available or `SHORT_TERM_MEMORY_EMPTY` when the authenticated
conversation has no completed prior turns. Feedback uses `FEEDBACK_GUIDANCE`.

The provider call is a dedicated low-temperature LangChain/OpenAI structured
schema call with no application tools, bounded untrusted input/context, finite
labels, and no free-form rationale field. Server guardrails run before and after
classification and remain authoritative for all protected paths.
