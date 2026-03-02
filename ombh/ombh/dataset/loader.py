"""Dataset loader for benchmark conversations."""

import json
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import yaml

from ombh.backends.base import Fact


class Conversation:
    """A multi-session conversation for benchmarking."""

    def __init__(
        self,
        conversation_id: str,
        sessions: List[Dict[str, Any]],
        ground_truth_queries: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.conversation_id = conversation_id
        self.sessions = sessions
        self.ground_truth_queries = ground_truth_queries
        self.metadata = metadata or {}

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "Conversation":
        return cls(
            conversation_id=data["conversation_id"],
            sessions=data.get("sessions", []),
            ground_truth_queries=data.get("ground_truth_queries", []),
            metadata=data.get("metadata"),
        )


class DatasetLoader:
    """Load benchmark datasets from various sources."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config = self._load_config(config_path) if config_path else {}

    def _load_config(self, path: Path) -> Dict[str, Any]:
        with open(path) as f:
            return yaml.safe_load(f)

    def load_jsonl(self, path: Path) -> Iterator[Conversation]:
        """Load conversations from JSONL file."""
        with open(path) as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    yield Conversation.from_json(data)

    def load_anchor_tier(self, base_path: Path) -> Iterator[Conversation]:
        """Load WhatsApp anchor tier data."""
        # Processed WhatsApp data
        whatsapp_path = base_path / "testbed/v2-realworld-data/processed"
        # TODO: Implement actual loading
        yield from []

    def load_locomo(self, base_path: Path) -> Iterator[Conversation]:
        """Load LoCoMo-10 dataset."""
        locomo_path = base_path / "dataset" / "locomo"
        # TODO: Download and load LoCoMo
        yield from []

    def load_synthetic(self, base_path: Path) -> Iterator[Conversation]:
        """Load synthetic OpenClaw conversations."""
        synthetic_path = base_path / "dataset" / "openclaw_synthetic.jsonl"
        if synthetic_path.exists():
            yield from self.load_jsonl(synthetic_path)

    def load_all(self, base_path: Path) -> Iterator[Conversation]:
        """Load all configured datasets."""
        tiers = self.config.get("dataset", {}).get("tiers", ["anchor", "locomo", "synthetic"])

        if "anchor" in tiers:
            yield from self.load_anchor_tier(base_path)
        if "locomo" in tiers:
            yield from self.load_locomo(base_path)
        if "synthetic" in tiers:
            yield from self.load_synthetic(base_path)
