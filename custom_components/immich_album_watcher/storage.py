"""Storage helpers for Immich Album Watcher."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = "immich_album_watcher"


class ImmichAlbumStorage:
    """Handles persistence of album state across restarts."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the storage."""
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY_PREFIX}.{entry_id}"
        )
        self._data: dict[str, Any] | None = None

    async def async_load(self) -> dict[str, Any]:
        """Load data from storage."""
        self._data = await self._store.async_load() or {"albums": {}}
        _LOGGER.debug("Loaded storage data with %d albums", len(self._data.get("albums", {})))
        return self._data

    async def async_save_album_state(self, album_id: str, asset_ids: set[str]) -> None:
        """Save album asset IDs to storage."""
        if self._data is None:
            self._data = {"albums": {}}

        self._data["albums"][album_id] = {
            "asset_ids": list(asset_ids),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        await self._store.async_save(self._data)

    def get_album_asset_ids(self, album_id: str) -> set[str] | None:
        """Get persisted asset IDs for an album.

        Returns None if no persisted state exists for the album.
        """
        if self._data and "albums" in self._data:
            album_data = self._data["albums"].get(album_id)
            if album_data:
                return set(album_data.get("asset_ids", []))
        return None

    async def async_remove_album(self, album_id: str) -> None:
        """Remove an album from storage."""
        if self._data and "albums" in self._data:
            self._data["albums"].pop(album_id, None)
            await self._store.async_save(self._data)

    async def async_remove(self) -> None:
        """Remove all storage data."""
        await self._store.async_remove()
        self._data = None
