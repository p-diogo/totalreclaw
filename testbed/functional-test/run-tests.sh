#!/bin/bash

# Functional Test Runner for OpenMemory + OpenClaw Integration
# Usage: ./run-tests.sh [--skip-cleanup] [--verbose]

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.functional-test.yml"
RESULTS_DIR="${SCRIPT_DIR}/test-results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${RESULTS_DIR}/test-run-${TIMESTAMP}.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
SKIP_CLEANUP=false
VERBOSE=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-cleanup)
            SKIP_CLEANUP=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--skip-cleanup] [--verbose]"
            exit 1
            ;;
    esac
done

# Logging functions
log() {
    local level=$1
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "[${timestamp}] [${level}] ${message}" >> "${LOG_FILE}"
    if [[ "${VERBOSE}" == true ]] || [[ "${level}" != "DEBUG" ]]; then
        case ${level} in
            INFO)  echo -e "${BLUE}[INFO]${NC} ${message}" ;;
            SUCCESS) echo -e "${GREEN}[SUCCESS]${NC} ${message}" ;;
            WARNING) echo -e "${YELLOW}[WARNING]${NC} ${message}" ;;
            ERROR) echo -e "${RED}[ERROR]${NC} ${message}" ;;
            DEBUG) echo -e "${DEBUG}[DEBUG]${NC} ${message}" ;;
        esac
    fi
}

info() { log "INFO" "$@"; }
success() { log "SUCCESS" "$@"; }
warn() { log "WARNING" "$@"; }
error() { log "ERROR" "$@"; exit 1; }
debug() { log "DEBUG" "$@"; }

# Create results directory
mkdir -p "${RESULTS_DIR}"

info "Starting Functional Test Run"
info "Log file: ${LOG_FILE}"

# ============================================
# Prerequisite Checks
# ============================================
info "Checking prerequisites..."

# Check Docker
if ! command -v docker &> /dev/null; then
    error "Docker is not installed. Please install Docker first."
fi

if ! docker info &> /dev/null; then
    error "Docker daemon is not running. Please start Docker."
fi

# Check Docker Compose
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    error "Docker Compose is not installed. Please install Docker Compose."
fi

# Use docker compose (v2) or docker-compose (v1)
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi
debug "Using: ${DOCKER_COMPOSE}"

# Check for OpenClaw repository
if [[ ! -d "${SCRIPT_DIR}/openclaw" ]]; then
    warn "OpenClaw repository not found at ${SCRIPT_DIR}/openclaw"
    echo ""
    echo "Please clone the OpenClaw repository:"
    echo "  cd ${SCRIPT_DIR}"
    echo "  git clone https://github.com/openclaw/openclaw.git openclaw"
    echo ""
    echo "If the repository is private or at a different location, adjust the URL."
    error "OpenClaw repository required for functional testing"
fi

# Check for OpenMemory server Dockerfile
if [[ ! -f "${SCRIPT_DIR}/../../server/Dockerfile" ]]; then
    warn "OpenMemory server Dockerfile not found"
    warn "Expected at: ${SCRIPT_DIR}/../../server/Dockerfile"
    error "OpenMemory server Dockerfile required"
fi

# Check for ZAI_API_KEY
if [[ -z "${ZAI_API_KEY}" ]]; then
    warn "ZAI_API_KEY environment variable is not set"
    echo ""
    echo "Please set the API key:"
    echo "  export ZAI_API_KEY=your_api_key_here"
    echo ""
    read -p "Enter ZAI_API_KEY (or press Enter to skip LLM tests): " api_key
    if [[ -n "${api_key}" ]]; then
        export ZAI_API_KEY="${api_key}"
    else
        warn "Running without API key - LLM-dependent tests will be skipped"
    fi
fi

success "Prerequisites checked"

# ============================================
# Start Services
# ============================================
info "Starting Docker services..."

cd "${SCRIPT_DIR}"

# Cleanup any existing containers
${DOCKER_COMPOSE} -f "${COMPOSE_FILE}" --profile functional-test down --remove-orphans 2>/dev/null || true

# Start services
${DOCKER_COMPOSE} -f "${COMPOSE_FILE}" --profile functional-test up -d

info "Waiting for services to be healthy..."

# Wait for PostgreSQL (max 30s)
info "Waiting for PostgreSQL..."
for i in {1..30}; do
    if ${DOCKER_COMPOSE} -f "${COMPOSE_FILE}" exec -T postgres pg_isready -U openmemory -d openmemory &>/dev/null; then
        success "PostgreSQL is ready"
        break
    fi
    if [[ $i -eq 30 ]]; then
        error "PostgreSQL failed to start within 30 seconds"
    fi
    sleep 1
done

# Wait for OpenMemory Server (max 60s)
info "Waiting for OpenMemory server..."
for i in {1..60}; do
    if curl -sf http://127.0.0.1:8080/health &>/dev/null; then
        success "OpenMemory server is ready"
        break
    fi
    if [[ $i -eq 60 ]]; then
        error "OpenMemory server failed to start within 60 seconds"
    fi
    sleep 1
done

# Wait for OpenClaw (max 90s)
info "Waiting for OpenClaw..."
for i in {1..90}; do
    if curl -sf http://127.0.0.1:8081/health &>/dev/null; then
        success "OpenClaw is ready"
        break
    fi
    if [[ $i -eq 90 ]]; then
        error "OpenClaw failed to start within 90 seconds"
    fi
    sleep 1
done

success "All services are healthy!"

# ============================================
# Run Test Scenarios
# ============================================
info "Running test scenarios..."

TESTS_PASSED=0
TESTS_FAILED=0

# Test 1: Health Check
info "Test 1: Health Check"
if curl -sf http://127.0.0.1:8080/health | grep -q "ok\|healthy\|UP"; then
    success "  OpenMemory health check passed"
    ((TESTS_PASSED++))
else
    warn "  OpenMemory health check failed"
    ((TESTS_FAILED++))
fi

if curl -sf http://127.0.0.1:8081/health | grep -q "ok\|healthy\|UP"; then
    success "  OpenClaw health check passed"
    ((TESTS_PASSED++))
else
    warn "  OpenClaw health check failed"
    ((TESTS_FAILED++))
fi

# Test 2: Basic Conversation
info "Test 2: Basic Conversation"
TEST_RESPONSE=$(curl -s -X POST http://127.0.0.1:8081/api/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "Hello, my name is Test User and I live in Test City.", "session_id": "test-session-1"}' 2>/dev/null || echo "")

if [[ -n "${TEST_RESPONSE}" && "${TEST_RESPONSE}" != *"error"* ]]; then
    success "  Basic conversation test passed"
    echo "${TEST_RESPONSE}" > "${RESULTS_DIR}/conversation-response-${TIMESTAMP}.json"
    ((TESTS_PASSED++))
else
    warn "  Basic conversation test failed"
    echo "${TEST_RESPONSE}" > "${RESULTS_DIR}/conversation-error-${TIMESTAMP}.json"
    ((TESTS_FAILED++))
fi

# Test 3: Memory Storage (if API key available)
if [[ -n "${ZAI_API_KEY}" ]]; then
    info "Test 3: Memory Storage"

    # Send a message with personal information
    curl -s -X POST http://127.0.0.1:8081/api/chat \
        -H "Content-Type: application/json" \
        -d '{"message": "Remember that my favorite color is blue and I have a cat named Whiskers.", "session_id": "test-session-2"}' \
        > "${RESULTS_DIR}/memory-store-response-${TIMESTAMP}.json" 2>/dev/null || true

    sleep 2  # Allow time for processing

    # Query OpenMemory directly to check if memory was stored
    MEMORY_CHECK=$(curl -s http://127.0.0.1:8080/api/memories?query=cat%20whiskers 2>/dev/null || echo "{}")

    if [[ "${MEMORY_CHECK}" != *"error"* && "${MEMORY_CHECK}" != "{}" ]]; then
        success "  Memory storage test passed"
        echo "${MEMORY_CHECK}" > "${RESULTS_DIR}/memory-check-${TIMESTAMP}.json"
        ((TESTS_PASSED++))
    else
        warn "  Memory storage test failed or returned empty"
        ((TESTS_FAILED++))
    fi

    # Test 4: Memory Retrieval
    info "Test 4: Memory Retrieval"

    RETRIEVAL_RESPONSE=$(curl -s -X POST http://127.0.0.1:8081/api/chat \
        -H "Content-Type: application/json" \
        -d '{"message": "What is my favorite color?", "session_id": "test-session-2"}' 2>/dev/null || echo "")

    if [[ "${RETRIEVAL_RESPONSE}" == *"blue"* ]]; then
        success "  Memory retrieval test passed (found 'blue' in response)"
        ((TESTS_PASSED++))
    else
        warn "  Memory retrieval test failed (expected 'blue' in response)"
        echo "${RETRIEVAL_RESPONSE}" > "${RESULTS_DIR}/retrieval-response-${TIMESTAMP}.json"
        ((TESTS_FAILED++))
    fi
else
    warn "  Skipping LLM-dependent tests (no API key)"
fi

# ============================================
# Collect Logs
# ============================================
info "Collecting logs..."

${DOCKER_COMPOSE} -f "${COMPOSE_FILE}" logs openmemory-server > "${RESULTS_DIR}/openmemory-logs-${TIMESTAMP}.txt" 2>&1 || true
${DOCKER_COMPOSE} -f "${COMPOSE_FILE}" logs openclaw-test > "${RESULTS_DIR}/openclaw-logs-${TIMESTAMP}.txt" 2>&1 || true
${DOCKER_COMPOSE} -f "${COMPOSE_FILE}" logs postgres > "${RESULTS_DIR}/postgres-logs-${TIMESTAMP}.txt" 2>&1 || true

# ============================================
# Summary
# ============================================
echo ""
echo "========================================"
info "Test Run Summary"
echo "========================================"
echo ""
echo "  Tests Passed: ${TESTS_PASSED}"
echo "  Tests Failed: ${TESTS_FAILED}"
echo ""
echo "  Results saved to: ${RESULTS_DIR}"
echo "  Log file: ${LOG_FILE}"
echo ""

if [[ ${TESTS_FAILED} -eq 0 ]]; then
    success "All tests passed!"
    EXIT_CODE=0
else
    warn "Some tests failed. Check logs for details."
    EXIT_CODE=1
fi

# ============================================
# Cleanup
# ============================================
if [[ "${SKIP_CLEANUP}" == true ]]; then
    info "Skipping cleanup (--skip-cleanup flag set)"
    info "To manually cleanup, run:"
    echo "  ${DOCKER_COMPOSE} -f ${COMPOSE_FILE} --profile functional-test down"
else
    info "Cleaning up..."
    ${DOCKER_COMPOSE} -f "${COMPOSE_FILE}" --profile functional-test down
    success "Cleanup complete"
fi

echo ""
info "Test run complete"
exit ${EXIT_CODE}
