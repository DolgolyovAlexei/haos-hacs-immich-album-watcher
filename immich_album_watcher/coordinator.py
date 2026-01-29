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
    ATTR_ALBUM_URL,
    ATTR_ASSET_CREATED,
    ATTR_ASSET_DESCRIPTION,
    ATTR_ASSET_FILENAME,
    ATTR_ASSET_OWNER,
    ATTR_ASSET_OWNER_ID,
    ATTR_ASSET_TYPE,
    ATTR_ASSET_URL,
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
class SharedLinkInfo:
    """Data class for shared link information."""

    id: str
    key: str
    has_password: bool = False
    password: str | None = None
    expires_at: datetime | None = None
    allow_download: bool = True
    show_metadata: bool = True

    @property
    def is_expired(self) -> bool:
        """Check if the link has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(self.expires_at.tzinfo) > self.expires_at

    @property
    def is_accessible(self) -> bool:
        """Check if the link is accessible without password and not expired."""
        return not self.has_password and not self.is_expired

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> SharedLinkInfo:
        """Create SharedLinkInfo from API response."""
        expires_at = None
        if data.get("expiresAt"):
            try:
                expires_at = datetime.fromisoformat(
                    data["expiresAt"].replace("Z", "+00:00")
                )
            except ValueError:
                pass

        password = data.get("password")
        return cls(
            id=data["id"],
            key=data["key"],
            has_password=bool(password),
            password=password if password else None,
            expires_at=expires_at,
            allow_download=data.get("allowDownload", True),
            show_metadata=data.get("showMetadata", True),
        )


@dataclass
class AssetInfo:
    """Data class for asset information."""

    id: str
    type: str  # IMAGE or VIDEO
    filename: str
    created_at: str
    owner_id: str = ""
    owner_name: str = ""
    description: str = ""
    people: list[str] = field(default_factory=list)

    @classmethod
    def from_api_response(
        cls, data: dict[str, Any], users_cache: dict[str, str] | None = None
    ) -> AssetInfo:
        """Create AssetInfo from API response."""
        people = []
        if "people" in data:
            people = [p.get("name", "") for p in data["people"] if p.get("name")]

        owner_id = data.get("ownerId", "")
        owner_name = ""
        if users_cache and owner_id:
            owner_name = users_cache.get(owner_id, "")

        # Get description from exifInfo if available
        description = ""
        exif_info = data.get("exifInfo")
        if exif_info:
            description = exif_info.get("description", "") or ""

        return cls(
            id=data["id"],
            type=data.get("type", ASSET_TYPE_IMAGE),
            filename=data.get("originalFileName", ""),
            created_at=data.get("fileCreatedAt", ""),
            owner_id=owner_id,
            owner_name=owner_name,
            description=description,
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
    def from_api_response(
        cls, data: dict[str, Any], users_cache: dict[str, str] | None = None
    ) -> AlbumData:
        """Create AlbumData from API response."""
        assets_data = data.get("assets", [])
        asset_ids = set()
        assets = {}
        people = set()
        photo_count = 0
        video_count = 0

        for asset_data in assets_data:
            asset = AssetInfo.from_api_response(asset_data, users_cache)
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
        self._users_cache: dict[str, str] = {}  # user_id -> name
        self._shared_links_cache: dict[str, list[SharedLinkInfo]] = {}  # album_id -> list of SharedLinkInfo

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

    async def async_refresh_album(self, album_id: str) -> None:
        """Force an immediate refresh of a specific album.

        Currently refreshes all albums as they share the same coordinator,
        but the method signature allows for future optimization.
        """
        if album_id in self._album_ids:
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
                "description": asset.description,
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

    async def _async_fetch_users(self) -> dict[str, str]:
        """Fetch all users from Immich and cache them."""
        if self._session is None:
            self._session = async_get_clientsession(self.hass)

        headers = {"x-api-key": self._api_key}
        try:
            async with self._session.get(
                f"{self._url}/api/users",
                headers=headers,
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    self._users_cache = {
                        u["id"]: u.get("name", u.get("email", "Unknown"))
                        for u in data
                        if u.get("id")
                    }
        except aiohttp.ClientError as err:
            _LOGGER.warning("Failed to fetch users: %s", err)

        return self._users_cache

    async def _async_fetch_shared_links(self) -> dict[str, list[SharedLinkInfo]]:
        """Fetch shared links from Immich and cache album_id -> SharedLinkInfo mapping."""
        if self._session is None:
            self._session = async_get_clientsession(self.hass)

        headers = {"x-api-key": self._api_key}
        try:
            async with self._session.get(
                f"{self._url}/api/shared-links",
                headers=headers,
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    _LOGGER.debug("Fetched %d shared links from Immich", len(data))
                    self._shared_links_cache.clear()
                    for link in data:
                        album = link.get("album")
                        key = link.get("key")
                        if album and key:
                            album_id = album.get("id")
                            if album_id:
                                link_info = SharedLinkInfo.from_api_response(link)
                                _LOGGER.debug(
                                    "Shared link: key=%s, album_id=%s, "
                                    "has_password=%s, expired=%s, accessible=%s",
                                    key[:8],
                                    album_id[:8],
                                    link_info.has_password,
                                    link_info.is_expired,
                                    link_info.is_accessible,
                                )
                                if album_id not in self._shared_links_cache:
                                    self._shared_links_cache[album_id] = []
                                self._shared_links_cache[album_id].append(link_info)
                    _LOGGER.debug(
                        "Cached shared links for %d albums", len(self._shared_links_cache)
                    )
                else:
                    _LOGGER.warning(
                        "Failed to fetch shared links: HTTP %s", response.status
                    )
        except aiohttp.ClientError as err:
            _LOGGER.warning("Failed to fetch shared links: %s", err)

        return self._shared_links_cache

    def _get_accessible_links(self, album_id: str) -> list[SharedLinkInfo]:
        """Get all accessible (no password, not expired) shared links for an album."""
        all_links = self._shared_links_cache.get(album_id, [])
        return [link for link in all_links if link.is_accessible]

    def _get_non_expired_links(self, album_id: str) -> list[SharedLinkInfo]:
        """Get all non-expired shared links for an album (including password-protected)."""
        all_links = self._shared_links_cache.get(album_id, [])
        return [link for link in all_links if not link.is_expired]

    def _get_protected_only_links(self, album_id: str) -> list[SharedLinkInfo]:
        """Get password-protected but not expired shared links for an album."""
        all_links = self._shared_links_cache.get(album_id, [])
        return [link for link in all_links if link.has_password and not link.is_expired]

    def get_album_public_url(self, album_id: str) -> str | None:
        """Get the public URL for an album if it has an accessible shared link."""
        accessible_links = self._get_accessible_links(album_id)
        if accessible_links:
            return f"{self._url}/share/{accessible_links[0].key}"
        return None

    def get_album_any_url(self, album_id: str) -> str | None:
        """Get any non-expired URL for an album (prefers accessible, falls back to protected)."""
        # First try accessible links
        accessible_links = self._get_accessible_links(album_id)
        if accessible_links:
            return f"{self._url}/share/{accessible_links[0].key}"
        # Fall back to any non-expired link (including password-protected)
        non_expired = self._get_non_expired_links(album_id)
        if non_expired:
            return f"{self._url}/share/{non_expired[0].key}"
        return None

    def get_album_protected_url(self, album_id: str) -> str | None:
        """Get a protected URL for an album if any password-protected link exists."""
        protected_links = self._get_protected_only_links(album_id)
        if protected_links:
            return f"{self._url}/share/{protected_links[0].key}"
        return None

    def get_album_protected_urls(self, album_id: str) -> list[str]:
        """Get all password-protected (but not expired) URLs for an album."""
        protected_links = self._get_protected_only_links(album_id)
        return [f"{self._url}/share/{link.key}" for link in protected_links]

    def get_album_protected_password(self, album_id: str) -> str | None:
        """Get the password for the first protected link (matches get_album_protected_url)."""
        protected_links = self._get_protected_only_links(album_id)
        if protected_links and protected_links[0].password:
            return protected_links[0].password
        return None

    def get_album_public_urls(self, album_id: str) -> list[str]:
        """Get all accessible public URLs for an album."""
        accessible_links = self._get_accessible_links(album_id)
        return [f"{self._url}/share/{link.key}" for link in accessible_links]

    def get_album_shared_links_info(self, album_id: str) -> list[dict[str, Any]]:
        """Get detailed info about all shared links for an album."""
        all_links = self._shared_links_cache.get(album_id, [])
        return [
            {
                "url": f"{self._url}/share/{link.key}",
                "has_password": link.has_password,
                "is_expired": link.is_expired,
                "expires_at": link.expires_at.isoformat() if link.expires_at else None,
                "is_accessible": link.is_accessible,
            }
            for link in all_links
        ]

    def _get_asset_public_url(self, album_id: str, asset_id: str) -> str | None:
        """Get the public URL for an asset (prefers accessible, falls back to protected)."""
        # First try accessible links
        accessible_links = self._get_accessible_links(album_id)
        if accessible_links:
            return f"{self._url}/share/{accessible_links[0].key}/photos/{asset_id}"
        # Fall back to any non-expired link
        non_expired = self._get_non_expired_links(album_id)
        if non_expired:
            return f"{self._url}/share/{non_expired[0].key}/photos/{asset_id}"
        return None

    async def _async_update_data(self) -> dict[str, AlbumData]:
        """Fetch data from Immich API."""
        if self._session is None:
            self._session = async_get_clientsession(self.hass)

        # Fetch users to resolve owner names
        if not self._users_cache:
            await self._async_fetch_users()

        # Fetch shared links to resolve public URLs (refresh each time as links can change)
        await self._async_fetch_shared_links()

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
                    album = AlbumData.from_api_response(data, self._users_cache)

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
        added_assets_detail = []
        for asset in change.added_assets:
            asset_detail = {
                "id": asset.id,
                ATTR_ASSET_TYPE: asset.type,
                ATTR_ASSET_FILENAME: asset.filename,
                ATTR_ASSET_CREATED: asset.created_at,
                ATTR_ASSET_OWNER: asset.owner_name,
                ATTR_ASSET_OWNER_ID: asset.owner_id,
                ATTR_ASSET_DESCRIPTION: asset.description,
                ATTR_PEOPLE: asset.people,
            }
            # Add public URL if album has a shared link
            asset_url = self._get_asset_public_url(change.album_id, asset.id)
            if asset_url:
                asset_detail[ATTR_ASSET_URL] = asset_url
            added_assets_detail.append(asset_detail)

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

        # Add album URL if it has a shared link (prefers accessible, falls back to protected)
        album_url = self.get_album_any_url(change.album_id)
        if album_url:
            event_data[ATTR_ALBUM_URL] = album_url

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

    def get_album_protected_link_id(self, album_id: str) -> str | None:
        """Get the ID of the first protected link (matches get_album_protected_url)."""
        protected_links = self._get_protected_only_links(album_id)
        if protected_links:
            return protected_links[0].id
        return None

    async def async_set_shared_link_password(
        self, link_id: str, password: str | None
    ) -> bool:
        """Update the password for a shared link via Immich API.

        Args:
            link_id: The ID of the shared link to update.
            password: The new password, or None/empty string to remove the password.

        Returns:
            True if successful, False otherwise.
        """
        if self._session is None:
            self._session = async_get_clientsession(self.hass)

        headers = {
            "x-api-key": self._api_key,
            "Content-Type": "application/json",
        }

        # Immich API expects null to remove password, or a string to set it
        payload = {"password": password if password else None}

        try:
            async with self._session.patch(
                f"{self._url}/api/shared-links/{link_id}",
                headers=headers,
                json=payload,
            ) as response:
                if response.status == 200:
                    _LOGGER.info("Successfully updated shared link password")
                    # Refresh shared links cache to reflect the change
                    await self._async_fetch_shared_links()
                    return True
                else:
                    _LOGGER.error(
                        "Failed to update shared link password: HTTP %s",
                        response.status,
                    )
                    return False
        except aiohttp.ClientError as err:
            _LOGGER.error("Error updating shared link password: %s", err)
            return False

    def clear_new_assets_flag(self, album_id: str) -> None:
        """Clear the new assets flag for an album."""
        if self.data and album_id in self.data:
            self.data[album_id].has_new_assets = False
            self.data[album_id].last_change_time = None
