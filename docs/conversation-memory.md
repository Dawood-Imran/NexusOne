# NexusOne conversation and user memory

## Baseline inventory (before server memory)

The launch checkout did not have durable conversation memory. The important
boundaries were:

- `app/api/dev_server.py` accepted `POST /api/chat` but did not accept a
  conversation identifier. SSE `response.start` always advertised
  `conversation_id: "web-chat"` and `turn_id: "web-turn"`.
- `ChatService._request_payload` supplied those same constant identifiers and
  passed only an optional, caller-provided `conversation_context`. It did not
  read or write a server conversation store. Direct callers could therefore
  discard all turns between invocations.
- `app/agents/orchestrator/graph.py` compiled a `StateGraph` without a
  checkpointer. Its LangSmith config carried metadata only; no checkpoint was
  resumed. The graph branches already present were RAG, SQL, combined SQL/RAG,
  ticket creation, `CASUAL`, `GENERAL_KNOWLEDGE`, feedback, clarification,
  unsupported, denial, and error. The existing `history_lookup` classifier
  label intentionally mapped to `unsupported` because history was unavailable.
- `app/agents/orchestrator/intent_classifier.py` bounded optional recent user
  hints, but those hints were not durable state. `answer_composer.py` received
  only the current graph drafts and approved sources.
- The browser stored complete conversations in `localStorage` under
  `nexusone.conversations.<user_id>`. Those IDs were browser-generated and did
  not identify server records. Deleting a conversation explicitly removed it
  only from that browser. Browser storage was not treated as server memory.
- Existing action/feedback/audit repositories may use an injected SQLAlchemy
  engine, but that persistence was unrelated to chat turns. The default local
  path had no Postgres requirement and no conversation table.

This document records the baseline so a migration does not accidentally treat
browser history or audit rows as a checkpointer.

## Design and current implementation

### Short-term memory

`app/memory/conversation_store.py` defines a replaceable `ConversationStore`
interface and a local `SQLiteConversationStore` implementation. It stores
owner-scoped conversations and turns in `data/runtime/nexusone_conversations.sqlite3`
by default (override with `NEXUSONE_RUNTIME_DIR`). A transaction atomically:

1. creates a UUID conversation when the authenticated request omits
   `conversation_id`, or verifies the supplied ID belongs to the authenticated
   owner;
2. reserves a UUID turn (or validates a supplied `turn_id`);
3. loads at most eight completed prior turns, bounded to 600 characters per
   message; and
4. completes the pending turn with the sanitized public response. Local
   retention compacts a conversation to the newest 100 completed turns; the
   prompt window is always the smaller eight-turn bound.

A repeated `(owner, conversation_id, turn_id)` with identical user text returns
the stored response (replay/idempotency). Reusing the turn ID with different
text is a conflict, and a concurrently pending duplicate is rejected. Unknown
or another-owner IDs have the same generic not-found behavior. The API exposes
`GET/POST/DELETE /api/conversations` and `GET /api/conversations/{id}` for
reload, reconnect, and explicit server deletion.

The orchestrator receives the conversation ID as `configurable.thread_id` in
its LangGraph config. Since this graph is not an agent created with a
checkpointer, the SQLite store is the repository-owned equivalent boundary;
a production LangGraph checkpointer can replace it without changing the API.
History is marked as untrusted context in classifier and answer prompts. It is
context only and never supplies authorization, policy, retrieval scope, SQL,
or tool authority.

### Long-term memory

`app/memory/user_memory.py` stores versioned per-user JSON profiles under the
configured runtime directory (`data/runtime/user_memory/u001.json` by default).
The path component is accepted only after validating a known authenticated
manifest ID; arbitrary paths and traversal strings cannot select a file.
Profile values are bounded, allowlisted facts/preferences with provenance and
UTC timestamps in the file. Passwords, tokens, credentials, health, salary,
banking, and similar sensitive fields are rejected. Writes use per-file
thread/process locking and atomic `os.replace`.

Preferences require an explicit user `remember`/`save`/`store` request (or an
explicit server runtime opt-in); ordinary conversation is never inferred into
memory. `app/memory/tools.py` provides server-controlled equivalents of
`get_user_memory` and `update_user_memory`. They receive an injected
`MemoryRuntimeContext`; the callable schema has no user ID selector, rejects
identity fields, and requires explicit user input for updates. Audit events
record action, owner, field names, and outcome only—never raw prompts or stored
values.

ChatService loads sanitized memory at the start of an authenticated turn and
passes only bounded values to classification and answer composition. An
explicitly recognized update is validated before it is persisted and the
response reports only the changed field names. Memory is never an authority
for roles, permissions, retrieval, SQL, tools, or safety policy.

## Official design references

The implementation adapts the current Python concepts rather than importing a
JS-only agent pattern:

- [Short-term memory](https://docs.langchain.com/oss/python/langchain/short-term-memory)
  describes graph state persisted by a checkpointer and resumed with
  `configurable.thread_id`.
- [Long-term memory](https://docs.langchain.com/oss/python/langchain/long-term-memory)
  describes user-scoped store namespaces and server-provided runtime context
  for tools such as `get_user_memory` and `update_user_memory`.

The current graph's SQLite boundary is intentionally replaceable with a
LangGraph SQLite/Postgres checkpointer when the repository upgrades its graph
construction and deployment dependencies.

## Browser migration and cleanup

The frontend no longer treats `localStorage` as conversation authority. After
login it loads server conversations, creates a server conversation for **New
conversation**, sends its `conversation_id` on every turn, and uses the server
response/SSE metadata as canonical. Browser state is only a rendering cache
for the active view; reloads recover from `/api/conversations`. Conversation
delete calls the server endpoint and is no longer described as device-only.
Existing `nexusone.conversations.*` keys from older builds are ignored and may
be removed by a later cleanup release; they are not migrated into server
memory because their ownership and integrity cannot be established.

## HTTP examples

Two turns in the same conversation use the ID returned by the first request:

```text
POST /api/chat {"message":"How do I request AWS access?"}
<- {"conversation_id":"<server UUID>","turn_id":"<turn UUID>", ...}
POST /api/chat {"conversation_id":"<server UUID>","message":"What did I ask earlier?"}
<- message: "Earlier in this conversation, you asked: ...AWS access..."
```

A different server conversation has a different ID and cannot read those
turns. A long-term example is:

```text
POST /api/chat {"conversation_id":"<id>","message":"Remember that my preferred name is Ada"}
<- {"memory":{"status":"updated","fields":["preferred_name"]}, ...}
POST /api/chat {"conversation_id":"<id>","message":"What is my preferred name?"}
<- the bounded sanitized profile is available to the classifier/answer path
```
