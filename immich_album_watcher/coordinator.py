"""Data coordinator for Immich Album Watcher."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ATTR_ADDED_ASSETS,
    ATTR_ADDED_COUNT,
    ATTR_ALBUM_ID,
    ATTR_ALBUM_NAME,
    ATTR_CHANGE_TYPE,
    ATTR_REMOVED_ASSETS,
    ATTR_REMOVED_COUNT,
    DOMAIN,
    EVENT_ALBUM_CHANGED,
    EVENT_ASSETS_ADDED,
    EVENT_ASSETS_REMOVED,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class AlbumData:
    """Data class for album information."""

    id: str
    name: str
    asset_count: int
    updated_at: str
    shared: bool
    owner: str
    thumbnail_asset_id: str | None
    asset_ids: set[str] = field(default_factory=set)

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> AlbumData:
        """Create AlbumData from API response."""
        asset_ids = {asset["id"] for asset in data.get("assets", [])}
        return cls(
            id=data["id"],
            name=data.get("albumName", "Unnamed"),
            asset_count=data.get("assetCount", len(asset_ids)),
            updated_at=data.get("updatedAt", ""),
            shared=data.get("shared", False),
            owner=data.get("owner", {}).get("name", "Unknown"),
            thumbnail_asset_id=data.get("albumThumbnailAssetId"),
            asset_ids=asset_ids,
        )


@dataclass
class AlbumChange:
    """Data class for album changes."""

    album_id: str
    album_name: str
    change_type: str
    added_count: int = 0
    removed_count: int = 0
    added_asset_ids: list[str] = field(default_factory=list)
    removed_asset_ids: list[str] = field(default_factory=list)


class ImmichAlbumWatcherCoordinator(DataUpdateCoordinator[dict[str, AlbumData]]):
    """Coordinator for fetching Immich album data."""

    def __init__(
        self,
        hass: HomeAssistant,
        url: str,
        api_key: str,
        album_ids: list[str],
        scan_interval: int,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self._url = url.rstrip("/")
        self._api_key = api_key
        self._album_ids = album_ids
        self._previous_states: dict[str, AlbumData] = {}
        self._session: aiohttp.ClientSession | None = None

    @property
    def immich_url(self) -> str:
        """Return the Immich URL."""
        return self._url

    def update_config(self, album_ids: list[str], scan_interval: int) -> None:
        """Update configuration."""
        self._album_ids = album_ids
        self.update_interval = timedelta(seconds=scan_interval)

    async def _async_update_data(self) -> dict[str, AlbumData]:
        """Fetch data from Immich API."""
        if self._session is None:
            self._session = async_get_clientsession(self.hass)

        headers = {"x-api-key": self._api_key}
        albums_data: dict[str, AlbumData] = {}

        for album_id in self._album_ids:
            try:
                async with self._session.get(
                    f"{self._url}/api/albums/{album_id}",
                    headers=headers,
                ) as response:
                    if response.status == 404:
                        _LOGGER.warning("Album %s not found, skipping", album_id)
                        continue
                    if response.status != 200:
                        raise UpdateFailed(
                            f"Error fetching album {album_id}: HTTP {response.status}"
                        )

                    data = await response.json()
                    album = AlbumData.from_api_response(data)
                    albums_data[album_id] = album

                    # Detect changes
                    if album_id in self._previous_states:
                        change = self._detect_change(
                            self._previous_states[album_id], album
                        )
                        if change:
                            self._fire_events(change)

            except aiohttp.ClientError as err:
                raise UpdateFailed(f"Error communicating with Immich: {err}") from err

        # Update previous states
        self._previous_states = albums_data.copy()

        return albums_data

    def _detect_change(
        self, old_state: AlbumData, new_state: AlbumData
    ) -> AlbumChange | None:
        """Detect changes between two album states."""
        added = new_state.asset_ids - old_state.asset_ids
        removed = old_state.asset_ids - new_state.asset_ids

        if not added and not removed:
            return None

        change_type = "changed"
        if added and not removed:
            change_type = "assets_added"
        elif removed and not added:
            change_type = "assets_removed"

        return AlbumChange(
            album_id=new_state.id,
            album_name=new_state.name,
            change_type=change_type,
            added_count=len(added),
            removed_count=len(removed),
            added_asset_ids=list(added),
            removed_asset_ids=list(removed),
        )

    def _fire_events(self, change: AlbumChange) -> None:
        """Fire Home Assistant events for album changes."""
        event_data = {
            ATTR_ALBUM_ID: change.album_id,
            ATTR_ALBUM_NAME: change.album_name,
            ATTR_CHANGE_TYPE: change.change_type,
            ATTR_ADDED_COUNT: change.added_count,
            ATTR_REMOVED_COUNT: change.removed_count,
            ATTR_ADDED_ASSETS: change.added_asset_ids,
            ATTR_REMOVED_ASSETS: change.removed_asset_ids,
        }

        # Fire general change event
        self.hass.bus.async_fire(EVENT_ALBUM_CHANGED, event_data)

        _LOGGER.info(
            "Album '%s' changed: +%d -%d assets",
            change.album_name,
            change.added_count,
            change.removed_count,
        )

        # Fire specific events
        if change.added_count > 0:
            self.hass.bus.async_fire(EVENT_ASSETS_ADDED, event_data)

        if change.removed_count > 0:
            self.hass.bus.async_fire(EVENT_ASSETS_REMOVED, event_data)
