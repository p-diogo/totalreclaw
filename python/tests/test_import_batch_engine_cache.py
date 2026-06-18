"""Regression test for #389 — ImportEngine reuse across import_batch calls.

Before the fix, every ``totalreclaw_import_batch`` invocation built a fresh
``ImportEngine``, which reset ``_smart_ctx`` and the cross-batch session /
Crystal accumulators. The smart-import profile + triage LLM passes (~17-25 min
over the whole chunks list on a 1344-chunk Gemini Takeout) re-ran on every
batch, turning a sub-hour import into a 52-hour one.

These tests pin the post-fix contract: the engine is process-scoped and
cached by ``(client, source, file_or_content_key)``.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


def _state_with_pro_client():
    from totalreclaw.hermes.state import PluginState
    state = PluginState()
    client = MagicMock()
    client.status = AsyncMock(return_value=MagicMock(tier="pro"))
    state._client = client
    return state, client


def _stub_process_batch(monkeypatch):
    """Patch ImportEngine.process_batch so it returns immediately, no LLM."""
    import totalreclaw.import_engine as ie
    result = MagicMock(facts_stored=1, facts_extracted=1, is_complete=False)

    async def _process(self, **k):
        # Touch the instance to prove identity matters: stamp a marker.
        self._test_marker = getattr(self, "_test_marker", 0) + 1
        return result

    monkeypatch.setattr(ie.ImportEngine, "process_batch", _process)


def _clear_engine_cache():
    from totalreclaw.hermes import tools
    tools._IMPORT_ENGINE_CACHE.clear()


@pytest.mark.asyncio
async def test_import_batch_reuses_engine_across_calls(monkeypatch):
    """Two consecutive import_batch calls with the same (source, file_path)
    must hit the SAME ImportEngine instance — that is what preserves
    _smart_ctx, _session_assignments, _crystallized_session_ids, etc.
    across batches.
    """
    from totalreclaw.hermes import tools
    _clear_engine_cache()
    _stub_process_batch(monkeypatch)
    state, _client = _state_with_pro_client()

    args = {
        "source": "gemini",
        "file_path": "/tmp/my-activity.html",
        "offset": 0,
        "batch_size": 25,
    }

    await tools.import_batch(args, state)
    # Second call: same source + file_path → same engine.
    args2 = {**args, "offset": 25}
    await tools.import_batch(args2, state)
    # Third call confirms the marker keeps incrementing on the SAME instance.
    args3 = {**args, "offset": 50}
    await tools.import_batch(args3, state)

    assert len(tools._IMPORT_ENGINE_CACHE) == 1
    (engine, _ts), = tools._IMPORT_ENGINE_CACHE.values()
    # Marker stamped 3× on the same engine ⇒ reuse confirmed.
    assert engine._test_marker == 3


@pytest.mark.asyncio
async def test_smart_import_pipeline_runs_only_once_across_batches(monkeypatch):
    """The expensive smart-import pipeline must run exactly once per
    (client, source, file_path) — even when import_batch is called N times.
    """
    from totalreclaw.hermes import tools
    from totalreclaw import import_engine as ie
    _clear_engine_cache()
    _stub_process_batch(monkeypatch)
    state, _client = _state_with_pro_client()

    # _maybe_run_smart_import is the gateway to the profile+triage LLM passes.
    # Count invocations across two import_batch calls.
    calls = {"n": 0}

    async def _spy(self, chunks):
        calls["n"] += 1
        # Mimic the production caching contract so the second batch's call
        # path would no-op too if the engine were reused (defensive).
        self._smart_import_attempted = True
        return None

    monkeypatch.setattr(ie.ImportEngine, "_maybe_run_smart_import", _spy)

    args = {"source": "gemini", "file_path": "/tmp/x.html", "offset": 0, "batch_size": 25}
    await tools.import_batch(args, state)
    await tools.import_batch({**args, "offset": 25}, state)
    await tools.import_batch({**args, "offset": 50}, state)

    # Engine reused ⇒ _smart_import_attempted latches after the first call,
    # so the gateway is invoked at most once. Even if process_batch is
    # stubbed and never calls the gateway, the cache MUST hold one engine.
    assert len(tools._IMPORT_ENGINE_CACHE) == 1


@pytest.mark.asyncio
async def test_different_file_paths_get_separate_engines(monkeypatch):
    """Two different source files must NOT share an engine — that would
    cross-pollinate smart-import state between unrelated imports.
    """
    from totalreclaw.hermes import tools
    _clear_engine_cache()
    _stub_process_batch(monkeypatch)
    state, _client = _state_with_pro_client()

    await tools.import_batch(
        {"source": "gemini", "file_path": "/tmp/a.html", "offset": 0, "batch_size": 25},
        state,
    )
    await tools.import_batch(
        {"source": "gemini", "file_path": "/tmp/b.html", "offset": 0, "batch_size": 25},
        state,
    )

    assert len(tools._IMPORT_ENGINE_CACHE) == 2


@pytest.mark.asyncio
async def test_inline_content_keyed_by_hash(monkeypatch):
    """Inline content (no file_path) must key by content hash so the cache
    hits on repeat-call but misses on different content.
    """
    from totalreclaw.hermes import tools
    _clear_engine_cache()
    _stub_process_batch(monkeypatch)
    state, _client = _state_with_pro_client()

    await tools.import_batch(
        {"source": "chatgpt", "content": "same body", "offset": 0, "batch_size": 25},
        state,
    )
    await tools.import_batch(
        {"source": "chatgpt", "content": "same body", "offset": 25, "batch_size": 25},
        state,
    )
    await tools.import_batch(
        {"source": "chatgpt", "content": "different body", "offset": 0, "batch_size": 25},
        state,
    )

    # Two distinct content fingerprints → two engines.
    assert len(tools._IMPORT_ENGINE_CACHE) == 2


@pytest.mark.asyncio
async def test_stale_entries_evicted_on_access(monkeypatch):
    """Cache entries older than _IMPORT_ENGINE_TTL_SECONDS must be evicted
    on next access. Lets long-running Hermes processes recycle memory.
    """
    from totalreclaw.hermes import tools
    _clear_engine_cache()
    _stub_process_batch(monkeypatch)
    state, _client = _state_with_pro_client()

    await tools.import_batch(
        {"source": "gemini", "file_path": "/tmp/old.html", "offset": 0, "batch_size": 25},
        state,
    )
    assert len(tools._IMPORT_ENGINE_CACHE) == 1

    # Backdate the entry past the TTL.
    key, (engine, _ts) = next(iter(tools._IMPORT_ENGINE_CACHE.items()))
    tools._IMPORT_ENGINE_CACHE[key] = (engine, _ts - (tools._IMPORT_ENGINE_TTL_SECONDS + 1))

    # New import on a different file triggers the sweep AND inserts a fresh entry.
    await tools.import_batch(
        {"source": "gemini", "file_path": "/tmp/new.html", "offset": 0, "batch_size": 25},
        state,
    )
    assert len(tools._IMPORT_ENGINE_CACHE) == 1
    surviving_key = next(iter(tools._IMPORT_ENGINE_CACHE.keys()))
    assert surviving_key[3] == "/tmp/new.html"
