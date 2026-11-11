# RaidRelic Preview — Shipwrit persistence validation

Date: 2026-11-11 UTC  
Application branch: `hosted-multitenant`  
Contract commit: `b95b585b00aeabab0f9df64f6d9228089cab7b96`  
Hermes profile: `forge`  
Shipwrit: `0.3.2` (enabled)  
Hermes Agent: `0.19.0`

## Result

The same read-only Shipwrit contract was run by actual LLM-driven Hermes CLI sessions against three isolated Preview states:

The BLOCK run used a copy of the root contract with only its host allowlist changed to the degraded deployment URL; that exact copy is preserved as `release-witness-broken.json` in this evidence folder.

| Run | Result | Observation |
|---|---|---|
| Baseline | PASS | Both health/durability and database-backed state-read checks passed |
| Adversarial | BLOCK | HTTP 200 concealed `service_ready=false` and `durable_storage=false`; Shipwrit stopped at the first step |
| Restored | PASS | Both checks passed again after the Preview database configuration was restored |

## Deployment isolation

- Baseline Preview: `dpl_8yNHKm2i5ZYZPySzrMGfu8TtaFeM`
- Deliberately degraded Preview: `dpl_4yGjPXJZA4YaxTs1Vo6wa8azQzwH`
- Restored Preview: `dpl_8jFz8mAgFqbpmcCsjm7VNQa8kQHN`

The adversarial deployment was built from the same `hosted-multitenant` commit. Only the Preview-targeted `DATABASE_URL` was temporarily set to an empty value. This caused the app to use its ephemeral fallback and report HTTP 200 with durability and readiness false. The Preview database URL was then restored to the isolated Neon branch `br-royal-mud-zacehomz`, database `raidrelic_validation`, and a fresh Preview deployment was built.

Production environment variables and production deployments were not modified.

## Data safety

All Shipwrit calls used `allow_writes=false`. No Twitch authorization was granted and no application data was written. After the test, Neon reported zero rows in all five application tables: `streamers`, `events`, `sessions`, `oauth_states`, and `oauth_health`.

## Actual Hermes sessions

- Baseline PASS: `20261112_044205_7ba5fe`
- Adversarial BLOCK: `20261112_045108_a8bb2e`
- Restored PASS: `20261112_045150_a89b2e`

The receipt JSON files below are the actual Shipwrit output. Each receipt's embedded SHA-256 was independently checked with Shipwrit's `verify_receipt.py` and returned `VALID receipt digest`.

## Receipts

- `baseline-pass.json`: `cd475dbfb8374c7f03078a1e1c52ea22a770092bdb3d265b71f12aa80f91bf46`
- `database-failure-block.json`: `04d4540491a735ba95a68037e1b2abf540ccc9c2cfca408577509c3171aff222`
- `restored-pass.json`: `5534ded04af6253862df4c76e99e2b50467dd59545b59b8a7910042e28ca82b2`

This validates the configured Preview health/read contract and the specific persistence failure tested. It is not a claim that every RaidRelic user journey, Twitch integration, or production workload has been certified.
