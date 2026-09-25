# Chat and run boundaries

A new project chat starts a new run by default. An opening such as "this is not a research run" opts out; an explicit request to continue a named run associates the chat with that run. Do not close earlier runs automatically. First-chat initialization is automatic under AGENTS.md, including for conceptual questions. An opt-out from a run alone does not skip initialization. Initialization and the opening task share the same run; never create an extra setup run.

At the genuine opening, register once with tools/runs.py enter-chat --chat-id ID and either --title TITLE --objective OBJECTIVE --slug SLUG, --opt-out, or --continue-run RUN_ID. Use the stable conversation ID when available. Otherwise choose and retain a stable local chat identifier in the existing run/handoff context; never generate another merely because context was compacted. No separate chat journal is needed.

On subsequent turns use chat-status --chat-id ID and the associated RUN.md. A missing association is not proof of a new chat: inspect available conversation context and existing records. If context is insufficient, continue authorized work without inventing a run boundary and clarify only if necessary. A completed or closed run, topic change, new substantial task, resumption, or compaction never authorizes a mid-chat start.

Only an explicit user request allows tools/runs.py start --user-requested --chat-id ID --request-id REQUEST --title TITLE --objective OBJECTIVE --slug SLUG mid-chat. Retain a stable request identifier so a retry is idempotent. These flags attest the conversation decision; they do not provide independent authorization.

research/runs/chat_state.json stores compact associations and pending start intent. Run records retain historical chat/request IDs. Repeating a start after interruption reconciles its reserved record without replacing scientific notes. Retry a busy lifecycle operation after the other operation ends; do not remove the lock file. OS locks are released when the process exits. The project handoff is a shared overview, not authority to switch this chat to another run.

Close only on the user's request using workflows/close_run.md. A closed association stays closed on later turns unless the user explicitly requests another run.
