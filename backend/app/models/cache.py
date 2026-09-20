"""Persistent cache rows for expensive third-party responses.

The application cache used to live only in process memory, which on a host that
restarts, sleeps, or runs several workers meant every search hit the paid search
API again. Rows here survive all of that and are shared by every worker.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ApiCache(Base):
    __tablename__ = "api_cache"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
