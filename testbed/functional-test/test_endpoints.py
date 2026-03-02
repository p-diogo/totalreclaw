#!/usr/bin/env python3
"""
Basic integration tests for TotalReclaw Server endpoints.

Tests:
1. /register - User registration
2. /store - Store encrypted facts
3. /search - Search with blind indices
"""

import hashlib
import json
import secrets
import uuid
from datetime import datetime

import httpx
from hkdf import Hkdf as HKDF

BASE_URL = "http://127.0.0.1:8080"
AUTH_KEY_INFO = b"openmemory-auth-v1"


def derive_auth_key(master_password: str, salt: bytes) -> bytes:
    """Derive auth key using HKDF-SHA256."""
    password_bytes = master_password.encode("utf-8")
    hkdf = HKDF(salt, password_bytes, hashlib.sha256)
    return hkdf.expand(AUTH_KEY_INFO, 32)


def hash_auth_key(auth_key: bytes) -> bytes:
    """Hash auth key for storage."""
    return hashlib.sha256(auth_key).digest()


def generate_test_user():
    """Generate a test user with credentials."""
    master_password = "test_master_password_123"
    salt = secrets.token_bytes(32)
    auth_key = derive_auth_key(master_password, salt)
    auth_key_hash = hash_auth_key(auth_key)
    return {
        "master_password": master_password,
        "salt": salt,
        "auth_key": auth_key,
        "auth_key_hash": auth_key_hash,
    }


def test_health():
    """Test health endpoint."""
    print("\n=== Testing /health ===")
    resp = httpx.get(f"{BASE_URL}/health")
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    print("PASS: Health check")
    return True


def test_register():
    """Test user registration."""
    print("\n=== Testing /register ===")
    user = generate_test_user()

    payload = {
        "auth_key_hash": user["auth_key_hash"].hex(),
        "salt": user["salt"].hex(),
    }

    resp = httpx.post(
        f"{BASE_URL}/register",
        json=payload,
        headers={"Content-Type": "application/json"},
    )

    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["user_id"] is not None

    user["user_id"] = data["user_id"]
    print(f"PASS: User registered with ID: {user['user_id']}")
    return user


def test_store(user):
    """Test storing facts."""
    print("\n=== Testing /store ===")

    # Create a test fact
    fact_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat()

    # Simulated encrypted blob (in reality this would be AES-256-GCM encrypted)
    encrypted_blob = secrets.token_bytes(64)

    # Simulated blind indices (SHA-256 hashes)
    blind_indices = [
        hashlib.sha256(b"test_keyword_1").hexdigest(),
        hashlib.sha256(b"test_keyword_2").hexdigest(),
        hashlib.sha256(b"category_personal").hexdigest(),
    ]

    payload = {
        "user_id": user["user_id"],
        "facts": [
            {
                "id": fact_id,
                "timestamp": timestamp,
                "encrypted_blob": encrypted_blob.hex(),
                "blind_indices": blind_indices,
                "decay_score": 1.0,
                "is_active": True,
                "version": 1,
                "source": "explicit",
            }
        ],
    }

    # Use auth_key (not auth_key_hash) for authorization
    auth_header = f"Bearer {user['auth_key'].hex()}"

    resp = httpx.post(
        f"{BASE_URL}/store",
        json=payload,
        headers={"Content-Type": "application/json", "Authorization": auth_header},
    )

    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert fact_id in data["ids"]

    print(f"PASS: Fact stored with ID: {fact_id}")

    # Store additional facts for search testing
    for i in range(3):
        extra_fact_id = str(uuid.uuid4())
        extra_payload = {
            "user_id": user["user_id"],
            "facts": [
                {
                    "id": extra_fact_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "encrypted_blob": secrets.token_bytes(64).hex(),
                    "blind_indices": blind_indices + [hashlib.sha256(f"extra_{i}".encode()).hexdigest()],
                    "decay_score": 0.8 - (i * 0.1),
                    "is_active": True,
                    "version": 1,
                    "source": "conversation",
                }
            ],
        }

        resp = httpx.post(
            f"{BASE_URL}/store",
            json=extra_payload,
            headers={"Content-Type": "application/json", "Authorization": auth_header},
        )
        assert resp.status_code == 200
        print(f"  Stored additional fact {i+1}: {extra_fact_id}")

    return fact_id, blind_indices


def test_search(user, blind_indices):
    """Test searching facts."""
    print("\n=== Testing /search ===")

    # Use some of the blind indices as trapdoors
    trapdoors = blind_indices[:2]

    payload = {
        "user_id": user["user_id"],
        "trapdoors": trapdoors,
        "max_candidates": 100,
        "min_decay_score": 0.0,
    }

    auth_header = f"Bearer {user['auth_key'].hex()}"

    resp = httpx.post(
        f"{BASE_URL}/search",
        json=payload,
        headers={"Content-Type": "application/json", "Authorization": auth_header},
    )

    print(f"Status: {resp.status_code}")
    print(f"Response: {json.dumps(resp.json(), indent=2)[:500]}...")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["total_candidates"] >= 1

    print(f"PASS: Found {data['total_candidates']} candidates")
    return True


def test_export(user):
    """Test exporting all facts."""
    print("\n=== Testing /export ===")

    auth_header = f"Bearer {user['auth_key'].hex()}"

    resp = httpx.get(
        f"{BASE_URL}/export",
        headers={"Authorization": auth_header},
    )

    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(f"Facts exported: {len(data.get('facts', []))}")

    assert resp.status_code == 200
    assert data["success"] is True

    print(f"PASS: Exported {len(data['facts'])} facts")
    return True


def test_unauthorized_access():
    """Test that unauthorized access is rejected."""
    print("\n=== Testing Unauthorized Access ===")

    # Try to store without auth
    resp = httpx.post(
        f"{BASE_URL}/store",
        json={"user_id": "test", "facts": []},
        headers={"Content-Type": "application/json"},
    )

    print(f"Store without auth - Status: {resp.status_code}")
    assert resp.status_code == 401

    # Try to search with invalid auth
    resp = httpx.post(
        f"{BASE_URL}/search",
        json={"user_id": "test", "trapdoors": []},
        headers={"Authorization": "Bearer invalid_hex_key"},
    )

    print(f"Search with invalid auth - Status: {resp.status_code}")
    assert resp.status_code == 401

    print("PASS: Unauthorized access properly rejected")
    return True


def main():
    print("=" * 60)
    print("TotalReclaw Server Integration Tests")
    print("=" * 60)

    results = []

    # Test 1: Health check
    try:
        test_health()
        results.append(("Health Check", "PASS"))
    except Exception as e:
        print(f"FAIL: {e}")
        results.append(("Health Check", "FAIL"))

    # Test 2: Register
    try:
        user = test_register()
        results.append(("Register", "PASS"))
    except Exception as e:
        print(f"FAIL: {e}")
        results.append(("Register", "FAIL"))
        return  # Can't continue without user

    # Test 3: Store
    try:
        fact_id, blind_indices = test_store(user)
        results.append(("Store", "PASS"))
    except Exception as e:
        print(f"FAIL: {e}")
        results.append(("Store", "FAIL"))
        blind_indices = []

    # Test 4: Search (if store succeeded)
    if blind_indices:
        try:
            test_search(user, blind_indices)
            results.append(("Search", "PASS"))
        except Exception as e:
            print(f"FAIL: {e}")
            results.append(("Search", "FAIL"))

    # Test 5: Export
    try:
        test_export(user)
        results.append(("Export", "PASS"))
    except Exception as e:
        print(f"FAIL: {e}")
        results.append(("Export", "FAIL"))

    # Test 6: Unauthorized access
    try:
        test_unauthorized_access()
        results.append(("Unauthorized Access", "PASS"))
    except Exception as e:
        print(f"FAIL: {e}")
        results.append(("Unauthorized Access", "FAIL"))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    for name, status in results:
        status_str = f"\033[92m{status}\033[0m" if status == "PASS" else f"\033[91m{status}\033[0m"
        print(f"  {name}: {status_str}")

    passed = sum(1 for _, s in results if s == "PASS")
    total = len(results)
    print(f"\nTotal: {passed}/{total} tests passed")


if __name__ == "__main__":
    main()
