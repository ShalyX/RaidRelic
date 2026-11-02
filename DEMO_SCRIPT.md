# RaidRelic final demo â€” target 2:35

## 0:00â€“0:08 â€” Hook
On screen: RaidRelic title + final relic drop.
Voiceover: â€œA Twitch raid usually disappears as fast as it arrives. RaidRelic turns that handoff into something the community can keep.â€

## 0:08â€“0:22 â€” Product in one sentence
On screen: dashboard / architecture cue.
Voiceover: â€œA real Twitch raid hijacks the OBS overlay. For 45 seconds, real chat messages and emotes forge a one-of-one relic. Participation changes its charge, shape and rarity, then the relic is saved to the channel archive.â€

## 0:22â€“1:32 â€” Real Twitch proof
Use the real OBS recording `C:\Users\USER\OneDrive\Videos\2026-11-01 02-04-20.mp4`.
Recommended source window: start a few seconds before media time ~174.43s, where the second real raid first appears, and continue through the forge/drop.
Overlay captions: `REAL TWITCH RAID`, `EventSub â†’ OBS ~0.5 s`, then `REAL CHAT + EMOTES FORGE THE RELIC`.
Voiceover: â€œThis is a real raid from jasseex into shalyx_04 â€” simulation is off. Twitchâ€™s raid event reaches the visible OBS overlay in about half a second. During the forge, chat messages and emote fragments increase charge and alter the artifact.â€

## 1:32â€“1:55 â€” Persistence / final state
On screen: `evidence/final-demo-04-drop.png`, then Raid Archive/dashboard.
Voiceover: â€œRarity is calculated from the actual raid and chat stats â€” it is not a hard-coded Legendary label. When the timer ends, the relic locks into a deterministic final form and is persisted to SQLite. We also verified the exact relic survives a full app restart.â€

## 1:55â€“2:23 â€” Codex proof
On screen: actual Codex build thread/session and 2â€“3 concrete build excerpts.
Show session ID `01a18920-5b89-704d-a5d8-fe8f5e392069`.
Voiceover: â€œI built RaidRelic with OpenAI Codex. Codex implemented and iterated on the EventSub raid and chat path, OAuth, reconnect behavior, the forge state engine, SSE overlay, SQLite archive and tests. During live testing I used it to diagnose OBS and Twitch issues, repair the real-chat renderer, and turn the acceptance runs into reproducible evidence.â€

## 2:23â€“2:35 â€” Close
On screen: final relic + RaidRelic logo/tagline.
Voiceover: â€œRaidRelic. Every raid leaves something behind.â€

## Recording rules
- Hard cap: under 3:00.
- Keep the real Twitch/OBS segment visually dominant.
- Show actual Codex evidence, not only a text claim that Codex was used.
- Do not label evidence-replay frames as live; the final screenshots already carry `EVIDENCE REPLAY Â· REAL TWITCH DATA`.
- Do not show Twitch secrets, access tokens, `.env` contents or private account data.

