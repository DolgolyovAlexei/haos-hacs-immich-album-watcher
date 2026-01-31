"""Sensor platform for Immich Album Watcher."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import voluptuous as vol

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant, ServiceResponse, SupportsResponse, callback
from homeassistant.helpers import entity_platform
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import (
    ATTR_ALBUM_ID,
    ATTR_ALBUM_PROTECTED_URL,
    ATTR_ALBUM_URLS,
    ATTR_ASSET_COUNT,
    ATTR_CREATED_AT,
    ATTR_LAST_UPDATED,
    ATTR_OWNER,
    ATTR_PEOPLE,
    ATTR_PHOTO_COUNT,
    ATTR_SHARED,
    ATTR_THUMBNAIL_URL,
    ATTR_VIDEO_COUNT,
    CONF_ALBUM_ID,
    CONF_ALBUM_NAME,
    CONF_HUB_NAME,
    CONF_TELEGRAM_BOT_TOKEN,
    DOMAIN,
    SERVICE_GET_RECENT_ASSETS,
    SERVICE_REFRESH,
    SERVICE_SEND_TELEGRAM_MEDIA_GROUP,
)
from .coordinator import AlbumData, ImmichAlbumWatcherCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Immich Album Watcher sensors from a config entry."""
    # Iterate through all album subentries
    for subentry_id, subentry in entry.subentries.items():
        subentry_data = hass.data[DOMAIN][entry.entry_id]["subentries"].get(subentry_id)
        if not subentry_data:
            _LOGGER.error("Subentry data not found for %s", subentry_id)
            continue

        coordinator = subentry_data.coordinator

        entities: list[SensorEntity] = [
            ImmichAlbumIdSensor(coordinator, entry, subentry),
            ImmichAlbumAssetCountSensor(coordinator, entry, subentry),
            ImmichAlbumPhotoCountSensor(coordinator, entry, subentry),
            ImmichAlbumVideoCountSensor(coordinator, entry, subentry),
            ImmichAlbumLastUpdatedSensor(coordinator, entry, subentry),
            ImmichAlbumCreatedSensor(coordinator, entry, subentry),
            ImmichAlbumPublicUrlSensor(coordinator, entry, subentry),
            ImmichAlbumProtectedUrlSensor(coordinator, entry, subentry),
            ImmichAlbumProtectedPasswordSensor(coordinator, entry, subentry),
        ]

        async_add_entities(entities, config_subentry_id=subentry_id)

    # Register entity services
    platform = entity_platform.async_get_current_platform()

    platform.async_register_entity_service(
        SERVICE_REFRESH,
        {},
        "async_refresh_album",
    )

    platform.async_register_entity_service(
        SERVICE_GET_RECENT_ASSETS,
        {
            vol.Optional("count", default=10): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=100)
            ),
        },
        "async_get_recent_assets",
        supports_response=SupportsResponse.ONLY,
    )

    platform.async_register_entity_service(
        SERVICE_SEND_TELEGRAM_MEDIA_GROUP,
        {
            vol.Optional("bot_token"): str,
            vol.Required("chat_id"): vol.Coerce(str),
            vol.Required("urls"): vol.All(list, vol.Length(min=1, max=10)),
            vol.Optional("caption"): str,
            vol.Optional("reply_to_message_id"): vol.Coerce(int),
        },
        "async_send_telegram_media_group",
        supports_response=SupportsResponse.ONLY,
    )


class ImmichAlbumBaseSensor(CoordinatorEntity[ImmichAlbumWatcherCoordinator], SensorEntity):
    """Base sensor for Immich album."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._subentry = subentry
        self._album_id = subentry.data[CONF_ALBUM_ID]
        self._album_name = subentry.data.get(CONF_ALBUM_NAME, "Unknown Album")
        self._hub_name = entry.data.get(CONF_HUB_NAME, "Immich")
        # Generate unique_id prefix: {hub_name}_album_{album_name}
        self._unique_id_prefix = slugify(f"{self._hub_name}_album_{self._album_name}")

    @property
    def _album_data(self) -> AlbumData | None:
        """Get the album data from coordinator."""
        return self.coordinator.data

    @property
    def translation_placeholders(self) -> dict[str, str]:
        """Return translation placeholders."""
        if self._album_data:
            return {"album_name": self._album_data.name}
        return {"album_name": self._album_name}

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self._album_data is not None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info - one device per album."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._subentry.subentry_id)},
            name=self._album_name,
            manufacturer="Immich",
            entry_type=DeviceEntryType.SERVICE,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    async def async_refresh_album(self) -> None:
        """Refresh data for this album."""
        await self.coordinator.async_refresh_now()

    async def async_get_recent_assets(self, count: int = 10) -> ServiceResponse:
        """Get recent assets for this album."""
        assets = await self.coordinator.async_get_recent_assets(count)
        return {"assets": assets}

    async def async_send_telegram_media_group(
        self,
        chat_id: str,
        urls: list[dict[str, str]],
        bot_token: str | None = None,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> ServiceResponse:
        """Send media URLs to Telegram as a media group.

        Each item in urls should be a dict with 'url' and 'type' (photo/video).
        Downloads media and uploads to Telegram to bypass CORS restrictions.
        """
        import json
        import aiohttp
        from aiohttp import FormData
        from homeassistant.helpers.aiohttp_client import async_get_clientsession

        # Get bot token from parameter or config
        token = bot_token or self._entry.options.get(CONF_TELEGRAM_BOT_TOKEN)
        if not token:
            return {
                "success": False,
                "error": "No bot token provided. Set it in integration options or pass as parameter.",
            }

        session = async_get_clientsession(self.hass)

        # Download all media files
        media_files: list[tuple[str, bytes, str]] = []
        for i, item in enumerate(urls):
            url = item.get("url")
            media_type = item.get("type", "photo")

            if not url:
                return {
                    "success": False,
                    "error": f"Missing 'url' in item {i}",
                }

            if media_type not in ("photo", "video"):
                return {
                    "success": False,
                    "error": f"Invalid type '{media_type}' in item {i}. Must be 'photo' or 'video'.",
                }

            try:
                _LOGGER.debug("Downloading media %d from %s", i, url[:80])
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return {
                            "success": False,
                            "error": f"Failed to download media {i}: HTTP {resp.status}",
                        }
                    data = await resp.read()
                    ext = "jpg" if media_type == "photo" else "mp4"
                    filename = f"media_{i}.{ext}"
                    media_files.append((media_type, data, filename))
                    _LOGGER.debug("Downloaded media %d: %d bytes", i, len(data))
            except aiohttp.ClientError as err:
                return {
                    "success": False,
                    "error": f"Failed to download media {i}: {err}",
                }

        # Build multipart form
        form = FormData()
        form.add_field("chat_id", chat_id)

        if reply_to_message_id:
            form.add_field("reply_to_message_id", str(reply_to_message_id))

        # Build media JSON with attach:// references
        media_json = []
        for i, (media_type, data, filename) in enumerate(media_files):
            attach_name = f"file{i}"
            media_item: dict[str, Any] = {
                "type": media_type,
                "media": f"attach://{attach_name}",
            }
            if i == 0 and caption:
                media_item["caption"] = caption
            media_json.append(media_item)

            content_type = "image/jpeg" if media_type == "photo" else "video/mp4"
            form.add_field(attach_name, data, filename=filename, content_type=content_type)

        form.add_field("media", json.dumps(media_json))

        # Send to Telegram
        telegram_url = f"https://api.telegram.org/bot{token}/sendMediaGroup"

        try:
            _LOGGER.debug("Uploading %d files to Telegram", len(media_files))
            async with session.post(telegram_url, data=form) as response:
                result = await response.json()
                _LOGGER.debug("Telegram API response: status=%d, ok=%s", response.status, result.get("ok"))
                if response.status == 200 and result.get("ok"):
                    return {
                        "success": True,
                        "message_ids": [
                            msg.get("message_id") for msg in result.get("result", [])
                        ],
                    }
                else:
                    _LOGGER.error("Telegram API error: %s", result)
                    return {
                        "success": False,
                        "error": result.get("description", "Unknown Telegram error"),
                        "error_code": result.get("error_code"),
                    }
        except aiohttp.ClientError as err:
            _LOGGER.error("Telegram upload failed: %s", err)
            return {"success": False, "error": str(err)}


class ImmichAlbumIdSensor(ImmichAlbumBaseSensor):
    """Sensor exposing the Immich album ID."""

    _attr_icon = "mdi:identifier"
    _attr_translation_key = "album_id"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, subentry)
        self._attr_unique_id = f"{self._unique_id_prefix}_album_id"

    @property
    def native_value(self) -> str | None:
        """Return the album ID."""
        if self._album_data:
            return self._album_data.id
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self._album_data:
            return {}

        attrs: dict[str, Any] = {
            "album_name": self._album_data.name,
        }

        # Primary share URL (prefers public, falls back to protected)
        share_url = self.coordinator.get_any_url()
        if share_url:
            attrs["share_url"] = share_url

        return attrs


class ImmichAlbumAssetCountSensor(ImmichAlbumBaseSensor):
    """Sensor representing an Immich album asset count."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:image-album"
    _attr_translation_key = "album_asset_count"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, subentry)
        self._attr_unique_id = f"{self._unique_id_prefix}_asset_count"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor (asset count)."""
        if self._album_data:
            return self._album_data.asset_count
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self._album_data:
            return {}

        attrs = {
            ATTR_ALBUM_ID: self._album_data.id,
            ATTR_ASSET_COUNT: self._album_data.asset_count,
            ATTR_PHOTO_COUNT: self._album_data.photo_count,
            ATTR_VIDEO_COUNT: self._album_data.video_count,
            ATTR_LAST_UPDATED: self._album_data.updated_at,
            ATTR_CREATED_AT: self._album_data.created_at,
            ATTR_SHARED: self._album_data.shared,
            ATTR_OWNER: self._album_data.owner,
            ATTR_PEOPLE: list(self._album_data.people),
        }

        if self._album_data.thumbnail_asset_id:
            attrs[ATTR_THUMBNAIL_URL] = (
                f"{self.coordinator.immich_url}/api/assets/"
                f"{self._album_data.thumbnail_asset_id}/thumbnail"
            )

        return attrs


class ImmichAlbumPhotoCountSensor(ImmichAlbumBaseSensor):
    """Sensor representing an Immich album photo count."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:image"
    _attr_translation_key = "album_photo_count"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, subentry)
        self._attr_unique_id = f"{self._unique_id_prefix}_photo_count"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor (photo count)."""
        if self._album_data:
            return self._album_data.photo_count
        return None


class ImmichAlbumVideoCountSensor(ImmichAlbumBaseSensor):
    """Sensor representing an Immich album video count."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:video"
    _attr_translation_key = "album_video_count"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, subentry)
        self._attr_unique_id = f"{self._unique_id_prefix}_video_count"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor (video count)."""
        if self._album_data:
            return self._album_data.video_count
        return None


class ImmichAlbumLastUpdatedSensor(ImmichAlbumBaseSensor):
    """Sensor representing an Immich album last updated time."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-outline"
    _attr_translation_key = "album_last_updated"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, subentry)
        self._attr_unique_id = f"{self._unique_id_prefix}_last_updated"

    @property
    def native_value(self) -> datetime | None:
        """Return the state of the sensor (last updated datetime)."""
        if self._album_data and self._album_data.updated_at:
            try:
                return datetime.fromisoformat(
                    self._album_data.updated_at.replace("Z", "+00:00")
                )
            except ValueError:
                return None
        return None


class ImmichAlbumCreatedSensor(ImmichAlbumBaseSensor):
    """Sensor representing an Immich album creation date."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:calendar-plus"
    _attr_translation_key = "album_created"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, subentry)
        self._attr_unique_id = f"{self._unique_id_prefix}_created"

    @property
    def native_value(self) -> datetime | None:
        """Return the state of the sensor (creation datetime)."""
        if self._album_data and self._album_data.created_at:
            try:
                return datetime.fromisoformat(
                    self._album_data.created_at.replace("Z", "+00:00")
                )
            except ValueError:
                return None
        return None


class ImmichAlbumPublicUrlSensor(ImmichAlbumBaseSensor):
    """Sensor representing an Immich album public URL."""

    _attr_icon = "mdi:link-variant"
    _attr_translation_key = "album_public_url"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, subentry)
        self._attr_unique_id = f"{self._unique_id_prefix}_public_url"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor (public URL)."""
        if self._album_data:
            return self.coordinator.get_public_url()
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self._album_data:
            return {}

        attrs = {
            ATTR_ALBUM_ID: self._album_data.id,
            ATTR_SHARED: self._album_data.shared,
        }

        all_urls = self.coordinator.get_public_urls()
        if len(all_urls) > 1:
            attrs[ATTR_ALBUM_URLS] = all_urls

        links_info = self.coordinator.get_shared_links_info()
        if links_info:
            attrs["shared_links"] = links_info

        return attrs


class ImmichAlbumProtectedUrlSensor(ImmichAlbumBaseSensor):
    """Sensor representing an Immich album password-protected URL."""

    _attr_icon = "mdi:link-lock"
    _attr_translation_key = "album_protected_url"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, subentry)
        self._attr_unique_id = f"{self._unique_id_prefix}_protected_url"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor (protected URL)."""
        if self._album_data:
            return self.coordinator.get_protected_url()
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self._album_data:
            return {}

        attrs = {
            ATTR_ALBUM_ID: self._album_data.id,
        }

        all_urls = self.coordinator.get_protected_urls()
        if len(all_urls) > 1:
            attrs["protected_urls"] = all_urls

        return attrs


class ImmichAlbumProtectedPasswordSensor(ImmichAlbumBaseSensor):
    """Sensor representing an Immich album protected link password."""

    _attr_icon = "mdi:key"
    _attr_translation_key = "album_protected_password"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, subentry)
        self._attr_unique_id = f"{self._unique_id_prefix}_protected_password"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor (protected link password)."""
        if self._album_data:
            return self.coordinator.get_protected_password()
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self._album_data:
            return {}

        return {
            ATTR_ALBUM_ID: self._album_data.id,
            ATTR_ALBUM_PROTECTED_URL: self.coordinator.get_protected_url(),
        }
