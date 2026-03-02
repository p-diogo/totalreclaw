#!/usr/bin/env bash
# ============================================================================
# TotalReclaw Direct Pipeline Test Runner
#
# Tests the full encrypted storage/recall pipeline WITHOUT needing a Claude
# agent or Anthropic API key. Validates T195, T196, T197.
#
# This script:
#   1. Starts postgres + totalreclaw-server via docker-compose
#   2. Waits for health checks
#   3. Installs npm deps (if needed)
#   4. Runs test-pipeline.ts via npx tsx from the HOST
#   5. Reports results
#   6. Cleans up (unless --no-cleanup)
#
# Prerequisites:
#   - Docker and docker-compose installed
#   - Node.js >= 18 installed on the host
#
# Usage:
#   ./run-pipeline-test.sh               # Run all tests, clean up after
#   ./run-pipeline-test.sh --no-cleanup  # Keep containers running after tests
#
# Environment variables (all optional):
#   TOTALRECLAW_MASTER_PASSWORD  — default "pipeline-test-password"
#   TOTALRECLAW_SERVER_URL       — default http://localhost:8090
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.nanoclaw-test.yml"
COMPOSE_PROJECT="pipeline-test"
TEST_FILE="$SCRIPT_DIR/test-pipeline.ts"
CREDENTIALS_FILE="$SCRIPT_DIR/test-credentials.json"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

CLEANUP=true

for arg in "$@"; do
  case $arg in
    --no-cleanup) CLEANUP=false ;;
    --help|-h)
      echo "Usage: $0 [--no-cleanup]"
      echo ""
      echo "Options:"
      echo "  --no-cleanup   Keep Docker containers running after tests"
      echo ""
      echo "Environment variables:"
      echo "  TOTALRECLAW_MASTER_PASSWORD  Test password (default: pipeline-test-password)"
      echo "  TOTALRECLAW_SERVER_URL       Server URL (default: http://localhost:8090)"
      exit 0
      ;;
  esac
done

log() {
  echo -e "${GREEN}[pipeline]${NC} $1"
}

warn() {
  echo -e "${YELLOW}[pipeline]${NC} $1"
}

fail() {
  echo -e "${RED}[pipeline]${NC} $1"
}

info() {
  echo -e "${CYAN}[pipeline]${NC} $1"
}

# Load .env if present (for POSTGRES_PASSWORD, etc.)
if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a
  source "$SCRIPT_DIR/.env"
  set +a
fi

# Set defaults
export TOTALRECLAW_MASTER_PASSWORD="${TOTALRECLAW_MASTER_PASSWORD:-pipeline-test-password}"
export TOTALRECLAW_SERVER_URL="${TOTALRECLAW_SERVER_URL:-http://localhost:8090}"
export TOTALRECLAW_CREDENTIALS_PATH="$CREDENTIALS_FILE"

cleanup() {
  if [ "$CLEANUP" = true ]; then
    log "Cleaning up..."

    # Remove test credentials
    rm -f "$CREDENTIALS_FILE"

    # Stop and remove containers + volumes
    docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" down -v --remove-orphans 2>/dev/null || true
  else
    warn "Skipping cleanup (--no-cleanup). To clean up manually run:"
    warn "  docker compose -p $COMPOSE_PROJECT -f $COMPOSE_FILE down -v"
    warn "  rm -f $CREDENTIALS_FILE"
  fi
}

trap cleanup EXIT

# ============================================================================
# Phase 1: Pre-flight checks
# ============================================================================

log "Phase 1: Pre-flight checks"

# Check Docker
if ! command -v docker &>/dev/null; then
  fail "Docker is not installed or not in PATH"
  exit 1
fi

if ! docker info &>/dev/null; then
  fail "Docker daemon is not running"
  exit 1
fi

# Check Node.js
if ! command -v node &>/dev/null; then
  fail "Node.js is not installed or not in PATH"
  exit 1
fi

NODE_VERSION=$(node --version | sed 's/^v//' | cut -d. -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
  fail "Node.js >= 18 required (found v$(node --version))"
  exit 1
fi

# Check test file exists
if [ ! -f "$TEST_FILE" ]; then
  fail "Test file not found: $TEST_FILE"
  exit 1
fi

log "  Docker: OK"
log "  Node.js: $(node --version)"
log "  Test file: $TEST_FILE"

# ============================================================================
# Phase 2: Install npm dependencies
# ============================================================================

log "Phase 2: Installing npm dependencies..."

# Check if node_modules exist with the required packages
NEEDS_INSTALL=false
if [ ! -d "$SCRIPT_DIR/node_modules/@noble/hashes" ]; then
  NEEDS_INSTALL=true
fi
if [ ! -d "$SCRIPT_DIR/node_modules/tsx" ]; then
  NEEDS_INSTALL=true
fi

if [ "$NEEDS_INSTALL" = true ]; then
  log "  Installing @noble/hashes, @scure/bip39, tsx, typescript..."
  (cd "$SCRIPT_DIR" && npm install --no-save @noble/hashes @scure/bip39 tsx typescript 2>&1 | tail -3)
  log "  Dependencies installed."
else
  log "  Dependencies already installed."
fi

# ============================================================================
# Phase 3: Start infrastructure (postgres + totalreclaw-server)
# ============================================================================

log "Phase 3: Starting postgres + totalreclaw-server..."

# Remove stale test credentials from previous runs
rm -f "$CREDENTIALS_FILE"

# Build and start services
docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" up -d --build postgres totalreclaw-server 2>&1 | tail -5

# Wait for health checks
log "  Waiting for services to be healthy..."

MAX_WAIT=120
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
  # Check health via curl (simpler than parsing docker compose JSON)
  if curl -sf http://127.0.0.1:8090/health &>/dev/null; then
    break
  fi

  sleep 2
  WAITED=$((WAITED + 2))
  if [ $((WAITED % 10)) -eq 0 ]; then
    info "  Still waiting for server... (${WAITED}s)"
  fi
done

if [ $WAITED -ge $MAX_WAIT ]; then
  fail "Server did not become healthy within ${MAX_WAIT}s"
  fail "Docker logs:"
  docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" logs --tail=50
  exit 1
fi

log "  Server healthy at ${TOTALRECLAW_SERVER_URL}"

# ============================================================================
# Phase 4: Run the pipeline test
# ============================================================================

log "Phase 4: Running pipeline test..."
echo ""

# Run the TypeScript test via tsx
set +e
(cd "$SCRIPT_DIR" && npx tsx "$TEST_FILE")
TEST_EXIT=$?
set -e

echo ""

# ============================================================================
# Phase 5: Results
# ============================================================================

if [ $TEST_EXIT -eq 0 ]; then
  log "========================================="
  log "  All pipeline tests PASSED"
  log "========================================="
else
  fail "========================================="
  fail "  Some pipeline tests FAILED (exit $TEST_EXIT)"
  fail "========================================="
fi

exit $TEST_EXIT
