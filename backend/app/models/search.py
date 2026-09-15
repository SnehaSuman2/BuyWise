"""Search history model."""

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONType, TimestampMixin, UUIDMixin, UUIDType


class Search(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "searches"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    query_text: Mapped[str | None] = mapped_column(Text)
    query_type: Mapped[str | None] = mapped_column(String(20))  # text | url | image
    query_url: Mapped[str | None] = mapped_column(Text)
    results_count: Mapped[int | None] = mapped_column(Integer)
    filters: Mapped[dict | None] = mapped_column(JSONType, default=dict)
    data_mode: Mapped[str | None] = mapped_column(String(10))
    providers_used: Mapped[list | None] = mapped_column(JSONType, default=list)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    user = relationship("User", back_populates="searches")
