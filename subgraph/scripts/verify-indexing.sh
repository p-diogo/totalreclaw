#!/usr/bin/env bash
# subgraph/scripts/verify-indexing.sh
# Verify Graph Node is running and indexing events
# Prerequisite: dev.sh is running in another terminal
set -euo pipefail

QUERY_URL="http://localhost:8000/subgraphs/name/totalreclaw"

echo "=== Checking Graph Node is running ==="
RESPONSE=$(curl -sf -X POST "$QUERY_URL" \
  -H "Content-Type: application/json" \
  -d '{"query": "{ _meta { block { number } } }"}' 2>/dev/null) || {
  echo "ERROR: Graph Node not reachable at $QUERY_URL"
  echo "Make sure dev.sh is running: cd subgraph && ./scripts/dev.sh"
  exit 1
}

BLOCK=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['_meta']['block']['number'])")
echo "Graph Node is indexing. Current block: $BLOCK"

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

echo "=== Graph Node verification complete ==="
