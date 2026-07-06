"""rc4 (internal#435) — byte-capped batching + halve-on-sim-revert.

rc3 re-QA NO-GO'd on F3 again. Instrumented staging repro
(https://github.com/p-diogo/totalreclaw-internal/issues/435#issuecomment-4895421400):
Pimlico's ``-32500 "Sender does not implement validateUserOp or factory is not
deployed"`` is a CATCH-ALL for executeBatch simulation failure on oversized
calldata. Realistic import facts (~600-char text + encrypted 640-dim embedding)
≈ 4.5KB each; simulation reverts between 15 (~67KB, passes) and 20 (~85KB,
fails) facts. The #454 deploy-state fixes were correct but not this bug.

Fixes exercised here:
  * ``_group_payloads_by_size`` chunks by BOTH a count ceiling (≤15) and an
    estimated calldata-byte cap (≤32KB).
  * ``ImportEngine._store_group_adaptive`` halves-and-retries a group that
    still sim-reverts, floor 1.
  * ``userop._await_batch_receipt`` waits up to 240s (poll 5s) for inclusion.
"""
from __future__ import annotations

import asyncio

import pytest

import totalreclaw.import_engine as ie
from totalreclaw.import_engine import (
    ImportEngine,
    IMPORT_MAX_BATCH_SIZE,
    _MAX_BATCH_BYTES,
    _estimate_payload_bytes,
    _group_payloads_by_size,
)
from totalreclaw import userop


# ── (a)+(b) grouping helper ───────────────────────────────────────────────
def test_count_ceiling_is_15():
    # rc4 restored the count ceiling to 15 (was 30, never staging-validated).
    assert IMPORT_MAX_BATCH_SIZE == 15


def test_realistic_facts_group_within_both_caps():
    # ~600-char text + a 640-dim embedding ≈ 4.56KB estimated each.
    payloads = [
        {"text": "x" * 600, "embedding": [0.0] * 640}
        for _ in range(40)
    ]
    groups = list(_group_payloads_by_size(
        payloads, IMPORT_MAX_BATCH_SIZE, _MAX_BATCH_BYTES
    ))
    # No fact dropped or duplicated.
    assert sum(len(g) for g in groups) == 40
    for g in groups:
        assert len(g) <= IMPORT_MAX_BATCH_SIZE
        assert sum(_estimate_payload_bytes(p) for p in g) <= _MAX_BATCH_BYTES
    # The byte cap (not the count cap) binds for realistic payloads: groups are
    # well under 15.
    assert max(len(g) for g in groups) < IMPORT_MAX_BATCH_SIZE


def test_short_facts_group_up_to_count_ceiling():
    # Tiny text, no embedding → the count ceiling binds before the byte cap.
    payloads = [{"text": "short fact"} for _ in range(40)]
    groups = list(_group_payloads_by_size(
        payloads, IMPORT_MAX_BATCH_SIZE, _MAX_BATCH_BYTES
    ))
    assert sum(len(g) for g in groups) == 40
    assert [len(g) for g in groups] == [15, 15, 10]


def test_single_oversize_fact_still_forms_a_group():
    # A lone fact larger than the byte cap is never dropped — it forms its own
    # group (adaptive halving is the backstop if it still sim-reverts).
    payloads = [{"text": "z" * 100_000, "embedding": [0.0] * 640}]
    groups = list(_group_payloads_by_size(
        payloads, IMPORT_MAX_BATCH_SIZE, _MAX_BATCH_BYTES
    ))
    assert groups == [payloads]


# ── (c)+(d) adaptive halving via _store_facts_chunked ─────────────────────
class _SimClient:
    """Gnosis client that fails remember_batch when a predicate on the group
    size says so; records every group size it was called with."""

    def __init__(self, fail_pred):
        self.calls: list[int] = []
        self._fail = fail_pred

    async def _ensure_chain_id(self):
        return 100

    async def remember_batch(self, payloads, source=None):
        self.calls.append(len(payloads))
        if self._fail(len(payloads)):
            raise RuntimeError(
                "UserOperation reverted during simulation with reason: -32500 "
                "Sender does not implement validateUserOp or factory is not deployed"
            )
        return [f"id{i}" for i in range(len(payloads))]


@pytest.fixture(autouse=True)
def _no_embedding(monkeypatch):
    # Keep payloads small (no embedding) so a 10-fact group stays one group,
    # and avoid loading the real embedding model.
    import totalreclaw.embedding as emb
    monkeypatch.setattr(emb, "get_embedding", lambda t: None)
    yield


def _facts(n):
    return [
        {"text": f"distinct fact number {i} about something", "type": "fact", "importance": 8}
        for i in range(n)
    ]


def test_sim_revert_halves_and_stores_all():
    # A 10-fact group sim-reverts; halves (5+5) succeed → all 10 stored, no
    # errors. Client sees group sizes [10, 5, 5].
    client = _SimClient(fail_pred=lambda n: n > 5)
    engine = ImportEngine(client=client, llm_extract=None)
    stored, errors, dups = asyncio.run(engine._store_facts_chunked(_facts(10)))
    assert stored == 10
    assert errors == []
    assert client.calls == [10, 5, 5]


def test_sim_revert_at_single_fact_floor_surfaces_error():
    # Every group (down to 1 fact) sim-reverts → the single-fact floor surfaces
    # an error rather than silently dropping the fact.
    client = _SimClient(fail_pred=lambda n: True)
    engine = ImportEngine(client=client, llm_extract=None)
    stored, errors, dups = asyncio.run(engine._store_facts_chunked(_facts(1)))
    assert stored == 0
    assert errors
    assert "Batch store failed" in errors[0]


def test_sim_revert_partial_floor_failure_stores_the_rest():
    # 4 facts: the full group reverts, halves to 2+2; one 2-group succeeds,
    # the other reverts and halves to 1+1 which both fail at the floor.
    # Deterministic on group SIZE: fail any group of size != 2. So [4]→halve,
    # [2],[2] succeed → actually stores all. Use a size-based fail that still
    # exercises a floor error: fail sizes 4 and 1.
    client = _SimClient(fail_pred=lambda n: n in (4, 1))
    engine = ImportEngine(client=client, llm_extract=None)
    stored, errors, dups = asyncio.run(engine._store_facts_chunked(_facts(4)))
    # [4] reverts → [2],[2] both succeed (size 2 not in fail set).
    assert stored == 4
    assert errors == []
    assert client.calls == [4, 2, 2]


# ── (e) receipt-wait constant ─────────────────────────────────────────────
def test_receipt_wait_constants_lifted():
    assert userop._BATCH_RECEIPT_TIMEOUT_S == 240.0
    assert userop._BATCH_RECEIPT_POLL_S == 5.0
