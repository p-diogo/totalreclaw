<!--
Product: OpenMemory (ARCHIVED)
Formerly: tech specs/archive/OpenMemory v0.3 PRD (TDX & Horizon).md
Version: 3.0.0
Last updated: 2026-02-24
-->

# Product Requirements Document (PRD): OpenMemory Decentralized Network

**Version:** 3.0.0 (Intel TDX Confidential Computing Architecture)

**Product Name:** OpenMemory

**Status:** Approved for Implementation

---

## 1. Executive Summary & Product Vision

**The Problem:** Local-first AI agents (OpenClaw, Nanobot, PicoClaw) store sensitive memory logs in local, clear-text Markdown files. This exposes user data to local extraction, prevents seamless memory portability across different AI clients, and locks out constrained IoT devices that cannot run heavy local vector databases.

**The Solution:** OpenMemory is a "Bring Your Own Memory" (BYOM) infrastructure. It provides a highly available, decentralized memory vault for AI agents, powered natively by **The Graph Horizon Data Service** and secured by **Intel Trust Domain Extensions (TDX)**.

**The Strategy ("The Trojan Horse"):** The product goes to market as a frictionless `npm` Skill for OpenClaw/Nanobot. To the user, it operates as a simple plugin. Architecturally, it routes the agent's memory over a secure mTLS tunnel to a hardware-encrypted enclave, delivering Web2 UX with Web3 data sovereignty.

---

## 2. The Architectural Pivot: Confidential Computing (Intel TDX)

Previous iterations required complex client-side End-to-End Encryption (E2EE), which physically excluded constrained IoT agents from participating. OpenMemory adopts a **Confidential Computing Architecture** to shift the cryptographic burden to the decentralized network without sacrificing zero-trust privacy.

- **Hardware Trust Domains:** The OpenMemory Data Service (and the SaaS MVP) runs entirely inside an Intel TDX enclave or AWS Nitro Enclave (a hardware-isolated Virtual Machine).
- **The Flow:** The client agent (even a $10 IoT PicoClaw device with <10MB RAM) sends plain-text memory over an mTLS connection directly to the enclave. The enclave generates the vector embedding, processes the memory, and encrypts it to disk.
- **The Guarantee:** The host operating system, the hypervisor, and the physical server owner (the Cloud Provider or Graph Indexer) are mathematically locked out of the enclave. The data is opaque in transit, in use (RAM), and at rest.

---

## 3. Search Architecture: Restoring Native Querying

By moving the secure boundary to the hardware enclave, OpenMemory eliminates the severe "Recall Bound" limitations of blind decentralized storage.

- **Full-Text & Vector Search:** Because the database (SQLite for MVP, PostgreSQL for The Graph) operates *inside*the secure TDX enclave, it can read the plain-text data natively in its protected RAM.
- **The Result:** The enclave executes standard, highly accurate Hybrid Search (Cosine Distance + FTS5 keyword matching) natively, calculates the exact relevance, and returns only the finalized snippet to the agent over mTLS. 100% search accuracy is restored with zero client-side reranking required.

---

## 4. Backend Infrastructure & Economics

The backend utilizes a bespoke **Horizon Data Service** tailored for Confidential Computing.

### 4.1 The Network Interface

- **Phase 1 (MVP SaaS):** Standard REST/JSON API hosted inside a cloud TEE (e.g., AWS Nitro). Prioritizes Go-To-Market speed.
- **Phase 2 (The Graph Production):** gRPC with Protocol Buffers (`.proto`) over mTLS. Packs floating-point vectors into compressed binary data, slashing bandwidth costs and Indexer CPU parsing overhead.

### 4.2 Storage Engines & Indexer Economics

- **Hardware Requirements:** Graph Indexers must provision servers with 4th Gen (Sapphire Rapids) or 5th Gen (Emerald Rapids) Intel Xeon Scalable processors to support TDX. **No expensive GPUs (H100s) are required.**
- **Indexer Economics:** Indexers can lease enterprise-grade TDX-capable servers (e.g., Hetzner DX153) for roughly **€209/month**, making network participation highly accessible.
- **Database Isolation:** Indexers deploy the OpenMemory gateway container connected to a TDX-isolated PostgreSQL + `pgvector` database, ensuring AI workloads never degrade Subgraph indexing performance.

---

## 5. User Experience & Agent Interoperability

### 5.1 The OpenClaw Skill Interface

- Overrides OpenClaw's default local file commands, registering `search_remote_vault` and `save_remote_fact` as native tools.
- **Remote Attestation:** Before an agent sends a single byte of memory, the local client automatically verifies the cryptographic quote from the TDX enclave, ensuring the server is running the unaltered, official OpenMemory code.
- **Agent Sharding:** Tags memories with an `agent_id` allowing users to test "burner agents" and instantly delete their associated shards.

### 5.2 Universal MCP Server

The local node spawns a background `stdio` process compliant with the **Model Context Protocol (MCP)**.

- Allows desktop agents (Claude Desktop, ChatGPT Desktop) to instantly connect to the centralized/decentralized enclave via the local mTLS proxy.

### 5.3 Anti-Vendor Lock-in (Data Sovereignty)

Running `openclaw-skill memory export` triggers the enclave to package the entire history, delivering standard, human-readable `YYYY-MM-DD.md` files back to the user's local workspace.