from abc import ABC, abstractmethod
from typing import Type, TypeVar, Optional
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class AIProvider(ABC):
    """Abstract interface for AI model integration."""

    @abstractmethod
    async def structured_output(
        self,
        prompt: str,
        schema: Type[T],
        system_instruction: str = "",
        model: Optional[str] = None
    ) -> T:
        """Generates structured output conforming strictly to the provided Pydantic schema."""
        pass

    @abstractmethod
    async def generate_prose(
        self,
        prompt: str,
        system_instruction: str = "",
        model: Optional[str] = None
    ) -> str:
        """Generates evocative narrative prose."""
        pass
