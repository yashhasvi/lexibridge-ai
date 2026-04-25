"""AbstractStore — base interface for all storage backends."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AbstractStore(ABC):
    @abstractmethod
    def close(self) -> None: ...

    def __enter__(self) -> "AbstractStore":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
