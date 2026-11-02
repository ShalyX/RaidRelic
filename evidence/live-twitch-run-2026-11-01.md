# RaidRelic live Twitch run — 2026-11-01

Classification: observed live Twitch evidence on target Windows PC. No simulation route was enabled.

## Environment
- Receiving broadcaster: `shalyx_04`
- Real raiding channel: `jasseex`
- OBS: regular Twitch RTMP stream active; Enhanced Broadcasting disabled because the Intel HD 520 was unsupported for that Twitch mode.
- RaidRelic Twitch connection: `connected`
- Enabled EventSub subscriptions: `channel.raid`, `channel.chat.message`

## Real raid observation
- EventSub type: `channel.raid`
- Event message ID: `yAYMLo-94gX-nlvGD0Pdsn2H5EBPq4-Q1gJeJgDVImo=`
- Twitch event timestamp: `2026-11-01T01:00:05.360860365Z`
- RaidRelic received_at: `1793494805.764065`
- Calculated Twitch timestamp -> server receive latency: approximately **0.403 s**
- Raider: `jasseex`
- Recipient: `shalyx_04`
- Viewer count: `1`
- Result: created a real `twitch` FORGING session.

## Real chat mutation
- One real `channel.chat.message` landed while the forge was active.
- Twitch event timestamp: `2026-11-01T01:00:32.238377838Z`
- RaidRelic received_at: `1793494832.7376118`
- Calculated Twitch timestamp -> server receive latency: approximately **0.500 s**
- Forge changed from messages `0` / charge `0` to messages `1` / unique chatters `1` / charge `8`.
- Emote count remained `0`; the emote acceptance detail was not captured before this forge expired.

## Completion
- Session ID: `twitch:yAYMLo-94gX-nlvGD0Pdsn2H5EBPq4-Q1gJeJgDVImo=`
- Completion reason: `timer`
- Final real-session counts: messages `1`, unique chatters `1`, emotes `0`, charge `8`
- Deterministic relic seed: `twitch:yAYMLo-94gX-nlvGD0Pdsn2H5EBPq4-Q1gJeJgDVImo=:1:1:0`
- Result: real Twitch forge archived successfully.

## What this proves
- Real incoming Twitch raid delivery: PROVEN.
- Real Twitch chat delivery and forge mutation: PROVEN.
- Real forge completion/archive: PROVEN for this run.
- Server-side Twitch EventSub transport latency: observed at ~0.403 s for raid and ~0.500 s for chat.

## Remaining limitations
- Visible Twitch -> OBS overlay latency was not measured from a recording or explicit visual timing observation; do not substitute server transport latency for that acceptance item.
- Emote-fragment mutation was not captured in this run.
- Persistence of this exact real Twitch relic across an app process restart still needs explicit verification.

## Second live run — emote proof

Observed real Twitch raid from `jasseex` into `shalyx_04` (1 viewer), session `twitch:KEJz0k5eNbAWCoMx_tYPLb1S6P8zPLfyiS0RnDpkgWI=`.

Final archived state: 5 messages, 1 unique chatter, 4 emotes, charge 36, completion reason `timer`.
Deterministic seed: `twitch:KEJz0k5eNbAWCoMx_tYPLb1S6P8zPLfyiS0RnDpkgWI=:5:1:4`.
This proves real Twitch emote fragments mutate the active forge.

OBS recording started at 2026-11-01 02:04:21 WAT before this run. Recording file: `C:\Users\USER\OneDrive\Videos\2026-11-01 02-04-20.mp4`. Visible-overlay timing analysis pending file finalization after recording stops.

## Visible OBS latency proof — second live run

Recording: `C:\Users\USER\OneDrive\Videos\2026-11-01 02-04-20.mp4` (1280×720, 30 fps). OBS log records recording start at `2026-11-01 02:04:21.841 WAT`.

Second-run raid EventSub timestamp: `2026-11-01T01:07:15.778042091Z` (`02:07:15.778 WAT`). RaidRelic `received_at`: `1793495236.1874518` (`02:07:16.187 WAT`). The first non-black RaidRelic overlay frame in the OBS recording is frame 5233 at media time `174.433333 s`; frame 5232 at `174.400000 s` is fully blank in the inspected crop.

Derived timing:
- Twitch event timestamp → first visible OBS overlay frame: approximately **0.496 s**.
- RaidRelic receive → first visible OBS overlay frame: approximately **0.087 s**.
- Acceptance target `<2 s`: **PASS**.

Cross-check on the earlier recorded real raid: first overlay frame at `108.233333 s`, corresponding to approximately **0.671 s** Twitch timestamp → visible OBS. Two independent real raids therefore rendered visibly in under one second.

Pixel-analysis artifact: `evidence/raid-transition-contact.png`.

## Exact real-relic restart persistence

Before restart, session `twitch:KEJz0k5eNbAWCoMx_tYPLb1S6P8zPLfyiS0RnDpkgWI=` was archived with messages `5`, emotes `4`, charge `36`, unique chatters `1`, and seed `twitch:KEJz0k5eNbAWCoMx_tYPLb1S6P8zPLfyiS0RnDpkgWI=:5:1:4`.

The RaidRelic app server process was stopped completely, port 3000 closed, and a fresh `python -m app.server` process was started against the same SQLite database with simulation disabled and no Twitch credentials. The restarted API returned the exact same session.

Pre/post comparison: ID `True`, phase `True`, counts `True`, raid metadata `True`, full relic parameters `True` (seed, hue, sides, facets).

Snapshots: `evidence/real-relic-pre-restart.json` and `evidence/real-relic-post-restart.json`.

## Final live acceptance result

Real raid delivery: **PROVEN**. Real chat mutation: **PROVEN**. Real emote mutation: **PROVEN**. Visible Twitch→OBS latency: **PROVEN** (<1 s in two observed raids). OBS alpha transparency: **PROVEN**. Real forge archive: **PROVEN**. Exact real-relic persistence across app restart: **PROVEN**. TECHNICAL_DERISK exit criteria are satisfied.
