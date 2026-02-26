<!--
Product: OpenMemory (ARCHIVED)
Formerly: tech specs/archive/OpenMemory v0.2 TS (E2EE & Horizon).md
Version: 0.2
Last updated: 2026-02-24
-->

# ENGINEERING SPECIFICATION: Decentralized OpenMemory (Graph Horizon)

## 1. System Architecture & Topology

The system abandons centralized Web2 SaaS and Trusted Execution Environments (TEEs). It is composed of two distinct operational layers:

1. **The Local Cryptographic Node (`npm` package):** Runs on the user's hardware. Acts simultaneously as an OpenClaw Skill and a local MCP Server. Handles all key derivation, AES-GCM encryption, ONNX vectorization, and BM25 reranking.
2. **The Graph Horizon Data Service:** A customized decentralized stack run by Graph Indexers. It acts purely as a highly available, mathematically blind storage and nearest-neighbor vector search engine.
    - **Crucial Infrastructure Constraint (The Noisy Neighbor Mitigation):** To prevent vector math (HNSW memory caching and floating-point CPU spikes) from degrading an Indexer's core Subgraph indexing performance, **the OpenMemory database must run as an entirely isolated container.** It must never share a database instance with existing Subgraph data.

---

## 2. Key Management & Authentication (Zero-Knowledge)

To prevent users from managing raw key files while maintaining E2EE, the local node utilizes a "Master Password" architecture.

- **User Identity:** The user's `Graph_API_Key` acts as their network identifier/username for routing and Indexer payment.
- **Cryptographic Derivation:** 1. User inputs a `Master_Password` during initial setup (`openclaw memory-vault login`). 2. The local node uses `Argon2id` (memory-hard KDF) combined with a local machine salt to derive a 256-bit `Master_Key`. 3. The `Master_Key` is immediately stored in the OS Secure Enclave (macOS Keychain / Windows Credential Manager). 4. The `Master_Key` is mathematically split into two operational keys:
    - `Data_Key` (256-bit): Used for AES-GCM file encryption.
    - `Blind_Key` (256-bit): Used for HMAC-SHA256 blind index generation.

---

## 3. Horizon Data Service: Database Schema

To participate in the OpenMemory network, Graph Indexers must deploy the Data Service alongside a dedicated, isolated database container. The system officially supports two engine paths, both of which operate under highly permissive open-source licenses.

### Option A: Isolated PostgreSQL + `pgvector` (PostgreSQL License)

The standard deployment path for Indexers who want operational familiarity. Must run PostgreSQL 16+ in a standalone container with hard memory/CPU limits (cgroups).

SQL

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE encrypted_vault (
    id UUID PRIMARY KEY,
    vault_id TEXT NOT NULL, 
    agent_id TEXT NOT NULL, 
    ciphertext BYTEA NOT NULL, 
    embedding vector(384) NOT NULL, 
    blind_indices TEXT[] NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for Semantic Search (HNSW)
CREATE INDEX ON encrypted_vault USING hnsw (embedding vector_cosine_ops);
-- Index for Blind Exact Matches (GIN)
CREATE INDEX ON encrypted_vault USING GIN (blind_indices);
CREATE INDEX ON encrypted_vault (vault_id);
```

### Option B: Dedicated Qdrant Engine (Apache License 2.0)

The high-performance deployment path for scale. Qdrant is a Rust-based, purpose-built vector database. Because it utilizes memory-mapped files and optimized disk I/O, it achieves significantly higher throughput than `pgvector` with a smaller memory footprint, making it ideal for high-traffic Indexers.

**Qdrant Collection Schema:**

- **Vector Size:** `384` (Distance: `Cosine`)
- **Payload Structure:**
    - `vault_id` (Type: `Keyword` - Indexed for exact filtering)
    - `agent_id` (Type: `Keyword` - Indexed for sharding)
    - `blind_indices` (Type: `Keyword` array - Indexed for exact hash matching)
    - `ciphertext` (Type: `Text` - Unindexed base64 encoded AES-GCM payload)

*Note for Coding Agent: The gRPC Gateway must abstract the database layer so that it can dynamically route read/write operations to either the Postgres container or the Qdrant container based on the Indexer's `.env` configuration.*

---

## 4. Network Interface & API Gateway

Because this is a bespoke Data Service and not a legacy Subgraph, the architecture completely abandons GraphQL in favor of direct API communication.

### 4.1 The Dual-Gateway Strategy

- **Phase 1: REST API (MVP):** For initial Go-To-Market and rapid prototyping, the Data Service will expose standard HTTP/JSON endpoints (`POST /v1/vault/fact`). This allows fast development but incurs a penalty of "JSON bloat" when transmitting floating-point vector arrays as text.
- **Phase 2: gRPC (Production Standard):** The Data Service must ultimately expose a **gRPC Gateway** utilizing Protocol Buffers (`.proto`).
    - *Why gRPC?* 384-dimensional vectors serialize into massive text strings in JSON. Protobuf packs these vectors into highly compressed binary data, slashing bandwidth costs across the decentralized network and dramatically reducing the Indexer's CPU parsing overhead. gRPC mathematically enforces the API contract, ensuring the `npm` skill and the Indexer never experience data-type mismatches.

### 4.2 The Write Path (Saving a Memory)

When OpenClaw triggers the `save_memory` tool, the Local Node executes:

1. **Entity Extraction:** Run a local Regex/NLP pipeline over the plain text to extract high-value exact-match targets (e.g., Email addresses, UUIDs, API keys).
2. **Blind Index Generation:** Hash each extracted entity using `HMAC-SHA256` with the `Blind_Key`.
3. **Local Vectorization:** Pass the full plain text through a local ONNX runtime of `all-MiniLM-L6-v2` (`INT8` quantized).
4. **Encryption:** Encrypt the full plain text using `AES-GCM` with the `Data_Key`.
5. **Network Mutation:** Transmit the payload to the Data Service.

**REST MVP Payload Example:**

JSON

```json
POST /v1/vault/fact
{
  "vault_id": "hashed_user_id",
  "agent_id": "openclaw-main",
  "ciphertext": "0xabc123...",
  "embedding": [0.012, -0.045, ...], 
  "blind_indices": ["a7b8x9...", "c4d5e6..."]
}
```

### 4.3 The Read Path (Retrieval & Reranking)

When OpenClaw triggers `search_memory`, the Local Node executes the Two-Pass retrieval strategy.

**Pass 1: Remote Blind Retrieval**

1. The local node generates a query vector and hashes any specific entities in the query using the `Blind_Key`.
2. It requests the Top 250 closest semantic matches, **OR** any exact matches from the blind index via the API.

**REST MVP Request Example:**

JSON

```json
POST /v1/vault/search
{
  "vault_id": "hashed_user_id",
  "query_vector": [0.012, -0.045, ...],
  "blind_match_hashes": ["a7b8x9..."],
  "limit": 250
}
```

**Pass 2: Local Decryption & BM25 Reranking**

1. **Bulk Decrypt:** The Local Node receives up to 250 ciphertexts and decrypts them in RAM using the `Data_Key`.
2. **Local BM25:** The Node runs a fast, in-memory BM25 keyword search across the 250 plain-text documents against the user's original query.
3. **RRF Scoring:** For each document, calculate the Reciprocal Rank Fusion score combining the Data Service's returned vector rank and the local BM25 rank.
    
    Score=60+rankvector1+60+rankBM251
    
4. **Final Delivery:** The Node selects the Top 3 highest-scoring plain-text documents, purges the rest from RAM, and returns them to OpenClaw.

### 4.4 gRPC Protobuf Schema (Production Standard)

For the Phase 2 production rollout, the local `npm` client and the Data Service indexer will adhere strictly to this `.proto`definition. The `repeated float` type perfectly maps to the 384-dimensional vector, and the `bytes` type securely handles the AES-GCM payload without encoding overhead.

Protocol Buffers

```protobuf
syntax = "proto3";

package openmemory;

// The core Data Service API hosted by Graph Indexers
service VaultService {
    rpc SaveMemory (SaveMemoryRequest) returns (SaveMemoryResponse);
    rpc SearchMemory (SearchMemoryRequest) returns (SearchMemoryResponse);
}

message SaveMemoryRequest {
    string vault_id = 1;                // Derived from the user's Graph API Key hash
    string agent_id = 2;                // e.g., 'openclaw-main'
    bytes ciphertext = 3;               // AES-GCM encrypted Markdown blob
    repeated float embedding = 4;       // 384-dimensional semantic vector
    repeated string blind_indices = 5;  // HMAC-SHA256 hashes of exact-match entities
}

message SaveMemoryResponse {
    string status = 1;
    string commit_id = 2;               // Unique UUID of the database insertion
}

message SearchMemoryRequest {
    string vault_id = 1;
    repeated float query_vector = 2;        // The vectorized search query
    repeated string blind_match_hashes = 3; // Any hashed entities extracted from the query
    int32 limit = 4;                        // Set to 250 for the Two-Pass retrieval strategy
}

message SearchResultItem {
    string file_id = 1;
    bytes ciphertext = 2;
    float vector_distance = 3;          // Returned by pgvector HNSW for local RRF calculation
}

message SearchMemoryResponse {
    repeated SearchResultItem results = 1;
}
```

---

## 5. Local Node Interfaces

To satisfy both OpenClaw's architecture and future AI agents, the Local Node exposes two interfaces simultaneously.

### 5.1 OpenClaw Interface (The Native Skill)

The node provides a `SKILL.md` that overrides the default file I/O commands.

- Registers `search_remote_vault` and `save_remote_fact` as native tools.
- Exposes CLI commands for data sovereignty:
    - `openclaw-skill memory export`: Triggers a full API pagination dump, decrypts all records locally, and writes standard `YYYY-MM-DD.md` files back to the local OpenClaw workspace directory, ensuring zero vendor lock-in.

### 5.2 The Universal MCP Server

The node spawns a background `stdio` process compliant with the Model Context Protocol.

- Claude Desktop / ChatGPT Desktop connects to this local process.
- The MCP server exposes the exact same `search_remote_vault` and `save_remote_fact` tools.
- Because the MCP server runs locally, it natively accesses the `Data_Key` in the OS Keychain, performs the decryption, and hands standard plain-text JSON-RPC responses directly to the Desktop AI clients.