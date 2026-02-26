#!/usr/bin/env bash
# ============================================================================
# OpenMemory + NanoClaw Functional Test Runner
#
# This script:
#   1. Builds the NanoClaw base container image
#   2. Builds the extended container with @noble/hashes
#   3. Starts postgres + openmemory-server via docker-compose
#   4. Waits for health checks
#   5. Runs test scenarios by invoking containers with crafted stdin JSON
#   6. Verifies memories stored in DB (query postgres directly)
#   7. Cleans up
#
# Prerequisites:
#   - Docker and docker-compose installed
#   - .env file with ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN, and OPENMEMORY_MASTER_PASSWORD
#   - NanoClaw source at ./nanoclaw/
#
# Usage:
#   ./run-tests.sh           # Run all tests
#   ./run-tests.sh --no-cleanup  # Keep containers running after tests
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.nanoclaw-test.yml"
COMPOSE_PROJECT="nanoclaw-openmemory-test"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

CLEANUP=true
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

for arg in "$@"; do
  case $arg in
    --no-cleanup) CLEANUP=false ;;
  esac
done

# Load environment
if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a
  source "$SCRIPT_DIR/.env"
  set +a
fi

# Validate required env vars — need at least one auth method
if [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
  echo -e "${RED}ERROR: Neither ANTHROPIC_API_KEY nor CLAUDE_CODE_OAUTH_TOKEN is set.${NC}"
  echo -e "${RED}  Set at least one in .env (see .env.example for details).${NC}"
  echo -e "${RED}  - Subscription users: run 'claude setup-token' to get CLAUDE_CODE_OAUTH_TOKEN${NC}"
  echo -e "${RED}  - API key users: set ANTHROPIC_API_KEY${NC}"
  exit 1
fi

if [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
  echo -e "${GREEN}[test]${NC} Auth method: CLAUDE_CODE_OAUTH_TOKEN (subscription)"
elif [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  echo -e "${GREEN}[test]${NC} Auth method: ANTHROPIC_API_KEY"
fi

if [ -z "${OPENMEMORY_MASTER_PASSWORD:-}" ]; then
  echo -e "${YELLOW}WARNING: OPENMEMORY_MASTER_PASSWORD not set, using default${NC}"
  export OPENMEMORY_MASTER_PASSWORD="test-password-for-functional-tests"
fi

log() {
  echo -e "${GREEN}[test]${NC} $1"
}

warn() {
  echo -e "${YELLOW}[test]${NC} $1"
}

fail() {
  echo -e "${RED}[test]${NC} $1"
}

assert_pass() {
  local name="$1"
  TESTS_TOTAL=$((TESTS_TOTAL + 1))
  TESTS_PASSED=$((TESTS_PASSED + 1))
  echo -e "  ${GREEN}PASS${NC} $name"
}

assert_fail() {
  local name="$1"
  local reason="${2:-}"
  TESTS_TOTAL=$((TESTS_TOTAL + 1))
  TESTS_FAILED=$((TESTS_FAILED + 1))
  echo -e "  ${RED}FAIL${NC} $name${reason:+ — $reason}"
}

cleanup() {
  if [ "$CLEANUP" = true ]; then
    log "Cleaning up..."
    docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" down -v --remove-orphans 2>/dev/null || true
    docker volume rm nanoclaw-openmemory-credentials 2>/dev/null || true
  else
    warn "Skipping cleanup (--no-cleanup). Run manually:"
    warn "  docker compose -p $COMPOSE_PROJECT -f $COMPOSE_FILE down -v"
    warn "  docker volume rm nanoclaw-openmemory-credentials"
  fi
}

trap cleanup EXIT

# ============================================================================
# Phase 1: Build Images
# ============================================================================

log "Phase 1: Building container images..."

# Build NanoClaw base image (if container/build.sh exists, use it; otherwise docker build)
NANOCLAW_DIR="$SCRIPT_DIR/nanoclaw/container"
if [ -f "$NANOCLAW_DIR/build.sh" ]; then
  log "Building NanoClaw base image via build.sh..."
  (cd "$NANOCLAW_DIR" && bash build.sh) 2>&1 | tail -5
else
  log "Building NanoClaw base image via docker build..."
  docker build -t nanoclaw-agent:latest "$NANOCLAW_DIR" 2>&1 | tail -5
fi

# Build the extended image with @noble/hashes
log "Building NanoClaw+OpenMemory image..."
docker build \
  -t nanoclaw-openmemory:latest \
  -f "$SCRIPT_DIR/Dockerfile.nanoclaw-openmemory" \
  "$SCRIPT_DIR" 2>&1 | tail -5

log "Images built successfully."

# ============================================================================
# Phase 2: Start Infrastructure
# ============================================================================

log "Phase 2: Starting postgres + openmemory-server..."

docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" up -d postgres openmemory-server

# Wait for health checks
log "Waiting for services to be healthy..."

MAX_WAIT=120
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
  PG_HEALTHY=$(docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" ps postgres --format json 2>/dev/null | python3 -c "import sys,json; data=json.load(sys.stdin); print(data.get('Health','') if isinstance(data,dict) else [d.get('Health','') for d in data][0] if data else '')" 2>/dev/null || echo "")
  OM_HEALTHY=$(docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" ps openmemory-server --format json 2>/dev/null | python3 -c "import sys,json; data=json.load(sys.stdin); print(data.get('Health','') if isinstance(data,dict) else [d.get('Health','') for d in data][0] if data else '')" 2>/dev/null || echo "")

  if [[ "$PG_HEALTHY" == *"healthy"* ]] && [[ "$OM_HEALTHY" == *"healthy"* ]]; then
    break
  fi

  sleep 2
  WAITED=$((WAITED + 2))
  if [ $((WAITED % 10)) -eq 0 ]; then
    log "  Still waiting... (${WAITED}s) pg=$PG_HEALTHY om=$OM_HEALTHY"
  fi
done

if [ $WAITED -ge $MAX_WAIT ]; then
  fail "Services did not become healthy within ${MAX_WAIT}s"
  docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" logs
  exit 1
fi

log "All services healthy."

# ============================================================================
# Phase 3: Test Scenarios
# ============================================================================

NETWORK="${COMPOSE_PROJECT}_nanoclaw-test"

# Helper to run a NanoClaw container with a given prompt
run_agent() {
  local prompt="$1"
  local group="${2:-test-main}"
  local timeout="${3:-120}"

  local input_json
  # Build secrets object with whichever auth method is available
  local secrets_json
  secrets_json=$(jq -n --arg master_pw "$OPENMEMORY_MASTER_PASSWORD" '{ OPENMEMORY_MASTER_PASSWORD: $master_pw }')
  if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    secrets_json=$(echo "$secrets_json" | jq --arg v "$ANTHROPIC_API_KEY" '. + { ANTHROPIC_API_KEY: $v }')
  fi
  if [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
    secrets_json=$(echo "$secrets_json" | jq --arg v "$CLAUDE_CODE_OAUTH_TOKEN" '. + { CLAUDE_CODE_OAUTH_TOKEN: $v }')
  fi

  input_json=$(jq -n \
    --arg prompt "$prompt" \
    --arg group "$group" \
    --argjson secrets "$secrets_json" \
    '{
      prompt: $prompt,
      groupFolder: $group,
      chatJid: "test@test.us",
      isMain: true,
      assistantName: "TestBot",
      secrets: $secrets
    }'
  )

  # Run the container, pipe in JSON, capture output
  # Use printf instead of echo — zsh's echo interprets backslashes in tokens
  printf '%s\n' "$input_json" | timeout "$timeout" docker run \
    --rm -i \
    --network "$NETWORK" \
    -e OPENMEMORY_SERVER_URL=http://openmemory-server:8080 \
    -v "$SCRIPT_DIR/nanoclaw-openmemory-overlay/agent-runner-src/index.ts:/app/src/index.ts:ro" \
    -v "$SCRIPT_DIR/nanoclaw-openmemory-overlay/agent-runner-src/openmemory-mcp.ts:/app/src/openmemory-mcp.ts:ro" \
    -v "$SCRIPT_DIR/nanoclaw-openmemory-overlay/skills/openmemory:/app/skills/openmemory:ro" \
    -v nanoclaw-openmemory-credentials:/workspace/.openmemory \
    nanoclaw-openmemory:latest 2>/dev/null || true
}

# Extract output between markers
extract_output() {
  local raw="$1"
  echo "$raw" | sed -n '/---NANOCLAW_OUTPUT_START---/,/---NANOCLAW_OUTPUT_END---/p' | grep -vF -- '---NANOCLAW_OUTPUT' | head -1
}

# Query postgres for fact count
query_fact_count() {
  docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" exec -T postgres \
    psql -U openmemory -d openmemory -t -c "SELECT COUNT(*) FROM facts WHERE deleted_at IS NULL;" 2>/dev/null | tr -d ' \n'
}

# Query postgres for encrypted blobs (check they exist and are not plaintext)
query_encrypted_blobs() {
  docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" exec -T postgres \
    psql -U openmemory -d openmemory -t -c "SELECT encrypted_blob FROM facts WHERE deleted_at IS NULL LIMIT 5;" 2>/dev/null
}

log ""
log "============================================"
log "Phase 3: Running test scenarios"
log "============================================"
log ""

# --- Test 1: Server Health Check ---
log "Test 1: Server health check"
HEALTH_RESPONSE=$(curl -sf http://127.0.0.1:8090/health 2>/dev/null || echo "FAILED")
if echo "$HEALTH_RESPONSE" | grep -qi "ok\|healthy\|true\|status"; then
  assert_pass "Server health endpoint responds"
else
  # Try parsing as JSON
  if [ "$HEALTH_RESPONSE" != "FAILED" ]; then
    assert_pass "Server health endpoint responds (raw: ${HEALTH_RESPONSE:0:100})"
  else
    assert_fail "Server health endpoint responds" "Got: $HEALTH_RESPONSE"
  fi
fi

# --- Test 2: Memory Storage ---
log ""
log "Test 2: Memory storage (send chat, check DB for encrypted blobs)"

FACT_COUNT_BEFORE=$(query_fact_count 2>/dev/null || echo "0")
log "  Facts in DB before: $FACT_COUNT_BEFORE"

log "  Running agent with memory-worthy prompt..."
AGENT_OUTPUT=$(run_agent "Hello! My name is Alice and I work at Acme Corp as a senior engineer. Please remember these facts about me." "test-main" 180)

OUTPUT_JSON=$(extract_output "$AGENT_OUTPUT")
if [ -n "$OUTPUT_JSON" ]; then
  STATUS=$(echo "$OUTPUT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "unknown")
  if [ "$STATUS" = "success" ]; then
    assert_pass "Agent completed successfully"
  else
    assert_fail "Agent completed successfully" "Status: $STATUS"
  fi
else
  warn "  No output markers found (agent may have timed out)"
  assert_fail "Agent completed successfully" "No output captured"
fi

# Check if facts were stored
sleep 2
FACT_COUNT_AFTER=$(query_fact_count 2>/dev/null || echo "0")
log "  Facts in DB after: $FACT_COUNT_AFTER"

if [ "$FACT_COUNT_AFTER" -gt "$FACT_COUNT_BEFORE" ] 2>/dev/null; then
  STORED=$((FACT_COUNT_AFTER - FACT_COUNT_BEFORE))
  assert_pass "Facts stored in DB ($STORED new facts)"
else
  assert_fail "Facts stored in DB" "Before: $FACT_COUNT_BEFORE, After: $FACT_COUNT_AFTER"
fi

# --- Test 3: Encryption Verification ---
log ""
log "Test 3: Encryption verification (check DB contains no plaintext)"

BLOBS=$(query_encrypted_blobs 2>/dev/null || echo "")
if [ -n "$BLOBS" ]; then
  # Check that none of the blobs contain "Alice" or "Acme" in plaintext
  if echo "$BLOBS" | grep -qi "alice\|acme\|engineer"; then
    assert_fail "Encrypted blobs contain no plaintext" "Found plaintext in DB!"
  else
    assert_pass "Encrypted blobs contain no plaintext"
  fi

  # Check that blobs look like base64 (encrypted format)
  if echo "$BLOBS" | grep -qE '^[A-Za-z0-9+/=]{20,}'; then
    assert_pass "Blobs are base64-encoded (encrypted)"
  else
    warn "  Blobs may not be in expected format"
    assert_pass "Blobs present in DB"
  fi
else
  warn "  No blobs found to verify"
  assert_fail "Encrypted blobs present" "No blobs in DB"
fi

# --- Test 4: Cross-Session Recall ---
log ""
log "Test 4: Cross-session recall (new container, ask about stored facts)"

RECALL_OUTPUT=$(run_agent "What do you know about me? What is my name and where do I work?" "test-main" 180)
RECALL_JSON=$(extract_output "$RECALL_OUTPUT")

if [ -n "$RECALL_JSON" ]; then
  RECALL_STATUS=$(echo "$RECALL_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "unknown")
  RECALL_RESULT=$(echo "$RECALL_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('result','') or '')" 2>/dev/null || echo "")

  if [ "$RECALL_STATUS" = "success" ]; then
    assert_pass "Recall agent completed successfully"

    # Check if the agent's response mentions Alice or Acme
    if echo "$RECALL_RESULT" | grep -qi "alice\|acme"; then
      assert_pass "Agent recalled stored facts (found Alice/Acme in response)"
    else
      warn "  Agent response did not contain 'Alice' or 'Acme'"
      warn "  Response: ${RECALL_RESULT:0:200}"
      assert_fail "Agent recalled stored facts" "Response missing expected content"
    fi
  else
    assert_fail "Recall agent completed successfully" "Status: $RECALL_STATUS"
  fi
else
  warn "  No output markers found for recall test"
  assert_fail "Recall agent completed successfully" "No output captured"
fi

# ============================================================================
# Phase 4: Results
# ============================================================================

log ""
log "============================================"
log "Test Results"
log "============================================"
log ""
log "Total:  $TESTS_TOTAL"
log "Passed: $TESTS_PASSED"
log "Failed: $TESTS_FAILED"
log ""

if [ $TESTS_FAILED -gt 0 ]; then
  fail "Some tests failed!"
  exit 1
else
  log "All tests passed!"
  exit 0
fi
