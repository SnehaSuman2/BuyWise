"""Shared schema pieces."""

from __future__ import annotations

from pydantic import BaseModel


class DataMeta(BaseModel):
    """Every data-bearing response says where the data came from."""

    data_mode: str  # live | demo | mixed
    is_demo: bool
    providers: list[str] = []
    cached: bool = False
    warnings: list[str] = []
