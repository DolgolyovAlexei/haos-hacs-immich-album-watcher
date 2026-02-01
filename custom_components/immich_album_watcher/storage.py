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

# Default TTL for Telegram file_id cache (48 hours in seconds)
DEFAULT_TELEGRAM_CACHE_TTL = 48 * 60 * 60


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


class TelegramFileCache:
    """Cache for Telegram file_ids to avoid re-uploading media.

    When a file is uploaded to Telegram, it returns a file_id that can be reused
    to send the same file without re-uploading. This cache stores these file_ids
    keyed by the source URL.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        album_id: str,
        ttl_seconds: int = DEFAULT_TELEGRAM_CACHE_TTL,
    ) -> None:
        """Initialize the Telegram file cache.

        Args:
            hass: Home Assistant instance
            album_id: Album ID for scoping the cache
            ttl_seconds: Time-to-live for cache entries in seconds (default: 48 hours)
        """
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY_PREFIX}.telegram_cache.{album_id}"
        )
        self._data: dict[str, Any] | None = None
        self._ttl_seconds = ttl_seconds

    async def async_load(self) -> None:
        """Load cache data from storage."""
        self._data = await self._store.async_load() or {"files": {}}
        # Clean up expired entries on load
        await self._cleanup_expired()
        _LOGGER.debug(
            "Loaded Telegram file cache with %d entries",
            len(self._data.get("files", {})),
        )

    async def _cleanup_expired(self) -> None:
        """Remove expired cache entries."""
        if not self._data or "files" not in self._data:
            return

        now = datetime.now(timezone.utc)
        expired_keys = []

        for url, entry in self._data["files"].items():
            cached_at_str = entry.get("cached_at")
            if cached_at_str:
                cached_at = datetime.fromisoformat(cached_at_str)
                age_seconds = (now - cached_at).total_seconds()
                if age_seconds > self._ttl_seconds:
                    expired_keys.append(url)

        if expired_keys:
            for key in expired_keys:
                del self._data["files"][key]
            await self._store.async_save(self._data)
            _LOGGER.debug("Cleaned up %d expired Telegram cache entries", len(expired_keys))

    def get(self, url: str) -> dict[str, Any] | None:
        """Get cached file_id for a URL.

        Args:
            url: The source URL of the media

        Returns:
            Dict with 'file_id' and 'type' if cached and not expired, None otherwise
        """
        if not self._data or "files" not in self._data:
            return None

        entry = self._data["files"].get(url)
        if not entry:
            return None

        # Check if expired
        cached_at_str = entry.get("cached_at")
        if cached_at_str:
            cached_at = datetime.fromisoformat(cached_at_str)
            age_seconds = (datetime.now(timezone.utc) - cached_at).total_seconds()
            if age_seconds > self._ttl_seconds:
                return None

        return {
            "file_id": entry.get("file_id"),
            "type": entry.get("type"),
        }

    async def async_set(self, url: str, file_id: str, media_type: str) -> None:
        """Store a file_id for a URL.

        Args:
            url: The source URL of the media
            file_id: The Telegram file_id
            media_type: The type of media ('photo', 'video', 'document')
        """
        if self._data is None:
            self._data = {"files": {}}

        self._data["files"][url] = {
            "file_id": file_id,
            "type": media_type,
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._store.async_save(self._data)
        _LOGGER.debug("Cached Telegram file_id for URL (type: %s)", media_type)

    async def async_remove(self) -> None:
        """Remove all cache data."""
        await self._store.async_remove()
        self._data = None
