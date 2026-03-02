"""
Multi-Variant Blind Index Generator for OpenMemory v0.5

Implements:
- Fast path: Regex-based multi-variant generation
- Smart path: LLM-based context-aware variant generation

This extends v0.2's single-variant approach with multiple variants per entity.
"""

import re
import hmac
import hashlib
from typing import Set, List, Optional, Dict, Any
from dataclasses import dataclass
from abc import ABC, abstractmethod

from .prompts import LLMVariantPrompt


@dataclass
class EntityMatch:
    """A matched entity in text."""
    entity: str
    start: int
    end: int
    entity_type: str


class VariantGenerator(ABC):
    """Base class for variant generators."""

    @abstractmethod
    def generate_variants(self, entity: str, entity_type: str) -> Set[str]:
        """Generate search variants for an entity."""
        pass


class RegexVariantGenerator(VariantGenerator):
    """
    Fast-path variant generation using regex patterns.

    Generates variants for:
    - Emails: full, local-part, domain
    - UUIDs: full, prefix, suffix
    - API keys: full, prefix, components
    - Code paths: full, with separator substitutions
    """

    # Separator substitution patterns
    SEPARATORS = ['-', '_', '.', '/']

    def generate_variants(self, entity: str, entity_type: str) -> Set[str]:
        """
        Generate regex-based variants for an entity.

        Args:
            entity: The entity string
            entity_type: Type of entity (email, uuid, api_key, etc.)

        Returns:
            Set of variant strings
        """
        variants = set()

        if entity_type == "email":
            variants.update(self._email_variants(entity))
        elif entity_type == "uuid":
            variants.update(self._uuid_variants(entity))
        elif entity_type == "api_key":
            variants.update(self._api_key_variants(entity))
        else:
            variants.update(self._generic_variants(entity))

        return variants

    def _email_variants(self, email: str) -> Set[str]:
        """Generate variants for email addresses."""
        variants = set()

        # Full email (lowercase)
        variants.add(email.lower())

        # Local part (before @)
        if '@' in email:
            local = email.split('@')[0]
            variants.add(local.lower())

            # Domain (after @)
            domain = email.split('@')[1]
            variants.add(domain.lower())

        return variants

    def _uuid_variants(self, uuid_str: str) -> Set[str]:
        """Generate variants for UUIDs."""
        variants = set()

        # Full UUID (lowercase)
        variants.add(uuid_str.lower())

        # Prefix (first 8 chars)
        if len(uuid_str) >= 8:
            variants.add(uuid_str[:8].lower())

        # Suffix (last 8 chars)
        if len(uuid_str) >= 8:
            variants.add(uuid_str[-8:].lower())

        return variants

    def _api_key_variants(self, key: str) -> Set[str]:
        """Generate variants for API keys."""
        variants = set()

        # Full key
        variants.add(key)

        # Prefix (first 8 chars)
        if len(key) >= 8:
            variants.add(key[:8])

        # Split by separators
        parts = re.split(r'[-_./]', key)

        # Add individual parts
        for part in parts:
            if len(part) >= 4:
                variants.add(part)

        return variants

    def _generic_variants(self, entity: str) -> Set[str]:
        """Generate variants for generic entities."""
        variants = set()

        # Lowercase
        variants.add(entity.lower())

        # Split by separators
        parts = re.split(r'[-_./]', entity)

        # Add prefix variants
        for i in range(1, min(len(parts), 3)):
            variant = '-'.join(parts[:i])
            if variant:
                variants.add(variant.lower())

        # Add suffix variants
        for i in range(len(parts), max(len(parts) - 2, 1), -1):
            variant = '-'.join(parts[i-1:])
            if variant:
                variants.add(variant.lower())

        # Separator substitutions
        for sep in self.SEPARATORS:
            if sep in entity:
                for alt_sep in self.SEPARATORS:
                    if alt_sep != sep:
                        variants.add(entity.replace(sep, alt_sep).lower())

        return variants


class LLMVariantGenerator(VariantGenerator):
    """
    Smart-path variant generation using LLM.

    Generates context-aware variants that regex cannot capture:
    - Project names with synonyms
    - Error codes with contextual meanings
    - Domain-specific concepts
    """

    def __init__(self, llm_client):
        """
        Initialize with LLM client.

        Args:
            llm_client: Client for the agent's LLM
        """
        self.llm_client = llm_client

    def generate_variants(self, entity: str, entity_type: str) -> Set[str]:
        """
        Generate LLM-based variants (not used directly - called via generate_from_text).

        This method is a placeholder. The main entry point is generate_from_text.
        """
        return {entity.lower()}

    def generate_from_text(self, text: str, max_variants: int = 20) -> Set[str]:
        """
        Extract entities and generate variants from full text using LLM.

        Args:
            text: The text to analyze
            max_variants: Maximum number of variants to generate

        Returns:
            Set of variant strings
        """
        # Format prompt
        prompt = LLMVariantPrompt.format_prompt(text)

        # Call LLM
        response = self._call_llm(prompt)

        # Parse response
        variants = self._parse_llm_response(response)

        # Limit variants
        return set(list(variants)[:max_variants])

    def _call_llm(self, prompt: str) -> str:
        """
        Call the LLM with the prompt.

        Args:
            prompt: The formatted prompt

        Returns:
            LLM response text
        """
        # This is a generic interface - adapt to your LLM client
        if hasattr(self.llm_client, 'complete'):
            return self.llm_client.complete(prompt)
        elif hasattr(self.llm_client, 'generate'):
            return self.llm_client.generate(prompt)
        elif callable(self.llm_client):
            return self.llm_client(prompt)
        else:
            raise ValueError(
                "LLM client must have 'complete', 'generate' method, or be callable"
            )

    def _parse_llm_response(self, response: str) -> Set[str]:
        """
        Parse LLM response to extract variants.

        Args:
            response: LLM response text

        Returns:
            Set of variant strings
        """
        import json

        variants = set()

        try:
            # Try to parse as JSON
            data = json.loads(response)

            for entity_data in data.get('entities', []):
                # Add original
                original = entity_data.get('original', '')
                if original:
                    variants.add(original.lower())

                # Add variants
                for variant in entity_data.get('variants', []):
                    if variant:
                        variants.add(variant.lower())

        except json.JSONDecodeError:
            # Fallback: extract potential variants from text
            # Look for quoted strings or comma-separated values
            matches = re.findall(r'"([^"]+)"', response)
            variants.update(m.lower() for m in matches)

        return variants


class MultiVariantBlindIndexGenerator:
    """
    Generates multi-variant blind indices for encrypted search.

    Combines:
    - Fast path: Regex-based variants (~10-30ms)
    - Smart path: LLM-based variants (~250-550ms)

    Zero-Knowledge Properties:
    - All variants are hashed with HMAC-SHA256
    - Server cannot reverse hashes to get plaintext
    """

    # Regex patterns for entity extraction
    PATTERNS = {
        "email": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
        "uuid": re.compile(r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b'),
        "api_key": re.compile(r'\b(sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{36,})\b'),
        "error_code": re.compile(r'\b(ERR-[0-9]+|HTTP-[0-9]{3})\b'),
    }

    def __init__(self, blind_key: bytes, llm_client=None):
        """
        Initialize multi-variant blind index generator.

        Args:
            blind_key: 256-bit key for HMAC-SHA256
            llm_client: Optional LLM client for smart-path generation
        """
        self.blind_key = blind_key
        self.llm_client = llm_client

        self.regex_generator = RegexVariantGenerator()

        if llm_client:
            self.llm_generator = LLMVariantGenerator(llm_client)
        else:
            self.llm_generator = None

    def generate_blind_indices(
        self,
        text: str,
        use_llm: bool = True
    ) -> Set[str]:
        """
        Generate multi-variant blind indices for text.

        Args:
            text: The text to generate indices for
            use_llm: Whether to use LLM for smart-path generation

        Returns:
            Set of hex-encoded HMAC-SHA256 hashes
        """
        all_variants = set()

        # Fast path: Regex-based extraction and variants
        regex_variants = self._generate_regex_variants(text)
        all_variants.update(regex_variants)

        # Smart path: LLM-based variants
        if use_llm and self.llm_generator:
            llm_variants = self.llm_generator.generate_from_text(text)
            all_variants.update(llm_variants)

        # Hash all variants to create blind indices
        blind_indices = set()
        for variant in all_variants:
            blind_index = self._hash_variant(variant)
            blind_indices.add(blind_index)

        return blind_indices

    def generate_query_blind_indices(
        self,
        query: str,
        use_llm: bool = False
    ) -> Set[str]:
        """
        Generate blind indices for a search query.

        Args:
            query: The search query
            use_llm: Whether to use LLM for query expansion

        Returns:
            Set of hex-encoded HMAC-SHA256 hashes
        """
        all_variants = set()

        # Always include the full query
        all_variants.add(query.lower())

        # Fast path: Extract and variant entities from query
        regex_variants = self._generate_regex_variants(query)
        all_variants.update(regex_variants)

        # Optional: LLM query expansion
        if use_llm and self.llm_generator:
            from .prompts import QueryExpansionPrompt
            prompt = QueryExpansionPrompt.format_prompt(query)
            response = self.llm_generator._call_llm(prompt)

            try:
                import json
                data = json.loads(response)
                expanded = data.get('expanded_terms', [])
                all_variants.update(term.lower() for term in expanded)
            except json.JSONDecodeError:
                pass  # Fall back to regex only

        # Hash all variants
        blind_indices = set()
        for variant in all_variants:
            blind_index = self._hash_variant(variant)
            blind_indices.add(blind_index)

        return blind_indices

    def _generate_regex_variants(self, text: str) -> Set[str]:
        """Generate variants using regex-based entity extraction."""
        variants = set()

        for entity_type, pattern in self.PATTERNS.items():
            for match in pattern.finditer(text):
                entity = match.group()
                entity_variants = self.regex_generator.generate_variants(
                    entity, entity_type
                )
                variants.update(entity_variants)

        return variants

    def _hash_variant(self, variant: str) -> str:
        """Hash a variant using HMAC-SHA256."""
        h = hmac.new(
            self.blind_key,
            variant.encode('utf-8'),
            hashlib.sha256
        )
        return h.hexdigest()
