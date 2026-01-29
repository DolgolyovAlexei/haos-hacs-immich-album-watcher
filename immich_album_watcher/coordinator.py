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
    ASSET_TYPE_IMAGE,
    ASSET_TYPE_VIDEO,
    ATTR_ADDED_ASSETS,
    ATTR_ADDED_COUNT,
    ATTR_ALBUM_ID,
    ATTR_ALBUM_NAME,
    ATTR_ASSET_CREATED,
    ATTR_ASSET_FILENAME,
    ATTR_ASSET_TYPE,
    ATTR_CHANGE_TYPE,
    ATTR_PEOPLE,
    ATTR_REMOVED_ASSETS,
    ATTR_REMOVED_COUNT,
    DOMAIN,
    EVENT_ALBUM_CHANGED,
    EVENT_ASSETS_ADDED,
    EVENT_ASSETS_REMOVED,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class AssetInfo:
    """Data class for asset information."""

    id: str
    type: str  # IMAGE or VIDEO
    filename: str
    created_at: str
    people: list[str] = field(default_factory=list)

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> AssetInfo:
        """Create AssetInfo from API response."""
        people = []
        if "people" in data:
            people = [p.get("name", "") for p in data["people"] if p.get("name")]
        return cls(
            id=data["id"],
            type=data.get("type", ASSET_TYPE_IMAGE),
            filename=data.get("originalFileName", ""),
            created_at=data.get("fileCreatedAt", ""),
            people=people,
        )


@dataclass
class AlbumData:
    """Data class for album information."""

    id: str
    name: str
    asset_count: int
    photo_count: int
    video_count: int
    created_at: str
    updated_at: str
    shared: bool
    owner: str
    thumbnail_asset_id: str | None
    asset_ids: set[str] = field(default_factory=set)
    assets: dict[str, AssetInfo] = field(default_factory=dict)
    people: set[str] = field(default_factory=set)
    has_new_assets: bool = False
    last_change_time: datetime | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> AlbumData:
        """Create AlbumData from API response."""
        assets_data = data.get("assets", [])
        asset_ids = set()
        assets = {}
        people = set()
        photo_count = 0
        video_count = 0

        for asset_data in assets_data:
            asset = AssetInfo.from_api_response(asset_data)
            asset_ids.add(asset.id)
            assets[asset.id] = asset
            people.update(asset.people)
            if asset.type == ASSET_TYPE_IMAGE:
                photo_count += 1
            elif asset.type == ASSET_TYPE_VIDEO:
                video_count += 1

        return cls(
            id=data["id"],
            name=data.get("albumName", "Unnamed"),
            asset_count=data.get("assetCount", len(asset_ids)),
            photo_count=photo_count,
            video_count=video_count,
            created_at=data.get("createdAt", ""),
            updated_at=data.get("updatedAt", ""),
            shared=data.get("shared", False),
            owner=data.get("owner", {}).get("name", "Unknown"),
            thumbnail_asset_id=data.get("albumThumbnailAssetId"),
            asset_ids=asset_ids,
            assets=assets,
            people=people,
        )


@dataclass
class AlbumChange:
    """Data class for album changes."""

    album_id: str
    album_name: str
    change_type: str
    added_count: int = 0
    removed_count: int = 0
    added_assets: list[AssetInfo] = field(default_factory=list)
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
        self._people_cache: dict[str, str] = {}  # person_id -> name

    @property
    def immich_url(self) -> str:
        """Return the Immich URL."""
        return self._url

    @property
    def api_key(self) -> str:
        """Return the API key."""
        return self._api_key

    def update_config(self, album_ids: list[str], scan_interval: int) -> None:
        """Update configuration."""
        self._album_ids = album_ids
        self.update_interval = timedelta(seconds=scan_interval)

    async def async_refresh_now(self) -> None:
        """Force an immediate refresh."""
        await self.async_request_refresh()

    async def async_get_recent_assets(
        self, album_id: str, count: int = 10
    ) -> list[dict[str, Any]]:
        """Get recent assets from an album."""
        if self.data is None or album_id not in self.data:
            return []

        album = self.data[album_id]
        # Sort assets by created_at descending
        sorted_assets = sorted(
            album.assets.values(),
            key=lambda a: a.created_at,
            reverse=True,
        )[:count]

        return [
            {
                "id": asset.id,
                "type": asset.type,
                "filename": asset.filename,
                "created_at": asset.created_at,
                "people": asset.people,
                "thumbnail_url": f"{self._url}/api/assets/{asset.id}/thumbnail",
            }
            for asset in sorted_assets
        ]

    async def async_fetch_people(self) -> dict[str, str]:
        """Fetch all people from Immich."""
        if self._session is None:
            self._session = async_get_clientsession(self.hass)

        headers = {"x-api-key": self._api_key}
        try:
            async with self._session.get(
                f"{self._url}/api/people",
                headers=headers,
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    people_list = data.get("people", data) if isinstance(data, dict) else data
                    self._people_cache = {
                        p["id"]: p.get("name", "")
                        for p in people_list
                        if p.get("name")
                    }
        except aiohttp.ClientError as err:
            _LOGGER.warning("Failed to fetch people: %s", err)

        return self._people_cache

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

                    # Detect changes and update flags
                    if album_id in self._previous_states:
                        change = self._detect_change(
                            self._previous_states[album_id], album
                        )
                        if change:
                            album.has_new_assets = change.added_count > 0
                            album.last_change_time = datetime.now()
                            self._fire_events(change, album)
                    else:
                        # First run, no changes
                        album.has_new_assets = False

                    # Preserve has_new_assets from previous state if still within window
                    if album_id in self._previous_states:
                        prev = self._previous_states[album_id]
                        if prev.has_new_assets and prev.last_change_time:
                            # Keep the flag if change was recent
                            album.last_change_time = prev.last_change_time
                            if not album.has_new_assets:
                                album.has_new_assets = prev.has_new_assets

                    albums_data[album_id] = album

            except aiohttp.ClientError as err:
                raise UpdateFailed(f"Error communicating with Immich: {err}") from err

        # Update previous states
        self._previous_states = albums_data.copy()

        return albums_data

    def _detect_change(
        self, old_state: AlbumData, new_state: AlbumData
    ) -> AlbumChange | None:
        """Detect changes between two album states."""
        added_ids = new_state.asset_ids - old_state.asset_ids
        removed_ids = old_state.asset_ids - new_state.asset_ids

        if not added_ids and not removed_ids:
            return None

        change_type = "changed"
        if added_ids and not removed_ids:
            change_type = "assets_added"
        elif removed_ids and not added_ids:
            change_type = "assets_removed"

        # Get full asset info for added assets
        added_assets = [
            new_state.assets[aid] for aid in added_ids if aid in new_state.assets
        ]

        return AlbumChange(
            album_id=new_state.id,
            album_name=new_state.name,
            change_type=change_type,
            added_count=len(added_ids),
            removed_count=len(removed_ids),
            added_assets=added_assets,
            removed_asset_ids=list(removed_ids),
        )

    def _fire_events(self, change: AlbumChange, album: AlbumData) -> None:
        """Fire Home Assistant events for album changes."""
        # Build detailed asset info for events
        added_assets_detail = [
            {
                "id": asset.id,
                ATTR_ASSET_TYPE: asset.type,
                ATTR_ASSET_FILENAME: asset.filename,
                ATTR_ASSET_CREATED: asset.created_at,
                ATTR_PEOPLE: asset.people,
            }
            for asset in change.added_assets
        ]

        event_data = {
            ATTR_ALBUM_ID: change.album_id,
            ATTR_ALBUM_NAME: change.album_name,
            ATTR_CHANGE_TYPE: change.change_type,
            ATTR_ADDED_COUNT: change.added_count,
            ATTR_REMOVED_COUNT: change.removed_count,
            ATTR_ADDED_ASSETS: added_assets_detail,
            ATTR_REMOVED_ASSETS: change.removed_asset_ids,
            ATTR_PEOPLE: list(album.people),
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

    def clear_new_assets_flag(self, album_id: str) -> None:
        """Clear the new assets flag for an album."""
        if self.data and album_id in self.data:
            self.data[album_id].has_new_assets = False
            self.data[album_id].last_change_time = None
