# Chat response streaming

NexusOne Copilot keeps `POST /api/chat` JSON behavior as the default for existing callers. Browser callers opt into streaming with:

```http
Accept: text/event-stream
```

The stdlib HTTP adapter returns a Server-Sent Events (SSE) stream. SSE was chosen because the current browser client already uses `fetch`, can consume a `ReadableStream` without a new dependency, and the existing route/auth/cookie contract can remain unchanged for non-streaming callers.

Each event has an SSE `event` name and a JSON `data` object with the same `type` value:

```text
event: response.start
data: {"type":"response.start","conversation_id":"<server-conversation-uuid>","turn_id":"<server-turn-uuid>"}

```

Supported event types:

- `response.start`: server-recognized conversation and turn identifiers only; no question, prompt, profile internals, or provider details. The conversation ID is stable across turns and is also the graph `thread_id`.
- `response.delta`: one user-visible assistant text delta in `delta`.
- `response.error`: a safe, typed error. Provider fallback errors may be marked `recoverable`; transport/orchestration failures are terminal.
- `response.complete`: the existing JSON chat response under `response`, including the accumulated `message`, citations, rows, trace/subgraph trace when requested, capabilities, and response metadata.

The server uses the existing LangGraph execution. The final answer composer emits custom LangGraph stream events; deterministic/offline composers emit the same answer in bounded chunks, while OpenAI-backed composers use the provider stream. Only sanitized answer deltas and the final public response cross the HTTP boundary. Graph state, prompts, SQL text/parameters, credentials, and provider exception text are never streamed.

The frontend treats the completion response as canonical, but updates the current assistant message for each delta. It tolerates malformed individual frames, displays terminal stream errors without leaving a pending loading state, and aborts its `fetch` request on session teardown/page unload. A client disconnect is observed by the stdlib handler as a broken write; iteration stops without attempting to send more data.
