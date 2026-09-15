from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class EmailResult(BaseModel):
    ok: bool
    provider: str
    message_id: str | None = None
    error: str | None = None
    skipped: bool = False


class BaseEmailProvider(ABC):
    name: str = "base"

    @property
    def enabled(self) -> bool:
        return True

    @abstractmethod
    async def send(
        self, to: str, subject: str, text: str, html: str | None = None
    ) -> EmailResult: ...
