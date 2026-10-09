"""Minimal response-cache interface shared by Redis and isolated test doubles."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class CacheInterface(ABC):
    """Minimal cache interface: get / set."""

    @abstractmethod
    def get(self, key: str) -> Optional[Any]: ...

    @abstractmethod
    def set(self, key: str, value: Any, ttl: int = 300) -> None: ...
