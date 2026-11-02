# RaidRelic final demo — target 2:35

## 0:00–0:08 — Hook
On screen: RaidRelic title + final relic drop.
Voiceover: “A Twitch raid usually disappears as fast as it arrives. RaidRelic turns that handoff into something the community can keep.”

## 0:08–0:22 — Product in one sentence
On screen: dashboard / architecture cue.
Voiceover: “A real Twitch raid hijacks the OBS overlay. For 45 seconds, real chat messages and emotes forge a one-of-one relic. Participation changes its charge, shape and rarity, then the relic is saved to the channel archive.”

## 0:22–1:32 — Real Twitch proof
Use the real OBS recording `C:\Users\USER\OneDrive\Videos\2026-11-01 02-04-20.mp4`.
Recommended source window: start a few seconds before media time ~174.43s, where the second real raid first appears, and continue through the forge/drop.
Overlay captions: `REAL TWITCH RAID`, `EventSub → OBS ~0.5 s`, then `REAL CHAT + EMOTES FORGE THE RELIC`.
Voiceover: “This is a real raid from jasseex into shalyx_04 — simulation is off. Twitch’s raid event reaches the visible OBS overlay in about half a second. During the forge, chat messages and emote fragments increase charge and alter the artifact.”

## 1:32–1:55 — Persistence / final state
On screen: `evidence/final-demo-04-drop.png`, then Raid Archive/dashboard.
Voiceover: “Rarity is calculated from the actual raid and chat stats — it is not a hard-coded Legendary label. When the timer ends, the relic locks into a deterministic final form and is persisted to SQLite. We also verified the exact relic survives a full app restart.”

## 1:55–2:23 — Codex proof
On screen: actual Codex build thread/session and 2–3 concrete build excerpts.
Show session ID `01a18533-b988-71d3-a923-3676d29efca1`.
Voiceover: “I built RaidRelic with OpenAI Codex. Codex implemented and iterated on the EventSub raid and chat path, OAuth, reconnect behavior, the forge state engine, SSE overlay, SQLite archive and tests. During live testing I used it to diagnose OBS and Twitch issues, repair the real-chat renderer, and turn the acceptance runs into reproducible evidence.”

## 2:23–2:35 — Close
On screen: final relic + RaidRelic logo/tagline.
Voiceover: “RaidRelic. Every raid leaves something behind.”

## Recording rules
- Hard cap: under 3:00.
- Keep the real Twitch/OBS segment visually dominant.
- Show actual Codex evidence, not only a text claim that Codex was used.
- Do not label evidence-replay frames as live; the final screenshots already carry `EVIDENCE REPLAY · REAL TWITCH DATA`.
- Do not show Twitch secrets, access tokens, `.env` contents or private account data.
