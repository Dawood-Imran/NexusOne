# NexusOne product walkthroughs

## Narrated version (v2)

Download [NexusOne-60s-voiced.mp4](NexusOne-60s-voiced.mp4). This version is exactly 60 seconds, 1920 × 1080, 30 fps, with AI-generated English narration and subtitles burned into the picture. A selectable English subtitle track is also embedded.

The footage records real app interactions, including mouse movements, opening a citation, inspecting ticket rows, approving a ticket, recalling personal memory, and inspecting a denied request. Focused camera moves point to the relevant controls. The role montage shows eight separately authenticated fictional accounts; the comparison shows the same revenue-risk question denied for an employee and answered for a CEO under the server-side authorization policy. It does not suggest that every role can access every category.

- [English subtitles](NexusOne-60s-voiced.srt)
- [Voice-over script and chapter timings](NexusOne-voiceover-script.txt)

### Chapters

| Time | Topic |
| --- | --- |
| 00:00 | Company knowledge, data, and support |
| 00:05 | Employee, manager, HR, finance, IT, admin, executive, and CEO roles |
| 00:12 | Server-side authorization and employee/CEO comparison |
| 00:20 | Source citations and retrieval grants |
| 00:27 | Live PostgreSQL ticket lookup and SQL boundaries |
| 00:34 | Ticket preview, explicit approval, and creation |
| 00:42 | Conversation history and personal memory across chats |
| 00:49 | Injection refusal, feedback, audit/trace, evaluations, mobile |
| 00:57 | Closing |

### Evidence and scope

The app uses synthetic development accounts and company records. The video uses an isolated conversation/memory directory. A fictional IT ticket was created in the local development database only after the recorded approval.

The offline evaluator executed all 21 cases successfully across authorization, route, grounded facts, citations, safe output, and response shape. The earlier full unit suite ran 255 tests: 254 passed and one memory integration test errored with `KeyError: name_and_nickname`; that known defect is displayed in the validation summary. The video is a demonstration of the recorded behavior, not a claim of production readiness or exhaustive security testing.

## Original caption-only version (v1)

[Original MP4](NexusOne-60s.mp4) and [original subtitles](NexusOne-60s.srt).
