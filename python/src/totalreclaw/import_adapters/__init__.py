"""Back-compat shim: import adapters now live in ``totalreclaw.imports.adapters``.

Re-exports the public adapter API from its new home so existing
``from totalreclaw.import_adapters import get_adapter`` imports keep working.
Reach-ins to individual adapter submodules should use the new
``totalreclaw.imports.adapters.<name>`` paths.
"""

from totalreclaw.imports.adapters import (
    get_adapter,
    list_sources,
    BaseImportAdapter,
    GeminiAdapter,
    ChatGPTAdapter,
    ClaudeAdapter,
    Mem0Adapter,
    ImportSource,
    NormalizedFact,
    ConversationChunk,
    AdapterParseResult,
    BatchImportResult,
)

__all__ = [
    "get_adapter",
    "list_sources",
    "BaseImportAdapter",
    "GeminiAdapter",
    "ChatGPTAdapter",
    "ClaudeAdapter",
    "Mem0Adapter",
    "ImportSource",
    "NormalizedFact",
    "ConversationChunk",
    "AdapterParseResult",
    "BatchImportResult",
]
