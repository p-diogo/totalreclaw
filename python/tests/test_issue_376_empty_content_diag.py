"""#376 follow-on — empty-content diagnostic must surface response shape.

The rc7 #376 hunt could not get finish_reason / reasoning_content from the
logs. GLM models on the z.ai Coding endpoint frequently return empty
``message.content`` while putting the actual text in
``message.reasoning_content`` — so "empty content" is misleading. The
``_call_openai`` empty-content WARN must log: finish_reason, usage,
message keys, and reasoning_content presence/length, so the operator (and
the coordinator's z.ai root-cause) can see WHY content was empty.
"""
from __future__ import annotations

import logging

import httpx
import pytest

from totalreclaw.agent import llm_client
from totalreclaw.agent.llm_client import LLMConfig, _call_openai


def _patch_openai_response(monkeypatch, payload: dict):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)

    class _Patched(httpx.AsyncClient):
        def __init__(self, *a, **k):
            k.pop("transport", None)
            super().__init__(*a, transport=transport, **k)

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", _Patched)


_CFG = LLMConfig(
    api_key="k",
    base_url="https://api.z.ai/api/coding/paas/v4",
    model="glm-4.5-flash",
    api_format="openai",
)


@pytest.mark.asyncio
async def test_empty_content_diag_surfaces_reasoning_content(monkeypatch, caplog):
    _patch_openai_response(
        monkeypatch,
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": "",
                        "reasoning_content": "answer was put here by the model",
                    },
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 0, "total_tokens": 12},
        },
    )
    with caplog.at_level(logging.WARNING, logger="totalreclaw.agent.llm_client"):
        out = await _call_openai(_CFG, "sys", "usr", 100, 0.0)

    assert not out  # content was empty
    diag = [r.getMessage() for r in caplog.records if "LLM returned empty content" in r.getMessage()]
    assert diag, "empty-content diag must fire"
    msg = diag[0]
    assert "finish_reason=stop" in msg
    assert "reasoning_content_present=True" in msg
    assert "reasoning_content_chars=" in msg
    assert "message_keys=" in msg


@pytest.mark.asyncio
async def test_diag_reports_no_reasoning_when_truly_empty(monkeypatch, caplog):
    _patch_openai_response(
        monkeypatch,
        {
            "choices": [{"finish_reason": "length", "message": {"content": ""}}],
            "usage": {"total_tokens": 5},
        },
    )
    with caplog.at_level(logging.WARNING, logger="totalreclaw.agent.llm_client"):
        await _call_openai(_CFG, "sys", "usr", 100, 0.0)
    diag = [r.getMessage() for r in caplog.records if "LLM returned empty content" in r.getMessage()]
    assert diag
    assert "reasoning_content_present=False" in diag[0]
    assert "finish_reason=length" in diag[0]
