#!/usr/bin/env bash
# subgraph/scripts/run-e2e-validation.sh
# Prerequisite: dev.sh is running in another terminal (Hardhat + Graph Node)
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== Verifying dev environment ==="
./scripts/verify-indexing.sh || {
  echo "ERROR: dev.sh must be running first."
  echo "Start it in another terminal: cd subgraph && ./scripts/dev.sh"
  exit 1
}

echo ""
echo "=== Running E2E OMBH Validation ==="
echo "This will ingest 415 facts and run 140 queries."
echo "Expected runtime: 10-30 minutes (depending on embedding model speed)."
echo ""

npx tsx --tsconfig tsconfig.node.json tests/e2e-ombh-validation.ts

echo ""
echo "=== Done. Results in subgraph/tests/e2e-results/ ==="
