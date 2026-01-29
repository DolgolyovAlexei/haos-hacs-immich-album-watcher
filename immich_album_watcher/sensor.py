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
    DOMAIN,
    SERVICE_GET_RECENT_ASSETS,
    SERVICE_REFRESH,
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
            ImmichAlbumAssetCountSensor(coordinator, entry, subentry),
            ImmichAlbumPhotoCountSensor(coordinator, entry, subentry),
            ImmichAlbumVideoCountSensor(coordinator, entry, subentry),
            ImmichAlbumLastUpdatedSensor(coordinator, entry, subentry),
            ImmichAlbumCreatedSensor(coordinator, entry, subentry),
            ImmichAlbumPeopleSensor(coordinator, entry, subentry),
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
            via_device=(DOMAIN, self._entry.entry_id),
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
        self._attr_unique_id = f"{subentry.subentry_id}_asset_count"

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
        self._attr_unique_id = f"{subentry.subentry_id}_photo_count"

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
        self._attr_unique_id = f"{subentry.subentry_id}_video_count"

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
        self._attr_unique_id = f"{subentry.subentry_id}_last_updated"

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
        self._attr_unique_id = f"{subentry.subentry_id}_created"

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


class ImmichAlbumPeopleSensor(ImmichAlbumBaseSensor):
    """Sensor representing people detected in an Immich album."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:account-group"
    _attr_translation_key = "album_people_count"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, subentry)
        self._attr_unique_id = f"{subentry.subentry_id}_people_count"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor (number of unique people)."""
        if self._album_data:
            return len(self._album_data.people)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self._album_data:
            return {}

        return {
            ATTR_PEOPLE: list(self._album_data.people),
        }


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
        self._attr_unique_id = f"{subentry.subentry_id}_public_url"

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
        self._attr_unique_id = f"{subentry.subentry_id}_protected_url"

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
        self._attr_unique_id = f"{subentry.subentry_id}_protected_password"

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
