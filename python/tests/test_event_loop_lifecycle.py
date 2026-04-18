"""Regression tests for Bug #2 — "Event loop is closed" across sync agent hooks.

QA reference: `docs/notes/QA-V1CLEAN-VPS-20260418.md`. On a fresh VPS install
of ``totalreclaw==2.0.1``, every call to ``totalreclaw_status`` and
``totalreclaw_export`` — and every first-turn ``pre_llm_call`` auto-recall —
returned ``RuntimeError: Event loop is closed``.

Root cause
----------
``totalreclaw.agent.recall.auto_recall`` and
``totalreclaw.agent.lifecycle.auto_extract`` each run synchronously from
Hermes's sync hook callbacks. Historically they used::

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(client.recall(...))
    finally:
        loop.close()

``client.recall`` eventually calls ``RelayClient._get_http()``, which caches
an ``httpx.AsyncClient`` on the RelayClient instance. ``httpx.AsyncClient``
binds to whichever event loop was running when it was constructed. After
the *first* hook call finished and its loop was closed, the cached
``httpx.AsyncClient`` was still held by the RelayClient — and on the *next*
hook call we created a fresh loop but reused the stale client, which still
had its underlying socket / connection pool referencing the closed loop.
That raises ``RuntimeError: Event loop is closed`` from inside anyio/httpx
on the first request attempted from the new loop.

Fix
---
Instead of per-call loops, run all per-instance async work through a single
long-lived background thread that owns one persistent event loop. The
httpx client is created on (and only used from) that one loop, so it is
never orphaned by a short-lived per-call loop. See
``totalreclaw.agent.loop_runner``.

These tests pin the invariant:

* ``_SyncLoopRunner`` survives repeated ``.run`` calls from different
  calling threads without raising.
* A ``RelayClient`` driven via ``_SyncLoopRunner`` can issue two HTTP
  requests (mocked transport) in sequence without tripping
  ``Event loop is closed``.
* Calling ``auto_recall(...)`` twice in a row against the same RelayClient
  does not raise.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


# ---------------------------------------------------------------------------
# Low-level: the loop runner itself must survive re-entry
# ---------------------------------------------------------------------------


def test_sync_loop_runner_survives_sequential_calls() -> None:
    """``_SyncLoopRunner.run`` must accept sequential awaitables.

    Before the fix, callers used a fresh ``asyncio.new_event_loop()`` each
    time and closed it at the end. That worked for single-call work but
    leaked any cached ``httpx.AsyncClient`` across loops. The new runner
    owns ONE loop in a background thread and runs every coroutine on it.
    """
    from totalreclaw.agent.loop_runner import get_sync_loop_runner

    runner = get_sync_loop_runner()

    async def _trivial(i: int) -> int:
        return i * 2

    assert runner.run(_trivial(3)) == 6
    assert runner.run(_trivial(5)) == 10
    assert runner.run(_trivial(7)) == 14


def test_sync_loop_runner_is_process_wide_singleton() -> None:
    """Multiple calls return the same runner — one loop for the process."""
    from totalreclaw.agent.loop_runner import get_sync_loop_runner

    a = get_sync_loop_runner()
    b = get_sync_loop_runner()
    assert a is b


# ---------------------------------------------------------------------------
# Mid-level: RelayClient re-entry must not blow up across sync calls
# ---------------------------------------------------------------------------


def test_relay_client_survives_sequential_sync_calls() -> None:
    """Two sequential calls to a RelayClient method from sync code must work.

    This is the exact pattern that broke in v2.0.1: ``totalreclaw_status``
    was called twice in a row by a user, and the second call returned
    ``Event loop is closed``. We mock the httpx transport so we don't
    actually hit a relay.
    """
    from totalreclaw.agent.loop_runner import get_sync_loop_runner
    from totalreclaw.relay import RelayClient

    # Mock httpx.AsyncClient so each .post() returns a canned billing response.
    # Importantly, the mock honors the httpx_mock.Response contract so that
    # the code path exercises the same async execution flow as production.
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "tier": "free",
                "free_writes_used": 3,
                "free_writes_limit": 500,
                "expires_at": None,
            },
        )

    transport = httpx.MockTransport(_handler)

    # Patch the RelayClient's _get_http so it returns a mock-transport client
    # on the long-lived loop.
    rc = RelayClient(
        relay_url="https://api-staging.totalreclaw.xyz",
        auth_key_hex="00" * 32,
        wallet_address="0x" + "ab" * 20,
    )

    runner = get_sync_loop_runner()

    # Replace the lazy async-client constructor with one bound to the runner's
    # loop (this is how the production fix wires things up).
    async def _mock_get_http() -> httpx.AsyncClient:
        if rc._http is None or rc._http.is_closed:
            rc._http = httpx.AsyncClient(transport=transport, timeout=10.0)
        return rc._http

    rc._get_http = _mock_get_http  # type: ignore[assignment]

    # Call twice — the regression is that the second call raises
    # "Event loop is closed".
    status1 = runner.run(rc.get_billing_status())
    status2 = runner.run(rc.get_billing_status())

    assert status1.tier == "free"
    assert status2.tier == "free"

    runner.run(rc.close())


# ---------------------------------------------------------------------------
# High-level: lifecycle functions must not create and tear down loops
# ---------------------------------------------------------------------------


def _make_state_with_fake_client():
    """Build a PluginState with a fake client. Mirrors _make_state from
    test_v1_hooks_integration.py but keeps the imports local so failure of
    the loop-runner module doesn't break test collection."""
    from totalreclaw.hermes.state import PluginState

    with patch.dict(os.environ, {}, clear=True):
        with patch.object(Path, "exists", return_value=False):
            state = PluginState()

    fake_client = MagicMock()
    fake_client.remember = AsyncMock(return_value="fact-uuid-abc")
    fake_client.recall = AsyncMock(return_value=[])
    fake_client.forget = AsyncMock(return_value=True)
    state._client = fake_client
    return state, fake_client


def _build_real_client_with_mock_transport(transport: httpx.MockTransport):
    """Build a real TotalReclaw client whose RelayClient uses a mock transport.

    Using a real RelayClient + real httpx.AsyncClient (not an AsyncMock) is
    essential to reproduce the ``Event loop is closed`` bug: the bug only
    surfaces when the same httpx client is carried across two different
    event loops, which MagicMock does not simulate.
    """
    from totalreclaw.client import TotalReclaw

    test_mnemonic = (
        "abandon abandon abandon abandon abandon abandon "
        "abandon abandon abandon abandon abandon about"
    )
    client = TotalReclaw(
        recovery_phrase=test_mnemonic,
        wallet_address="0x2c0cf74b2b76110708ca431796367779e3738250",
    )
    client._registered = True

    # Monkeypatch _get_http so it returns a real httpx.AsyncClient with the
    # mock transport. The RelayClient still owns the reference, so if the
    # code creates a loop, tears it down, and then reuses the cached
    # AsyncClient from a new loop, we will hit "Event loop is closed".
    rc = client._relay
    original_get_http = rc._get_http

    async def _patched() -> httpx.AsyncClient:
        if rc._http is None or rc._http.is_closed:
            rc._http = httpx.AsyncClient(transport=transport, timeout=10.0)
        return rc._http

    rc._get_http = _patched  # type: ignore[assignment]
    return client


def test_sync_auto_recall_does_not_hit_event_loop_is_closed() -> None:
    """Reproduces the QA bug: two sync calls to auto_recall against the
    same TotalReclaw instance used to raise ``Event loop is closed`` on the
    second call. Must not raise any more.
    """
    from totalreclaw.agent.recall import auto_recall
    from totalreclaw.hermes.state import PluginState

    # Minimal empty-search response: no facts found.
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": {"blindIndexes": [], "facts": []}},
        )

    transport = httpx.MockTransport(_handler)
    client = _build_real_client_with_mock_transport(transport)

    with patch.dict(os.environ, {}, clear=True):
        with patch.object(Path, "exists", return_value=False):
            state = PluginState()
    state._client = client

    out1 = auto_recall("hello", state)
    out2 = auto_recall("world", state)
    assert out1 is None
    assert out2 is None


def test_sync_client_status_does_not_hit_event_loop_is_closed() -> None:
    """Reproduces the QA bug: calling client.status() from two different
    short-lived loops used to raise ``Event loop is closed`` on the second.

    This is the ``totalreclaw_status`` path — the single most visible break
    for users in the v2.0.1 QA because it's the first sanity tool a user
    reaches for.
    """
    from totalreclaw.agent.loop_runner import get_sync_loop_runner

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "tier": "free",
                "free_writes_used": 2,
                "free_writes_limit": 500,
            },
        )

    transport = httpx.MockTransport(_handler)
    client = _build_real_client_with_mock_transport(transport)

    runner = get_sync_loop_runner()
    s1 = runner.run(client.status())
    s2 = runner.run(client.status())
    assert s1.tier == "free"
    assert s2.tier == "free"
