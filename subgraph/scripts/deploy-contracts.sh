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

DATA_EDGE=$(python3 -c "import json; print(json.load(open('$ADDRESSES_FILE'))['eventfulDataEdge'])")
START_BLOCK=$(python3 -c "import json; print(json.load(open('$ADDRESSES_FILE'))['blockNumber'])")

echo "DataEdge: $DATA_EDGE (block $START_BLOCK)"

echo "=== Updating subgraph.yaml ==="
cd "$SUBGRAPH_DIR"
sed -i.bak "s|address: \"0x[0-9a-fA-F]*\"|address: \"$DATA_EDGE\"|" subgraph.yaml
sed -i.bak "s|startBlock: [0-9]*|startBlock: $START_BLOCK|" subgraph.yaml
rm -f subgraph.yaml.bak

echo "=== Copying ABI ==="
mkdir -p "$SUBGRAPH_DIR/abis"
cp "$CONTRACTS_DIR/artifacts/contracts/EventfulDataEdge.sol/EventfulDataEdge.json" \
   "$SUBGRAPH_DIR/abis/EventfulDataEdge.json"

echo "=== Done ==="
