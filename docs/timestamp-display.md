# User-visible timestamp display

NexusOne ticket, source, and structured-result timestamps use a single local UI
contract: values are parsed as server timestamps and rendered in the browser's
locale, with the display timezone fixed to **UTC**. Every formatted value ends
with `UTC`; the UI never relabels an offset value as local time.

- ISO timestamps with `Z`, `UTC`, `UT`, or an explicit numeric offset are parsed
  before conversion to UTC.
- A server timestamp without an offset is treated as UTC by contract.
- Date-only values are rendered as a UTC calendar date.
- Invalid or empty values render the stable fallback `Timestamp unavailable`.

The browser helper is `formatTimestamp` in `frontend/static/app.js`. SQL
terminal-answer text uses the matching explicit-UTC formatter
`format_timestamp_for_user` in `app/agents/sql_subgraph/presentation.py`.
