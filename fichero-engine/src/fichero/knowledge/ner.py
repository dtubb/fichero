"""Shared NER contracts and record types.

These types are intentionally lightweight so both the workflow layer and
the KG helpers can share one provider abstraction without importing the
full extraction toolchain.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class ExtractedEntity(BaseModel):
    """Normalised entity record returned by every NER provider."""

    model_config = ConfigDict(extra="forbid")

    name: str
    type: str
    confidence: float = 1.0
    source_offsets: tuple[int, int] | None = None
    provider_name: str
    model_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class NERProvider(Protocol):
    """Interface shared by all NER backends."""

    name: str
    model_name: str | None

    async def extract(
        self,
        text: str,
        *,
        language: str | None = None,
        state: Any | None = None,
        llm_config: Any | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> list[ExtractedEntity]:
        """Extract entities from text."""


class BaseNERProvider(ABC):
    """Convenience base class for NER providers."""

    name: str
    model_name: str | None

    @abstractmethod
    async def extract(
        self,
        text: str,
        *,
        language: str | None = None,
        state: Any | None = None,
        llm_config: Any | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> list[ExtractedEntity]:
        """Extract entities from text."""


__all__ = [name for name in globals() if not name.startswith("__")]
