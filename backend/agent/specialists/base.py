"""VESPER Specialist Agent Base Contract.

Defines the standard interface for all specialist agents in the VESPER swarm.
Specialists expose:
  1. `get_capabilities()`: High-level domain summary for Alfred's Stage 1 Planner.
  2. `get_tool_schemas()`: OpenAI-compatible JSON schemas for fine-grained tool calls.
  3. `execute()`: Uniform async execution returning structured `SpecialistResult`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SpecialistResult(BaseModel):
    """Standard execution result returned by all specialist agents."""

    success: bool = True
    action: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)
    speech_summary: str = ""
    card_payload: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class BaseSpecialist(ABC):
    """Abstract base class for all specialist sub-agents."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this specialist (e.g., 'tasks', 'finance', 'media')."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of this specialist's role."""
        pass

    @abstractmethod
    def get_capabilities(self) -> str:
        """Concise summary of this specialist's domain capabilities for Stage 1 planning.

        Should be 1-2 sentences to minimize prompt token overhead.
        """
        pass

    @abstractmethod
    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Returns JSON schema definitions of tools exposed by this specialist."""
        pass

    @abstractmethod
    async def execute(
        self, action: str, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> SpecialistResult:
        """Executes a specific tool action with the provided parameters."""
        pass
