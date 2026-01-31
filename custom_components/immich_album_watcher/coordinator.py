"""Data coordinator for Immich Album Watcher."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .storage import ImmichAlbumStorage

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
    ATTR_ASSET_DOWNLOAD_URL,
    ATTR_ASSET_FILENAME,
    ATTR_ASSET_IS_FAVORITE,
    ATTR_ASSET_OWNER,
    ATTR_ASSET_OWNER_ID,
    ATTR_ASSET_PLAYBACK_URL,
    ATTR_ASSET_RATING,
    ATTR_ASSET_TYPE,
    ATTR_ASSET_URL,
    ATTR_CHANGE_TYPE,
    ATTR_HUB_NAME,
    ATTR_PEOPLE,
    ATTR_REMOVED_ASSETS,
    ATTR_REMOVED_COUNT,
    ATTR_OLD_NAME,
    ATTR_NEW_NAME,
    ATTR_OLD_SHARED,
    ATTR_NEW_SHARED,
    ATTR_SHARED,
    DOMAIN,
    EVENT_ALBUM_CHANGED,
    EVENT_ASSETS_ADDED,
    EVENT_ASSETS_REMOVED,
    EVENT_ALBUM_RENAMED,
    EVENT_ALBUM_DELETED,
    EVENT_ALBUM_SHARING_CHANGED,
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
    is_favorite: bool = False
    rating: int | None = None

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

        # Get favorites and rating
        is_favorite = data.get("isFavorite", False)
        rating = data.get("exifInfo", {}).get("rating") if exif_info else None

        return cls(
            id=data["id"],
            type=data.get("type", ASSET_TYPE_IMAGE),
            filename=data.get("originalFileName", ""),
            created_at=data.get("fileCreatedAt", ""),
            owner_id=owner_id,
            owner_name=owner_name,
            description=description,
            people=people,
            is_favorite=is_favorite,
            rating=rating,
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
    old_name: str | None = None
    new_name: str | None = None
    old_shared: bool | None = None
    new_shared: bool | None = None


class ImmichAlbumWatcherCoordinator(DataUpdateCoordinator[AlbumData | None]):
    """Coordinator for fetching Immich album data."""

    def __init__(
        self,
        hass: HomeAssistant,
        url: str,
        api_key: str,
        album_id: str,
        album_name: str,
        scan_interval: int,
        hub_name: str = "Immich",
        storage: ImmichAlbumStorage | None = None,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{album_id}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self._url = url.rstrip("/")
        self._api_key = api_key
        self._album_id = album_id
        self._album_name = album_name
        self._hub_name = hub_name
        self._previous_state: AlbumData | None = None
        self._session: aiohttp.ClientSession | None = None
        self._people_cache: dict[str, str] = {}  # person_id -> name
        self._users_cache: dict[str, str] = {}  # user_id -> name
        self._shared_links: list[SharedLinkInfo] = []
        self._storage = storage
        self._persisted_asset_ids: set[str] | None = None

    @property
    def immich_url(self) -> str:
        """Return the Immich URL."""
        return self._url

    @property
    def api_key(self) -> str:
        """Return the API key."""
        return self._api_key

    @property
    def album_id(self) -> str:
        """Return the album ID."""
        return self._album_id

    @property
    def album_name(self) -> str:
        """Return the album name."""
        return self._album_name

    def update_scan_interval(self, scan_interval: int) -> None:
        """Update the scan interval."""
        self.update_interval = timedelta(seconds=scan_interval)

    async def async_refresh_now(self) -> None:
        """Force an immediate refresh."""
        await self.async_request_refresh()

    async def async_load_persisted_state(self) -> None:
        """Load persisted asset IDs from storage.

        This should be called before the first refresh to enable
        detection of changes that occurred during downtime.
        """
        if self._storage:
            self._persisted_asset_ids = self._storage.get_album_asset_ids(
                self._album_id
            )
            if self._persisted_asset_ids is not None:
                _LOGGER.debug(
                    "Loaded %d persisted asset IDs for album '%s'",
                    len(self._persisted_asset_ids),
                    self._album_name,
                )

    async def async_get_recent_assets(self, count: int = 10) -> list[dict[str, Any]]:
        """Get recent assets from the album."""
        if self.data is None:
            return []

        # Sort assets by created_at descending
        sorted_assets = sorted(
            self.data.assets.values(),
            key=lambda a: a.created_at,
            reverse=True,
        )[:count]

        result = []
        for asset in sorted_assets:
            asset_data = {
                "id": asset.id,
                "type": asset.type,
                "filename": asset.filename,
                "created_at": asset.created_at,
                "description": asset.description,
                "people": asset.people,
                "is_favorite": asset.is_favorite,
                "rating": asset.rating,
                "thumbnail_url": f"{self._url}/api/assets/{asset.id}/thumbnail",
            }
            if asset.type == ASSET_TYPE_VIDEO:
                video_url = self._get_asset_video_url(asset.id)
                if video_url:
                    asset_data["video_url"] = video_url
            result.append(asset_data)
        return result

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

    async def _async_fetch_shared_links(self) -> list[SharedLinkInfo]:
        """Fetch shared links for this album from Immich."""
        if self._session is None:
            self._session = async_get_clientsession(self.hass)

        headers = {"x-api-key": self._api_key}
        self._shared_links = []

        try:
            async with self._session.get(
                f"{self._url}/api/shared-links",
                headers=headers,
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    for link in data:
                        album = link.get("album")
                        key = link.get("key")
                        if album and key and album.get("id") == self._album_id:
                            link_info = SharedLinkInfo.from_api_response(link)
                            self._shared_links.append(link_info)
                            _LOGGER.debug(
                                "Found shared link for album: key=%s, has_password=%s",
                                key[:8],
                                link_info.has_password,
                            )
        except aiohttp.ClientError as err:
            _LOGGER.warning("Failed to fetch shared links: %s", err)

        return self._shared_links

    def _get_accessible_links(self) -> list[SharedLinkInfo]:
        """Get all accessible (no password, not expired) shared links."""
        return [link for link in self._shared_links if link.is_accessible]

    def _get_protected_links(self) -> list[SharedLinkInfo]:
        """Get password-protected but not expired shared links."""
        return [link for link in self._shared_links if link.has_password and not link.is_expired]

    def get_public_url(self) -> str | None:
        """Get the public URL if album has an accessible shared link."""
        accessible_links = self._get_accessible_links()
        if accessible_links:
            return f"{self._url}/share/{accessible_links[0].key}"
        return None

    def get_any_url(self) -> str | None:
        """Get any non-expired URL (prefers accessible, falls back to protected)."""
        accessible_links = self._get_accessible_links()
        if accessible_links:
            return f"{self._url}/share/{accessible_links[0].key}"
        non_expired = [link for link in self._shared_links if not link.is_expired]
        if non_expired:
            return f"{self._url}/share/{non_expired[0].key}"
        return None

    def get_protected_url(self) -> str | None:
        """Get a protected URL if any password-protected link exists."""
        protected_links = self._get_protected_links()
        if protected_links:
            return f"{self._url}/share/{protected_links[0].key}"
        return None

    def get_protected_urls(self) -> list[str]:
        """Get all password-protected URLs."""
        return [f"{self._url}/share/{link.key}" for link in self._get_protected_links()]

    def get_protected_password(self) -> str | None:
        """Get the password for the first protected link."""
        protected_links = self._get_protected_links()
        if protected_links and protected_links[0].password:
            return protected_links[0].password
        return None

    def get_public_urls(self) -> list[str]:
        """Get all accessible public URLs."""
        return [f"{self._url}/share/{link.key}" for link in self._get_accessible_links()]

    def get_shared_links_info(self) -> list[dict[str, Any]]:
        """Get detailed info about all shared links."""
        return [
            {
                "url": f"{self._url}/share/{link.key}",
                "has_password": link.has_password,
                "is_expired": link.is_expired,
                "expires_at": link.expires_at.isoformat() if link.expires_at else None,
                "is_accessible": link.is_accessible,
            }
            for link in self._shared_links
        ]

    def _get_asset_public_url(self, asset_id: str) -> str | None:
        """Get the public viewer URL for an asset (web page)."""
        accessible_links = self._get_accessible_links()
        if accessible_links:
            return f"{self._url}/share/{accessible_links[0].key}/photos/{asset_id}"
        non_expired = [link for link in self._shared_links if not link.is_expired]
        if non_expired:
            return f"{self._url}/share/{non_expired[0].key}/photos/{asset_id}"
        return None

    def _get_asset_download_url(self, asset_id: str) -> str | None:
        """Get the direct download URL for an asset (media file)."""
        accessible_links = self._get_accessible_links()
        if accessible_links:
            return f"{self._url}/api/assets/{asset_id}/original?key={accessible_links[0].key}"
        non_expired = [link for link in self._shared_links if not link.is_expired]
        if non_expired:
            return f"{self._url}/api/assets/{asset_id}/original?key={non_expired[0].key}"
        return None

    def _get_asset_video_url(self, asset_id: str) -> str | None:
        """Get the transcoded video playback URL for a video asset."""
        accessible_links = self._get_accessible_links()
        if accessible_links:
            return f"{self._url}/api/assets/{asset_id}/video/playback?key={accessible_links[0].key}"
        non_expired = [link for link in self._shared_links if not link.is_expired]
        if non_expired:
            return f"{self._url}/api/assets/{asset_id}/video/playback?key={non_expired[0].key}"
        return None

    async def _async_update_data(self) -> AlbumData | None:
        """Fetch data from Immich API."""
        if self._session is None:
            self._session = async_get_clientsession(self.hass)

        # Fetch users to resolve owner names
        if not self._users_cache:
            await self._async_fetch_users()

        # Fetch shared links (refresh each time as links can change)
        await self._async_fetch_shared_links()

        headers = {"x-api-key": self._api_key}

        try:
            async with self._session.get(
                f"{self._url}/api/albums/{self._album_id}",
                headers=headers,
            ) as response:
                if response.status == 404:
                    _LOGGER.warning("Album %s not found", self._album_id)
                    # Fire album_deleted event if we had previous state (album was deleted)
                    if self._previous_state:
                        event_data = {
                            ATTR_HUB_NAME: self._hub_name,
                            ATTR_ALBUM_ID: self._album_id,
                            ATTR_ALBUM_NAME: self._previous_state.name,
                        }
                        self.hass.bus.async_fire(EVENT_ALBUM_DELETED, event_data)
                        _LOGGER.info("Album '%s' was deleted", self._previous_state.name)
                    return None
                if response.status != 200:
                    raise UpdateFailed(
                        f"Error fetching album {self._album_id}: HTTP {response.status}"
                    )

                data = await response.json()
                album = AlbumData.from_api_response(data, self._users_cache)

                # Detect changes
                if self._previous_state:
                    change = self._detect_change(self._previous_state, album)
                    if change:
                        album.has_new_assets = change.added_count > 0
                        album.last_change_time = datetime.now()
                        self._fire_events(change, album)
                elif self._persisted_asset_ids is not None:
                    # First refresh after restart - compare with persisted state
                    added_ids = album.asset_ids - self._persisted_asset_ids
                    removed_ids = self._persisted_asset_ids - album.asset_ids

                    if added_ids or removed_ids:
                        change_type = "changed"
                        if added_ids and not removed_ids:
                            change_type = "assets_added"
                        elif removed_ids and not added_ids:
                            change_type = "assets_removed"

                        added_assets = [
                            album.assets[aid]
                            for aid in added_ids
                            if aid in album.assets
                        ]

                        change = AlbumChange(
                            album_id=album.id,
                            album_name=album.name,
                            change_type=change_type,
                            added_count=len(added_ids),
                            removed_count=len(removed_ids),
                            added_assets=added_assets,
                            removed_asset_ids=list(removed_ids),
                        )
                        album.has_new_assets = change.added_count > 0
                        album.last_change_time = datetime.now()
                        self._fire_events(change, album)
                        _LOGGER.info(
                            "Detected changes during downtime for album '%s': +%d -%d",
                            album.name,
                            len(added_ids),
                            len(removed_ids),
                        )
                    else:
                        album.has_new_assets = False

                    # Clear persisted state after first comparison
                    self._persisted_asset_ids = None
                else:
                    album.has_new_assets = False

                # Preserve has_new_assets from previous state if still within window
                if self._previous_state:
                    prev = self._previous_state
                    if prev.has_new_assets and prev.last_change_time:
                        album.last_change_time = prev.last_change_time
                        if not album.has_new_assets:
                            album.has_new_assets = prev.has_new_assets

                # Update previous state
                self._previous_state = album

                # Persist current state for recovery after restart
                if self._storage:
                    await self._storage.async_save_album_state(
                        self._album_id, album.asset_ids
                    )

                return album

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with Immich: {err}") from err

    def _detect_change(
        self, old_state: AlbumData, new_state: AlbumData
    ) -> AlbumChange | None:
        """Detect changes between two album states."""
        added_ids = new_state.asset_ids - old_state.asset_ids
        removed_ids = old_state.asset_ids - new_state.asset_ids

        # Detect metadata changes
        name_changed = old_state.name != new_state.name
        sharing_changed = old_state.shared != new_state.shared

        # Return None only if nothing changed at all
        if not added_ids and not removed_ids and not name_changed and not sharing_changed:
            return None

        # Determine primary change type
        change_type = "changed"
        if name_changed and not added_ids and not removed_ids and not sharing_changed:
            change_type = "album_renamed"
        elif sharing_changed and not added_ids and not removed_ids and not name_changed:
            change_type = "album_sharing_changed"
        elif added_ids and not removed_ids and not name_changed and not sharing_changed:
            change_type = "assets_added"
        elif removed_ids and not added_ids and not name_changed and not sharing_changed:
            change_type = "assets_removed"

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
            old_name=old_state.name if name_changed else None,
            new_name=new_state.name if name_changed else None,
            old_shared=old_state.shared if sharing_changed else None,
            new_shared=new_state.shared if sharing_changed else None,
        )

    def _fire_events(self, change: AlbumChange, album: AlbumData) -> None:
        """Fire Home Assistant events for album changes."""
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
                ATTR_ASSET_IS_FAVORITE: asset.is_favorite,
                ATTR_ASSET_RATING: asset.rating,
            }
            asset_url = self._get_asset_public_url(asset.id)
            if asset_url:
                asset_detail[ATTR_ASSET_URL] = asset_url
            asset_download_url = self._get_asset_download_url(asset.id)
            if asset_download_url:
                asset_detail[ATTR_ASSET_DOWNLOAD_URL] = asset_download_url
            if asset.type == ASSET_TYPE_VIDEO:
                asset_video_url = self._get_asset_video_url(asset.id)
                if asset_video_url:
                    asset_detail[ATTR_ASSET_PLAYBACK_URL] = asset_video_url
            added_assets_detail.append(asset_detail)

        event_data = {
            ATTR_HUB_NAME: self._hub_name,
            ATTR_ALBUM_ID: change.album_id,
            ATTR_ALBUM_NAME: change.album_name,
            ATTR_CHANGE_TYPE: change.change_type,
            ATTR_ADDED_COUNT: change.added_count,
            ATTR_REMOVED_COUNT: change.removed_count,
            ATTR_ADDED_ASSETS: added_assets_detail,
            ATTR_REMOVED_ASSETS: change.removed_asset_ids,
            ATTR_PEOPLE: list(album.people),
            ATTR_SHARED: album.shared,
        }

        # Add metadata change attributes if applicable
        if change.old_name is not None:
            event_data[ATTR_OLD_NAME] = change.old_name
            event_data[ATTR_NEW_NAME] = change.new_name

        if change.old_shared is not None:
            event_data[ATTR_OLD_SHARED] = change.old_shared
            event_data[ATTR_NEW_SHARED] = change.new_shared

        album_url = self.get_any_url()
        if album_url:
            event_data[ATTR_ALBUM_URL] = album_url

        self.hass.bus.async_fire(EVENT_ALBUM_CHANGED, event_data)

        _LOGGER.info(
            "Album '%s' changed: +%d -%d assets",
            change.album_name,
            change.added_count,
            change.removed_count,
        )

        if change.added_count > 0:
            self.hass.bus.async_fire(EVENT_ASSETS_ADDED, event_data)

        if change.removed_count > 0:
            self.hass.bus.async_fire(EVENT_ASSETS_REMOVED, event_data)

        # Fire specific events for metadata changes
        if change.old_name is not None:
            self.hass.bus.async_fire(EVENT_ALBUM_RENAMED, event_data)
            _LOGGER.info(
                "Album renamed: '%s' -> '%s'",
                change.old_name,
                change.new_name,
            )

        if change.old_shared is not None:
            self.hass.bus.async_fire(EVENT_ALBUM_SHARING_CHANGED, event_data)
            _LOGGER.info(
                "Album '%s' sharing changed: %s -> %s",
                change.album_name,
                change.old_shared,
                change.new_shared,
            )

    def get_protected_link_id(self) -> str | None:
        """Get the ID of the first protected link."""
        protected_links = self._get_protected_links()
        if protected_links:
            return protected_links[0].id
        return None

    async def async_set_shared_link_password(
        self, link_id: str, password: str | None
    ) -> bool:
        """Update the password for a shared link via Immich API."""
        if self._session is None:
            self._session = async_get_clientsession(self.hass)

        headers = {
            "x-api-key": self._api_key,
            "Content-Type": "application/json",
        }

        payload = {"password": password if password else None}

        try:
            async with self._session.patch(
                f"{self._url}/api/shared-links/{link_id}",
                headers=headers,
                json=payload,
            ) as response:
                if response.status == 200:
                    _LOGGER.info("Successfully updated shared link password")
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

    def clear_new_assets_flag(self) -> None:
        """Clear the new assets flag."""
        if self.data:
            self.data.has_new_assets = False
            self.data.last_change_time = None

    def has_unprotected_link(self) -> bool:
        """Check if album has an unprotected (accessible) shared link."""
        return len(self._get_accessible_links()) > 0

    def has_protected_link(self) -> bool:
        """Check if album has a protected (password) shared link."""
        return len(self._get_protected_links()) > 0

    def get_unprotected_link_id(self) -> str | None:
        """Get the ID of the first unprotected link."""
        accessible_links = self._get_accessible_links()
        if accessible_links:
            return accessible_links[0].id
        return None

    async def async_create_shared_link(self, password: str | None = None) -> bool:
        """Create a new shared link for the album via Immich API."""
        if self._session is None:
            self._session = async_get_clientsession(self.hass)

        headers = {
            "x-api-key": self._api_key,
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "albumId": self._album_id,
            "type": "ALBUM",
            "allowDownload": True,
            "allowUpload": False,
            "showMetadata": True,
        }

        if password:
            payload["password"] = password

        try:
            async with self._session.post(
                f"{self._url}/api/shared-links",
                headers=headers,
                json=payload,
            ) as response:
                if response.status == 201:
                    _LOGGER.info(
                        "Successfully created shared link for album %s",
                        self._album_name,
                    )
                    await self._async_fetch_shared_links()
                    return True
                else:
                    error_text = await response.text()
                    _LOGGER.error(
                        "Failed to create shared link: HTTP %s - %s",
                        response.status,
                        error_text,
                    )
                    return False
        except aiohttp.ClientError as err:
            _LOGGER.error("Error creating shared link: %s", err)
            return False

    async def async_delete_shared_link(self, link_id: str) -> bool:
        """Delete a shared link via Immich API."""
        if self._session is None:
            self._session = async_get_clientsession(self.hass)

        headers = {"x-api-key": self._api_key}

        try:
            async with self._session.delete(
                f"{self._url}/api/shared-links/{link_id}",
                headers=headers,
            ) as response:
                if response.status == 200:
                    _LOGGER.info("Successfully deleted shared link")
                    await self._async_fetch_shared_links()
                    return True
                else:
                    error_text = await response.text()
                    _LOGGER.error(
                        "Failed to delete shared link: HTTP %s - %s",
                        response.status,
                        error_text,
                    )
                    return False
        except aiohttp.ClientError as err:
            _LOGGER.error("Error deleting shared link: %s", err)
            return False
