# RaidRelic â€” Devpost submission copy

## Project name
RaidRelic

## Tagline
A Twitch raid hijacks the stream, and chat forges the moment into a collectible relic.

## Short description
RaidRelic turns the first minute after a Twitch raid into a live community ritual. A real raid triggers an OBS takeover, incoming chat and emotes visibly charge and reshape a one-of-one relic, participation determines its rarity, and the finished artifact is saved to a persistent Raid Archive. Instead of a raid alert disappearing after a few seconds, RaidRelic gives the streamer and both communities a memory of the handoff.

## Full project description
Most raid alerts answer one question â€” â€œwho raided?â€ â€” and then disappear. RaidRelic treats the raid itself as content.

When Twitch delivers a real `channel.raid` EventSub event, RaidRelic starts a 45-second forge in a transparent OBS browser overlay. The incoming raid appears as a signal intrusion over the live stream. During the forge, real `channel.chat.message` events become visible strikes: messages, unique chatters and emote fragments increase charge and alter the artifact. A stat-derived rarity system moves the relic through Common, Rare, Epic and Legendary tiers based on the actual raid/chat participation rather than a fixed label.

At the end of the ritual, the relic locks into its final deterministic form and is saved to the channelâ€™s Raid Archive with raid metadata and participation stats. The same session data produces the same artifact, so each relic acts as a persistent fingerprint of that raid moment.

The prototype has been tested with real Twitch raids and chat, including emote fragments, transparent OBS rendering, sub-second visible overlay response on measured raids, timed completion, and exact persistence across an app restart.

## What makes it different
- It turns a passive raid alert into a shared activity for both communities.
- Chat is not decoration: participation changes charge, geometry and rarity.
- The relic survives after the alert and becomes part of a channel history.
- The overlay runs directly in OBS and requires no setup from viewers.
- Real Twitch and simulation data are isolated so development triggers cannot masquerade as live proof.

## How I used OpenAI Codex
Codex was the implementation partner for the main build. I used it to design and implement the Twitch EventSub raid/chat path, OAuth/token validation, reconnect and session-migration behavior, event deduplication, the 45-second forge state engine, SSE updates, the browser/OBS overlay, SQLite persistence, deterministic relic generation and the integration test suite.

Codex was also used iteratively during live acceptance testing: diagnosing Twitch/OBS issues, tracing EventSub state, separating simulation from real evidence, fixing the real-chat reaction rail and stat-driven rarity, and building evidence tooling. I deliberately kept a technical gate so local fake-Twitch tests were never presented as live Twitch proof; the project advanced only after real raid, chat, emote, OBS and persistence evidence existed.

Primary Codex session ID: `01a18920-5b89-704d-a5d8-fe8f5e392069`

## Technology
Python, aiohttp, Twitch EventSub WebSocket, Twitch OAuth/chat, Server-Sent Events, SQLite, HTML/CSS/JavaScript, OBS Browser Source, OpenAI Codex.

## Evidence highlights
- 6/6 automated tests passing.
- Real Twitch raid and chat delivery proven.
- Real emote-fragment mutation proven.
- Twitch event â†’ first visible OBS overlay measured under 1 second on two real raids.
- Archived relic survived a full server restart with matching ID, counts, raid metadata and relic parameters.
- Final evidence session: 1 raid viewer, 8 messages, 1 unique chatter, 2 emotes, 47 charge â†’ RARE RAID.

## Submission fields
- Repository URL: **TODO after GitHub push**
- YouTube demo URL: **TODO after upload**
- Codex Session ID: `01a18920-5b89-704d-a5d8-fe8f5e392069`

