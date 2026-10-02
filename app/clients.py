"""Shared long-lived clients (one per process)."""

from temporalio.client import Client

from app.config import get_settings

_temporal: Client | None = None


async def temporal() -> Client:
    global _temporal
    if _temporal is None:
        _temporal = await Client.connect(get_settings().temporal_address)
    return _temporal
