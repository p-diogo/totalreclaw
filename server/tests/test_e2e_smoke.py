#!/usr/bin/env python3
"""
TotalReclaw Server — End-to-End Smoke Test

Tests the full API flow against a running Docker instance.

Usage:
    # Standalone
    SERVER_URL=http://localhost:8080 python tests/test_e2e_smoke.py

    # With pytest
    SERVER_URL=http://localhost:8080 pytest tests/test_e2e_smoke.py -v

Requirements:
    pip install requests

Environment variables:
    SERVER_URL  — Base URL of the TotalReclaw server (default: http://localhost:8080)
"""
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:8080").rstrip("/")

# Test-scoped state shared across steps
_state: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sha256_hex(data: bytes) -> str:
    """Return the hex-encoded SHA-256 digest of *data*."""
    return hashlib.sha256(data).hexdigest()


def blind_index(word: str) -> str:
    """
    Compute a blind index for a keyword.

    In production these are SHA-256(HMAC-key || LSH-bucket), but for smoke
    testing a simple SHA-256 of the lowered word suffices.
    """
    return sha256_hex(word.lower().encode("utf-8"))


def make_auth_headers(auth_key_hex: str) -> Dict[str, str]:
    """Build the Authorization header expected by the server."""
    return {"Authorization": f"Bearer {auth_key_hex}"}


def pp(label: str, obj: Any) -> None:
    """Pretty-print a labelled JSON-serializable object to stderr."""
    print(f"  {label}: {json.dumps(obj, indent=2, default=str)}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

class TestResult:
    def __init__(self):
        self.passed: List[str] = []
        self.failed: List[Tuple[str, str]] = []

    def record(self, name: str, ok: bool, detail: str = ""):
        if ok:
            self.passed.append(name)
            print(f"  PASS  {name}")
        else:
            self.failed.append((name, detail))
            print(f"  FAIL  {name}: {detail}")

    @property
    def all_passed(self) -> bool:
        return len(self.failed) == 0

    def summary(self) -> str:
        total = len(self.passed) + len(self.failed)
        lines = [
            "",
            "=" * 60,
            f"Results: {len(self.passed)}/{total} passed",
        ]
        if self.failed:
            lines.append("")
            lines.append("Failures:")
            for name, detail in self.failed:
                lines.append(f"  - {name}: {detail}")
        lines.append("=" * 60)
        return "\n".join(lines)


results = TestResult()


# ---------------------------------------------------------------------------
# Test steps
# ---------------------------------------------------------------------------

def test_health_check():
    """Step 1 — GET /health, verify status=healthy."""
    r = requests.get(f"{SERVER_URL}/health", timeout=10)
    data = r.json()

    ok = r.status_code == 200 and data.get("status") == "healthy"
    results.record(
        "health_check",
        ok,
        f"status_code={r.status_code}, body={data}" if not ok else "",
    )
    if not ok:
        raise SystemExit("Server is not healthy — aborting remaining tests")


def test_register():
    """Step 2 — POST /v1/register, create a new user."""
    # Generate a random 32-byte auth key (simulates HKDF output on client)
    auth_key = os.urandom(32)
    auth_key_hex = auth_key.hex()
    auth_key_hash_hex = sha256_hex(auth_key)
    salt = os.urandom(32)
    salt_hex = salt.hex()

    payload = {
        "auth_key_hash": auth_key_hash_hex,
        "salt": salt_hex,
    }
    r = requests.post(f"{SERVER_URL}/v1/register", json=payload, timeout=10)
    data = r.json()

    ok = r.status_code == 200 and data.get("success") is True and data.get("user_id") is not None
    results.record(
        "register",
        ok,
        f"status_code={r.status_code}, body={data}" if not ok else "",
    )

    # Persist for later steps
    _state["auth_key"] = auth_key
    _state["auth_key_hex"] = auth_key_hex
    _state["auth_key_hash_hex"] = auth_key_hash_hex
    _state["salt_hex"] = salt_hex
    _state["user_id"] = data.get("user_id", "")
    _state["headers"] = make_auth_headers(auth_key_hex)


def test_store_facts():
    """Step 3 — POST /v1/store with 2 facts."""
    user_id = _state["user_id"]
    headers = _state["headers"]

    # Build blind indices from real words
    words_fact1 = ["coffee", "prefer", "morning"]
    words_fact2 = ["python", "project", "backend"]
    indices_1 = [blind_index(w) for w in words_fact1]
    indices_2 = [blind_index(w) for w in words_fact2]

    fact1_id = str(uuid.uuid4())
    fact2_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    # Dummy encrypted blobs (hex-encoded)
    blob1 = os.urandom(64).hex()
    blob2 = os.urandom(64).hex()

    # Content fingerprint for fact 1 (used later in dedup test)
    content_fp_1 = sha256_hex(b"fact1-unique-content")

    facts = [
        {
            "id": fact1_id,
            "timestamp": now_iso,
            "encrypted_blob": blob1,
            "blind_indices": indices_1,
            "decay_score": 0.9,
            "is_active": True,
            "version": 1,
            "source": "conversation",
            "content_fp": content_fp_1,
            "agent_id": "smoke-test-agent",
        },
        {
            "id": fact2_id,
            "timestamp": now_iso,
            "encrypted_blob": blob2,
            "blind_indices": indices_2,
            "decay_score": 0.8,
            "is_active": True,
            "version": 1,
            "source": "conversation",
            "agent_id": "smoke-test-agent",
        },
    ]

    payload = {"user_id": user_id, "facts": facts}
    r = requests.post(f"{SERVER_URL}/v1/store", json=payload, headers=headers, timeout=10)
    data = r.json()

    ids_ok = set(data.get("ids", [])) == {fact1_id, fact2_id}
    ok = r.status_code == 200 and data.get("success") is True and ids_ok
    detail = ""
    if not ok:
        detail = f"status_code={r.status_code}, body={data}"
    results.record("store_facts", ok, detail)

    # Persist for later steps
    _state["fact1_id"] = fact1_id
    _state["fact2_id"] = fact2_id
    _state["blob1"] = blob1
    _state["blob2"] = blob2
    _state["indices_1"] = indices_1
    _state["indices_2"] = indices_2
    _state["content_fp_1"] = content_fp_1


def test_search():
    """Step 4 — POST /v1/search, verify stored facts are returned."""
    user_id = _state["user_id"]
    headers = _state["headers"]

    # Search using trapdoors that match fact 1's blind indices ("coffee")
    trapdoors = [blind_index("coffee")]

    payload = {
        "user_id": user_id,
        "trapdoors": trapdoors,
        "max_candidates": 100,
    }
    r = requests.post(f"{SERVER_URL}/v1/search", json=payload, headers=headers, timeout=10)
    data = r.json()

    search_results = data.get("results") or []
    found_ids = {sr["fact_id"] for sr in search_results}

    # fact1 should be found (it has the "coffee" blind index)
    fact1_found = _state["fact1_id"] in found_ids
    # verify encrypted_blob is present in the result for fact1
    blob_present = any(
        sr.get("encrypted_blob") == _state["blob1"]
        for sr in search_results
        if sr["fact_id"] == _state["fact1_id"]
    )

    ok = (
        r.status_code == 200
        and data.get("success") is True
        and fact1_found
        and blob_present
    )
    detail = ""
    if not ok:
        detail = (
            f"status_code={r.status_code}, fact1_found={fact1_found}, "
            f"blob_present={blob_present}, body={data}"
        )
    results.record("search", ok, detail)


def test_search_multiple_trapdoors():
    """Step 4b — Search with trapdoors matching fact 2."""
    user_id = _state["user_id"]
    headers = _state["headers"]

    trapdoors = [blind_index("python"), blind_index("project")]
    payload = {
        "user_id": user_id,
        "trapdoors": trapdoors,
        "max_candidates": 100,
    }
    r = requests.post(f"{SERVER_URL}/v1/search", json=payload, headers=headers, timeout=10)
    data = r.json()

    search_results = data.get("results") or []
    found_ids = {sr["fact_id"] for sr in search_results}
    fact2_found = _state["fact2_id"] in found_ids

    ok = r.status_code == 200 and data.get("success") is True and fact2_found
    detail = ""
    if not ok:
        detail = f"status_code={r.status_code}, fact2_found={fact2_found}, body={data}"
    results.record("search_multiple_trapdoors", ok, detail)


def test_dedup():
    """Step 5 — POST /v1/store with same content_fp, verify duplicate detection."""
    user_id = _state["user_id"]
    headers = _state["headers"]

    dup_fact_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    facts = [
        {
            "id": dup_fact_id,
            "timestamp": now_iso,
            "encrypted_blob": os.urandom(32).hex(),
            "blind_indices": [blind_index("coffee")],
            "decay_score": 0.5,
            "is_active": True,
            "version": 1,
            "source": "conversation",
            "content_fp": _state["content_fp_1"],  # same fingerprint as fact 1
            "agent_id": "smoke-test-agent",
        }
    ]

    payload = {"user_id": user_id, "facts": facts}
    r = requests.post(f"{SERVER_URL}/v1/store", json=payload, headers=headers, timeout=10)
    data = r.json()

    duplicate_ids = data.get("duplicate_ids") or []
    stored_ids = data.get("ids") or []

    # The duplicate fact should NOT be in stored_ids
    # And duplicate_ids should reference the original fact1's id
    dup_detected = len(duplicate_ids) > 0
    not_stored = dup_fact_id not in stored_ids

    ok = r.status_code == 200 and data.get("success") is True and dup_detected and not_stored
    detail = ""
    if not ok:
        detail = (
            f"status_code={r.status_code}, dup_detected={dup_detected}, "
            f"not_stored={not_stored}, body={data}"
        )
    results.record("dedup", ok, detail)


def test_export():
    """Step 6 — GET /v1/export, verify facts are returned."""
    headers = _state["headers"]

    r = requests.get(
        f"{SERVER_URL}/v1/export",
        headers=headers,
        params={"limit": 10},
        timeout=10,
    )
    data = r.json()

    facts = data.get("facts") or []
    fact_ids = {f["id"] for f in facts}

    # Both stored facts should appear in export
    has_fact1 = _state["fact1_id"] in fact_ids
    has_fact2 = _state["fact2_id"] in fact_ids

    ok = (
        r.status_code == 200
        and data.get("success") is True
        and has_fact1
        and has_fact2
    )
    detail = ""
    if not ok:
        detail = (
            f"status_code={r.status_code}, has_fact1={has_fact1}, "
            f"has_fact2={has_fact2}, body={data}"
        )
    results.record("export", ok, detail)

    # Test cursor-based pagination: request with limit=1 to get a cursor
    r2 = requests.get(
        f"{SERVER_URL}/v1/export",
        headers=headers,
        params={"limit": 1},
        timeout=10,
    )
    data2 = r2.json()
    page1_facts = data2.get("facts") or []
    cursor = data2.get("cursor")
    has_more = data2.get("has_more", False)

    # With 2 facts and limit=1, we should get has_more=True and a cursor
    pagination_ok = (
        r2.status_code == 200
        and data2.get("success") is True
        and len(page1_facts) == 1
        and has_more is True
        and cursor is not None
    )
    results.record("export_pagination", pagination_ok,
                    f"page1_count={len(page1_facts)}, has_more={has_more}, cursor={cursor}" if not pagination_ok else "")

    if pagination_ok and cursor:
        # Fetch page 2 using cursor
        r3 = requests.get(
            f"{SERVER_URL}/v1/export",
            headers=headers,
            params={"limit": 1, "cursor": cursor},
            timeout=10,
        )
        data3 = r3.json()
        page2_facts = data3.get("facts") or []
        page2_ok = (
            r3.status_code == 200
            and data3.get("success") is True
            and len(page2_facts) >= 1
        )
        # Ensure page 2 has different fact than page 1
        if page2_ok and page1_facts and page2_facts:
            page2_ok = page1_facts[0]["id"] != page2_facts[0]["id"]
        results.record("export_pagination_page2", page2_ok,
                        f"page2_count={len(page2_facts)}, body={data3}" if not page2_ok else "")


def test_sync():
    """Step 7 — GET /v1/sync with since_sequence=0."""
    headers = _state["headers"]

    r = requests.get(
        f"{SERVER_URL}/v1/sync",
        headers=headers,
        params={"since_sequence": 0, "limit": 100},
        timeout=10,
    )
    data = r.json()

    facts = data.get("facts") or []
    fact_ids = {f["id"] for f in facts}
    latest_sequence = data.get("latest_sequence", 0)

    has_fact1 = _state["fact1_id"] in fact_ids
    has_fact2 = _state["fact2_id"] in fact_ids
    # Check sequence_ids are present
    has_sequence_ids = all(f.get("sequence_id") is not None for f in facts)

    ok = (
        r.status_code == 200
        and data.get("success") is True
        and has_fact1
        and has_fact2
        and has_sequence_ids
        and latest_sequence > 0
    )
    detail = ""
    if not ok:
        detail = (
            f"status_code={r.status_code}, has_fact1={has_fact1}, has_fact2={has_fact2}, "
            f"has_seq_ids={has_sequence_ids}, latest_seq={latest_sequence}, body={data}"
        )
    results.record("sync", ok, detail)


def test_delete_fact():
    """Step 8 — DELETE /v1/facts/{fact_id}, then verify search no longer returns it."""
    headers = _state["headers"]
    fact1_id = _state["fact1_id"]

    # Delete fact 1
    r = requests.delete(
        f"{SERVER_URL}/v1/facts/{fact1_id}",
        headers=headers,
        timeout=10,
    )
    data = r.json()

    delete_ok = r.status_code == 200 and data.get("success") is True
    results.record("delete_fact", delete_ok,
                    f"status_code={r.status_code}, body={data}" if not delete_ok else "")

    # Verify deleted fact is no longer returned by search
    user_id = _state["user_id"]
    trapdoors = [blind_index("coffee")]
    payload = {
        "user_id": user_id,
        "trapdoors": trapdoors,
        "max_candidates": 100,
    }
    r2 = requests.post(f"{SERVER_URL}/v1/search", json=payload, headers=headers, timeout=10)
    data2 = r2.json()
    search_results = data2.get("results") or []
    found_ids = {sr["fact_id"] for sr in search_results}

    not_found = fact1_id not in found_ids
    search_after_delete_ok = r2.status_code == 200 and data2.get("success") is True and not_found
    results.record(
        "search_after_delete",
        search_after_delete_ok,
        f"fact1 still in results: found_ids={found_ids}" if not search_after_delete_ok else "",
    )


def test_delete_account():
    """Step 9 — DELETE /v1/account, then verify subsequent auth fails."""
    headers = _state["headers"]

    r = requests.delete(f"{SERVER_URL}/v1/account", headers=headers, timeout=10)
    data = r.json()

    ok = r.status_code == 200 and data.get("success") is True
    results.record("delete_account", ok,
                    f"status_code={r.status_code}, body={data}" if not ok else "")

    # Verify subsequent authenticated request fails
    r2 = requests.get(
        f"{SERVER_URL}/v1/export",
        headers=headers,
        params={"limit": 1},
        timeout=10,
    )

    # After account deletion, auth should fail (401)
    auth_fails = r2.status_code == 401
    results.record(
        "auth_after_account_deletion",
        auth_fails,
        f"expected 401, got status_code={r2.status_code}, body={r2.text}" if not auth_fails else "",
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

ALL_STEPS = [
    test_health_check,
    test_register,
    test_store_facts,
    test_search,
    test_search_multiple_trapdoors,
    test_dedup,
    test_export,
    test_sync,
    test_delete_fact,
    test_delete_account,
]


def run_all():
    """Execute all test steps sequentially."""
    print(f"\nTotalReclaw E2E Smoke Test")
    print(f"Server: {SERVER_URL}")
    print("-" * 60)

    for step_fn in ALL_STEPS:
        try:
            step_fn()
        except SystemExit:
            # Health check failed — abort
            break
        except requests.ConnectionError as e:
            results.record(step_fn.__name__, False, f"Connection error: {e}")
            break
        except Exception as e:
            results.record(step_fn.__name__, False, f"Unexpected error: {e}")

    print(results.summary())
    return 0 if results.all_passed else 1


# ---------------------------------------------------------------------------
# pytest compatibility — each step is also a standalone test function
# ---------------------------------------------------------------------------

def _make_pytest_test(step_fn):
    """Wrap a step function so pytest can discover and run it."""

    def wrapper():
        step_fn()
        # Check if this specific step failed
        for name, detail in results.failed:
            if name == step_fn.__name__ or name.startswith(step_fn.__name__.replace("test_", "")):
                raise AssertionError(f"{name}: {detail}")
        # Also check sub-results recorded inside the step
        step_base = step_fn.__name__.replace("test_", "")
        for name, detail in results.failed:
            if step_base in name:
                raise AssertionError(f"{name}: {detail}")

    wrapper.__name__ = step_fn.__name__
    wrapper.__doc__ = step_fn.__doc__
    return wrapper


# When running under pytest, the functions below are discovered as tests.
# They share _state so they MUST run in order. Use:
#     pytest tests/test_e2e_smoke.py -v
#
# pytest-ordering or pytest-order can enforce order, but by default pytest
# runs tests in file order, which works here.

class TestE2ESmoke:
    """End-to-end smoke tests against a running TotalReclaw server.

    Tests MUST run in order (each depends on state from prior steps).
    """

    def test_01_health_check(self):
        test_health_check()
        self._check_failures("health_check")

    def test_02_register(self):
        test_register()
        self._check_failures("register")

    def test_03_store_facts(self):
        test_store_facts()
        self._check_failures("store_facts")

    def test_04_search(self):
        test_search()
        self._check_failures("search")

    def test_05_search_multiple_trapdoors(self):
        test_search_multiple_trapdoors()
        self._check_failures("search_multiple_trapdoors")

    def test_06_dedup(self):
        test_dedup()
        self._check_failures("dedup")

    def test_07_export(self):
        test_export()
        self._check_failures("export")

    def test_08_sync(self):
        test_sync()
        self._check_failures("sync")

    def test_09_delete_fact(self):
        test_delete_fact()
        self._check_failures("delete_fact")

    def test_10_delete_account(self):
        test_delete_account()
        self._check_failures("delete_account")

    @staticmethod
    def _check_failures(step_key: str):
        """Raise AssertionError if any result recorded for this step failed."""
        for name, detail in results.failed:
            if step_key in name:
                raise AssertionError(f"{name}: {detail}")


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(run_all())
