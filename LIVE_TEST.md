# First real Twitch slice — acceptance record

**Status: PASS. Real Twitch raid, chat + emote mutation, visible OBS latency, forge archive, transparency, and exact real-relic restart persistence are all proven.**

## Prerequisites

- Developer app credentials configured in the runtime; no secrets in project files.
- Receiving broadcaster authorizes `user:read:chat`; app shows connected and both subscriptions enabled.
- Second Twitch account/channel available to raid the receiver.
- Receiving stream live and overlay source active in OBS.
- App stays running through forge completion. Disable developer simulation for the live test.

## Observe this exact path

1. Record Twitch itself and OBS together. Note timestamp and current code revision.
2. From the second account, perform a real raid into the receiving channel.
3. Confirm the overlay opens automatically and shows the actual raider + viewer count.
4. Send one real Twitch chat message during the 45 seconds; observe message/unique-chatter count and charge change. Send an emote and observe its count/charge change.
5. Measure chat action → visible overlay response from the recording. Record measured latency; do not infer it from server receive time alone. Initial acceptance target: visible within 2 seconds, subject to recording/network limits.
6. Wait for the forge to complete. Observe the final deterministic relic and matching archive entry.
7. Reload the archive, restart the app using the same SQLite file, and confirm the relic ID/seed, raid metadata and counts still match.
8. Verify OBS captures the overlay with transparent surrounding area, without a full-screen opaque page.

## Evidence to retain

- Recording reference, checked-at time, code revision and machine/browser/OBS versions.
- `/api/state` response immediately after real raid, after chat, and after completion; includes most recent transport event ID/timestamps and aggregated session data. Inspect before sharing. No tokens are returned.
- Same relic after app restart; a screenshot alone does not prove durability.
- Distinguish observed Twitch delivery from local fixtures. Only the transport adapter accepts real notifications; no HTTP route can inject into the Twitch namespace.

## Pass record (fill only after observation)

| Item | Current result |
|---|---|
| Real incoming raid opens forge | PROVEN — repeated real `jasseex` → `shalyx_04` raids, 1 viewer, real `twitch` forge created |
| Real chat mutates visible forge | PROVEN — real chat and emote fragments mutated the forge; second run finished at 5 messages, 1 chatter, 4 emotes, charge 36 |
| Measured Twitch-to-overlay latency | PROVEN — second recorded raid ~0.496 s Twitch timestamp → first visible OBS frame; earlier recorded raid cross-check ~0.671 s |
| OBS transparent browser source | PROVEN — alpha compositing verified over red test background; real overlay recorded using the same Browser Source |
| Forge finishes and archive matches | PROVEN — second real run archived session `twitch:KEJz0k5eNbAWCoMx_tYPLb1S6P8zPLfyiS0RnDpkgWI=` with seed ending `:5:1:4` |
| Persistence after process restart | PROVEN — exact second-run session matched after full app-process restart: ID, phase, counts, raid metadata and complete relic parameters |
| Same seed reproduces geometry | PROVEN — deterministic local test plus unchanged real relic parameters after restart |

TECHNICAL_DERISK exit criteria are satisfied by the observed live evidence above. The project may advance through the already-complete vertical-slice checkpoint into PRODUCT_REVIEW; scope remains locked until that review.


## Separate local rehearsal note (2026-10-30)

A simulated raid/chat/forge/archive path and SQLite restart persistence test passed on the target PC. This is recorded in `evidence/local-rehearsal-2026-10-30.md`. It remains separate from live proof. The first real Twitch run is now recorded in `evidence/live-twitch-run-2026-11-01.md`; visible OBS latency, emote mutation, and restart persistence of that real relic remain open.


## Local OBS prerequisite update — 2026-11-01

OBS Browser Source rendering and alpha transparency are proven locally with the simulation overlay. The real Twitch raid/chat path has now passed. Remaining OBS acceptance work is explicit visible live-overlay timing/observation using the same Browser Source configuration.

## Twitch OAuth + EventSub prerequisite pass � 2026-11-01

- Receiving broadcaster authorization completed for `shalyx_04` (channel id 1599174289).
- `/api/state` reported `connected` with both required subscriptions enabled: `channel.raid` and `channel.chat.message` (2/2).
- Simulation remained disabled.
- OBS Browser Source was switched from `/overlay/simulation` to the real broadcaster route `/overlay/1599174289` and OBS restarted successfully.
- A local watcher was armed at `evidence/live-twitch-watch.jsonl` to retain state transitions and Twitch event timestamps during the real raid/chat test.
- OAuth/EventSub setup was subsequently followed by an observed real raid, real chat mutation, and real forge archive. See `evidence/live-twitch-run-2026-11-01.md`; visible OBS timing, emote mutation, and real-relic restart persistence remain open.
