#!/usr/bin/env bash
# Run ALL billing E2E tests (Journeys A-G + edge cases)
#
# Usage:
#   cd tests/e2e-functional && bash billing-tests/run-all-billing.sh
#   bash billing-tests/run-all-billing.sh --journey=A,D   # run specific journeys

set -euo pipefail
cd "$(dirname "$0")/.."

JOURNEYS="${1:-all}"
FAILED=0
PASSED=0
TOTAL=0

run_test() {
  local name="$1"
  shift
  echo ""
  echo "=========================================="
  echo "  $name"
  echo "=========================================="
  if npx tsx "$@" 2>&1; then
    echo "  => $name: PASS"
  else
    echo "  => $name: FAIL"
    FAILED=$((FAILED + 1))
  fi
  TOTAL=$((TOTAL + 1))
}

# Journey A/B/C via orchestrator
if [[ "$JOURNEYS" == "all" || "$JOURNEYS" == *"A"* || "$JOURNEYS" == *"B"* || "$JOURNEYS" == *"C"* ]]; then
  FILTER=""
  if [[ "$JOURNEYS" != "all" ]]; then
    # Extract A,B,C from the filter
    FILTER_PARTS=""
    for letter in A B C; do
      if [[ "$JOURNEYS" == *"$letter"* ]]; then
        FILTER_PARTS="${FILTER_PARTS:+$FILTER_PARTS,}$letter"
      fi
    done
    if [[ -n "$FILTER_PARTS" ]]; then
      FILTER="--journey=$FILTER_PARTS"
    fi
  fi
  if [[ -n "$FILTER" ]]; then
    run_test "Journeys A/B/C (Free Tier + Stripe + Coinbase)" billing-tests/run-billing-tests.ts "$FILTER"
  else
    run_test "Journeys A/B/C (Free Tier + Stripe + Coinbase)" billing-tests/run-billing-tests.ts
  fi
fi

# Journey D (standalone)
if [[ "$JOURNEYS" == "all" || "$JOURNEYS" == *"D"* ]]; then
  run_test "Journey D (Unauthorized / Attack Scenarios)" billing-tests/journey-d.test.ts
fi

# Journey E (standalone)
if [[ "$JOURNEYS" == "all" || "$JOURNEYS" == *"E"* ]]; then
  run_test "Journey E (Cross-Device Recovery)" billing-tests/journey-e.test.ts
fi

# Journey F (standalone)
if [[ "$JOURNEYS" == "all" || "$JOURNEYS" == *"F"* ]]; then
  run_test "Journey F (Agent-Driven UX)" billing-tests/journey-f.test.ts
fi

# Journey G (standalone)
if [[ "$JOURNEYS" == "all" || "$JOURNEYS" == *"G"* ]]; then
  run_test "Journey G (Relay Pipeline)" billing-tests/journey-g.test.ts
fi

# Edge cases (standalone)
if [[ "$JOURNEYS" == "all" || "$JOURNEYS" == *"X"* ]]; then
  run_test "Cross-Journey Edge Cases" billing-tests/edge-cases.test.ts
fi

PASSED=$((TOTAL - FAILED))

echo ""
echo "=========================================="
echo "  FINAL RESULTS: $PASSED/$TOTAL test suites passed"
if [[ $FAILED -gt 0 ]]; then
  echo "  $FAILED FAILED"
fi
echo "=========================================="

exit $FAILED
