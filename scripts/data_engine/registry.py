"""Adapter registry with duplicate protection and deterministic ordering."""

from __future__ import annotations

from .contracts import SourceAdapter


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, SourceAdapter] = {}

    def register(self, adapter: SourceAdapter) -> None:
        if adapter.source_key in self._adapters:
            raise ValueError(f"Adapter already registered: {adapter.source_key}")
        self._adapters[adapter.source_key] = adapter

    def get(self, source_key: str) -> SourceAdapter:
        try:
            return self._adapters[source_key]
        except KeyError as exc:
            raise KeyError(f"Unknown adapter: {source_key}") from exc

    def select(self, source_keys: list[str] | None = None) -> list[SourceAdapter]:
        keys = source_keys or list(self._adapters)
        return [self.get(key) for key in keys]

    def descriptors(self) -> list[dict[str, str]]:
        return [adapter.descriptor() for adapter in self._adapters.values()]
