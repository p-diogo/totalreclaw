# Graph Node Dev Mode (GND) — Local Subgraph Testing

> Reference: https://thegraph.com/docs/en/subgraphs/developing/creating/graph-node-dev/

## Overview

GND is a developer-friendly Graph Node runner for local subgraph development. Simplifies setup by removing the need for IPFS and offering smart defaults like automatic database handling (on Unix) and live subgraph redeployment.

## Prerequisites

- Local subgraph that completes `graph build`
- PostgreSQL installed and running (auto-managed on Unix)
- Access to an Ethereum RPC endpoint (e.g., Anvil, Hardhat)

## Setup

```bash
npm install -g @graphprotocol/graph-cli
graph install gnd
```

Ensure `~/.local/bin` is in your PATH.

## Usage

```bash
# From subgraph/ directory, with Hardhat local node running:
gnd --ethereum-rpc base-sepolia:http://127.0.0.1:8545 --watch
```

- `--watch` enables automatic redeploys when build directory changes
- On macOS/Linux, PostgreSQL is auto-managed (temp instance in `./build`)
- IPFS is optional (defaults to `https://api.thegraph.com/ipfs`)

## Query Endpoint

```
http://localhost:8000/subgraphs/name/<subgraph-name>
```

## Local Dev Workflow

```bash
# Terminal 1: Hardhat local node
cd contracts && npx hardhat node

# Terminal 2: GND with hot-reload
cd subgraph && gnd --ethereum-rpc base-sepolia:http://127.0.0.1:8545 --watch

# Terminal 3: Deploy contracts to local node, then query subgraph
cd contracts && npx hardhat run scripts/deploy.ts --network localhost
curl -X POST http://localhost:8000/subgraphs/name/totalreclaw \
  -H "Content-Type: application/json" \
  -d '{"query": "{ dataEdgeEvents(first: 5) { id owner cid } }"}'
```

## Flags

| Flag | Description |
|------|-------------|
| `--watch` | Auto-redeploy on build changes |
| `--manifests` | Path to manifest files |
| `--database-dir` | Temp Postgres dir (Unix only, default: `./build`) |
| `--postgres-url` | Postgres URL (required on Windows) |
| `--ethereum-rpc` | Format: `network[:capabilities]:URL` (required) |
| `--ipfs` | IPFS endpoint (default: The Graph's public IPFS) |

## Impact on TotalReclaw

This replaces the original plan's Docker Compose setup (Graph Node + IPFS + PostgreSQL containers) with a much simpler local dev experience. Use GND for development/testing, full Docker setup only for production self-hosted indexing.
