# NexusOne conversation and user memory

NexusOne has two separate server-owned memory boundaries:

- **Short-term conversation memory** is an owner-scoped SQLite conversation and
  turn store. It is bounded context for the current conversation only.
- **Long-term personal memory** is one bounded Markdown profile per authenticated
  user. It is shared across that user's conversations, never across users, and
  is not an authority for roles, permissions, retrieval, SQL, tickets, or
  safety policy.

## Long-term profile format

Profiles are written under `NEXUSONE_USER_MEMORY_DIR` (or
`NEXUSONE_RUNTIME_DIR/user_memory`) as `<authenticated-user-id>.md`. The file
name is created only after the server validates the ID against the synthetic
server manifest (`u001` through `u008`); neither a browser nor a model can
provide a path or namespace.

Each file is Markdown with server-parsed front matter and these bounded
sections:

```markdown
---
schema_version: 2
user_id: "u001"
created_at: "2026-01-01T00:00:00+00:00"
updated_at: "2026-01-01T00:00:00+00:00"
---
# NexusOne personal memory

## Name and nickname
- nickname: {"source":"explicit_user","updated_at":"...","value":"Davis"}

## Profession
- profession: {"source":"explicit_user","updated_at":"...","value":"Designer"}

## Preferences
- response_style: {"source":"explicit_user","updated_at":"...","value":"concise"}

## Current activities
- {"source":"explicit_user","updated_at":"...","value":"billing migration"}

## Other durable facts
- office_location: {"source":"explicit_user","updated_at":"...","value":"Lahore"}
```

The implementation bounds the profile to eight total entries, five current
activities, and 120 characters per value (80 for a name/nickname). Field names
are allowlisted, values are normalized to one line, and secret/credential,
health, financial, prompt-instruction, role, permission, and similar sensitive
content is rejected. Every entry has a server timestamp and provenance; audit
records contain only user ID, action, outcome, and field names, never values or
raw prompts.

Writes use a per-profile in-process lock, an advisory process lock, a flushed
temporary file, and `os.replace`. Readers therefore see either the previous
complete Markdown profile or the next complete profile. Malformed or old-schema
files fail closed to an empty sanitized profile rather than becoming model
context.

## Tool contract

The server exposes exactly two model tools through the LangChain/OpenAI answer
path:

### `get_user_memory`

- Input: `{}` only; additional properties are forbidden.
- Output: sanitized profile values and schema version, with no provenance,
  timestamp, user ID, path, secret, or hidden field.
- Identity: captured by a server-created `MemoryRuntimeContext` from the
  authenticated session.

### `update_user_memory`

- Input properties: `name_and_nickname`, `profession`, `preferences`,
  `current_activities`, and `other_facts`; additional properties are
  forbidden. User IDs, paths, roles, permissions, credentials, and policy
  changes are never part of the schema.
- The server validates sections and values again at execution time.
- The tool executes only with `explicit_user_input=True`, which the server sets
  only when the current authenticated user has made a supported explicit
  statement. The model cannot set this flag or choose another identity.
- Tool calls are limited to a bounded loop and produce safe tool outcomes in
  traces. Raw tool arguments and profile values are not placed in audit logs.

`app/memory/tools.py` also provides a provider-independent contract for tests
and builds LangChain `StructuredTool` instances with the same strict schemas.
Offline tests inject a fake model that returns a tool call followed by a final
model message; no OpenAI or network is required.

## Update policy

The profile is updated only from a current user-authored explicit durable
statement, for example:

- `My nickname is Davis`
- `Remember that my profession is designer`
- `I prefer concise responses`
- `I am currently working on the billing migration`

Ordinary conversation, assistant prose, conversation history, retrieved
Markdown/PDF text, and SQL rows are never passed to the update extractor. A
prompt-injection request is denied by the existing guardrail precheck or the
value validator and cannot update memory. Unsupported fields, line breaks,
oversized values, sensitive markers, and invalid enumerated preferences are
rejected. Preference updates require the explicit statement to count as the
user opt-in; a model cannot manufacture that opt-in.

The deterministic no-provider path uses the same server validator as a safe
fallback for explicit statements. When a configured model-capable composer is
used, the model is bound to the two server-owned tools and must decide whether
to call `update_user_memory` or `get_user_memory`; a static prompt alone does
not write memory.

## Conversation behavior

At the start of every authenticated turn, `ChatService` reads the sanitized
profile and passes bounded values to the classifier/answer path. A new server
conversation therefore has access to a profile saved in an earlier
conversation:

```text
POST /api/chat {"message":"My nickname is Davis"}
<- {"memory":{"status":"updated","fields":["nickname"]}, ...}

POST /api/chat {"message":"What is my nickname?"}
<- message: "You asked me to remember that your nickname is Davis."
```

Short-term history remains limited to the current authenticated conversation
and is marked untrusted context. A different user, a traversal-like ID, or an
unknown conversation receives a generic owner-safe error. The normal JSON and
SSE response contracts, retrieval scope, SQL scope, ticket authority, and
pre-model guardrails remain unchanged.

## Limitations

The local implementation uses Markdown files and SQLite for the repository's
dev/runtime boundary. A production deployment should replace these with a
shared encrypted store and deployment-grade locking/retention while keeping
the same server-owned namespace and tool contract. Long-term memory is
intentionally not a general knowledge base: it stores only bounded personal
facts/preferences and does not infer facts from behavior.
