#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Install test deps
npm install 2>/dev/null

echo "=== Starting Docker services ==="
docker compose up -d --build --wait --wait-timeout 120

echo "=== Services ready. Running tests ==="
EXIT_CODE=0
npx tsx run-integration-tests.ts || EXIT_CODE=$?

echo "=== Tearing down ==="
docker compose down -v --remove-orphans

exit $EXIT_CODE
