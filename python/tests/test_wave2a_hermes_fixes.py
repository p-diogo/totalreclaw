"""Tests for Wave 2a Hermes fixes (Python 2.2.2 / Plugin 3.2.1).

Covers the three bugs surfaced in the 2026-04-20 QA run of
``totalreclaw==2.2.1`` on the VPS — see
``docs/notes/QA-hermes-RC-2.2.1-20260420.md`` (internal repo) for the
source-of-truth finding details.

Wave 2a bug numbering mirrors the QA report:
- Bug #4: ``auto_extract`` still requires ``OPENAI_MODEL`` even when
          ``~/.hermes/config.yaml`` has a valid model + provider.
- Bug #7: ``~/.totalreclaw/credentials.json`` key divergence —
          Python wrote ``recovery_phrase``, plugin 3.2.0 wrote
          ``mnemonic``. Cross-client portability broken.
- Bug #8: Python ``pin_fact()`` only emits a v=3 tombstone on-chain;
          the companion v=4 ``pin_status: pinned`` claim that plugin
          3.2.0 + MCP 3.2.0 (PR #51) produce was missing.
"""
from __future__ import annotations

import base64
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from totalreclaw.agent.llm_client import (
    LLMConfig,
    _extract_provider_and_model,
    detect_llm_config,
    read_hermes_llm_config,
)


# ----------------------------------------------------------------------------
# Bug #4 — Hermes config.yaml + .env picks up provider/model
# ----------------------------------------------------------------------------


class TestBug4HermesConfigYaml:
    """``read_hermes_llm_config`` must accept the actual YAML shape that
    Hermes writes (top-level ``provider`` + ``model`` keys), NOT only the
    nested ``model: {provider, model}`` shape that the 2.2.1 helper required.
    """

    def test_extract_accepts_top_level_provider_model(self):
        cfg = {"provider": "zai", "model": "glm-5-turbo"}
        provider, model = _extract_provider_and_model(cfg)
        assert provider == "zai"
        assert model == "glm-5-turbo"

    def test_extract_accepts_nested_model_block(self):
        """Defensive — future-proofs against Hermes reorganizing."""
        cfg = {"model": {"provider": "openai", "model": "gpt-4o-mini"}}
        provider, model = _extract_provider_and_model(cfg)
        assert provider == "openai"
        assert model == "gpt-4o-mini"

    def test_extract_missing_keys_returns_empty(self):
        assert _extract_provider_and_model({}) == ("", "")
        assert _extract_provider_and_model({"provider": "zai"}) == ("", "")
        assert _extract_provider_and_model({"model": "glm-5-turbo"}) == ("", "")

    def test_read_hermes_llm_config_resolves_with_top_level_yaml(self, tmp_path, monkeypatch):
        """End-to-end: top-level YAML + adjacent .env → full LLMConfig.

        This reproduces the QA scenario EXACTLY — ``config.yaml`` with
        ``provider: zai`` + ``model: glm-5-turbo`` top-level keys and
        ``.env`` carrying only ``ZAI_API_KEY``. No ``OPENAI_MODEL`` in
        process env. Prior to 2.2.2 this returned ``None``.
        """
        hermes_dir = tmp_path / ".hermes"
        hermes_dir.mkdir()
        (hermes_dir / "config.yaml").write_text(
            yaml.safe_dump({"provider": "zai", "model": "glm-5-turbo"})
        )
        (hermes_dir / ".env").write_text("ZAI_API_KEY=zai-key-123\n")

        # Force the helper to look at our tmp_path (via HERMES_CONFIG override).
        monkeypatch.setenv("HERMES_CONFIG", str(hermes_dir / "config.yaml"))
        # Clear all provider env vars so no env-only path resolves first.
        for k in ("ZAI_API_KEY", "OPENAI_API_KEY", "OPENAI_MODEL", "GLM_API_KEY"):
            monkeypatch.delenv(k, raising=False)

        config = read_hermes_llm_config()
        assert config is not None, "expected LLMConfig from top-level YAML shape"
        assert config.model == "glm-5-turbo"
        assert config.api_key == "zai-key-123"
        assert config.api_format == "openai"
        assert "z.ai" in config.base_url

    def test_read_hermes_llm_config_returns_none_when_no_key(self, tmp_path, monkeypatch):
        """Config present but .env missing the provider key → None."""
        hermes_dir = tmp_path / ".hermes"
        hermes_dir.mkdir()
        (hermes_dir / "config.yaml").write_text(
            yaml.safe_dump({"provider": "zai", "model": "glm-5-turbo"})
        )
        # No .env file at all.

        monkeypatch.setenv("HERMES_CONFIG", str(hermes_dir / "config.yaml"))
        for k in ("ZAI_API_KEY", "OPENAI_API_KEY", "OPENAI_MODEL", "GLM_API_KEY"):
            monkeypatch.delenv(k, raising=False)

        assert read_hermes_llm_config() is None

    def test_detect_llm_config_falls_through_to_hermes_when_env_bare(
        self, tmp_path, monkeypatch
    ):
        """The headline fix: ``detect_llm_config()`` resolves via Hermes
        YAML when NO env vars are set. This is the path ``extract_facts_llm``
        takes when no ``llm_config`` is passed explicitly.
        """
        hermes_dir = tmp_path / ".hermes"
        hermes_dir.mkdir()
        (hermes_dir / "config.yaml").write_text(
            yaml.safe_dump({"provider": "zai", "model": "glm-5-turbo"})
        )
        (hermes_dir / ".env").write_text("ZAI_API_KEY=zai-abc\n")

        monkeypatch.setenv("HERMES_CONFIG", str(hermes_dir / "config.yaml"))
        # Clear all provider env vars so the env-only path returns None.
        for k in (
            "ZAI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
            "OPENAI_MODEL", "ANTHROPIC_MODEL", "LLM_MODEL",
            "GLM_API_KEY", "GROQ_API_KEY", "DEEPSEEK_API_KEY",
            "OPENROUTER_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
            "XAI_API_KEY", "TOGETHER_API_KEY", "MISTRAL_API_KEY",
        ):
            monkeypatch.delenv(k, raising=False)

        config = detect_llm_config()
        assert config is not None, (
            "detect_llm_config should fall through to Hermes config.yaml "
            "when no env vars resolve"
        )
        assert config.model == "glm-5-turbo"
        assert config.api_key == "zai-abc"

    def test_detect_llm_config_prefers_env_over_hermes(self, tmp_path, monkeypatch):
        """Env vars take priority — if the user set both, we trust the env."""
        hermes_dir = tmp_path / ".hermes"
        hermes_dir.mkdir()
        (hermes_dir / "config.yaml").write_text(
            yaml.safe_dump({"provider": "zai", "model": "glm-5-turbo"})
        )
        (hermes_dir / ".env").write_text("ZAI_API_KEY=zai-from-hermes\n")

        monkeypatch.setenv("HERMES_CONFIG", str(hermes_dir / "config.yaml"))
        # Clear most, keep OPENAI_API_KEY + OPENAI_MODEL for env priority path.
        for k in (
            "ZAI_API_KEY", "ANTHROPIC_API_KEY", "GLM_API_KEY",
            "ANTHROPIC_MODEL", "LLM_MODEL",
        ):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env-wins")
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")

        config = detect_llm_config()
        assert config is not None
        # Env priority: should resolve via OPENAI_API_KEY + OPENAI_MODEL,
        # not the z.ai path from config.yaml.
        assert config.model == "gpt-4o-mini"
        assert config.api_key == "sk-env-wins"


# ----------------------------------------------------------------------------
# Bug #7 — credentials.json key parity
# ----------------------------------------------------------------------------


class TestBug7CredentialsKeyParity:
    """Python must accept BOTH ``mnemonic`` (canonical) and
    ``recovery_phrase`` (legacy) on read, and emit canonical ``mnemonic``
    on write. Plugin 3.2.0 already does this — symmetric parity is the
    Wave 2a fix on the Python side.
    """

    def test_state_reads_legacy_recovery_phrase_key(self, tmp_path, monkeypatch):
        """Pre-2.2.2 fixture: file keyed as ``recovery_phrase`` still loads."""
        from totalreclaw.agent.state import AgentState

        monkeypatch.setenv("HOME", str(tmp_path))
        creds_dir = tmp_path / ".totalreclaw"
        creds_dir.mkdir()
        (creds_dir / "credentials.json").write_text(
            json.dumps({"recovery_phrase": "abandon " * 11 + "about"})
        )

        # Clear any auto-configure env that would short-circuit.
        monkeypatch.delenv("TOTALRECLAW_RECOVERY_PHRASE", raising=False)

        with patch("pathlib.Path.home", return_value=tmp_path):
            state = AgentState()

        assert state.is_configured(), "state should configure from legacy recovery_phrase key"

    def test_state_reads_canonical_mnemonic_key(self, tmp_path, monkeypatch):
        """Plugin-3.2.0-written file (mnemonic key) also loads."""
        from totalreclaw.agent.state import AgentState

        monkeypatch.setenv("HOME", str(tmp_path))
        creds_dir = tmp_path / ".totalreclaw"
        creds_dir.mkdir()
        (creds_dir / "credentials.json").write_text(
            json.dumps({"mnemonic": "abandon " * 11 + "about"})
        )
        monkeypatch.delenv("TOTALRECLAW_RECOVERY_PHRASE", raising=False)

        with patch("pathlib.Path.home", return_value=tmp_path):
            state = AgentState()

        assert state.is_configured(), "state should configure from canonical mnemonic key"

    def test_state_prefers_mnemonic_when_both_keys_present(self, tmp_path, monkeypatch):
        """Canonical wins — both keys present → ``mnemonic`` is used."""
        from totalreclaw.agent.state import AgentState

        creds_dir = tmp_path / ".totalreclaw"
        creds_dir.mkdir()
        (creds_dir / "credentials.json").write_text(
            json.dumps({
                "mnemonic": "abandon " * 11 + "about",
                "recovery_phrase": "different " * 11 + "phrase",
            })
        )
        monkeypatch.delenv("TOTALRECLAW_RECOVERY_PHRASE", raising=False)

        with patch("pathlib.Path.home", return_value=tmp_path):
            state = AgentState()

        assert state.is_configured()
        # Can't directly inspect the stored mnemonic without exposing it;
        # the observable effect is that the canonical key wins. We verify
        # that by calling configure() via the loader and checking the
        # EOA address matches the canonical phrase.
        from totalreclaw.client import _get_eoa_address
        expected_eoa = _get_eoa_address("abandon " * 11 + "about")
        assert state._client._eoa_address.lower() == expected_eoa.lower()

    def test_state_writes_canonical_mnemonic_key(self, tmp_path, monkeypatch):
        """After configure(), credentials.json should use the canonical
        ``mnemonic`` key going forward.
        """
        from totalreclaw.agent.state import AgentState

        monkeypatch.delenv("TOTALRECLAW_RECOVERY_PHRASE", raising=False)

        with patch("pathlib.Path.home", return_value=tmp_path):
            state = AgentState()
            assert not state.is_configured()
            state.configure("abandon " * 11 + "about")

        creds = json.loads((tmp_path / ".totalreclaw" / "credentials.json").read_text())
        assert creds.get("mnemonic") == "abandon " * 11 + "about", (
            f"write path must emit canonical mnemonic key (2.2.2); got: {creds}"
        )

    def test_state_write_preserves_existing_recovery_phrase_file(self, tmp_path):
        """If a legacy ``recovery_phrase`` file already exists, don't
        clobber it on configure() — leave it until the user re-onboards.

        Rationale: the file is 0600 and the user may have external
        tooling that reads it. Migration is opt-in (next fresh onboarding
        writes the canonical key).
        """
        from totalreclaw.agent.state import AgentState

        creds_dir = tmp_path / ".totalreclaw"
        creds_dir.mkdir()
        legacy_payload = {"recovery_phrase": "abandon " * 11 + "about"}
        (creds_dir / "credentials.json").write_text(json.dumps(legacy_payload))

        with patch("pathlib.Path.home", return_value=tmp_path):
            state = AgentState()
            assert state.is_configured(), "legacy-key file should still load"

            # Calling configure() with the SAME mnemonic shouldn't flip the
            # key (no "migration" on touch). Only a fresh configure() with
            # a different mnemonic writes the canonical key.
            state.configure("abandon " * 11 + "about")

        # Legacy key preserved, no accidental downgrade.
        creds = json.loads((creds_dir / "credentials.json").read_text())
        assert "recovery_phrase" in creds, "must not drop the legacy key silently"


# ----------------------------------------------------------------------------
# Bug #8 — Python pin path must emit v=4 pinned claim
# ----------------------------------------------------------------------------


TEST_MNEMONIC_PIN = (
    "abandon abandon abandon abandon abandon abandon abandon abandon "
    "abandon abandon abandon about"
)


class TestBug8PinEmitsV4Pinned:
    """Python's ``pin_fact`` must emit a v=4 protobuf wrapper with an
    inner v1.1 ``MemoryClaimV1`` JSON blob carrying
    ``pin_status: "pinned"`` — matching the plugin's 3.2.0 pin path
    (``skill/plugin/pin.ts::executePinOperation``) and MCP 3.2.0 (PR #51).

    The QA report observed that 2.2.1 Python only wrote a v=3 tombstone;
    the companion v=4 pinned-claim payload was missing. These tests
    capture the two protobuf payloads the tombstone+new-fact write
    produces and assert on their shape.
    """

    @pytest.fixture
    def keys(self):
        from totalreclaw.crypto import derive_keys_from_mnemonic
        return derive_keys_from_mnemonic(TEST_MNEMONIC_PIN)

    @pytest.fixture
    def eoa(self):
        from eth_account import Account
        Account.enable_unaudited_hdwallet_features()
        acct = Account.from_mnemonic(TEST_MNEMONIC_PIN, account_path="m/44'/60'/0'/0/0")
        return acct.address, bytes(acct.key)

    @staticmethod
    def _make_v1_blob_fixture(text: str) -> str:
        """Produce a v1.1 MemoryClaimV1 JSON blob for the existing fact."""
        from totalreclaw.claims_helper import build_canonical_claim_v1

        class _Fake:
            pass

        f = _Fake()
        f.text = text
        f.type = "preference"
        f.importance = 7
        f.source = "user"
        f.scope = "work"
        f.confidence = 0.9
        f.entities = None
        f.reasoning = None
        f.volatility = "stable"
        return build_canonical_claim_v1(f, importance=7, claim_id="orig-fact-uuid")

    @staticmethod
    def _encrypted_hex(plaintext: str, key: bytes) -> str:
        from totalreclaw.crypto import encrypt
        b64 = encrypt(plaintext, key)
        return "0x" + base64.b64decode(b64).hex()

    def _build_relay_mock(self, keys, fact_id: str, claim_json: str):
        from totalreclaw.relay import RelayClient
        relay = AsyncMock(spec=RelayClient)
        relay._relay_url = "https://api.totalreclaw.xyz"
        relay._auth_key_hex = "deadbeef"
        relay._client_id = "test"

        async def query(query_str, variables, chain=None):
            if "fact(id" in query_str or "id: $id" in query_str:
                return {
                    "data": {
                        "fact": {
                            "id": fact_id,
                            "owner": "0x0000000000000000000000000000000000001234".lower(),
                            "encryptedBlob": self._encrypted_hex(claim_json, keys.encryption_key),
                            "encryptedEmbedding": None,
                            "decayScore": "0.7",
                            "timestamp": "1760000000",
                            "createdAt": "1760000000",
                            "isActive": True,
                            "contentFp": "abc",
                        }
                    }
                }
            return {"data": {}}

        relay.query_subgraph = AsyncMock(side_effect=query)
        return relay

    @staticmethod
    def _extract_protobuf_version(payload: bytes) -> int:
        """Extract the outer protobuf ``version`` field (field #11, wire type 0).

        Mirrors the helper in ``test_pin_unpin.py`` but scanning for the
        specific field we care about. Returns 0 if the field is absent.
        """
        from totalreclaw import protobuf
        # Rather than re-implement a parser, re-use the Python decoder.
        decoded = protobuf.decode_fact_protobuf(payload)
        return int(decoded.version or 0)

    @staticmethod
    def _extract_encrypted_blob(payload: bytes) -> bytes:
        from totalreclaw import protobuf
        decoded = protobuf.decode_fact_protobuf(payload)
        return decoded.encrypted_blob

    @pytest.mark.asyncio
    @patch("totalreclaw.operations.build_and_send_userop", new_callable=AsyncMock)
    async def test_pin_emits_v4_for_new_fact(self, mock_send, keys, eoa):
        """The new-fact write (after the tombstone) MUST carry
        ``protobuf version = 4`` and an inner v1 MemoryClaimV1 JSON blob.
        """
        from totalreclaw.operations import pin_fact

        eoa_addr, eoa_pk = eoa
        existing_blob = self._make_v1_blob_fixture("Pedro prefers dark mode")
        relay = self._build_relay_mock(keys, "orig-fact-uuid", existing_blob)

        captured: list[bytes] = []

        async def capture(**kwargs):
            captured.append(kwargs["protobuf_payload"])
            return "0xok"

        mock_send.side_effect = capture

        result = await pin_fact(
            fact_id="orig-fact-uuid",
            keys=keys,
            owner="0x0000000000000000000000000000000000001234",
            relay=relay,
            eoa_private_key=eoa_pk,
            eoa_address=eoa_addr,
            sender="0x0000000000000000000000000000000000001234",
        )

        assert result["success"] is True
        assert result["new_status"] == "pinned"
        assert len(captured) == 2, "expected tombstone + new-fact writes"

        # Second payload = new fact. MUST be v=4 (per QA bug #8).
        new_payload = captured[1]
        version = self._extract_protobuf_version(new_payload)
        assert version == 4, (
            f"new-fact payload must be protobuf v=4 (v1 taxonomy); "
            f"got v={version}. Bug #8: pin path was emitting v=3 in 2.2.1."
        )

    @pytest.mark.asyncio
    @patch("totalreclaw.operations.build_and_send_userop", new_callable=AsyncMock)
    async def test_pin_new_blob_carries_pin_status_pinned(self, mock_send, keys, eoa):
        """The inner blob of the new-fact v=4 payload must be a v1
        MemoryClaimV1 JSON with ``pin_status: "pinned"``.
        """
        from totalreclaw.crypto import decrypt
        from totalreclaw.operations import pin_fact

        eoa_addr, eoa_pk = eoa
        existing_blob = self._make_v1_blob_fixture("Sarah loves Django")
        relay = self._build_relay_mock(keys, "orig-fact-2", existing_blob)

        captured: list[bytes] = []

        async def capture(**kwargs):
            captured.append(kwargs["protobuf_payload"])
            return "0xok"

        mock_send.side_effect = capture

        await pin_fact(
            fact_id="orig-fact-2",
            keys=keys,
            owner="0x0000000000000000000000000000000000001234",
            relay=relay,
            eoa_private_key=eoa_pk,
            eoa_address=eoa_addr,
            sender="0x0000000000000000000000000000000000001234",
        )

        new_payload = captured[1]
        encrypted_blob = self._extract_encrypted_blob(new_payload)
        encrypted_b64 = base64.b64encode(encrypted_blob).decode("ascii")
        plaintext = decrypt(encrypted_b64, keys.encryption_key)

        parsed = json.loads(plaintext)
        assert parsed.get("schema_version", "").startswith("1."), (
            f"expected v1 MemoryClaimV1 JSON; got: {parsed}"
        )
        assert parsed.get("pin_status") == "pinned", (
            f"Bug #8: pin path must emit pin_status=pinned in v1 blob; got: {parsed}"
        )
        assert parsed.get("superseded_by") == "orig-fact-2", (
            "new v1 blob should link to the old fact via superseded_by"
        )
        # The v1 inner shape uses long-form keys — verify we're not
        # accidentally still emitting the short-key v0 format.
        assert "t" not in parsed or "text" in parsed, (
            "v1 blob should use long-form 'text', not short-key 't'"
        )
        assert parsed.get("text") == "Sarah loves Django"

    @pytest.mark.asyncio
    @patch("totalreclaw.operations.build_and_send_userop", new_callable=AsyncMock)
    async def test_pin_tombstone_remains_v3(self, mock_send, keys, eoa):
        """The first payload (tombstone) should remain at v=3 — matches
        plugin's behavior exactly (``pin.ts`` line 640: ``version = legacy v3``).
        """
        from totalreclaw.operations import pin_fact

        eoa_addr, eoa_pk = eoa
        existing_blob = self._make_v1_blob_fixture("some preference")
        relay = self._build_relay_mock(keys, "tombstone-fact", existing_blob)

        captured: list[bytes] = []

        async def capture(**kwargs):
            captured.append(kwargs["protobuf_payload"])
            return "0xok"

        mock_send.side_effect = capture

        await pin_fact(
            fact_id="tombstone-fact",
            keys=keys,
            owner="0x0000000000000000000000000000000000001234",
            relay=relay,
            eoa_private_key=eoa_pk,
            eoa_address=eoa_addr,
            sender="0x0000000000000000000000000000000000001234",
        )

        tombstone_payload = captured[0]
        version = self._extract_protobuf_version(tombstone_payload)
        # v=3 or v=0 (v=0 gets treated as default v=3 on decode).
        assert version in (0, 3), (
            f"tombstone should be protobuf v=3 (legacy); got v={version}"
        )


# ----------------------------------------------------------------------------
# Bug #7 — cross-client parity sanity check
# ----------------------------------------------------------------------------


class TestBug7CrossClientParity:
    """Round-trip sanity: a plugin-format credentials.json (canonical
    ``mnemonic`` key) read via the Python loader derives the same wallet
    as the same mnemonic fed through the Python client directly.

    This is the "cross-client" acceptance gate from the task scope: pick
    a sample mnemonic, write via one client's format, read via the
    other, and assert identical wallet derivation.
    """

    def test_plugin_written_mnemonic_derives_same_smart_account(self, tmp_path):
        """Simulate the plugin's write: ``{"mnemonic": "..."}`` file at
        the canonical path. Python loader derives the same EOA.
        """
        from totalreclaw.agent.state import AgentState
        from totalreclaw.client import _get_eoa_address

        test_mnemonic = (
            "letter sugar brave morning absurd pattern advice flight "
            "few pledge chef leisure"
        )

        creds_dir = tmp_path / ".totalreclaw"
        creds_dir.mkdir()
        (creds_dir / "credentials.json").write_text(
            json.dumps({"mnemonic": test_mnemonic})
        )

        with patch("pathlib.Path.home", return_value=tmp_path):
            state = AgentState()

        assert state.is_configured()
        expected_eoa = _get_eoa_address(test_mnemonic).lower()
        assert state._client._eoa_address.lower() == expected_eoa

    def test_python_written_mnemonic_readable_by_plugin_shape(self, tmp_path):
        """After 2.2.2's Python writes a fresh credentials.json, the
        resulting file has the ``mnemonic`` key — which is exactly what
        the plugin reads. This is the integrity guarantee: a user who
        sets up via Python can switch to the plugin without re-onboarding.
        """
        from totalreclaw.agent.state import AgentState

        test_mnemonic = (
            "letter sugar brave morning absurd pattern advice flight "
            "few pledge chef leisure"
        )

        with patch("pathlib.Path.home", return_value=tmp_path):
            state = AgentState()
            state.configure(test_mnemonic)

        creds = json.loads((tmp_path / ".totalreclaw" / "credentials.json").read_text())
        assert creds.get("mnemonic") == test_mnemonic, (
            "Python write path MUST emit canonical 'mnemonic' key "
            "for plugin compat (Bug #7)"
        )
