<!--
Product: TotalReclaw (Full Stack E2E)
Version: 2.0
Last updated: 2026-03-04
-->

# E2E Integration Test Plan v2 — Relay + Paymaster + Billing

**Version:** 2.0
**Date:** March 4, 2026
**Scope:** End-to-end testing of the full production stack: OpenClaw Skill -> Relay Server -> Pimlico Paymaster -> Gnosis Chain -> Subgraph -> Client retrieval, including Stripe and Coinbase Commerce billing integration.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Test Infrastructure Architecture](#2-test-infrastructure-architecture)
3. [Test Tiers](#3-test-tiers)
4. [Journey A — New User (Free Tier)](#4-journey-a--new-user-free-tier)
5. [Journey B — Paid User (Stripe)](#5-journey-b--paid-user-stripe)
6. [Journey C — Paid User (Coinbase Commerce)](#6-journey-c--paid-user-coinbase-commerce)
7. [Journey D — Unauthorized / Attack Scenarios](#7-journey-d--unauthorized--attack-scenarios)
8. [Journey E — Cross-Device Recovery](#8-journey-e--cross-device-recovery)
9. [Journey F — Agent-Driven UX](#9-journey-f--agent-driven-ux)
10. [Journey G — Relay-Specific (Full Pipeline)](#10-journey-g--relay-specific-full-pipeline)
11. [Cross-Journey Edge Cases](#11-cross-journey-edge-cases)
12. [Test Applicability Matrix](#12-test-applicability-matrix)
13. [Estimated Effort](#13-estimated-effort)
14. [Open Questions](#14-open-questions)

---

## 1. Overview

### Motivation

The existing E2E functional test suite (`tests/e2e-functional/`) validates retrieval quality across server-mode and subgraph-mode backends using fully mocked infrastructure. It covers 8 scenarios (A-H) across 5 instance configurations and achieves 66/66 PASS.

This plan extends coverage to the **billing and relay layers** — the production code paths that did not exist when the original suite was written. These include:

- **Relay server** (`server/src/relay/`) — UserOp sponsorship, Pimlico JSON-RPC, webhook authorization
- **Billing** (`server/src/billing/`) — Stripe Checkout, Coinbase Commerce charges, subscription state machine, free-tier gating
- **Paymaster** — Pimlico conditional sponsorship via webhook callback
- **On-chain execution** — UserOp submission, Gnosis Chain transaction, Graph Node indexing

### Goals

1. Validate every user journey a real Opus user would encounter, from seed generation through paid subscription and cross-device recovery.
2. Identify which tests can run in CI (fast, mocked) vs. which require live testnet/sandbox (slow, manual).
3. Define a clear mock boundary for each test tier.
4. Cover security edge cases (replay attacks, signature spoofing, contract targeting).

### Non-Goals

- Benchmark performance (covered by `subgraph/tests/` and OMBH).
- Retrieval quality measurement (covered by existing E2E functional suite).
- Load testing (separate effort).

---

## 2. Test Infrastructure Architecture

### 2.1 Three-Tier Test Pyramid

```
                    +---------------------------+
                    |   Tier 3: Live Testnet     |  <- Chiado + Stripe sandbox
                    |   (manual, weekly)         |     + Coinbase sandbox
                    +---------------------------+
               +-----------------------------------+
               |   Tier 2: Integration (Docker)     |  <- Real PG + FastAPI
               |   (CI, per-PR)                     |     + mock Pimlico/Stripe
               +-----------------------------------+
          +-----------------------------------------+
          |   Tier 1: Unit + Mock (In-Process)       |  <- Extend existing
          |   (CI, every commit, <30s)               |     mock infrastructure
          +-----------------------------------------+
```

### 2.2 Mock Service Inventory

| Service | Tier 1 (Mock) | Tier 2 (Docker) | Tier 3 (Live) |
|---------|:---:|:---:|:---:|
| TotalReclaw Server (FastAPI) | In-memory mock (existing `mock-server.ts`) | Real process in Docker | Real process |
| PostgreSQL | Mocked via in-memory dict | Real PG container | Real PG |
| Pimlico Paymaster API | Mock HTTP server (JSON-RPC) | Mock HTTP server | **Real Pimlico (Chiado)** |
| Pimlico Bundler | Mock (returns fake hashes) | Mock | **Real Pimlico** |
| Stripe API | Mock (returns fake sessions) | Stripe sandbox (test keys) | **Stripe sandbox** |
| Coinbase Commerce API | Mock (returns fake charges) | Mock | **Coinbase sandbox** |
| Gnosis Chain (Chiado) | N/A | Local Hardhat fork | **Real Chiado testnet** |
| Graph Node | N/A | Docker container | **Chiado subgraph** |
| OpenClaw Plugin | Direct import (existing pattern) | Direct import | Real OpenClaw agent |

### 2.3 Mock Relay + Paymaster Server (New)

Extends `tests/e2e-functional/mock-subgraph.ts` to add:

1. **`POST /v1/relay/sponsor`** — Mock sponsorship endpoint. Validates UserOp structure, checks in-memory subscription state, returns fake `userOpHash`.
2. **`POST /v1/relay/webhook/pimlico`** — Mock Pimlico webhook. Calls the `WebhookHandler` logic against in-memory subscription state.
3. **`GET /v1/relay/status/:hash`** — Returns configurable status (`pending` | `included` | `failed`).
4. **`POST /v1/billing/checkout`** — Returns a fake Stripe Checkout URL.
5. **`POST /v1/billing/checkout/crypto`** — Returns a fake Coinbase Commerce hosted URL.
6. **`POST /v1/billing/webhook/stripe`** — Accepts simulated Stripe webhook events, updates in-memory subscription state.
7. **`POST /v1/billing/webhook/coinbase`** — Accepts simulated Coinbase webhook events, updates in-memory subscription state.
8. **`GET /v1/billing/status`** — Returns subscription status from in-memory state.

**In-memory subscription store:**
```typescript
interface MockSubscription {
  wallet_address: string;
  tier: 'free' | 'pro';
  source: 'stripe' | 'coinbase_commerce' | null;
  expires_at: Date | null;
  free_writes_used: number;
  free_writes_limit: number;  // configurable, default 100
}
const subscriptions = new Map<string, MockSubscription>();
```

### 2.4 Test Runner Integration

The new tests integrate into the existing `run-all.ts` orchestrator as additional instance configurations (e.g., `relay-free`, `relay-paid-stripe`, `relay-paid-crypto`). The mock relay server is started alongside the existing mock server and mock subgraph.

For Tier 2 (Docker), a separate `docker-compose.test.yml` spins up:
- PostgreSQL (with `subscriptions` table migration)
- FastAPI server (with billing + relay routes)
- Mock Pimlico HTTP server

For Tier 3 (Live), a CLI script (`tests/e2e-live/run-chiado.sh`) orchestrates against real services with manual confirmation steps.

---

## 3. Test Tiers

### Tier 1 — Unit + Mock (In-Process)

- **Runtime:** <30 seconds total
- **Trigger:** Every commit, CI
- **Services:** All mocked in-process
- **Database:** In-memory Maps
- **Coverage:** Journeys A-G (all tests below marked `Tier 1`)
- **Framework:** Extends existing `tests/e2e-functional/`

### Tier 2 — Integration (Docker)

- **Runtime:** ~3-5 minutes
- **Trigger:** Per-PR, CI
- **Services:** Real FastAPI + PG, mock Pimlico, mock Stripe/Coinbase
- **Database:** Real PostgreSQL
- **Coverage:** All Tier 1 tests + database consistency checks
- **Framework:** `docker-compose.test.yml` + pytest + tsx test runner

### Tier 3 — Live Testnet

- **Runtime:** ~15-30 minutes (includes on-chain confirmation time)
- **Trigger:** Weekly manual, pre-release
- **Services:** Real Pimlico (Chiado), Stripe sandbox, Coinbase sandbox
- **Database:** Real PostgreSQL
- **Coverage:** Journeys A, B, C, G (on-chain verification)
- **Framework:** `tests/e2e-live/run-chiado.sh`
- **Prerequisites:** Chiado xDAI faucet, Pimlico Chiado API key, Stripe test keys, Coinbase sandbox keys

---

## 4. Journey A — New User (Free Tier)

### T-A01: Seed Generation and Wallet Derivation
**Journey:** A
**Prerequisites:** Clean environment, no credentials file
**Steps:**
1. Initialize the plugin with a fresh `TOTALRECLAW_MASTER_PASSWORD`.
2. Plugin generates BIP-39 seed internally.
3. Plugin derives Smart Account address from seed via `m/44'/60'/0'/0/0`.
4. Plugin registers with the relay server.
**Expected:** Wallet address is a valid ERC-4337 Smart Account address (0x-prefixed, 42 chars). Registration succeeds.
**Asserts:**
- assert wallet_address matches `/^0x[0-9a-fA-F]{40}$/`
- assert registration response `success == true`
- assert credentials file is written to `TOTALRECLAW_CREDENTIALS_PATH`
**Mock/Real:** All mocked (Tier 1)

---

### T-A02: First Memory Store (Free Tier, Sponsored)
**Journey:** A
**Prerequisites:** T-A01 complete. User has wallet address. Free tier (no subscription row).
**Steps:**
1. User sends a message: "I prefer dark mode and use VS Code."
2. Plugin fires `agent_end` hook, extracts facts.
3. Plugin encodes facts as protobuf, submits to relay (`POST /v1/relay/sponsor`).
4. Relay checks subscription status — no row exists, treated as free tier.
5. Relay sponsors the UserOp (mock paymaster returns stub data).
6. Relay submits to bundler (mock returns `userOpHash`).
7. Plugin receives success response.
**Expected:** Store succeeds. Subscription row created with `tier=free`, `free_writes_used=1`.
**Asserts:**
- assert relay response `success == true`
- assert `userOpHash` is 0x-prefixed, 66 chars
- assert mock subscription state: `free_writes_used == 1`
- assert protobuf payload decodes correctly (blind indices present, encrypted blob non-empty)
**Mock/Real:** All mocked (Tier 1). Tier 2 validates against real PG.

---

### T-A03: First Memory Retrieval (Free Tier)
**Journey:** A
**Prerequisites:** T-A02 complete. At least one fact stored.
**Steps:**
1. User sends a message: "What are my editor preferences?"
2. Plugin fires `before_agent_start` hook, generates trapdoors.
3. Plugin queries subgraph (mock GraphQL) with trapdoors.
4. Mock subgraph returns matching blind index entries with encrypted facts.
5. Plugin decrypts candidates, runs BM25 + cosine + RRF reranking.
6. Top results injected into agent context.
**Expected:** At least one relevant result returned and decrypted successfully.
**Asserts:**
- assert injected context contains reference to "dark mode" or "VS Code"
- assert GraphQL query includes correct `owner` (wallet address)
- assert decryption does not throw
**Mock/Real:** All mocked (Tier 1)

---

### T-A04: Free Tier Counter Increments Correctly
**Journey:** A
**Prerequisites:** Clean subscription state.
**Steps:**
1. Store N facts (where N = 5) sequentially via relay.
2. After each store, check the mock subscription state.
**Expected:** `free_writes_used` increments from 0 to 5.
**Asserts:**
- assert after store i: `free_writes_used == i` for i in 1..5
- assert all stores return `success == true`
**Mock/Real:** All mocked (Tier 1). Tier 2 validates atomicity with real PG.

---

### T-A05: Free Tier Limit Reached — Sponsorship Denied
**Journey:** A
**Prerequisites:** Subscription state with `free_writes_used == FREE_TIER_LIMIT` (default 100).
**Steps:**
1. Set mock subscription: `{ tier: 'free', free_writes_used: 100, free_writes_limit: 100 }`.
2. User stores a new memory.
3. Plugin submits to relay.
4. Relay checks subscription — free tier exhausted.
5. Relay/paymaster returns `{ sponsor: false, reason: "upgrade_required" }`.
6. Plugin receives sponsorship denied error.
**Expected:** Store fails with upgrade_required reason. Plugin should surface an upgrade prompt.
**Asserts:**
- assert relay response `success == false`
- assert error contains "upgrade_required" or "SPONSORSHIP_FAILED"
- assert `free_writes_used` remains at 100 (no increment on failure)
**Mock/Real:** All mocked (Tier 1)

---

### T-A06: Reads Still Work After Write Limit Exhausted
**Journey:** A
**Prerequisites:** T-A05 state (free tier exhausted), but facts exist from previous writes.
**Steps:**
1. User sends a search query: "What do I prefer?"
2. Plugin fires `before_agent_start`, generates trapdoors.
3. Plugin queries subgraph — GraphQL reads do NOT require relay sponsorship.
4. Results returned and decrypted.
**Expected:** Search succeeds. Reads are not gated by free-tier write limits.
**Asserts:**
- assert search returns results (not empty)
- assert no relay/sponsor call is made for reads
- assert decrypted results contain previously stored facts
**Mock/Real:** All mocked (Tier 1)

---

### T-A07: Free Tier Monthly Reset
**Journey:** A
**Prerequisites:** Subscription state with `free_writes_used == 100`, `free_writes_reset_at` set to previous month.
**Steps:**
1. Set mock subscription: `{ free_writes_used: 100, free_writes_reset_at: 2026-02-01T00:00:00Z }`.
2. Current date is March 2026.
3. User stores a new memory.
4. Relay/webhook handler checks `free_writes_reset_at` against current month start.
5. Counter resets to 0, then increments to 1.
**Expected:** Store succeeds because the monthly reset triggers.
**Asserts:**
- assert relay response `success == true`
- assert `free_writes_used == 1` after store
- assert `free_writes_reset_at` updated to current month start
**Mock/Real:** Tier 1 (mock with controlled clock). Tier 2 validates with real PG + `check_and_increment_free_usage`.

---

## 5. Journey B — Paid User (Stripe)

### T-B01: Create Stripe Checkout Session
**Journey:** B
**Prerequisites:** Authenticated user with wallet address. Free tier.
**Steps:**
1. Plugin (or agent) calls `POST /v1/billing/checkout` with `{ wallet_address, tier: "pro" }`.
2. Server calls Stripe API (mocked) to create a Checkout Session.
3. Server returns checkout URL.
**Expected:** Valid checkout URL returned.
**Asserts:**
- assert response `success == true`
- assert `checkout_url` is a valid URL (starts with `https://checkout.stripe.com/` in mock)
- assert Stripe Customer created (or reused) for wallet address
**Mock/Real:** Tier 1 (mock Stripe). Tier 2 (Stripe sandbox with test keys). Tier 3 (Stripe sandbox).

---

### T-B02: Stripe Webhook — checkout.session.completed
**Journey:** B
**Prerequisites:** T-B01 complete. Checkout session ID known.
**Steps:**
1. Simulate Stripe webhook: `checkout.session.completed` event with `client_reference_id = wallet_address`, `subscription = sub_xxx`.
2. Include valid `Stripe-Signature` header (mock: any valid signature; Tier 2: real Stripe test signature).
3. Server processes webhook, upserts subscription row.
**Expected:** Subscription activated. Tier changed to `pro`.
**Asserts:**
- assert webhook response `success == true`
- assert subscription row: `tier == "pro"`, `source == "stripe"`, `stripe_id == "sub_xxx"`
- assert `expires_at` is set (from Stripe `current_period_end`)
**Mock/Real:** Tier 1 (mock). Tier 2 (mock Stripe, real PG). Tier 3 (Stripe sandbox webhook).

---

### T-B03: Paid User Stores Memories — No Limit
**Journey:** B
**Prerequisites:** T-B02 complete. User is on `pro` tier with active subscription.
**Steps:**
1. Store 150 facts sequentially (exceeding the free-tier limit of 100).
2. Each store goes through relay sponsorship.
**Expected:** All 150 stores succeed. No sponsorship denial.
**Asserts:**
- assert all 150 relay responses: `success == true`
- assert `free_writes_used` does NOT increment (pro tier bypasses counter)
- assert webhook handler returns `{ sponsor: true, reason: "active_subscription" }` for each
**Mock/Real:** Tier 1 (mock, but can use 5 stores to test the pattern). Tier 2 (real PG, 20 stores).

---

### T-B04: Stripe Subscription Updated — Period Extended
**Journey:** B
**Prerequisites:** Active pro subscription via Stripe.
**Steps:**
1. Simulate Stripe webhook: `customer.subscription.updated` with `status: "active"`, new `current_period_end`.
2. Server processes webhook.
**Expected:** Subscription `expires_at` updated to new period end.
**Asserts:**
- assert subscription row: `expires_at` matches new `current_period_end`
- assert `tier` remains `"pro"`
**Mock/Real:** Tier 1 (mock). Tier 2 (mock Stripe, real PG).

---

### T-B05: Stripe Subscription Deleted — Downgrade to Free
**Journey:** B
**Prerequisites:** Active pro subscription via Stripe.
**Steps:**
1. Simulate Stripe webhook: `customer.subscription.deleted` with `id = sub_xxx`.
2. Server processes webhook.
**Expected:** User downgraded to free tier.
**Asserts:**
- assert subscription row: `tier == "free"`, `expires_at == null`, `stripe_id == null`
- assert subsequent stores are gated by free-tier limit
**Mock/Real:** Tier 1 (mock). Tier 2 (mock Stripe, real PG).

---

### T-B06: Stripe Subscription Expired — Treated as Free
**Journey:** B
**Prerequisites:** Pro subscription with `expires_at` in the past.
**Steps:**
1. Set subscription: `{ tier: "pro", expires_at: 2026-02-15T00:00:00Z }` (past date).
2. User stores a fact.
3. Relay webhook handler checks subscription — expired.
4. Falls through to free-tier logic.
**Expected:** If free-tier quota remains, store succeeds. If exhausted, store denied.
**Asserts:**
- assert webhook handler returns `reason: "free_tier"` (not "active_subscription")
- assert `free_writes_used` increments (free-tier counter engaged)
**Mock/Real:** Tier 1 (mock with controlled clock). Tier 2 (real PG).

---

### T-B07: Invoice Payment Succeeded — Subscription Renewed
**Journey:** B
**Prerequisites:** Active pro subscription via Stripe.
**Steps:**
1. Simulate Stripe webhook: `invoice.payment_succeeded` with `subscription = sub_xxx`.
2. Server fetches updated subscription from Stripe (mocked) to get new `current_period_end`.
3. Server updates `expires_at`.
**Expected:** Subscription extended.
**Asserts:**
- assert `expires_at` updated to new period end
- assert `tier` remains `"pro"`
**Mock/Real:** Tier 1 (mock). Tier 2 (mock Stripe, real PG).

---

### T-B08: Invalid Tier in Checkout Request
**Journey:** B
**Prerequisites:** Authenticated user.
**Steps:**
1. Call `POST /v1/billing/checkout` with `{ wallet_address, tier: "enterprise" }`.
**Expected:** Request rejected with INVALID_TIER.
**Asserts:**
- assert response `success == false`
- assert `error_code == "INVALID_TIER"`
**Mock/Real:** All tiers (this is pure server validation).

---

## 6. Journey C — Paid User (Coinbase Commerce)

### T-C01: Create Coinbase Commerce Charge
**Journey:** C
**Prerequisites:** Authenticated user with wallet address. Free tier.
**Steps:**
1. Plugin calls `POST /v1/billing/checkout/crypto` with `{ wallet_address, tier: "pro" }`.
2. Server calls Coinbase Commerce API (mocked) to create a charge.
3. Server returns hosted checkout URL.
**Expected:** Valid Coinbase Commerce checkout URL returned.
**Asserts:**
- assert response `success == true`
- assert `checkout_url` is a valid URL (starts with `https://commerce.coinbase.com/` in mock)
- assert charge metadata includes `wallet_address`
**Mock/Real:** Tier 1 (mock). Tier 2 (mock). Tier 3 (Coinbase sandbox).

---

### T-C02: Coinbase Webhook — charge:confirmed
**Journey:** C
**Prerequisites:** T-C01 complete. Charge created.
**Steps:**
1. Simulate Coinbase Commerce webhook: `charge:confirmed` with `metadata.wallet_address = wallet_address`.
2. Include valid `X-CC-Webhook-Signature` header (HMAC-SHA256).
3. Server processes webhook, activates subscription.
**Expected:** Pro subscription activated for 30 days.
**Asserts:**
- assert webhook response `status == "activated"`
- assert subscription row: `tier == "pro"`, `source == "coinbase_commerce"`
- assert `expires_at` is approximately `now + 30 days`
- assert `coinbase_id` is set
**Mock/Real:** Tier 1 (mock). Tier 2 (mock, real PG). Tier 3 (Coinbase sandbox webhook).

---

### T-C03: Coinbase Pro User Stores Memories
**Journey:** C
**Prerequisites:** T-C02 complete. Active pro subscription via Coinbase.
**Steps:**
1. Store 5 facts via relay.
**Expected:** All stores succeed (pro tier, no limit).
**Asserts:**
- assert all relay responses `success == true`
- assert webhook handler returns `{ sponsor: true, reason: "active_subscription" }`
**Mock/Real:** Tier 1 (mock). Tier 2 (real PG).

---

### T-C04: Coinbase Subscription Expires After 30 Days
**Journey:** C
**Prerequisites:** Active Coinbase-sourced pro subscription.
**Steps:**
1. Set subscription: `{ tier: "pro", source: "coinbase_commerce", expires_at: 2026-02-01T00:00:00Z }` (31+ days ago).
2. User stores a fact.
3. Relay checks subscription — expired.
**Expected:** Falls through to free-tier logic. Store succeeds if free quota remains, fails if exhausted.
**Asserts:**
- assert webhook handler does NOT return `reason: "active_subscription"`
- assert if `free_writes_used < limit`: store succeeds
- assert if `free_writes_used >= limit`: store denied with "upgrade_required"
**Mock/Real:** Tier 1 (mock with controlled clock). Tier 2 (real PG).

---

### T-C05: Coinbase Charge Extension — Stacking
**Journey:** C
**Prerequisites:** Active Coinbase pro subscription with `expires_at` 15 days from now.
**Steps:**
1. User pays again. Simulate `charge:confirmed` webhook with a new charge ID.
2. Server extends expiry: `new_expires = current_expires + 30 days` (not `now + 30`).
**Expected:** Expiry extended by 30 days from current expiry, not from now.
**Asserts:**
- assert `expires_at` is approximately `old_expires_at + 30 days`
- assert `expires_at` is NOT `now + 30 days`
- assert new `coinbase_id` is set (updated from previous)
**Mock/Real:** Tier 1 (mock). Tier 2 (real PG).

---

### T-C06: Coinbase Webhook — charge:failed
**Journey:** C
**Prerequisites:** Charge created but payment fails.
**Steps:**
1. Simulate Coinbase webhook: `charge:failed`.
**Expected:** No subscription change. User remains on free tier.
**Asserts:**
- assert webhook response `status == "failed"`
- assert subscription tier unchanged (still "free" or whatever it was before)
**Mock/Real:** Tier 1 (mock).

---

### T-C07: Coinbase Webhook — Idempotency
**Journey:** C
**Prerequisites:** T-C02 complete. Charge already processed.
**Steps:**
1. Replay the same `charge:confirmed` webhook with the same `charge_id`.
**Expected:** No duplicate activation. Subscription unchanged.
**Asserts:**
- assert `expires_at` did NOT extend again
- assert no error (200 OK response)
**Mock/Real:** Tier 1 (mock). Tier 2 (real PG — validates ON CONFLICT behavior).

---

### T-C08: Coinbase Webhook — Invalid Signature
**Journey:** C + D
**Prerequisites:** Webhook secret configured.
**Steps:**
1. Send a Coinbase webhook with an incorrect `X-CC-Webhook-Signature`.
**Expected:** Request rejected with 400.
**Asserts:**
- assert HTTP status 400
- assert no subscription change
**Mock/Real:** All tiers.

---

## 7. Journey D — Unauthorized / Attack Scenarios

### T-D01: No Auth Header — Relay Rejected
**Journey:** D
**Prerequisites:** Relay server running.
**Steps:**
1. Call `POST /v1/relay/sponsor` with no `Authorization` header.
**Expected:** 401 Unauthorized.
**Asserts:**
- assert HTTP status 401
- assert response body contains "unauthorized" or similar
**Mock/Real:** Tier 1 (mock), Tier 2 (real FastAPI with `get_current_user` dependency).

---

### T-D02: Invalid Signature — Relay Rejected
**Journey:** D
**Prerequisites:** Relay server running.
**Steps:**
1. Call `POST /v1/relay/sponsor` with `Authorization: Bearer <garbage>`.
**Expected:** 401 Unauthorized.
**Asserts:**
- assert HTTP status 401
**Mock/Real:** Tier 1 (mock), Tier 2 (real FastAPI).

---

### T-D03: Expired Pro + Exhausted Free Tier — Sponsorship Denied
**Journey:** D
**Prerequisites:** Subscription: `{ tier: "pro", expires_at: past, free_writes_used: 100 }`.
**Steps:**
1. Pimlico webhook calls relay with sponsorship request for this wallet.
2. Relay checks subscription — pro expired, free tier exhausted.
**Expected:** Sponsorship denied.
**Asserts:**
- assert `{ sponsor: false, reason: "upgrade_required" }`
**Mock/Real:** Tier 1 (mock). Tier 2 (real PG, `WebhookHandler._check_subscription`).

---

### T-D04: Replay Attack — Same UserOp Hash
**Journey:** D
**Prerequisites:** A UserOp has already been submitted and included on-chain.
**Steps:**
1. Capture the `userOpHash` from a successful submission.
2. Re-submit the same signed UserOp to `POST /v1/relay/sponsor`.
**Expected:** Bundler rejects with nonce error (the nonce has already been used).
**Asserts:**
- assert relay response `success == false`
- assert error message mentions "nonce" or "already known" or "AA25"
**Mock/Real:** Tier 1 (mock bundler returns nonce error for duplicate hash). Tier 3 (real Pimlico on Chiado — actual nonce check).

---

### T-D05: UserOp Targeting Wrong Contract
**Journey:** D
**Prerequisites:** Relay server running with `DATA_EDGE_ADDRESS` configured.
**Steps:**
1. Submit a UserOp with `target = 0x0000000000000000000000000000000000000001` (not the DataEdge contract).
**Expected:** Relay rejects before forwarding to paymaster.
**Asserts:**
- assert HTTP status 403
- assert error detail contains "Invalid target contract address"
**Mock/Real:** Tier 1 (mock), Tier 2 (real FastAPI with `data_edge_address` config).

---

### T-D06: Empty Calldata
**Journey:** D
**Prerequisites:** Relay server running.
**Steps:**
1. Submit a UserOp with `callData = "0x"` (empty).
**Expected:** Relay rejects with 400.
**Asserts:**
- assert HTTP status 400
- assert error detail contains "Empty calldata"
**Mock/Real:** All tiers.

---

### T-D07: Malformed Calldata (Invalid Protobuf)
**Journey:** D
**Prerequisites:** Relay server running.
**Steps:**
1. Submit a UserOp with `callData = "0xdeadbeef"` (valid hex but not valid protobuf for a fact).
**Expected:** If calldata validation happens at relay level, rejected. If not, the on-chain transaction may fail silently (subgraph mapping ignores unparseable data).
**Asserts:**
- assert either relay rejects before submission, OR bundler/chain execution reverts
- assert no subscription state change
**Mock/Real:** Tier 1 (mock relay can validate). Tier 3 (real chain — verify revert or silent failure).

---

### T-D08: Pimlico Webhook — Missing Signature
**Journey:** D
**Prerequisites:** Relay server running with `PIMLICO_WEBHOOK_SECRET` configured.
**Steps:**
1. Send `POST /v1/relay/webhook/pimlico` with no `X-Pimlico-Signature` header.
**Expected:** 400 Bad Request.
**Asserts:**
- assert HTTP status 400
- assert error detail contains "Missing X-Pimlico-Signature"
**Mock/Real:** All tiers.

---

### T-D09: Pimlico Webhook — Invalid Signature
**Journey:** D
**Prerequisites:** Relay server running with `PIMLICO_WEBHOOK_SECRET` configured.
**Steps:**
1. Send `POST /v1/relay/webhook/pimlico` with `X-Pimlico-Signature: invalid_signature`.
**Expected:** 401 Unauthorized.
**Asserts:**
- assert HTTP status 401
- assert error detail contains "Invalid webhook signature"
**Mock/Real:** All tiers.

---

### T-D10: Pimlico Webhook — Unknown Event Type
**Journey:** D
**Prerequisites:** Relay server running, valid signature.
**Steps:**
1. Send a Pimlico webhook with `type: "unknown.event.type"`.
**Expected:** Sponsorship denied (safe default for unknown events).
**Asserts:**
- assert `{ sponsor: false, reason: "unknown_event_type: unknown.event.type" }`
**Mock/Real:** Tier 1 (mock). Tier 2 (real FastAPI).

---

### T-D11: Pimlico Webhook — Missing Sender Address
**Journey:** D
**Prerequisites:** Valid Pimlico webhook with signature.
**Steps:**
1. Send a `user_operation.sponsorship.requested` webhook with `userOperation: {}` (no `sender` field).
**Expected:** Sponsorship denied.
**Asserts:**
- assert `{ sponsor: false, reason: "missing_sender_address" }`
**Mock/Real:** All tiers.

---

### T-D12: Stripe Webhook — Missing Signature
**Journey:** D
**Prerequisites:** Relay server running.
**Steps:**
1. Send `POST /v1/billing/webhook/stripe` with no `Stripe-Signature` header.
**Expected:** 400 Bad Request.
**Asserts:**
- assert HTTP status 400
- assert detail contains "Missing Stripe-Signature"
**Mock/Real:** All tiers.

---

### T-D13: Stripe Webhook — Invalid Signature
**Journey:** D
**Prerequisites:** Relay server running with `STRIPE_WEBHOOK_SECRET` configured.
**Steps:**
1. Send `POST /v1/billing/webhook/stripe` with a forged `Stripe-Signature`.
**Expected:** 400 Bad Request (signature verification fails).
**Asserts:**
- assert HTTP status 400
- assert no subscription state change
**Mock/Real:** Tier 2 (real Stripe SDK verification). Tier 3 (real Stripe webhook).

---

### T-D14: Database Error During Subscription Check — Fail Closed
**Journey:** D
**Prerequisites:** Relay webhook handler configured.
**Steps:**
1. Simulate a database error during `_check_subscription` (e.g., mock DB throws).
2. Pimlico webhook asks for sponsorship.
**Expected:** Sponsorship denied (fail-closed).
**Asserts:**
- assert `{ sponsor: false, reason: "internal_error" }`
- assert error is logged
**Mock/Real:** Tier 1 (mock DB that throws). Tier 2 (kill PG connection mid-request).

---

### T-D15: UserOp Hash Format Validation
**Journey:** D
**Prerequisites:** Relay server running.
**Steps:**
1. Call `GET /v1/relay/status/not-a-valid-hash`.
2. Call `GET /v1/relay/status/0x123` (too short).
**Expected:** 400 Bad Request for both.
**Asserts:**
- assert HTTP status 400 for invalid format
- assert error detail contains "Invalid UserOperation hash format"
**Mock/Real:** All tiers.

---

## 8. Journey E — Cross-Device Recovery

### T-E01: Store Memories on Device A
**Journey:** E
**Prerequisites:** Clean environment. Known seed.
**Steps:**
1. Initialize plugin with seed `S` on "Device A" (instance A).
2. Store 5 distinct facts: "I like Python", "My birthday is Jan 1", "I work at ACME Corp", "I have a cat named Whiskers", "I prefer dark mode".
3. Wait for all stores to succeed.
4. Record wallet address `W` and all fact IDs.
**Expected:** 5 facts stored, associated with wallet `W`.
**Asserts:**
- assert all 5 stores succeed
- assert wallet address `W` is deterministic from seed `S`
**Mock/Real:** Tier 1 (mock). Tier 3 (real Chiado — verify on-chain events).

---

### T-E02: Recover Memories on Device B
**Journey:** E
**Prerequisites:** T-E01 complete. Different plugin instance ("Device B").
**Steps:**
1. Initialize plugin with the same seed `S` on "Device B" (new instance).
2. Derive wallet address — should be identical to `W`.
3. Query subgraph for all facts owned by `W`.
4. Decrypt all returned facts.
**Expected:** All 5 original facts recovered and decrypted correctly.
**Asserts:**
- assert derived wallet address == `W`
- assert 5 facts returned from subgraph
- assert decrypted texts match: "I like Python", "My birthday is Jan 1", etc.
- assert no decryption errors
**Mock/Real:** Tier 1 (mock — use shared in-memory store between two plugin instances). Tier 3 (real Chiado subgraph query).

---

### T-E03: Subscription Survives Cross-Device Recovery
**Journey:** E
**Prerequisites:** T-E01 complete. Wallet `W` has an active pro subscription.
**Steps:**
1. On "Device B", check subscription status via `GET /v1/billing/status?wallet_address=W`.
**Expected:** Subscription is still active (same wallet = same subscription).
**Asserts:**
- assert `tier == "pro"`
- assert `expires_at` matches what was set on Device A
**Mock/Real:** Tier 1 (mock). Tier 2 (real PG — subscription keyed by wallet address).

---

### T-E04: Wrong Seed Cannot Read Other User's Memories
**Journey:** E + D
**Prerequisites:** T-E01 complete. Facts stored under wallet `W`.
**Steps:**
1. Initialize plugin with a different seed `S'` on "Device C".
2. Derive wallet address `W'` (different from `W`).
3. Query subgraph for facts owned by `W'`.
4. Even if attacker knew fact IDs, attempt to decrypt with wrong key.
**Expected:** No facts returned for `W'`. Decryption fails for any intercepted ciphertexts.
**Asserts:**
- assert subgraph query returns 0 facts for `W'`
- assert AES-GCM decryption throws (wrong key)
**Mock/Real:** Tier 1 (mock — two instances with different seeds, verify isolation).

---

## 9. Journey F — Agent-Driven UX

### T-F01: Automatic Search on Every Message (before_agent_start Hook)
**Journey:** F
**Prerequisites:** Plugin initialized with some stored facts.
**Steps:**
1. User sends 3 messages sequentially: "Hello", "What's the weather?", "Tell me about my preferences."
2. Observe hook invocations.
**Expected:** `before_agent_start` fires for each message >= 5 chars. "Hello" (5 chars) triggers search. Short messages may be skipped depending on config.
**Asserts:**
- assert `before_agent_start` fired at least 2 times (for messages >= 5 chars)
- assert each invocation includes search trapdoors
**Mock/Real:** Tier 1 (mock — already tested in existing E2E suite, but verify relay path too).

---

### T-F02: Automatic Store on Every Turn (agent_end Hook)
**Journey:** F
**Prerequisites:** Plugin initialized.
**Steps:**
1. User has a conversation with extractable facts: "I just moved to Berlin and started working at TechCo."
2. Agent responds.
3. `agent_end` hook fires.
**Expected:** Plugin extracts facts and stores them via relay.
**Asserts:**
- assert `agent_end` hook fired
- assert at least one relay `/v1/relay/sponsor` call made
- assert relay response `success == true`
**Mock/Real:** Tier 1 (mock).

---

### T-F03: Agent Detects Free Tier Limit and Shows Upgrade Message
**Journey:** F
**Prerequisites:** Subscription state with `free_writes_used == 99` (one write remaining).
**Steps:**
1. User stores a fact — succeeds (100th write).
2. User stores another fact — relay denies sponsorship.
3. Plugin receives `SPONSORSHIP_FAILED` with "upgrade_required" reason.
4. Agent should detect this and present an upgrade prompt.
**Expected:** After denial, the plugin/agent surfaces an upgrade message to the user.
**Asserts:**
- assert first store succeeds (`free_writes_used` goes to 100)
- assert second store fails with `SPONSORSHIP_FAILED`
- assert plugin logs or returns a message containing "upgrade" or "limit"
**Mock/Real:** Tier 1 (mock relay returns sponsorship denied at 101st write).

---

### T-F04: Agent Creates Checkout URL and Presents It
**Journey:** F
**Prerequisites:** T-F03 triggered (user prompted to upgrade).
**Steps:**
1. User says "I want to upgrade" (or agent auto-triggers).
2. Agent calls `totalreclaw_upgrade` tool (or equivalent billing endpoint).
3. Agent receives checkout URL from server.
4. Agent presents URL to user.
**Expected:** Checkout URL is returned and included in agent's response.
**Asserts:**
- assert billing endpoint called with correct wallet address
- assert checkout URL returned
- assert agent response text includes the URL
**Mock/Real:** Tier 1 (mock billing endpoint). This test validates the agent integration path.

---

### T-F05: Agent Detects Subscription Activation After Webhook
**Journey:** F
**Prerequisites:** User has clicked checkout URL and completed payment.
**Steps:**
1. Simulate Stripe webhook: `checkout.session.completed`.
2. Agent polls `GET /v1/billing/status` (or reacts to status change).
3. Agent detects `tier == "pro"`.
**Expected:** Agent acknowledges activation: "You're all set" or similar.
**Asserts:**
- assert billing status returns `tier == "pro"` after webhook
- assert subsequent store attempt succeeds
**Mock/Real:** Tier 1 (mock — simulate webhook then check status).

---

### T-F06: Store and Compaction Hooks Fire Correctly
**Journey:** F
**Prerequisites:** Plugin initialized with conversation history.
**Steps:**
1. Trigger `before_compaction` hook (simulating OpenClaw compaction).
2. Trigger `before_reset` hook (simulating OpenClaw reset).
**Expected:** Both hooks trigger a store operation (extracting and persisting facts from conversation history).
**Asserts:**
- assert `before_compaction` fires store
- assert `before_reset` fires store
- assert relay `/v1/relay/sponsor` called for each
**Mock/Real:** Tier 1 (mock — already tested in existing suite, but verify relay path).

---

## 10. Journey G — Relay-Specific (Full Pipeline)

### T-G01: Relay Forwards UserOp to Pimlico
**Journey:** G
**Prerequisites:** Authenticated user, valid UserOp, relay and mock Pimlico running.
**Steps:**
1. Submit a valid UserOp to `POST /v1/relay/sponsor`.
2. Relay calls Pimlico `pm_getPaymasterStubData` (mock).
3. Relay calls Pimlico `pm_getPaymasterData` (mock).
4. Both calls return valid gas estimates and paymaster data.
**Expected:** Sponsored UserOp has gas fields and paymasterAndData populated.
**Asserts:**
- assert Pimlico received exactly 2 RPC calls: `pm_getPaymasterStubData`, `pm_getPaymasterData`
- assert sponsored UserOp has non-zero `callGasLimit`, `verificationGasLimit`, `preVerificationGas`
- assert sponsored UserOp has non-empty `paymasterAndData`
**Mock/Real:** Tier 1 (mock Pimlico). Tier 3 (real Pimlico on Chiado).

---

### T-G02: Pimlico Webhook Callback — Subscription Check
**Journey:** G
**Prerequisites:** Mock Pimlico configured with a webhook policy that calls back to relay.
**Steps:**
1. Submit a UserOp.
2. During sponsorship, Pimlico calls `POST /v1/relay/webhook/pimlico` with `user_operation.sponsorship.requested`.
3. Relay checks subscription: wallet has active pro subscription.
4. Relay returns `{ sponsor: true }`.
**Expected:** Sponsorship approved via webhook.
**Asserts:**
- assert webhook received with correct sender address
- assert webhook response `{ sponsor: true, reason: "active_subscription" }`
**Mock/Real:** Tier 1 (mock). Tier 2 (real FastAPI + PG). Tier 3 (real Pimlico webhook).

---

### T-G03: Pimlico Webhook Callback — Free Tier Denial
**Journey:** G
**Prerequisites:** Mock Pimlico with webhook policy. Wallet has exhausted free tier.
**Steps:**
1. Submit a UserOp.
2. Pimlico webhook calls relay.
3. Relay checks subscription: free tier exhausted.
4. Relay returns `{ sponsor: false, reason: "upgrade_required" }`.
**Expected:** Pimlico does NOT sponsor the UserOp.
**Asserts:**
- assert webhook response `{ sponsor: false, reason: "upgrade_required" }`
- assert relay `/sponsor` endpoint returns `success: false`
**Mock/Real:** Tier 1 (mock). Tier 2 (real FastAPI + PG).

---

### T-G04: Bundler Submits Sponsored UserOp
**Journey:** G
**Prerequisites:** Sponsored UserOp ready (gas estimates + paymaster data).
**Steps:**
1. Relay calls Pimlico `eth_sendUserOperation` with the sponsored UserOp.
2. Bundler returns `userOpHash`.
**Expected:** Valid userOpHash returned.
**Asserts:**
- assert `userOpHash` is 0x-prefixed hex, 66 chars
- assert Pimlico received `eth_sendUserOperation` with correct UserOp and EntryPoint
**Mock/Real:** Tier 1 (mock bundler). Tier 3 (real Pimlico bundler on Chiado).

---

### T-G05: Transaction Confirmed On-Chain
**Journey:** G
**Prerequisites:** T-G04 complete. UserOp submitted.
**Steps:**
1. Poll `GET /v1/relay/status/{userOpHash}`.
2. Wait for status to change from `"pending"` to `"included"`.
**Expected:** Transaction confirmed with receipt.
**Asserts:**
- assert final status == `"included"`
- assert `transactionHash` is 0x-prefixed hex
- assert `blockNumber > 0`
- assert `userOpSuccess == true`
**Mock/Real:** Tier 1 (mock — return `included` after 1 poll). Tier 3 (real Chiado — poll until mined, ~5-15s).

---

### T-G06: Graph Node Indexes the Event
**Journey:** G
**Prerequisites:** T-G05 complete. Transaction confirmed on Chiado.
**Steps:**
1. Wait for Graph Node to process the block containing the transaction.
2. Query the subgraph for the fact by its content fingerprint.
**Expected:** Fact appears in subgraph with correct fields.
**Asserts:**
- assert subgraph query returns the stored fact
- assert `encryptedBlob` matches what was submitted
- assert `blindIndices` count matches
- assert `owner` matches the wallet address
- assert `isActive == true`
**Mock/Real:** Tier 1 (mock subgraph — fact appears immediately). Tier 3 (real Graph Node on Chiado — may need to wait for indexing).

---

### T-G07: Subgraph Query Returns the Stored Fact
**Journey:** G
**Prerequisites:** T-G06 complete. Fact indexed.
**Steps:**
1. Generate trapdoors for the stored fact's content.
2. Query the subgraph using `searchSubgraph(owner, trapdoors, maxCandidates)`.
3. Decrypt the returned fact.
**Expected:** Full round-trip: store -> chain -> index -> query -> decrypt.
**Asserts:**
- assert at least one result returned
- assert decrypted text matches original plaintext
- assert `decayScore`, `timestamp`, `version` are preserved
**Mock/Real:** Tier 1 (mock — already covered by existing E2E suite). Tier 3 (real Chiado — full end-to-end on live network).

---

### T-G08: Pimlico API Key Not Configured — Graceful Error
**Journey:** G
**Prerequisites:** Relay server running without `PIMLICO_API_KEY`.
**Steps:**
1. Submit a UserOp to `POST /v1/relay/sponsor`.
**Expected:** Clear error message about missing API key.
**Asserts:**
- assert response `success == false`
- assert error message contains "PIMLICO_API_KEY not configured"
**Mock/Real:** Tier 1 (mock — clear env var). Tier 2 (real FastAPI without env var).

---

### T-G09: Pimlico API Timeout
**Journey:** G
**Prerequisites:** Mock Pimlico configured to delay responses by >30 seconds.
**Steps:**
1. Submit a UserOp.
2. Relay calls Pimlico, which times out.
**Expected:** Relay returns a timeout error within reasonable time (~35s).
**Asserts:**
- assert response `success == false`
- assert error message contains "timed out"
**Mock/Real:** Tier 1 (mock Pimlico with artificial delay). Tier 2 (mock Pimlico).

---

### T-G10: Pimlico RPC Error Response
**Journey:** G
**Prerequisites:** Mock Pimlico configured to return a JSON-RPC error.
**Steps:**
1. Submit a UserOp.
2. Pimlico returns `{ "jsonrpc": "2.0", "error": { "code": -32602, "message": "Invalid UserOp" } }`.
**Expected:** Relay propagates the error with meaningful message.
**Asserts:**
- assert response `success == false`
- assert error message contains "Invalid UserOp" or the RPC error message
**Mock/Real:** Tier 1 (mock Pimlico). Tier 2 (mock Pimlico).

---

### T-G11: DATA_EDGE_ADDRESS Not Configured
**Journey:** G
**Prerequisites:** Relay server running without `DATA_EDGE_ADDRESS`.
**Steps:**
1. Submit a UserOp.
**Expected:** 503 Service Unavailable.
**Asserts:**
- assert HTTP status 503
- assert detail contains "DATA_EDGE_ADDRESS"
**Mock/Real:** Tier 1 (mock). Tier 2 (real FastAPI without env var).

---

## 11. Cross-Journey Edge Cases

### T-X01: Mixed Payment Sources — Stripe Pro then Coinbase Extension
**Journey:** B + C
**Prerequisites:** Active Stripe pro subscription.
**Steps:**
1. User pays with Coinbase Commerce (additional payment).
2. `charge:confirmed` webhook fires.
3. Subscription extended from current Stripe expiry by 30 days.
4. Source changes to `coinbase_commerce`.
**Expected:** Expiry extended. Source updated. No conflict.
**Asserts:**
- assert `expires_at` extended by 30 days from Stripe period end
- assert `source == "coinbase_commerce"` (most recent payment source)
- assert `tier == "pro"`
**Mock/Real:** Tier 1 (mock). Tier 2 (real PG).

---

### T-X02: Concurrent Stores — Race Condition on Free Tier Counter
**Journey:** A
**Prerequisites:** Subscription with `free_writes_used == 99`, `free_writes_limit == 100`.
**Steps:**
1. Submit 3 store requests concurrently (parallel HTTP calls).
2. All arrive at `check_and_increment_free_usage` simultaneously.
**Expected:** Exactly 1 succeeds (incrementing to 100). The other 2 may succeed (race) or be denied. No counter goes above limit + small race window.
**Asserts:**
- assert `free_writes_used <= 102` (some minor race tolerance)
- assert at least 1 store succeeds
- assert system does not crash or corrupt state
**Mock/Real:** Tier 2 only (requires real PG with `FOR UPDATE` locking). This is a database concurrency test.

---

### T-X03: Wallet Address Case Sensitivity
**Journey:** A + B + C + D
**Prerequisites:** Subscription created with lowercase wallet address.
**Steps:**
1. Query subscription status with mixed-case wallet address (e.g., `0xAbCd...`).
2. Submit UserOp with sender in checksummed format.
3. Pimlico webhook sends sender in lowercase.
**Expected:** All lookups succeed regardless of case.
**Asserts:**
- assert subscription found regardless of `0xabcd` vs `0xAbCd`
- assert webhook handler normalizes to lowercase before DB lookup
**Mock/Real:** Tier 1 (mock). Tier 2 (real PG — verify case-insensitive queries).

---

### T-X04: Billing Status Endpoint — No Subscription Row
**Journey:** A
**Prerequisites:** Brand new wallet with no subscription row in DB.
**Steps:**
1. Call `GET /v1/billing/status?wallet_address=0xnew...`.
**Expected:** Returns free tier defaults.
**Asserts:**
- assert `tier == "free"`
- assert `source == null`
- assert `free_writes_used == 0`
- assert `free_writes_limit == 100` (or configured value)
**Mock/Real:** Tier 1 (mock). Tier 2 (real PG).

---

### T-X05: Stripe Webhook — checkout.session.completed with Missing client_reference_id
**Journey:** B + D
**Prerequisites:** Stripe webhook configured.
**Steps:**
1. Simulate `checkout.session.completed` event with `client_reference_id = null`.
**Expected:** Webhook handler logs error but returns 200 (don't block Stripe retries).
**Asserts:**
- assert webhook response `success == true` (Stripe expects 200)
- assert no subscription row created
- assert error logged
**Mock/Real:** Tier 1 (mock). Tier 2 (real FastAPI).

---

### T-X06: Pimlico Webhook — Sponsorship Finalized (Informational)
**Journey:** G
**Prerequisites:** Relay webhook handler configured.
**Steps:**
1. Send Pimlico webhook with `type: "user_operation.sponsorship.finalized"`.
**Expected:** Acknowledged without error. No subscription side effects.
**Asserts:**
- assert `{ sponsor: true, reason: "finalized_notification" }`
**Mock/Real:** All tiers.

---

### T-X07: Coinbase Webhook — Missing wallet_address in Metadata
**Journey:** C + D
**Prerequisites:** Coinbase webhook configured with valid signature.
**Steps:**
1. Send `charge:confirmed` webhook with `metadata: {}` (no `wallet_address`).
**Expected:** Webhook rejected with error.
**Asserts:**
- assert HTTP status 400
- assert error mentions "wallet_address"
**Mock/Real:** Tier 1 (mock). Tier 2 (real FastAPI).

---

### T-X08: Pimlico HTTP 500 — Transient Failure
**Journey:** G
**Prerequisites:** Mock Pimlico configured to return HTTP 500.
**Steps:**
1. Submit a UserOp.
2. Pimlico returns HTTP 500.
**Expected:** Relay returns a clear error (not a crash).
**Asserts:**
- assert response `success == false`
- assert error message mentions HTTP status
**Mock/Real:** Tier 1 (mock Pimlico). Tier 2 (mock Pimlico).

---

## 12. Test Applicability Matrix

| Test ID | Tier 1 (Mock) | Tier 2 (Docker) | Tier 3 (Live Testnet) | Dependencies |
|---------|:---:|:---:|:---:|---|
| **Journey A** | | | | |
| T-A01 | X | X | X | Plugin crypto |
| T-A02 | X | X | X | Relay, paymaster mock |
| T-A03 | X | X | X | Subgraph mock |
| T-A04 | X | X | | Relay, subscription state |
| T-A05 | X | X | | Relay, subscription state |
| T-A06 | X | X | X | Subgraph mock |
| T-A07 | X | X | | Controlled clock |
| **Journey B** | | | | |
| T-B01 | X | X | X | Stripe API |
| T-B02 | X | X | X | Stripe webhook |
| T-B03 | X | X | | Relay, subscription |
| T-B04 | X | X | | Stripe webhook |
| T-B05 | X | X | | Stripe webhook |
| T-B06 | X | X | | Controlled clock |
| T-B07 | X | X | | Stripe webhook |
| T-B08 | X | X | X | Server validation |
| **Journey C** | | | | |
| T-C01 | X | X | X | Coinbase API |
| T-C02 | X | X | X | Coinbase webhook |
| T-C03 | X | X | | Relay, subscription |
| T-C04 | X | X | | Controlled clock |
| T-C05 | X | X | | Subscription state |
| T-C06 | X | X | | Coinbase webhook |
| T-C07 | X | X | | Idempotency |
| T-C08 | X | X | X | Signature verification |
| **Journey D** | | | | |
| T-D01 | X | X | X | Auth middleware |
| T-D02 | X | X | X | Auth middleware |
| T-D03 | X | X | | Subscription + clock |
| T-D04 | X | | X | Bundler nonce check |
| T-D05 | X | X | X | Contract address config |
| T-D06 | X | X | X | Calldata validation |
| T-D07 | X | | X | Protobuf validation |
| T-D08 | X | X | X | Signature middleware |
| T-D09 | X | X | X | HMAC verification |
| T-D10 | X | X | | Webhook handler |
| T-D11 | X | X | | Webhook handler |
| T-D12 | X | X | X | Stripe signature |
| T-D13 | | X | X | Real Stripe SDK |
| T-D14 | X | X | | Error handling |
| T-D15 | X | X | X | Input validation |
| **Journey E** | | | | |
| T-E01 | X | X | X | Seed derivation |
| T-E02 | X | X | X | Subgraph query |
| T-E03 | X | X | | Billing status |
| T-E04 | X | X | | Crypto isolation |
| **Journey F** | | | | |
| T-F01 | X | | | Plugin hooks |
| T-F02 | X | | | Plugin hooks |
| T-F03 | X | X | | Relay denial handling |
| T-F04 | X | | | Billing integration |
| T-F05 | X | X | | Webhook + polling |
| T-F06 | X | | | Compaction hooks |
| **Journey G** | | | | |
| T-G01 | X | | X | Pimlico RPC |
| T-G02 | X | X | X | Pimlico webhook |
| T-G03 | X | X | | Webhook denial |
| T-G04 | X | | X | Bundler submission |
| T-G05 | X | | X | On-chain confirmation |
| T-G06 | | | X | Graph Node indexing |
| T-G07 | X | | X | Full round-trip |
| T-G08 | X | X | | Config validation |
| T-G09 | X | X | | Timeout handling |
| T-G10 | X | X | | Error propagation |
| T-G11 | X | X | | Config validation |
| **Cross-Journey** | | | | |
| T-X01 | X | X | | Multi-source billing |
| T-X02 | | X | | PG locking |
| T-X03 | X | X | | Case normalization |
| T-X04 | X | X | | Default handling |
| T-X05 | X | X | | Error handling |
| T-X06 | X | X | | Webhook handling |
| T-X07 | X | X | | Validation |
| T-X08 | X | X | | Error handling |

### Summary Counts

| Tier | Test Count | Runtime | Trigger |
|------|:---:|---------|---------|
| Tier 1 (Mock) | 48 | <30s | Every commit |
| Tier 2 (Docker) | 42 | ~3-5 min | Per-PR |
| Tier 3 (Live) | 19 | ~15-30 min | Weekly/pre-release |

---

## 13. Estimated Effort

### Phase 1: Mock Infrastructure (Tier 1)

| Component | Effort | Description |
|-----------|:---:|-------------|
| Mock relay server (extend `mock-subgraph.ts`) | 3 days | Add `/v1/relay/sponsor`, `/v1/relay/webhook/pimlico`, `/v1/relay/status`, billing endpoints, in-memory subscription store |
| Mock Pimlico JSON-RPC server | 2 days | New mock that responds to `pm_getPaymasterStubData`, `pm_getPaymasterData`, `eth_sendUserOperation`, `eth_getUserOperationReceipt` |
| Mock Stripe/Coinbase service | 1 day | Return fake checkout URLs, accept simulated webhooks |
| Journey A tests (T-A01 to T-A07) | 2 days | 7 test cases |
| Journey B tests (T-B01 to T-B08) | 2 days | 8 test cases |
| Journey C tests (T-C01 to T-C08) | 1.5 days | 8 test cases |
| Journey D tests (T-D01 to T-D15) | 2 days | 15 test cases |
| Journey E tests (T-E01 to T-E04) | 1.5 days | 4 test cases |
| Journey F tests (T-F01 to T-F06) | 1.5 days | 6 test cases |
| Journey G tests (T-G01 to T-G11) | 2 days | 11 test cases |
| Cross-journey tests (T-X01 to T-X08) | 1.5 days | 8 test cases |
| **Phase 1 Total** | **~18 days** | 76 test cases, all mockable in Tier 1 |

### Phase 2: Docker Integration (Tier 2)

| Component | Effort | Description |
|-----------|:---:|-------------|
| `docker-compose.test.yml` | 1 day | PG + FastAPI + mock Pimlico containers |
| DB migration script for test environment | 0.5 days | `subscriptions` table + seed data |
| Port existing Tier 1 tests to Tier 2 runner | 2 days | Swap mock URLs for Docker container URLs |
| Concurrency test (T-X02) | 1 day | PG locking verification |
| **Phase 2 Total** | **~4.5 days** | |

### Phase 3: Live Testnet (Tier 3)

| Component | Effort | Description |
|-----------|:---:|-------------|
| Chiado test script (`run-chiado.sh`) | 2 days | Deploy contract, configure Pimlico, run subset |
| Stripe sandbox integration | 1 day | Test keys, webhook forwarding (Stripe CLI) |
| Coinbase sandbox integration | 1 day | Test keys, webhook simulation |
| Full pipeline verification (T-G05 to T-G07) | 1 day | On-chain confirmation + indexing wait |
| **Phase 3 Total** | **~5 days** | |

### Grand Total: ~27.5 days

Priority recommendation:
1. **Phase 1 first** (18 days) — covers 48 tests in CI, catches 90% of bugs
2. **Phase 2 second** (4.5 days) — adds DB concurrency and real FastAPI validation
3. **Phase 3 last** (5 days) — live testnet validation before each release

---

## 14. Open Questions

| # | Question | Impact | Proposed Resolution |
|---|----------|--------|---------------------|
| 1 | Should the plugin expose a `totalreclaw_upgrade` tool or handle upgrade flow internally? | Affects T-F03, T-F04 | Recommend: explicit tool for agent to call |
| 2 | Free-tier limit: 100 is the code default, but spec says TBD. Which value to test against? | Affects T-A04, T-A05 | Test with configurable limit (env var `FREE_TIER_LIMIT`) |
| 3 | Should reads be rate-limited at the relay level too? | Affects T-A06 | Current code: reads go direct to subgraph, no relay. Keep as-is. |
| 4 | Pimlico vs ZeroDev — does the test infrastructure need to support both? | Affects all G tests | Recommend: abstract paymaster mock behind interface, implement Pimlico first |
| 5 | Should T-D04 (replay attack) be a Tier 1 test or Tier 3 only? | Affects CI coverage | Recommend: Tier 1 with mock nonce tracking + Tier 3 for real validation |
| 6 | How does the plugin detect sponsorship denial and surface upgrade prompts? | Affects T-F03 error handling path | Needs plugin code review — may require new error handling in `submitToRelay` |
| 7 | Is `sponsorshipPolicyId` required or optional in the `/v1/relay/sponsor` request? | Affects T-G01, T-G02 | Current code: optional. Tests should cover both with and without. |
