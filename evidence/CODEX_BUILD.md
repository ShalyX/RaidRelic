# Codex build trail

Primary Codex session ID: `01a18920-5b89-704d-a5d8-fe8f5e392069`

The RaidRelic build thread is a durable Codex thread surfaced by the Codex/ChatGPT thread list as the Codex session associated with the `Continue RaidRelic Testing` work. Unlike local Codex sessions, it does not have a matching local rollout JSONL under `.codex/sessions` on this PC, so this file does not claim a local rollout artifact for it.

Codex was used as the implementation partner for the project’s main technical slice: Twitch EventSub raid/chat integration, OAuth and token validation, reconnect/migration behavior, deduplicated forge state, SSE/browser overlay, SQLite persistence, deterministic relic logic, integration tests, debugging and acceptance-test iteration.

The build deliberately kept a technical gate: local fake-Twitch tests were not treated as live evidence. The project was advanced only after real Twitch raids, real chat/emotes, OBS rendering/latency and restart persistence were observed.

Submission note: use the session ID above for the hackathon field requesting the thread where most of the project was built.
