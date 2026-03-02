# Subgraph v2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the centralized TotalReclaw server with a fully decentralized subgraph-based architecture — on-chain storage via ERC-4337 on Base L2, self-hosted Graph Node for indexing, inverted blind index schema for direct GraphQL search, and a client-side hot cache for instant auto-recall.

**Architecture:** Encrypted facts are written on-chain via ERC-4337 UserOps → EventfulDataEdge contract emits Log events → self-hosted Graph Node indexes events into PostgreSQL with inverted BlindIndex entities → client searches via GraphQL `hash_in` queries → decrypts + reranks locally. A persistent encrypted hot cache (top ~30 facts) enables instant auto-recall on conversation start without network round-trip.

**Tech Stack:** Solidity (Hardhat), AssemblyScript (subgraph mappings), TypeScript, GraphQL, GND (Graph Node Dev — local subgraph runner, no IPFS/Docker needed), viem, bip39, @noble/hashes, @huggingface/transformers

---

## Prerequisites (Before Starting Any Task)

| Prerequisite | How to Verify |
|---|---|
| Node.js >= 18 | `node -v` |
| PostgreSQL installed | `psql --version` (GND auto-manages on macOS/Linux but needs it installed) |
| Graph CLI + GND installed | `npm install -g @graphprotocol/graph-cli && graph install gnd` then verify `~/.local/bin` is in PATH |
| Local repo clone | `cd /Users/pdiogo/Documents/code/totalreclaw && git status` |
| `feature/subgraph` branch | `git checkout feature/subgraph` |
| Internal repo (for OMBH data) | `ls /Users/pdiogo/Documents/code/totalreclaw-internal/ombh/synthetic-benchmark/ground-truth/` |
| Contract dependencies installed | `cd contracts && npm install` |
| Subgraph dependencies installed | `cd subgraph && npm install` |
| Plugin dependencies installed | `cd skill/plugin && npm install` |

**No external API keys required** — all testing is local (Hardhat node, GND for subgraph indexing, local embeddings).

**GND (Graph Node Dev)** replaces the Docker-based Graph Node + IPFS + PostgreSQL setup. It's a lightweight local runner that auto-manages PostgreSQL and doesn't need IPFS. Reference: https://thegraph.com/docs/en/subgraphs/developing/creating/graph-node-dev/

---

## Existing Code Context

The implementing agent MUST read these files before starting:

| Module | Path | What It Does | Lines |
|---|---|---|---|
| EventfulDataEdge.sol | `contracts/contracts/EventfulDataEdge.sol` | Minimal on-chain DA. `fallback()` emits `Log(bytes)` with encrypted Protobuf. Access restricted to EntryPoint. | 69 |
| TotalReclawPaymaster.sol | `contracts/contracts/TotalReclawPaymaster.sol` | ERC-4337 paymaster with per-sender rate limiting. Validates target = DataEdge. | 179 |
| deploy.ts | `contracts/scripts/deploy.ts` | Deploys both contracts. Saves addresses to `deployed-addresses.json`. Copies ABI to subgraph. | 128 |
| schema.graphql | `subgraph/schema.graphql` | Current schema: `FactEntity` with `blindIndices: [String!]!` as array field. `GlobalState` for sequence tracking. | 62 |
| mapping.ts | `subgraph/src/mapping.ts` | Handles `Log` events. Decodes Protobuf → creates FactEntity. | 82 |
| protobuf.ts | `subgraph/src/protobuf.ts` | Minimal AssemblyScript Protobuf wire-format decoder. | 151 |
| seed.ts | `client/src/crypto/seed.ts` | BIP-39 → private key + EOA + encryption/auth keys. Smart Account address is TODO (returns EOA). | 230 |
| builder.ts | `client/src/userop/builder.ts` | Builds + signs ERC-4337 UserOps. Hardcoded gas estimates. Pimlico-compatible format. | 173 |
| relay.py | `server/src/handlers/relay.py` | Server-side relay: validates UserOp → submits to Pimlico bundler. Rate limited. | 257 |
| plugin/crypto.ts | `skill/plugin/crypto.ts` | BIP-39 auto-detection, AES-256-GCM, blind indices (tokenize + stem + SHA-256), content fingerprint. | 351 |
| plugin/lsh.ts | `skill/plugin/lsh.ts` | Random Hyperplane LSH: 32-bit × 20 tables, deterministic from seed. | 257 |
| plugin/embedding.ts | `skill/plugin/embedding.ts` | Local bge-small-en-v1.5 ONNX (384-dim). Query prefix support. | 84 |
| plugin/reranker.ts | `skill/plugin/reranker.ts` | BM25 + cosine + RRF fusion. Porter stemmer. | 305 |
| plugin/index.ts | `skill/plugin/index.ts` | Full store/search flow. Dynamic candidate pool. 4 tools + 4 hooks. | 1061 |

**OMBH Benchmark Data** (in `totalreclaw-internal` repo):
- `ombh/synthetic-benchmark/ground-truth/facts-ingested.json` — 415 facts with id, text, type, importance
- `ombh/synthetic-benchmark/ground-truth/queries-ingested.json` — 140 queries with id, text, category, relevant_facts (ground truth)

---

## Task Overview

| Task | Description | Depends On | Est. |
|---|---|---|---|
| 1 | Local dev environment with GND + Hardhat | — | 15 min |
| 2 | Inverted BlindIndex schema + mapping rewrite | — | 30 min |
| 3 | Protobuf v2 (add encrypted_embedding field) | — | 20 min |
| 4 | Verify contract deployment via dev.sh | 1 | 15 min |
| 5 | Verify subgraph indexing via GND | 1, 2, 4 | 15 min |
| 6 | Subgraph client library (GraphQL queries) | 5 | 30 min |
| 7 | Client hot cache (persistent encrypted) | 6 | 25 min |
| 8 | Plugin subgraph integration (store path) | 3, 6 | 30 min |
| 9 | Plugin subgraph integration (search path) | 6, 7 | 30 min |
| 10 | E2E validation: OMBH ingest + query | 8, 9 | 30 min |
| 11 | Gas cost measurement + report | 10 | 20 min |
| 12 | Recovery flow (seed → full restore) | 9 | 20 min |

---

## Task 1: Local Dev Environment with GND + Hardhat

**Goal:** Set up the local development environment using GND (Graph Node Dev) and Hardhat. GND is a lightweight local subgraph runner that auto-manages PostgreSQL and doesn't need IPFS or Docker. After this task, two terminal commands give a working local blockchain + indexer.

**Reference:** https://thegraph.com/docs/en/subgraphs/developing/creating/graph-node-dev/

**Files:**

| Action | Path |
|---|---|
| Create | `subgraph/scripts/dev.sh` |
| Modify | `subgraph/subgraph.yaml` (set network name to match GND ethereum-rpc) |

### Step 1: Install GND

```bash
npm install -g @graphprotocol/graph-cli
graph install gnd
# Ensure ~/.local/bin is in PATH
export PATH="$HOME/.local/bin:$PATH"
```

Verify: `gnd --help` should print usage.

### Step 2: Write dev.sh (convenience script)

```bash
#!/usr/bin/env bash
# subgraph/scripts/dev.sh
# Local development: starts Hardhat node + GND with hot-reload
# Usage: ./scripts/dev.sh
#
# Prerequisites:
#   - npm install -g @graphprotocol/graph-cli && graph install gnd
#   - PostgreSQL installed (GND auto-manages a temp instance on macOS/Linux)
#   - Contracts compiled: cd ../contracts && npx hardhat compile
#
# This script:
#   1. Starts Hardhat node in background
#   2. Deploys contracts to local Hardhat
#   3. Updates subgraph.yaml with deployed addresses
#   4. Starts GND with --watch for hot-reload
#
# Endpoints:
#   - Hardhat RPC: http://127.0.0.1:8545
#   - GraphQL queries: http://localhost:8000/subgraphs/name/totalreclaw

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SUBGRAPH_DIR="$(dirname "$SCRIPT_DIR")"
CONTRACTS_DIR="$SUBGRAPH_DIR/../contracts"

cleanup() {
  echo "Shutting down..."
  [ -n "${HARDHAT_PID:-}" ] && kill "$HARDHAT_PID" 2>/dev/null
  exit 0
}
trap cleanup INT TERM

echo "=== Starting Hardhat node ==="
cd "$CONTRACTS_DIR"
npx hardhat node &
HARDHAT_PID=$!
sleep 3

echo "=== Deploying contracts ==="
npx hardhat run scripts/deploy.ts --network localhost

echo "=== Updating subgraph config ==="
ADDRESSES_FILE="$CONTRACTS_DIR/deployed-addresses.json"
DATA_EDGE=$(python3 -c "import json; print(json.load(open('$ADDRESSES_FILE'))['dataEdge'])")
START_BLOCK=$(python3 -c "import json; print(json.load(open('$ADDRESSES_FILE'))['blockNumber'])")

cd "$SUBGRAPH_DIR"
sed -i.bak "s|address: '0x0000.*'|address: '$DATA_EDGE'|" subgraph.yaml
sed -i.bak "s|startBlock: 0|startBlock: $START_BLOCK|" subgraph.yaml
rm -f subgraph.yaml.bak

echo "=== Copying ABI ==="
cp "$CONTRACTS_DIR/artifacts/contracts/EventfulDataEdge.sol/EventfulDataEdge.json" \
   "$SUBGRAPH_DIR/abis/EventfulDataEdge.json"

echo "=== Building subgraph ==="
npx graph codegen
npx graph build

echo "=== Starting GND (Graph Node Dev) with hot-reload ==="
echo "Query endpoint: http://localhost:8000/subgraphs/name/totalreclaw"
echo "Press Ctrl+C to stop."
gnd --ethereum-rpc hardhat:http://127.0.0.1:8545 --watch
```

### Step 3: Update subgraph.yaml network name

The `network` field in `subgraph.yaml` must match the GND `--ethereum-rpc` prefix. Check current value and update if needed:

```yaml
# In subgraph.yaml, the dataSources[0].network should be "hardhat" for local dev
# (matches the "hardhat:" prefix in the --ethereum-rpc flag)
network: hardhat
```

**Note:** For testnet deployment later, this would change to `base-sepolia`.

### Step 4: Verify the dev environment works

```bash
# Terminal 1:
cd subgraph && chmod +x scripts/dev.sh && ./scripts/dev.sh

# Terminal 2 (after dev.sh shows "Starting GND"):
curl -s -X POST http://localhost:8000/subgraphs/name/totalreclaw \
  -H "Content-Type: application/json" \
  -d '{"query": "{ _meta { block { number } } }"}'
```

Expected: Returns JSON with block number (confirming GND is indexing the Hardhat chain).

### Step 5: Commit

```bash
git add subgraph/scripts/dev.sh subgraph/subgraph.yaml
git commit -m "feat(subgraph): local dev environment with GND + Hardhat (no Docker needed)"
```

---

## Task 2: Inverted BlindIndex Schema + Mapping Rewrite

**Goal:** Replace the `blindIndices: [String!]!` array on FactEntity with separate `BlindIndex` entities. This enables efficient `hash_in` GraphQL queries for search (OR semantics) instead of the unsupported `_contains_any` array overlap.

**Why:** The Graph's `_contains` filter requires ALL elements to match (AND semantics). Our search needs ANY match (OR semantics). Inverted index entities solve this — `blindIndices(where: { hash_in: $trapdoors })` is standard and fast.

**Files:**

| Action | Path |
|---|---|
| Modify | `subgraph/schema.graphql` |
| Modify | `subgraph/src/mapping.ts` |
| Create | `subgraph/tests/mapping.test.ts` |

### Step 1: Rewrite schema.graphql

Replace the full file:

```graphql
"""
TotalReclaw Subgraph Schema v2
Key change: BlindIndex entities for efficient hash_in queries.
"""

type Fact @entity {
  id: ID!
  "Smart Account address (owner of this fact)"
  owner: Bytes!
  "AES-256-GCM encrypted Protobuf blob"
  encryptedBlob: Bytes!
  "AES-256-GCM encrypted embedding vector (384-dim bge-small-en-v1.5). Nullable for v1 facts."
  encryptedEmbedding: String
  "Decay score (0.0-1.0). Facts below 0.3 are considered inactive."
  decayScore: BigDecimal!
  "Whether this fact is active (decayScore >= 0.3)"
  isActive: Boolean!
  "HMAC-SHA256 content fingerprint for dedup (hex)"
  contentFp: String!
  "Monotonic sequence ID for delta sync"
  sequenceId: BigInt!
  "Agent identifier for multi-agent scenarios"
  agentId: String!
  "Protobuf schema version"
  version: Int!
  "Source: conversation, pre_compaction, explicit, recovery"
  source: String!
  "Block number when this fact was written"
  blockNumber: BigInt!
  "Block timestamp"
  timestamp: BigInt!
  "Transaction hash"
  txHash: Bytes!
  "Derived: all blind index entries for this fact"
  blindIndexEntries: [BlindIndex!]! @derivedFrom(field: "fact")
}

type BlindIndex @entity {
  id: ID!
  "The SHA-256 blind hash value"
  hash: String!
  "The fact this index belongs to"
  fact: Fact!
  "Owner address (denormalized for efficient filtering)"
  owner: Bytes!
}

type GlobalState @entity {
  id: ID!
  "Next monotonic sequence ID"
  nextSequenceId: BigInt!
  "Total facts indexed"
  totalFacts: BigInt!
  "Last updated block timestamp"
  lastUpdated: BigInt!
}
```

### Step 2: Rewrite mapping.ts

Replace the full file:

```typescript
import { Bytes, BigDecimal, BigInt, log } from "@graphprotocol/graph-ts";
import { Log } from "../generated/EventfulDataEdge/EventfulDataEdge";
import { Fact, BlindIndex, GlobalState } from "../generated/schema";
import { decodeFact, DecodedFact } from "./protobuf";

const GLOBAL_STATE_ID = "global";
const INACTIVE_THRESHOLD = BigDecimal.fromString("0.3");

function getOrCreateGlobalState(): GlobalState {
  let state = GlobalState.load(GLOBAL_STATE_ID);
  if (!state) {
    state = new GlobalState(GLOBAL_STATE_ID);
    state.nextSequenceId = BigInt.fromI32(1);
    state.totalFacts = BigInt.zero();
    state.lastUpdated = BigInt.zero();
  }
  return state;
}

export function handleLog(event: Log): void {
  let data = event.params.data;
  if (data.length == 0) {
    log.warning("Empty Log event in tx {}", [event.transaction.hash.toHexString()]);
    return;
  }

  let decoded = decodeFact(data);
  if (!decoded) {
    log.warning("Failed to decode Protobuf in tx {}", [event.transaction.hash.toHexString()]);
    return;
  }

  // Use Protobuf ID or fall back to tx hash + log index
  let factId = decoded.id.length > 0
    ? decoded.id
    : event.transaction.hash.toHexString() + "-" + event.logIndex.toString();

  let fact = Fact.load(factId);
  let isNew = fact === null;
  if (!fact) {
    fact = new Fact(factId);
  }

  // Owner: from Protobuf or tx.from
  let owner = decoded.owner.length > 0
    ? Bytes.fromHexString(decoded.owner)
    : event.transaction.from;
  fact.owner = owner;

  fact.encryptedBlob = decoded.encryptedBlob;
  fact.encryptedEmbedding = decoded.encryptedEmbedding;
  fact.decayScore = decoded.decayScore;
  fact.isActive = decoded.decayScore.ge(INACTIVE_THRESHOLD);
  fact.contentFp = decoded.contentFp;
  fact.agentId = decoded.agentId;
  fact.version = decoded.version;
  fact.source = decoded.source;
  fact.blockNumber = event.block.number;
  fact.timestamp = event.block.timestamp;
  fact.txHash = event.transaction.hash;

  // Assign monotonic sequence ID
  let state = getOrCreateGlobalState();
  fact.sequenceId = state.nextSequenceId;
  state.nextSequenceId = state.nextSequenceId.plus(BigInt.fromI32(1));
  if (isNew) {
    state.totalFacts = state.totalFacts.plus(BigInt.fromI32(1));
  }
  state.lastUpdated = event.block.timestamp;
  state.save();

  fact.save();

  // Create inverted BlindIndex entities
  let indices = decoded.blindIndices;
  for (let i = 0; i < indices.length; i++) {
    let hash = indices[i];
    let indexId = factId + "-" + hash;
    let blindIndex = new BlindIndex(indexId);
    blindIndex.hash = hash;
    blindIndex.fact = factId;
    blindIndex.owner = owner;
    blindIndex.save();
  }

  log.info("Indexed fact {} with {} blind indices for owner {}", [
    factId,
    indices.length.toString(),
    owner.toHexString()
  ]);
}
```

### Step 3: Run codegen to verify schema compiles

Run: `cd subgraph && npx graph codegen`
Expected: Generated files in `subgraph/generated/` without errors.

### Step 4: Build subgraph to verify mapping compiles

Run: `cd subgraph && npx graph build`
Expected: Build successful, WASM output in `subgraph/build/`.

### Step 5: Commit

```bash
git add subgraph/schema.graphql subgraph/src/mapping.ts
git commit -m "feat(subgraph): inverted BlindIndex schema for hash_in search"
```

---

## Task 3: Protobuf v2 (Add encrypted_embedding Field)

**Goal:** Update the Protobuf schema and the AssemblyScript decoder to handle the `encrypted_embedding` field added in PoC v2. Also add proper `content_fp` and `agent_id` field decoding.

**Files:**

| Action | Path |
|---|---|
| Modify | `server/proto/totalreclaw.proto` (reference — check current field numbers) |
| Modify | `subgraph/src/protobuf.ts` |

### Step 1: Check current Protobuf schema field numbers

Read: `server/proto/totalreclaw.proto` (or `server/proto/openmemory.proto` if not renamed)
Note the field numbers for all existing fields. The implementing agent must map these to the decoder.

### Step 2: Update protobuf.ts decoder

Add these fields to the `DecodedFact` class and the decode loop:

```typescript
// Add to DecodedFact class:
encryptedEmbedding: string = "";  // Field 10: encrypted embedding (base64/hex string)
contentFp: string = "";            // Field 11: HMAC-SHA256 content fingerprint
agentId: string = "";              // Field 12: agent identifier

// Add to decode loop (after existing field handlers):
// Field 10: encrypted_embedding (length-delimited string)
// Field 11: content_fp (length-delimited string)
// Field 12: agent_id (length-delimited string)
```

**IMPORTANT:** Check the actual field numbers in the .proto file. The numbers above (10, 11, 12) are placeholders. The decoder must match the wire format exactly.

### Step 3: Verify build still passes

Run: `cd subgraph && npx graph build`
Expected: Build successful.

### Step 4: Commit

```bash
git add subgraph/src/protobuf.ts
git commit -m "feat(subgraph): decode encrypted_embedding + contentFp + agentId from Protobuf"
```

---

## Task 4: Verify Contract Deployment via dev.sh

**Goal:** Verify that the `dev.sh` script from Task 1 correctly deploys contracts and produces `deployed-addresses.json`. Add a `localhost` network to Hardhat config if missing.

**Note:** Contract deployment is handled by `dev.sh` (Task 1). This task ensures the Hardhat config supports it and adds a standalone deploy script for use outside dev.sh.

**Files:**

| Action | Path |
|---|---|
| Modify | `contracts/hardhat.config.ts` (add localhost network if missing) |
| Create | `subgraph/scripts/deploy-contracts.sh` (standalone, for CI or manual use) |

### Step 1: Add localhost network to Hardhat config

Check `contracts/hardhat.config.ts` for a `localhost` network entry. If missing, add:

```typescript
networks: {
  hardhat: {},
  localhost: {
    url: "http://127.0.0.1:8545",
  },
  // ... existing baseSepolia, base entries
}
```

### Step 2: Write deploy-contracts.sh (standalone)

```bash
#!/usr/bin/env bash
# subgraph/scripts/deploy-contracts.sh
# Deploy contracts to a running Hardhat node (standalone, for use outside dev.sh)
# Prerequisite: Hardhat node running on http://127.0.0.1:8545
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SUBGRAPH_DIR="$(dirname "$SCRIPT_DIR")"
CONTRACTS_DIR="$SUBGRAPH_DIR/../contracts"

echo "=== Deploying contracts to local Hardhat node ==="
cd "$CONTRACTS_DIR"
npx hardhat run scripts/deploy.ts --network localhost

ADDRESSES_FILE="$CONTRACTS_DIR/deployed-addresses.json"
if [ ! -f "$ADDRESSES_FILE" ]; then
  echo "ERROR: deployed-addresses.json not found"
  exit 1
fi

DATA_EDGE=$(python3 -c "import json; print(json.load(open('$ADDRESSES_FILE'))['dataEdge'])")
START_BLOCK=$(python3 -c "import json; print(json.load(open('$ADDRESSES_FILE'))['blockNumber'])")

echo "DataEdge: $DATA_EDGE (block $START_BLOCK)"

echo "=== Updating subgraph.yaml ==="
cd "$SUBGRAPH_DIR"
sed -i.bak "s|address: '0x0000.*'|address: '$DATA_EDGE'|" subgraph.yaml
sed -i.bak "s|startBlock: 0|startBlock: $START_BLOCK|" subgraph.yaml
rm -f subgraph.yaml.bak

echo "=== Copying ABI ==="
cp "$CONTRACTS_DIR/artifacts/contracts/EventfulDataEdge.sol/EventfulDataEdge.json" \
   "$SUBGRAPH_DIR/abis/EventfulDataEdge.json"

echo "=== Done ==="
```

### Step 3: Verify

Run `dev.sh` from Task 1. Confirm:
- `contracts/deployed-addresses.json` exists with `dataEdge` and `blockNumber`
- `subgraph.yaml` has real addresses (not `0x0000...`)
- ABI file copied to `subgraph/abis/`

### Step 4: Commit

```bash
git add contracts/hardhat.config.ts subgraph/scripts/deploy-contracts.sh
git commit -m "feat(subgraph): standalone contract deployment script + localhost network"
```

---

## Task 5: Verify Subgraph Indexing via GND

**Goal:** Verify that GND (started by `dev.sh`) correctly indexes events from the deployed contracts. GND handles subgraph deployment automatically — no separate deploy step needed.

**Note:** GND with `--watch` auto-deploys the subgraph when the build directory changes. The `dev.sh` script from Task 1 runs `graph codegen` + `graph build` before starting GND, which triggers the initial deployment.

**Files:**

| Action | Path |
|---|---|
| Create | `subgraph/scripts/verify-indexing.sh` |

### Step 1: Write verify-indexing.sh

```bash
#!/usr/bin/env bash
# subgraph/scripts/verify-indexing.sh
# Verify GND is running and indexing events
# Prerequisite: dev.sh is running in another terminal
set -euo pipefail

QUERY_URL="http://localhost:8000/subgraphs/name/totalreclaw"

echo "=== Checking GND is running ==="
RESPONSE=$(curl -sf -X POST "$QUERY_URL" \
  -H "Content-Type: application/json" \
  -d '{"query": "{ _meta { block { number } } }"}' 2>/dev/null) || {
  echo "ERROR: GND not reachable at $QUERY_URL"
  echo "Make sure dev.sh is running: cd subgraph && ./scripts/dev.sh"
  exit 1
}

BLOCK=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['_meta']['block']['number'])")
echo "GND is indexing. Current block: $BLOCK"

echo "=== Querying GlobalState ==="
RESPONSE=$(curl -sf -X POST "$QUERY_URL" \
  -H "Content-Type: application/json" \
  -d '{"query": "{ globalStates(first: 1) { id totalFacts nextSequenceId } }"}')
echo "GlobalState: $RESPONSE"

echo "=== Querying facts (first 5) ==="
RESPONSE=$(curl -sf -X POST "$QUERY_URL" \
  -H "Content-Type: application/json" \
  -d '{"query": "{ facts(first: 5) { id owner isActive decayScore } }"}')
echo "Facts: $RESPONSE"

echo "=== Querying blind indices (first 5) ==="
RESPONSE=$(curl -sf -X POST "$QUERY_URL" \
  -H "Content-Type: application/json" \
  -d '{"query": "{ blindIndices(first: 5) { id hash fact { id } } }"}')
echo "BlindIndices: $RESPONSE"

echo "=== GND verification complete ==="
```

### Step 2: Verify

1. Start dev.sh in Terminal 1: `cd subgraph && ./scripts/dev.sh`
2. In Terminal 2: `chmod +x subgraph/scripts/verify-indexing.sh && ./subgraph/scripts/verify-indexing.sh`
Expected: GND is reachable, returns block number, empty facts/indices (no events emitted yet).

### Step 3: Commit

```bash
git add subgraph/scripts/verify-indexing.sh
git commit -m "feat(subgraph): GND verification script"
```

---

## Task 6: Subgraph Client Library (GraphQL Queries)

**Goal:** TypeScript client that queries the subgraph via GraphQL. Supports search (blind index lookup via `hash_in`), bulk download (all facts by owner), and delta sync (facts since block N). This replaces the HTTP API client used in PoC v2.

**Files:**

| Action | Path |
|---|---|
| Create | `client/src/subgraph/client.ts` |
| Create | `client/src/subgraph/queries.ts` |
| Create | `client/src/subgraph/index.ts` |
| Create | `client/tests/subgraph-client.test.ts` |

### Step 1: Write the failing test

```typescript
// client/tests/subgraph-client.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { SubgraphClient } from "../src/subgraph/client";

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe("SubgraphClient", () => {
  let client: SubgraphClient;

  beforeEach(() => {
    client = new SubgraphClient("http://localhost:8000/subgraphs/name/totalreclaw/totalreclaw");
    mockFetch.mockReset();
  });

  describe("search", () => {
    it("should query with hash_in for blind index lookup", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          data: {
            blindIndices: [
              { fact: { id: "f1", encryptedBlob: "0xabc", encryptedEmbedding: "enc1", decayScore: "0.9", isActive: true } },
              { fact: { id: "f1", encryptedBlob: "0xabc", encryptedEmbedding: "enc1", decayScore: "0.9", isActive: true } },
              { fact: { id: "f2", encryptedBlob: "0xdef", encryptedEmbedding: null, decayScore: "0.5", isActive: true } },
            ]
          }
        })
      });

      const results = await client.search("0xowner", ["hash1", "hash2", "hash3"]);

      // Should deduplicate by fact ID
      expect(results).toHaveLength(2);
      expect(results[0].id).toBe("f1");
      expect(results[1].id).toBe("f2");

      // Should use hash_in query
      const body = JSON.parse(mockFetch.mock.calls[0][1].body);
      expect(body.query).toContain("hash_in");
      expect(body.variables.trapdoors).toEqual(["hash1", "hash2", "hash3"]);
    });

    it("should paginate when trapdoors exceed GraphQL limit", async () => {
      // GraphQL _in filter has a practical limit of ~500 items
      const manyTrapdoors = Array.from({ length: 600 }, (_, i) => `hash${i}`);

      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => ({ data: { blindIndices: [] } })
      });

      await client.search("0xowner", manyTrapdoors);

      // Should split into 2 batches (500 + 100)
      expect(mockFetch).toHaveBeenCalledTimes(2);
    });
  });

  describe("fetchAllFacts", () => {
    it("should fetch all facts for an owner", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          data: {
            facts: [
              { id: "f1", encryptedBlob: "0xabc", encryptedEmbedding: "enc1", decayScore: "0.9", isActive: true, sequenceId: "1", blockNumber: "100", timestamp: "1000" },
            ]
          }
        })
      });

      const facts = await client.fetchAllFacts("0xowner");
      expect(facts).toHaveLength(1);
      expect(facts[0].id).toBe("f1");
    });
  });

  describe("deltaSyncFacts", () => {
    it("should fetch facts since a given block number", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          data: {
            facts: [
              { id: "f2", encryptedBlob: "0xdef", encryptedEmbedding: null, decayScore: "0.7", isActive: true, sequenceId: "2", blockNumber: "200", timestamp: "2000" },
            ]
          }
        })
      });

      const facts = await client.deltaSyncFacts("0xowner", 100);
      expect(facts).toHaveLength(1);

      const body = JSON.parse(mockFetch.mock.calls[0][1].body);
      expect(body.variables.sinceBlock).toBe("100");
    });
  });

  describe("getFactCount", () => {
    it("should return total fact count for an owner", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          data: {
            facts: [{ id: "count" }]  // use aggregation or count query
          }
        })
      });

      const count = await client.getFactCount("0xowner");
      expect(typeof count).toBe("number");
    });
  });
});
```

### Step 2: Run test to verify it fails

Run: `cd client && npx vitest run tests/subgraph-client.test.ts`
Expected: FAIL — module not found.

### Step 3: Write queries.ts (GraphQL query strings)

```typescript
// client/src/subgraph/queries.ts

/** Search: find facts matching any of the given blind index trapdoors */
export const SEARCH_BY_BLIND_INDEX = `
  query SearchByBlindIndex($trapdoors: [String!]!, $owner: Bytes!, $first: Int!) {
    blindIndices(
      where: { hash_in: $trapdoors, owner: $owner }
      first: $first
    ) {
      fact {
        id
        encryptedBlob
        encryptedEmbedding
        decayScore
        isActive
        contentFp
        sequenceId
        version
      }
    }
  }
`;

/** Fetch all active facts for an owner (bulk download / recovery) */
export const FETCH_ALL_FACTS = `
  query FetchAllFacts($owner: Bytes!, $first: Int!, $skip: Int!) {
    facts(
      where: { owner: $owner, isActive: true }
      orderBy: sequenceId
      orderDirection: asc
      first: $first
      skip: $skip
    ) {
      id
      encryptedBlob
      encryptedEmbedding
      decayScore
      isActive
      contentFp
      sequenceId
      blockNumber
      timestamp
      version
    }
  }
`;

/** Delta sync: facts since a given block number */
export const DELTA_SYNC_FACTS = `
  query DeltaSyncFacts($owner: Bytes!, $sinceBlock: BigInt!, $first: Int!, $skip: Int!) {
    facts(
      where: { owner: $owner, blockNumber_gt: $sinceBlock }
      orderBy: blockNumber
      orderDirection: asc
      first: $first
      skip: $skip
    ) {
      id
      encryptedBlob
      encryptedEmbedding
      decayScore
      isActive
      contentFp
      sequenceId
      blockNumber
      timestamp
      version
    }
  }
`;

/** Count facts for an owner (for dynamic pool sizing) */
export const COUNT_FACTS = `
  query CountFacts($owner: Bytes!) {
    facts(where: { owner: $owner, isActive: true }, first: 1000) {
      id
    }
  }
`;
```

### Step 4: Write client.ts

```typescript
// client/src/subgraph/client.ts

import { SEARCH_BY_BLIND_INDEX, FETCH_ALL_FACTS, DELTA_SYNC_FACTS, COUNT_FACTS } from "./queries";

export interface SubgraphFact {
  id: string;
  encryptedBlob: string;
  encryptedEmbedding: string | null;
  decayScore: string;
  isActive: boolean;
  contentFp?: string;
  sequenceId?: string;
  blockNumber?: string;
  timestamp?: string;
  version?: number;
}

const TRAPDOOR_BATCH_SIZE = 500; // GraphQL _in filter practical limit
const PAGE_SIZE = 1000;          // Max entities per query

export class SubgraphClient {
  constructor(private endpoint: string) {}

  /** Search for facts matching any of the given trapdoors */
  async search(owner: string, trapdoors: string[]): Promise<SubgraphFact[]> {
    const allResults = new Map<string, SubgraphFact>();

    // Batch trapdoors to stay within GraphQL _in limits
    for (let i = 0; i < trapdoors.length; i += TRAPDOOR_BATCH_SIZE) {
      const batch = trapdoors.slice(i, i + TRAPDOOR_BATCH_SIZE);
      const data = await this.query(SEARCH_BY_BLIND_INDEX, {
        trapdoors: batch,
        owner,
        first: PAGE_SIZE,
      });

      if (data?.blindIndices) {
        for (const entry of data.blindIndices) {
          if (entry.fact && !allResults.has(entry.fact.id)) {
            allResults.set(entry.fact.id, entry.fact);
          }
        }
      }
    }

    return Array.from(allResults.values());
  }

  /** Fetch all active facts for an owner (paginated) */
  async fetchAllFacts(owner: string): Promise<SubgraphFact[]> {
    const allFacts: SubgraphFact[] = [];
    let skip = 0;

    while (true) {
      const data = await this.query(FETCH_ALL_FACTS, {
        owner,
        first: PAGE_SIZE,
        skip,
      });

      const facts = data?.facts || [];
      allFacts.push(...facts);

      if (facts.length < PAGE_SIZE) break;
      skip += PAGE_SIZE;
    }

    return allFacts;
  }

  /** Delta sync: fetch facts written after a given block number */
  async deltaSyncFacts(owner: string, sinceBlock: number): Promise<SubgraphFact[]> {
    const allFacts: SubgraphFact[] = [];
    let skip = 0;

    while (true) {
      const data = await this.query(DELTA_SYNC_FACTS, {
        owner,
        sinceBlock: sinceBlock.toString(),
        first: PAGE_SIZE,
        skip,
      });

      const facts = data?.facts || [];
      allFacts.push(...facts);

      if (facts.length < PAGE_SIZE) break;
      skip += PAGE_SIZE;
    }

    return allFacts;
  }

  /** Get fact count for an owner (for dynamic pool sizing) */
  async getFactCount(owner: string): Promise<number> {
    const data = await this.query(COUNT_FACTS, { owner });
    return data?.facts?.length || 0;
  }

  private async query(query: string, variables: Record<string, unknown>): Promise<any> {
    const response = await fetch(this.endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, variables }),
    });

    if (!response.ok) {
      throw new Error(`Subgraph query failed: ${response.status} ${response.statusText}`);
    }

    const json = await response.json();
    if (json.errors) {
      throw new Error(`Subgraph query error: ${json.errors[0].message}`);
    }

    return json.data;
  }
}
```

### Step 5: Write index.ts

```typescript
// client/src/subgraph/index.ts
export { SubgraphClient } from "./client";
export type { SubgraphFact } from "./client";
```

### Step 6: Run tests

Run: `cd client && npx vitest run tests/subgraph-client.test.ts`
Expected: All tests pass.

### Step 7: Commit

```bash
git add client/src/subgraph/ client/tests/subgraph-client.test.ts
git commit -m "feat(client): subgraph client with hash_in search, bulk download, delta sync"
```

---

## Task 7: Client Hot Cache (Persistent Encrypted)

**Goal:** A small persistent cache that stores the top ~30 high-importance facts (encrypted at rest) for instant auto-recall. Also caches fact count and last-synced block number. The cache is encrypted with the same AES-256-GCM key used for facts.

**Where it lives:** `~/.totalreclaw/cache.enc` (JSON encrypted with master key). The plugin and MCP server both use this path.

**Files:**

| Action | Path |
|---|---|
| Create | `client/src/cache/hot-cache.ts` |
| Create | `client/src/cache/index.ts` |
| Create | `client/tests/hot-cache.test.ts` |

### Step 1: Write the failing test

```typescript
// client/tests/hot-cache.test.ts
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { HotCache } from "../src/cache/hot-cache";
import { existsSync, unlinkSync } from "fs";

const TEST_CACHE_PATH = "/tmp/totalreclaw-test-cache.enc";
// 32-byte test key (hex)
const TEST_KEY = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

describe("HotCache", () => {
  let cache: HotCache;

  beforeEach(() => {
    cache = new HotCache(TEST_CACHE_PATH, TEST_KEY);
    if (existsSync(TEST_CACHE_PATH)) unlinkSync(TEST_CACHE_PATH);
  });

  afterEach(() => {
    if (existsSync(TEST_CACHE_PATH)) unlinkSync(TEST_CACHE_PATH);
  });

  it("should start empty", () => {
    expect(cache.getHotFacts()).toEqual([]);
    expect(cache.getFactCount()).toBe(0);
    expect(cache.getLastSyncedBlock()).toBe(0);
  });

  it("should store and retrieve hot facts", () => {
    const facts = [
      { id: "f1", text: "User is a software engineer", importance: 9 },
      { id: "f2", text: "User likes TypeScript", importance: 7 },
    ];
    cache.setHotFacts(facts);
    expect(cache.getHotFacts()).toEqual(facts);
  });

  it("should persist to disk encrypted and load back", () => {
    const facts = [{ id: "f1", text: "Persistent fact", importance: 8 }];
    cache.setHotFacts(facts);
    cache.setFactCount(42);
    cache.setLastSyncedBlock(12345);
    cache.flush();

    // File should exist and NOT be readable as plaintext
    expect(existsSync(TEST_CACHE_PATH)).toBe(true);

    // Load from disk with same key
    const cache2 = new HotCache(TEST_CACHE_PATH, TEST_KEY);
    cache2.load();
    expect(cache2.getHotFacts()).toEqual(facts);
    expect(cache2.getFactCount()).toBe(42);
    expect(cache2.getLastSyncedBlock()).toBe(12345);
  });

  it("should fail to load with wrong key", () => {
    cache.setHotFacts([{ id: "f1", text: "secret", importance: 9 }]);
    cache.flush();

    const wrongKey = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789";
    const cache2 = new HotCache(TEST_CACHE_PATH, wrongKey);
    // Should not throw, just return empty (graceful degradation)
    cache2.load();
    expect(cache2.getHotFacts()).toEqual([]);
  });

  it("should limit hot facts to 30", () => {
    const facts = Array.from({ length: 50 }, (_, i) => ({
      id: `f${i}`, text: `Fact ${i}`, importance: i % 10
    }));
    cache.setHotFacts(facts);
    // Should keep only top 30 by importance
    expect(cache.getHotFacts().length).toBeLessThanOrEqual(30);
  });

  it("should store Smart Account address", () => {
    cache.setSmartAccountAddress("0x1234567890abcdef");
    cache.flush();

    const cache2 = new HotCache(TEST_CACHE_PATH, TEST_KEY);
    cache2.load();
    expect(cache2.getSmartAccountAddress()).toBe("0x1234567890abcdef");
  });
});
```

### Step 2: Run test to verify it fails

Run: `cd client && npx vitest run tests/hot-cache.test.ts`
Expected: FAIL — module not found.

### Step 3: Implement hot-cache.ts

The implementing agent should:
- Use `crypto.createCipheriv` / `crypto.createDecipheriv` with AES-256-GCM
- Store as `[iv:12][tag:16][ciphertext]` (same format as the rest of the codebase, see `skill/plugin/crypto.ts`)
- JSON serialize the cache data before encrypting
- Graceful degradation: if decryption fails (wrong key, corrupt file), return empty cache
- Cap hot facts at 30, sorted by importance descending
- Include `factCount`, `lastSyncedBlock`, `smartAccountAddress` in the cached payload

### Step 4: Run tests

Run: `cd client && npx vitest run tests/hot-cache.test.ts`
Expected: All tests pass.

### Step 5: Commit

```bash
git add client/src/cache/ client/tests/hot-cache.test.ts
git commit -m "feat(client): persistent encrypted hot cache for auto-recall"
```

---

## Task 8: Plugin Subgraph Integration (Store Path)

**Goal:** Add a subgraph store path to the OpenClaw plugin. When configured for subgraph mode, facts are written on-chain via UserOp instead of HTTP POST to the centralized server. The store path: encrypt → embed → LSH → blind indices → build Protobuf → build UserOp → submit to relay.

**Files:**

| Action | Path |
|---|---|
| Create | `skill/plugin/subgraph-client.ts` (thin wrapper importing from client/) |
| Modify | `skill/plugin/index.ts` (add subgraph store path alongside existing server path) |
| Create | `skill/plugin/tests/subgraph-store.test.ts` |

### Step 1: Design the integration

The plugin's `index.ts` currently does:
```
handleStore → encrypt(fact) → generateBlindIndices → generateEmbedding → LSH hash → POST /v1/store
```

For subgraph mode, replace the last step:
```
handleStore → encrypt(fact) → generateBlindIndices → generateEmbedding → LSH hash → buildProtobuf → buildUserOp → POST /relay
```

**Detection:** Check for `TOTALRECLAW_SUBGRAPH_MODE=true` env var (or config).

**Key constraint:** The existing server store path MUST continue to work unchanged. Subgraph mode is opt-in.

### Step 2: Write the failing test

The test should verify:
1. In subgraph mode, store builds a UserOp and submits to relay
2. The UserOp calldata contains the encrypted blob + blind indices + encrypted embedding
3. In default mode, store still uses HTTP POST to server (no regression)

### Step 3: Implement the subgraph store path

The implementing agent should:
- Import `buildUserOperation` and `encodeFactAsCalldata` from `client/src/userop/builder.ts`
- Import `mnemonicToKeys` from `client/src/crypto/seed.ts` for signing
- Serialize the fact (encrypted_blob + blind_indices + encrypted_embedding + metadata) as Protobuf
- Build and sign the UserOp
- Submit via HTTP POST to the relay endpoint
- Update the hot cache optimistically after successful relay submission

### Step 4: Run tests

Run: `cd skill/plugin && npm test`
Expected: All existing tests + new subgraph store tests pass.

### Step 5: Commit

```bash
git add skill/plugin/subgraph-client.ts skill/plugin/index.ts skill/plugin/tests/
git commit -m "feat(plugin): subgraph store path via UserOp + relay"
```

---

## Task 9: Plugin Subgraph Integration (Search Path)

**Goal:** Add a subgraph search path to the plugin. In subgraph mode, search queries the subgraph via GraphQL `hash_in` instead of HTTP POST to `/v1/search`. Auto-recall uses the hot cache for instant results with background subgraph refresh.

**Files:**

| Action | Path |
|---|---|
| Modify | `skill/plugin/index.ts` (add subgraph search path) |
| Create | `skill/plugin/tests/subgraph-search.test.ts` |

### Step 1: Design the search flow

```
Search (subgraph mode):
  1. Generate trapdoors (word + stem + LSH) — same as PoC v2
  2. Query subgraph: blindIndices(hash_in: trapdoors, owner: address)
  3. Deduplicate results by fact ID
  4. Decrypt encrypted_blob + encrypted_embedding
  5. Rerank: BM25 + cosine + RRF fusion — same as PoC v2
  6. Return top-k

Auto-recall (subgraph mode):
  1. Read hot cache → instant response with cached top facts
  2. Background: query subgraph with user's first message
  3. Update hot cache with fresh results
```

### Step 2: Write the failing test

The test should verify:
1. Search generates trapdoors and queries the subgraph via hash_in
2. Results are decrypted and reranked (BM25 + cosine + RRF)
3. Auto-recall reads from hot cache first
4. Hot cache is updated after subgraph query

### Step 3: Implement the subgraph search path

The implementing agent should:
- Import `SubgraphClient` from `client/src/subgraph/client`
- Import `HotCache` from `client/src/cache/hot-cache`
- On search: generate trapdoors → SubgraphClient.search() → decrypt → rerank
- On auto-recall (before_agent_start hook): read hot cache → return instantly → background refresh
- Update hot cache after every subgraph search

### Step 4: Run tests

Run: `cd skill/plugin && npm test`
Expected: All tests pass.

### Step 5: Commit

```bash
git add skill/plugin/index.ts skill/plugin/tests/
git commit -m "feat(plugin): subgraph search path with hot cache auto-recall"
```

---

## Task 10: E2E Validation — OMBH Ingest + Query

**Goal:** Ingest the 415 benchmark facts through the full subgraph pipeline (encrypt → UserOp → local chain → Graph Node indexes → query via GraphQL → decrypt → rerank) and validate recall against the 140 ground-truth queries. Compare results with PoC v2 baseline.

**Files:**

| Action | Path |
|---|---|
| Create | `subgraph/tests/e2e-ombh-validation.ts` |
| Create | `subgraph/scripts/run-e2e-validation.sh` |

### Step 1: Write the E2E validation script

The script should:

1. **Setup:** Start the Docker dev stack (Task 1), deploy contracts (Task 4), deploy subgraph (Task 5)
2. **Generate a test BIP-39 mnemonic** (deterministic for reproducibility)
3. **Ingest 415 facts** from `totalreclaw-internal/ombh/synthetic-benchmark/ground-truth/facts-ingested.json`:
   - For each fact: encrypt → generate blind indices → generate embedding → LSH hash → build Protobuf → build UserOp → submit to relay (or directly send transaction to Hardhat node)
   - Log progress every 50 facts
   - Record total time and per-fact timing
4. **Wait for indexing** — poll the subgraph until fact count reaches 415
5. **Run 140 queries** from `totalreclaw-internal/ombh/synthetic-benchmark/ground-truth/queries-ingested.json`:
   - For each query: generate trapdoors → query subgraph via hash_in → decrypt → rerank → top-8
   - Compare returned fact IDs against `relevant_facts` ground truth
   - Calculate recall@8, precision@8, MRR
6. **Generate report** with:
   - Total ingest time, per-fact average
   - Total query time, per-query average
   - Recall@8, precision@8, MRR (overall and per-category: factual, semantic, cross_conv)
   - Comparison table vs PoC v2 baseline numbers
   - BlindIndex entity count (should be ~415 × 60 = ~25,000)

### Step 2: Write run-e2e-validation.sh

```bash
#!/usr/bin/env bash
# subgraph/scripts/run-e2e-validation.sh
# Prerequisite: dev.sh is running in another terminal (Hardhat + GND)
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== Verifying dev environment ==="
./scripts/verify-indexing.sh || {
  echo "ERROR: dev.sh must be running first."
  echo "Start it in another terminal: cd subgraph && ./scripts/dev.sh"
  exit 1
}

echo "=== Running E2E validation ==="
npx tsx tests/e2e-ombh-validation.ts

echo "=== Done. Results in subgraph/tests/e2e-results/ ==="
```

### Step 3: Run validation

Prerequisite: `dev.sh` running in another terminal.

Run: `cd subgraph && chmod +x scripts/run-e2e-validation.sh && ./scripts/run-e2e-validation.sh`
Expected:
- All 415 facts ingested and indexed
- Recall@8 ≥ 90% (target: within 5% of PoC v2 baseline)
- Per-query latency ≤ 200ms on GND (self-hosted Graph Node)
- Results report generated

### Step 4: Commit

```bash
git add subgraph/tests/e2e-ombh-validation.ts subgraph/scripts/run-e2e-validation.sh
git commit -m "test(subgraph): E2E validation with 415 OMBH facts + 140 queries"
```

---

## Task 11: Gas Cost Measurement + Report

**Goal:** Measure actual gas costs per fact with PoC v2 payloads (encrypted blob + embedding + blind indices). Extrapolate to 10k, 100k, and 1M facts. Compare with spec estimates.

**Files:**

| Action | Path |
|---|---|
| Create | `subgraph/tests/gas-measurement.ts` |
| Create | `subgraph/tests/gas-report.md` (generated) |

### Step 1: Write gas measurement script

The script should:

1. Deploy contracts to Hardhat local node
2. Create 10 representative facts of varying sizes:
   - Small fact (20 words, ~50 blind indices, 384-dim embedding)
   - Medium fact (50 words, ~80 blind indices, 384-dim embedding)
   - Large fact (100 words, ~120 blind indices, 384-dim embedding)
   - Fact without embedding (v1 backward compat)
3. For each fact, submit as a transaction (not UserOp, to measure raw gas):
   - Record `gasUsed` from the transaction receipt
   - Record calldata size in bytes
4. Calculate:
   - Gas per byte of calldata
   - Gas per fact (small/medium/large)
   - Estimated cost on Base L2 mainnet at current gas prices (fetch from API or use $0.001/KB L1 data)
5. Extrapolation table:
   | Scale | Facts | BlindIndex Entities | Est. Gas (total) | Est. Cost (Base L2) |
   |---|---|---|---|---|
   | Single user (1 year) | 5,000 | ~300,000 | ... | ... |
   | Power user | 50,000 | ~3,000,000 | ... | ... |
   | 10K users × 1 year | 50,000,000 | ~3B | ... | ... |
6. Generate markdown report

### Step 2: Run measurement

Run: `cd subgraph && npx tsx tests/gas-measurement.ts`
Expected: Report generated at `subgraph/tests/gas-report.md`.

### Step 3: Commit

```bash
git add subgraph/tests/gas-measurement.ts subgraph/tests/gas-report.md
git commit -m "docs(subgraph): gas cost measurement report for PoC v2 payloads"
```

---

## Task 12: Recovery Flow (Seed → Full Restore)

**Goal:** Implement and test the full recovery flow: user pastes 12-word mnemonic on a new device → derive Smart Account address → query subgraph for all facts → decrypt → verify integrity. This is the core UX promise of the subgraph version.

**Files:**

| Action | Path |
|---|---|
| Create | `client/src/recovery/restore.ts` |
| Create | `client/tests/recovery-flow.test.ts` |

### Step 1: Write the failing test

```typescript
// client/tests/recovery-flow.test.ts
import { describe, it, expect } from "vitest";

describe("Recovery Flow", () => {
  it("should restore all facts from a mnemonic", async () => {
    // 1. Generate mnemonic
    // 2. Derive keys + Smart Account address
    // 3. Store N facts via subgraph (from Task 10)
    // 4. Create a NEW client with ONLY the mnemonic (no cache, no state)
    // 5. Call restore(mnemonic)
    // 6. Verify all N facts are recovered and decrypted correctly
  });

  it("should populate hot cache after recovery", async () => {
    // After restore, the hot cache should contain top 30 facts
  });

  it("should handle empty subgraph (new user)", async () => {
    // Fresh mnemonic with no on-chain data → empty result, no errors
  });
});
```

### Step 2: Implement restore.ts

```typescript
// client/src/recovery/restore.ts
import { mnemonicToKeys } from "../crypto/seed";
import { SubgraphClient } from "../subgraph/client";
import { HotCache } from "../cache/hot-cache";

export interface RestoredFact {
  id: string;
  text: string;
  type?: string;
  importance?: number;
  decayScore: number;
}

export interface RestoreResult {
  totalFacts: number;
  restoredFacts: RestoredFact[];
  hotCachePopulated: boolean;
  smartAccountAddress: string;
}

export async function restoreFromMnemonic(
  mnemonic: string,
  subgraphEndpoint: string,
  cachePath: string,
): Promise<RestoreResult> {
  // 1. Derive keys
  // 2. Derive Smart Account address
  // 3. Fetch all facts from subgraph
  // 4. Decrypt each fact
  // 5. Sort by importance, populate hot cache (top 30)
  // 6. Return all decrypted facts
}
```

### Step 3: Run tests (requires Docker dev stack from Task 10)

Run: `cd client && npx vitest run tests/recovery-flow.test.ts`
Expected: All tests pass. Full round-trip: store → index → recover → decrypt → verify.

### Step 4: Commit

```bash
git add client/src/recovery/ client/tests/recovery-flow.test.ts
git commit -m "feat(client): full recovery flow — mnemonic to restored facts via subgraph"
```

---

## Post-Implementation Checklist

After all 12 tasks are complete:

- [ ] All contract tests pass: `cd contracts && npx hardhat test`
- [ ] Subgraph builds: `cd subgraph && npx graph build`
- [ ] GND indexes events correctly: `cd subgraph && ./scripts/verify-indexing.sh`
- [ ] Client tests pass: `cd client && npx vitest run`
- [ ] Plugin tests pass: `cd skill/plugin && npm test`
- [ ] E2E validation passes with ≥90% recall@8
- [ ] Gas report generated and reviewed
- [ ] Recovery flow demonstrated end-to-end
- [ ] Hot cache encrypts at rest (verified by wrong-key test)
- [ ] No regression in existing PoC v2 tests (343/343 still pass)
- [ ] All changes on `feature/subgraph` branch
- [ ] TASKS.md and CHANGELOG.md updated

## Local Dev Workflow Summary

The implementing agent should keep two terminals open throughout development:

```
Terminal 1 (always running):
  cd subgraph && ./scripts/dev.sh
  # Starts Hardhat node + deploys contracts + starts GND with --watch
  # GND auto-redeploys subgraph when build/ changes

Terminal 2 (working terminal):
  # Make code changes, run tests, etc.
  cd subgraph && npx graph codegen && npx graph build  # triggers GND redeploy
  ./scripts/verify-indexing.sh                          # check indexing
  npx tsx tests/e2e-ombh-validation.ts                  # run E2E tests
```

GND manages its own PostgreSQL instance (in `./build/`) — no Docker, no IPFS, no manual database setup.
