"""
LLM Client — Thin async wrapper around OpenAI-compatible APIs.

Supports:
- Ollama (highest priority if OLLAMA_MODEL set — local, no rate limits)
- Gemini (if GEMINI_API_KEY set — uses OpenAI-compatible v1beta endpoint)
- OpenRouter (fallback if OPENROUTER_API_KEY set)
- Z.AI Coding Plan (if ZAI_API_KEY set — uses /api/coding/paas/v4 endpoint)
- Z.AI Standard (fallback — uses /api/paas/v4 endpoint)
- Cross-provider fallback: Ollama -> Gemini -> OpenRouter -> Z.AI when quotas exhaust
- Automatic retry with exponential backoff for 429 / timeout
- Model fallback chain: tries primary model, then falls back to alternatives
- Token counting (input + output) per call and cumulative
- JSON output format when supported
- Temperature control for deterministic extraction (default 0.3)

Provider priority:
    1. Ollama — if OLLAMA_MODEL is set (local, unlimited, no API key needed)
    2. Gemini — if GEMINI_API_KEY is set (fast, free tier)
    3. OpenRouter — if OPENROUTER_API_KEY is set
    4. Z.AI Coding Plan (/api/coding/paas/v4) — if ZAI_API_KEY is set
    5. Z.AI Standard (/api/paas/v4) — fallback within Z.AI

When Gemini models exhaust their free tier quotas, the client automatically
falls back to OpenRouter (if OPENROUTER_API_KEY is also set), then Z.AI.

Usage:
    from ombh.llm.client import LLMClient

    client = LLMClient()  # reads OLLAMA_MODEL, GEMINI_API_KEY, OPENROUTER_API_KEY, or ZAI_API_KEY from env
    response = await client.complete(
        system="You are a fact extractor.",
        user="Extract facts from: ...",
    )
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Load .env from multiple possible locations
# ---------------------------------------------------------------------------
_PROJECT_ROOTS = [
    os.path.join(os.path.dirname(__file__), "..", ".."),       # ombh/ombh/llm -> ombh/ (inner package)
    os.path.join(os.path.dirname(__file__), "..", "..", ".."), # ombh/ombh/llm -> ombh project root (where .env lives)
    os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."),  # -> monorepo root
]
for _root in _PROJECT_ROOTS:
    _env_path = os.path.join(_root, ".env")
    if os.path.isfile(_env_path):
        load_dotenv(_env_path)


# ---------------------------------------------------------------------------
# Ollama (local) configuration — highest priority when OLLAMA_MODEL is set
# ---------------------------------------------------------------------------

_OLLAMA_BASE_URL = "http://localhost:11434/v1"
_OLLAMA_DUMMY_API_KEY = "ollama"  # Ollama ignores the API key but openai lib requires one

# ---------------------------------------------------------------------------
# Default model configuration (OpenRouter)
# ---------------------------------------------------------------------------

# Primary model — Llama 3.3 70B: fast, cheap ($0.12/$0.30 per M tokens), great at JSON
_DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"

# Fallback models in priority order (paid then free)
_FALLBACK_MODELS = [
    "qwen/qwen3-8b",
    "arcee-ai/trinity-large-preview:free",
    "stepfun/step-3.5-flash:free",
    "deepseek/deepseek-r1-0528:free",
    "openrouter/free",
]

# Default base URL for OpenRouter
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# ---------------------------------------------------------------------------
# Gemini model configuration (used when GEMINI_API_KEY is set)
# ---------------------------------------------------------------------------

# Gemini OpenAI-compatible endpoint
_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"

_GEMINI_DEFAULT_MODEL = "gemini-2.5-flash-lite"

_GEMINI_FALLBACK_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
]

# ---------------------------------------------------------------------------
# Z.AI model configuration (used when ZAI_API_KEY is set)
# ---------------------------------------------------------------------------

# Z.AI Coding Plan endpoint (subscription-based, higher quota)
_ZAI_CODING_BASE_URL = "https://api.z.ai/api/coding/paas/v4"
# Z.AI Standard endpoint (balance-based, free models available)
_ZAI_STANDARD_BASE_URL = "https://api.z.ai/api/paas/v4"

_ZAI_DEFAULT_MODEL = "glm-4.5-air"

_ZAI_FALLBACK_MODELS = [
    "glm-4.7",
    "glm-4.6",
    "glm-5",
]


# ---------------------------------------------------------------------------
# Provider configuration helper
# ---------------------------------------------------------------------------

@dataclass
class _ProviderConfig:
    """Configuration for a single LLM provider."""
    name: str
    api_key: str
    base_url: str
    model: str
    fallback_models: List[str]
    is_zai: bool = False
    is_gemini: bool = False
    is_ollama: bool = False


def _build_provider_chain(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    fallback_models: Optional[List[str]] = None,
) -> List[_ProviderConfig]:
    """
    Build an ordered list of provider configs to try.
    If explicit api_key/base_url are given, returns a single-provider chain.
    Otherwise builds Ollama -> Gemini -> OpenRouter -> Z.AI based on env vars.
    """
    if api_key and base_url:
        # Explicit config — single provider
        return [_ProviderConfig(
            name="custom",
            api_key=api_key,
            base_url=base_url,
            model=model or _DEFAULT_MODEL,
            fallback_models=fallback_models if fallback_models is not None else list(_FALLBACK_MODELS),
        )]

    providers: List[_ProviderConfig] = []

    ollama_model = os.environ.get("OLLAMA_MODEL")
    ollama_base_url = os.environ.get("OLLAMA_BASE_URL", _OLLAMA_BASE_URL)
    gemini_key = os.environ.get("GEMINI_API_KEY")
    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    zai_key = os.environ.get("ZAI_API_KEY")

    # Ollama (local) — highest priority when OLLAMA_MODEL is set
    if ollama_model:
        providers.append(_ProviderConfig(
            name="ollama",
            api_key=_OLLAMA_DUMMY_API_KEY,
            base_url=ollama_base_url,
            model=ollama_model,
            fallback_models=[],  # no fallbacks for local model
            is_ollama=True,
        ))

    if gemini_key:
        providers.append(_ProviderConfig(
            name="gemini",
            api_key=gemini_key,
            base_url=_GEMINI_BASE_URL,
            model=model or _GEMINI_DEFAULT_MODEL,
            fallback_models=fallback_models if fallback_models is not None else list(_GEMINI_FALLBACK_MODELS),
            is_gemini=True,
        ))

    if openrouter_key:
        providers.append(_ProviderConfig(
            name="openrouter",
            api_key=openrouter_key,
            base_url=_OPENROUTER_BASE_URL,
            model=model if (model and not model.startswith("gemini")) else _DEFAULT_MODEL,
            fallback_models=fallback_models if (fallback_models is not None and not any(m.startswith("gemini") for m in fallback_models)) else list(_FALLBACK_MODELS),
        ))

    if zai_key:
        providers.append(_ProviderConfig(
            name="zai",
            api_key=zai_key,
            base_url=os.environ.get("ZAI_BASE_URL", "https://api.z.ai/api/paas/v4"),
            model=model if (model and not model.startswith("gemini") and not "/" in (model or "")) else _ZAI_DEFAULT_MODEL,
            fallback_models=fallback_models if (fallback_models is not None and not any("/" in m for m in fallback_models)) else list(_ZAI_FALLBACK_MODELS),
            is_zai=True,
        ))

    if not providers:
        raise ValueError(
            "No API key found. Set OLLAMA_MODEL, GEMINI_API_KEY, OPENROUTER_API_KEY, ZAI_API_KEY, "
            "or pass api_key= to LLMClient."
        )

    return providers


# ---------------------------------------------------------------------------
# Usage tracking
# ---------------------------------------------------------------------------

@dataclass
class LLMUsageStats:
    """Cumulative token usage and cost tracking."""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_calls: int = 0
    total_errors: int = 0
    total_retries: int = 0
    total_latency_ms: float = 0.0
    per_call_latencies: List[float] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def avg_latency_ms(self) -> float:
        if not self.per_call_latencies:
            return 0.0
        return sum(self.per_call_latencies) / len(self.per_call_latencies)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "total_calls": self.total_calls,
            "total_errors": self.total_errors,
            "total_retries": self.total_retries,
            "total_latency_ms": self.total_latency_ms,
            "avg_latency_ms": self.avg_latency_ms,
        }


# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503}
_MAX_RETRIES = 4
_BASE_BACKOFF_S = 1.0  # doubles each attempt: 1, 2, 4, 8


# ---------------------------------------------------------------------------
# LLMClient
# ---------------------------------------------------------------------------

class LLMClient:
    """
    Async wrapper around an OpenAI-compatible chat completions endpoint.

    Supports cross-provider fallback: when all models on one provider are
    exhausted (e.g. Gemini free tier quota), automatically switches to the
    next provider (OpenRouter, Z.AI).

    Constructor args:
        api_key:         API key (falls back to GEMINI_API_KEY, OPENROUTER_API_KEY, then ZAI_API_KEY)
        base_url:        Base URL (falls back to provider-specific URL)
        model:           Primary model name
        fallback_models: List of fallback model names to try if primary fails
        temperature:     Sampling temperature (default 0.3 for deterministic extraction)
        max_tokens:      Max tokens in the response (default 4096)
        request_json:    Whether to request JSON output mode (default True)
        timeout:         Per-request timeout in seconds (default 180)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        fallback_models: Optional[List[str]] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        request_json: bool = True,
        timeout: float = 180.0,
    ):
        # Build the provider chain (Gemini -> OpenRouter -> Z.AI)
        self._provider_chain = _build_provider_chain(api_key, base_url, model, fallback_models)
        self._current_provider_idx = 0
        self._current_provider = self._provider_chain[0]

        # Set initial config from the first provider
        self._api_key = self._current_provider.api_key
        self._base_url = self._current_provider.base_url
        self._model = self._current_provider.model
        self._fallback_models = self._current_provider.fallback_models
        self._using_zai = self._current_provider.is_zai
        self._using_gemini = self._current_provider.is_gemini
        self._using_ollama = self._current_provider.is_ollama

        self._temperature = temperature
        self._max_tokens = max_tokens
        self._request_json = request_json
        self._timeout = timeout

        # Track which model is actually working (set after first success)
        self._active_model: Optional[str] = None

        # Lazy-initialised AsyncOpenAI client (rebuilt on provider switch)
        self._client: Any = None

        # Usage tracking
        self.usage = LLMUsageStats()

    def _switch_to_provider(self, idx: int) -> None:
        """Switch to a different provider in the chain."""
        if idx >= len(self._provider_chain):
            return
        self._current_provider_idx = idx
        self._current_provider = self._provider_chain[idx]
        self._api_key = self._current_provider.api_key
        self._base_url = self._current_provider.base_url
        self._model = self._current_provider.model
        self._fallback_models = self._current_provider.fallback_models
        self._using_zai = self._current_provider.is_zai
        self._using_gemini = self._current_provider.is_gemini
        self._using_ollama = self._current_provider.is_ollama
        self._active_model = None
        # Force client recreation
        self._client = None
        logger.info(
            "Switched to provider: %s (base_url=%s, model=%s)",
            self._current_provider.name,
            self._base_url,
            self._model,
        )

    @property
    def usage_stats(self) -> Dict[str, Any]:
        """Alias for usage.to_dict() for convenience."""
        return self.usage.to_dict()

    def _ensure_client(self) -> Any:
        """Lazily create the AsyncOpenAI client (avoids import at module level)."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError:
                raise ImportError(
                    "The 'openai' package is required.  Install it with: "
                    "pip install openai"
                )

            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=self._timeout,
            )
        return self._client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        request_json: Optional[bool] = None,
        model: Optional[str] = None,
    ) -> str:
        """
        Send a chat completion request and return the response text.

        If the primary model fails with a non-retryable error (e.g. spending
        limit, model not found, 402/403), automatically falls back through
        the fallback model chain. When all models on a provider are exhausted,
        switches to the next provider in the chain.

        Args:
            system:       System prompt
            user:         User prompt
            temperature:  Override instance temperature
            max_tokens:   Override instance max_tokens
            request_json: Override instance request_json
            model:        Override instance model (skips fallback if set)

        Returns:
            The assistant's response as a string.

        Raises:
            RuntimeError: If all models and providers are exhausted.
        """
        # If caller specified an explicit model, just try that one
        if model:
            return await self._complete_with_model(
                model=model,
                system=system,
                user=user,
                temperature=temperature,
                max_tokens=max_tokens,
                request_json=request_json,
            )

        # Try current provider's models, then fall back to next provider
        start_provider_idx = self._current_provider_idx
        last_error: Optional[Exception] = None

        for provider_idx in range(start_provider_idx, len(self._provider_chain)):
            if provider_idx != self._current_provider_idx:
                self._switch_to_provider(provider_idx)

            # Build model chain: active model (if known) > primary > fallbacks
            if self._active_model:
                models_to_try = [self._active_model]
            else:
                models_to_try = [self._model] + self._fallback_models

            for model_name in models_to_try:
                try:
                    result = await self._complete_with_model(
                        model=model_name,
                        system=system,
                        user=user,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        request_json=request_json,
                    )
                    # Mark this model as active for future calls
                    if self._active_model != model_name:
                        self._active_model = model_name
                        logger.info("Active model set to: %s (provider: %s)", model_name, self._current_provider.name)
                    return result

                except RuntimeError as e:
                    last_error = e
                    error_str = str(e)

                    # Determine if we should fall back to the next model
                    is_fallback_worthy = any(
                        indicator in error_str.lower()
                        for indicator in [
                            "spending limit",
                            "402",
                            "403",
                            "404",
                            "payment required",
                            "quota",
                            "insufficient",
                            "not found",
                            "does not exist",
                            "model_not_found",
                            "invalid_model",
                            "rate limit",
                            "rate-limit",
                            "429",
                        ]
                    )

                    # Also fall back if all retries were exhausted (any error)
                    if "failed after" in error_str.lower():
                        is_fallback_worthy = True

                    if is_fallback_worthy:
                        logger.warning(
                            "Model %s failed (%s), trying next fallback...",
                            model_name,
                            error_str[:150],
                        )
                        # Reset active model since it failed
                        if self._active_model == model_name:
                            self._active_model = None
                        continue
                    else:
                        raise

            # All models on this provider exhausted, try next provider
            if provider_idx < len(self._provider_chain) - 1:
                logger.warning(
                    "All models exhausted on provider %s, switching to next provider...",
                    self._current_provider.name,
                )
            else:
                # Last provider, no more fallbacks
                break

        raise RuntimeError(
            f"All models and providers exhausted. Last error: {last_error}"
        )

    async def _complete_with_model(
        self,
        model: str,
        system: str,
        user: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        request_json: Optional[bool] = None,
    ) -> str:
        """
        Send a chat completion request to a specific model with retries.

        Raises RuntimeError if all retries are exhausted.
        """
        client = self._ensure_client()

        # For Ollama with Qwen3-style models, disable thinking mode by
        # prepending /no_think to the user message. This prevents the model
        # from emitting <think>...</think> reasoning blocks.
        effective_user = user
        if self._using_ollama:
            effective_user = "/no_think\n" + user

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": effective_user},
        ]

        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self._temperature,
            "max_tokens": max_tokens or self._max_tokens,
        }

        # Request JSON output if supported.
        # Skip response_format for models on OpenRouter that may not support
        # structured output reliably (openrouter/free router, deepseek with
        # think tags, smaller models). The prompts already ask for JSON output,
        # and the parser handles markdown code blocks.
        # Gemini supports response_format with json_object when "JSON" is
        # mentioned in the prompt (our prompts do this).
        # Ollama supports response_format with json_object.
        use_json = request_json if request_json is not None else self._request_json
        _skip_json_format = (
            model.startswith("openrouter/")
            or model.startswith("deepseek/")
            or ":free" in model
            or self._using_zai  # Z.AI does not support response_format
        )
        if use_json and not _skip_json_format:
            kwargs["response_format"] = {"type": "json_object"}

        last_error: Optional[Exception] = None

        for attempt in range(_MAX_RETRIES + 1):
            start_time = time.monotonic()
            try:
                response = await client.chat.completions.create(**kwargs)

                latency_ms = (time.monotonic() - start_time) * 1000

                # Track usage
                self.usage.total_calls += 1
                self.usage.total_latency_ms += latency_ms
                self.usage.per_call_latencies.append(latency_ms)

                if response.usage:
                    self.usage.total_input_tokens += response.usage.prompt_tokens or 0
                    self.usage.total_output_tokens += response.usage.completion_tokens or 0

                # Keep rolling window of latencies (max 10k)
                if len(self.usage.per_call_latencies) > 10_000:
                    self.usage.per_call_latencies = self.usage.per_call_latencies[-10_000:]

                content = response.choices[0].message.content or ""
                # Strip <think>...</think> blocks (DeepSeek-R1 reasoning traces)
                import re as _re
                content = _re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
                # Strip markdown code blocks wrapping JSON
                code_match = _re.match(r"^```(?:json)?\s*([\s\S]*?)```$", content)
                if code_match:
                    content = code_match.group(1).strip()
                return content

            except Exception as e:
                latency_ms = (time.monotonic() - start_time) * 1000
                last_error = e
                error_str = str(e)

                # Determine if retryable (transient errors)
                is_retryable = False

                # Gemini daily quota exhaustion is NOT retryable — fail fast
                # to allow fallback to next model/provider instead of wasting
                # 15+ seconds on pointless retries
                error_lower = error_str.lower()
                if "quota" in error_lower and "exceeded" in error_lower:
                    if "perdayperproject" in error_lower or "perday" in error_lower:
                        self.usage.total_errors += 1
                        logger.warning(
                            "Daily quota exhausted for model %s, failing fast for fallback",
                            model,
                        )
                        raise RuntimeError(
                            f"LLM call failed after {attempt + 1} attempts with model "
                            f"{model}: daily quota exhausted - {error_str[:200]}"
                        ) from e

                # Check for HTTP status-based retries
                for code in _RETRYABLE_STATUS_CODES:
                    if str(code) in error_str:
                        is_retryable = True
                        break

                # Timeout errors are retryable
                if "timeout" in error_str.lower() or "timed out" in error_str.lower():
                    is_retryable = True

                # Connection errors are retryable
                if "connection" in error_str.lower():
                    is_retryable = True

                # Non-retryable errors (model-level): raise immediately for fallback
                if not is_retryable or attempt == _MAX_RETRIES:
                    self.usage.total_errors += 1
                    logger.error(
                        "LLM call failed [%s] (attempt %d/%d): %s",
                        model,
                        attempt + 1,
                        _MAX_RETRIES + 1,
                        error_str[:300],
                    )
                    raise RuntimeError(
                        f"LLM call failed after {attempt + 1} attempts with model "
                        f"{model}: {error_str}"
                    ) from e

                # Exponential backoff
                self.usage.total_retries += 1
                backoff = _BASE_BACKOFF_S * (2 ** attempt)

                # For 429, try to read Retry-After header value from error message
                if "429" in error_str:
                    import re
                    match = re.search(r"retry.?after[:\s]+(\d+\.?\d*)", error_str, re.I)
                    if match:
                        backoff = max(backoff, float(match.group(1)))

                logger.warning(
                    "Retryable error [%s] (attempt %d/%d), backing off %.1fs: %s",
                    model,
                    attempt + 1,
                    _MAX_RETRIES + 1,
                    backoff,
                    error_str[:200],
                )
                await asyncio.sleep(backoff)

        # Should not reach here, but just in case
        raise RuntimeError(f"LLM call failed with model {model}: {last_error}")

    async def complete_batch(
        self,
        prompts: List[Dict[str, str]],
        *,
        concurrency: int = 5,
        **kwargs,
    ) -> List[str]:
        """
        Run multiple completions with bounded concurrency.

        Args:
            prompts:     List of dicts with "system" and "user" keys
            concurrency: Max parallel requests (default 5)
            **kwargs:    Extra args forwarded to complete()

        Returns:
            List of response strings (same order as input).
        """
        semaphore = asyncio.Semaphore(concurrency)
        results: List[Optional[str]] = [None] * len(prompts)

        async def _run(index: int, prompt: Dict[str, str]) -> None:
            async with semaphore:
                try:
                    result = await self.complete(
                        system=prompt["system"],
                        user=prompt["user"],
                        **kwargs,
                    )
                    results[index] = result
                except Exception as e:
                    logger.error("Batch item %d failed: %s", index, e)
                    results[index] = ""

        tasks = [_run(i, p) for i, p in enumerate(prompts)]
        await asyncio.gather(*tasks)

        return [r or "" for r in results]

    def reset_usage(self) -> None:
        """Reset all usage counters."""
        self.usage = LLMUsageStats()

    def __repr__(self) -> str:
        return (
            f"LLMClient(model={self._model!r}, "
            f"base_url={self._base_url!r}, "
            f"provider={self._current_provider.name!r}, "
            f"temperature={self._temperature})"
        )
