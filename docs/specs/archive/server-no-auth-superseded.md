<!--
Product: OpenMemory (SUPERSEDED by docs/specs/openmemory/server.md)
Formerly: tech specs/v0.3 (grok)/TS v0.3 Server-side PoC (no Subgraph).md
Version: 0.3 (1.0)
Last updated: 2026-02-24
-->

# Technical Specification: OpenMemory POC Server Component
**(Future-Proof for Decentralized DataEdge + Subgraph Migration)**

**Version:** 1.0 (Complete for Coding Agent)  
**Date:** February 21, 2026  
**Target:** Immediate Proof-of-Concept deployment (simple, single binary or Docker)  
**Compatibility:** 100% with  
- OpenMemory Skill for OpenClaw (v1.0)  
- OpenMemory v0.3 LSH + Encrypted Embeddings  
- Future Decentralized version (DataEdge + subgraph + ERC-4337 paymaster)  

**Core Design Principle:**  
The client (OpenClaw skill) talks to **one single interface** (Protobuf over HTTP) that will never change.  
In the POC the server is a normal web service backed by PostgreSQL.  
In production it becomes a thin relay to DataEdge + subgraph.  
All payloads, schemas, and flows stay identical — upgrade is a drop-in replacement of the backend.

---

## 1. Goals & Non-Goals

### Goals
- Provide a **real, working POC** that the OpenClaw skill can talk to today (store encrypted facts, search via blind indices + LSH, update/decay/eviction).
- Use **exactly the same Protobuf schema** that will be used in the future DataEdge events.
- Keep the server **extremely simple** (one Docker container, Postgres, no complex infra).
- Make the **client code unchanged** when we later switch to the full decentralized version.
- Support the full OpenMemory Skill features (fact extraction, graph layer, decay, eviction, blind indices, LSH pre-filter, client-side rerank).

### Non-Goals (for POC)
- No subgraphs, no ERC-4337, no paymaster yet.
- No production-scale indexing (single Postgres instance is fine for POC).
- No vector search inside the server (LSH blind indices only — client does exact rerank).

---

## 2. Protobuf Schema (Shared & Immutable)

This is the **single source of truth** for all communication. It is identical to what will be emitted in `EventfulDataEdge.Log` later.

```proto
syntax = "proto3";
package openmemory;

message OpenMemoryFact {
  string id = 1;                    // UUIDv7 (time-sortable)
  string timestamp = 2;             // ISO 8601
  string owner = 3;                 // Smart Account address (for future) or userID in POC
  string encrypted_blob = 4;        // Base64 of AES-256-GCM (doc + embedding + metadata)
  repeated string blind_indices = 5; // SHA-256(token) + SHA-256(LSH bucket)
  float decay_score = 6;
  bool is_active = 7;
  int32 version = 8;
  string source = 9;                // conversation | pre_compaction | explicit | etc.
}

message StoreRequest {
  repeated OpenMemoryFact facts = 1;
}

message SearchRequest {
  string owner = 1;
  repeated string blind_trapdoors = 2;   // LSH + keyword trapdoors from client
  int32 limit = 3;                       // default 500-1000
  float min_decay_score = 4;             // default 0.3
}

message SearchResponse {
  repeated OpenMemoryFact facts = 1;     // encrypted, client decrypts & reranks
}
```
Client always sends/receives these Protobuf messages (over HTTP/JSON or gRPC — HTTP + protobuf binary body is simplest for POC).

## 3. Server Architecture (POC)
Tech stack (simple & fast to build):

- Language: Node.js (TypeScript) or Python (FastAPI) — match your preference.
- Web framework: Express/Fastify or FastAPI.
- Database: PostgreSQL 16+ (single instance, Docker).
- Protobuf handling: @bufbuild/protobuf (TS) or google-protobuf (Python).
- No external dependencies beyond Postgres.

In**ternal storage (event-sourced style — future-proof):**

Two tables:
- raw_events — immutable log of every incoming StoreRequest (raw protobuf bytes + timestamp).
This becomes the DataEdge event log later.
- facts — mutable view (processed entities for fast querying).
Updated on every store/update/decay.


This design makes migration trivial: later the facts table becomes the subgraph entities, and raw_events becomes the on-chain events.
```
DB Schema (PostgreSQL):
SQLCREATE TABLE raw_events (
  id BIGSERIAL PRIMARY KEY,
  owner TEXT NOT NULL,
  event_bytes BYTEA NOT NULL,        -- raw Protobuf of StoreRequest
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE facts (
  id TEXT PRIMARY KEY,               -- fact UUIDv7
  owner TEXT NOT NULL,
  encrypted_blob BYTEA NOT NULL,
  blind_indices TEXT[] NOT NULL,
  decay_score FLOAT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT true,
  version INT NOT NULL DEFAULT 1,
  source TEXT NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_facts_owner ON facts(owner);
CREATE INDEX idx_facts_blind_gin ON facts USING GIN(blind_indices);  -- fast contains queries
CREATE INDEX idx_facts_active_decay ON facts(is_active, decay_score);
```

## 4. API Endpoints (Protobuf over HTTP)
All endpoints accept application/x-protobuf and return the same.

SEE table in "TS v0.3 Server-side PoC (no Subgraph)_table.csv"


**Example flow (search):**  

1. Client computes query embedding → LSH trapdoors.
2. POST /search with trapdoors.
3. Server: WHERE owner = ? AND blind_indices && ARRAY[trapdoors] AND is_active = true (GIN index).
4. Returns up to limit encrypted facts.
5. Client decrypts → exact cosine rerank + BM25 + RRF.


## 5. Integration with OpenClaw Skill & Client Library
The existing OpenMemory client library (from LSH spec) only needs one small change:
```
// Instead of direct server.upload(...)
const response = await fetch(`${SERVER_URL}/store`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/x-protobuf' },
  body: storeRequest.toBinary()   // Protobuf binary
});
```
Same for /search.
Everything else (fact extraction, graph layer, decay logic, client-side rerank, seed-derived encryption) stays exactly the same.

## 6. Future Migration Path (Zero Client Changes)
When you are ready for the full decentralized version:

1. Deploy EventfulDataEdge on Base.
2. Deploy subgraph that listens to Log(bytes) events and populates the same facts entities.
3. Change the server from Postgres to a thin relay:
    - /store → build UserOperation → send to your paymaster.
    - /search → query subgraph GraphQL instead of Postgres.
4. The Protobuf schema never changes → client code is untouched.

The POC server is literally a drop-in prototype of the future decentralized backend.

## 7. Implementation Order (for Coding Agent)
**Day 1–2**

- Protobuf schema + code generation (TS/Python).
- Postgres schema + migrations.
/store and /search endpoints.

**Day 3**

- Blind-index GIN queries + LSH support.
- Update/decay/eviction logic.

**Day 4**

- Integration tests with OpenClaw skill (use existing benchmark harness).
- Docker + docker-compose (Postgres + server).

**Day 5**

- Documentation + migration guide to decentralized version.

**Deliverables**

- Dockerized server (Dockerfile + docker-compose.yml with Postgres).
- Full OpenAPI/Swagger (even though Protobuf) for debugging.
- README with “How to switch to DataEdge later” section.


