"""Tests for the prod-vs-staging signal on the ``totalreclaw_status`` tool.

The relay's production cap (250 writes/month) is enforced only on
``api.totalreclaw.xyz``. The staging relay (``api-staging.totalreclaw.xyz``)
does not enforce the quota so QA + RC builds can write past 250. The
status tool must:

1. Return ``environment="production"`` for the production relay (and emit
   NO ``staging_note`` — production users should see no mention of staging).
2. Return ``environment="staging"`` for the staging relay AND include a
   ``staging_note`` explaining the cap is not enforced.
3. Default ``period="monthly"`` on the free tier (forward-compat shim for
   older relays that don't yet emit the field).
4. Infer ``environment`` from the relay URL when the relay doesn't
   populate it explicitly.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from totalreclaw.hermes.state import PluginState
from totalreclaw.relay import BillingStatus, _infer_environment_from_url


def _make_state_with_billing(billing: BillingStatus) -> PluginState:
    """Return a configured PluginState whose client.status() returns ``billing``."""
    with patch.dict(os.environ, {}, clear=True):
        with patch.object(Path, "exists", return_value=False):
            state = PluginState()
    fake_client = MagicMock()
    fake_client.status = AsyncMock(return_value=billing)
    state._client = fake_client
    return state


class TestInferEnvironmentFromUrl:
    def test_production_default(self) -> None:
        assert _infer_environment_from_url("https://api.totalreclaw.xyz") == "production"

    def test_production_with_trailing_slash(self) -> None:
        assert _infer_environment_from_url("https://api.totalreclaw.xyz/") == "production"

    def test_staging(self) -> None:
        assert _infer_environment_from_url("https://api-staging.totalreclaw.xyz") == "staging"

    def test_staging_case_insensitive(self) -> None:
        assert _infer_environment_from_url("HTTPS://API-STAGING.totalreclaw.xyz") == "staging"

    def test_self_hosted_defaults_to_production(self) -> None:
        # Self-hosted URLs don't match the staging marker; treat as production
        # behavior (operator runs their own relay, not our staging instance).
        assert _infer_environment_from_url("https://relay.example.com") == "production"
        assert _infer_environment_from_url("http://localhost:8000") == "production"


class TestStatusToolProductionEnvironment:
    @pytest.mark.asyncio
    async def test_production_omits_staging_note(self) -> None:
        from totalreclaw.hermes.tools import status

        billing = BillingStatus(
            tier="free",
            free_writes_used=30,
            free_writes_limit=250,
            expires_at=None,
            environment="production",
        )
        state = _make_state_with_billing(billing)
        result = json.loads(await status({}, state))

        assert result["tier"] == "free"
        assert result["free_writes_limit"] == 250
        assert result["free_writes_used"] == 30
        assert result["environment"] == "production"
        # Period defaults to monthly on free tier even when relay omits it.
        assert result["period"] == "monthly"
        # CRITICAL: production users must NEVER see staging mentioned.
        assert "staging_note" not in result

    @pytest.mark.asyncio
    async def test_production_pro_tier_no_period_default(self) -> None:
        """Pro tier with no relay-provided period stays ``None`` — only the
        free tier gets the monthly default."""
        from totalreclaw.hermes.tools import status

        billing = BillingStatus(
            tier="pro",
            free_writes_used=0,
            free_writes_limit=0,
            expires_at="2026-12-31T00:00:00Z",
            environment="production",
        )
        state = _make_state_with_billing(billing)
        result = json.loads(await status({}, state))
        assert result["tier"] == "pro"
        assert result["period"] is None
        assert "staging_note" not in result


class TestStatusToolStagingEnvironment:
    @pytest.mark.asyncio
    async def test_staging_includes_staging_note(self) -> None:
        from totalreclaw.hermes.tools import status

        billing = BillingStatus(
            tier="free",
            free_writes_used=500,  # Past the production cap — only possible on staging.
            free_writes_limit=250,
            expires_at=None,
            environment="staging",
        )
        state = _make_state_with_billing(billing)
        result = json.loads(await status({}, state))

        assert result["environment"] == "staging"
        assert "staging_note" in result
        note = result["staging_note"]
        # The note must explain BOTH the staging behavior AND the production cap
        # so the agent can relay an accurate comparison.
        assert "staging" in note.lower()
        assert "NOT enforced" in note or "not enforced" in note.lower()
        assert "250" in note
        # And it must point at the relay hostnames so the user can verify.
        assert "api-staging.totalreclaw.xyz" in note
        assert "api.totalreclaw.xyz" in note

    @pytest.mark.asyncio
    async def test_staging_passes_through_relay_provided_period(self) -> None:
        """If the relay sends ``period``, the tool must use it verbatim
        (not overwrite with the free-tier monthly default)."""
        from totalreclaw.hermes.tools import status

        billing = BillingStatus(
            tier="free",
            free_writes_used=10,
            free_writes_limit=250,
            expires_at=None,
            period="lifetime",  # Relay-provided wins over the default.
            environment="staging",
        )
        state = _make_state_with_billing(billing)
        result = json.loads(await status({}, state))
        assert result["period"] == "lifetime"


class TestBillingStatusUrlInference:
    """Verify the dataclass-level inference fallback (used when the relay
    response omits ``environment``)."""

    def test_billing_status_with_explicit_environment(self) -> None:
        billing = BillingStatus(
            tier="free",
            free_writes_used=0,
            free_writes_limit=250,
            environment="staging",
        )
        assert billing.environment == "staging"

    def test_billing_status_environment_optional(self) -> None:
        """Default is None — RelayClient.get_billing_status fills it in."""
        billing = BillingStatus(
            tier="free",
            free_writes_used=0,
            free_writes_limit=250,
        )
        assert billing.environment is None
