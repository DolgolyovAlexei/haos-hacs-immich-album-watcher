"""Sensor platform for Immich Album Watcher."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from datetime import datetime
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_ALBUM_ID,
    ATTR_ASSET_COUNT,
    ATTR_LAST_UPDATED,
    ATTR_OWNER,
    ATTR_SHARED,
    ATTR_THUMBNAIL_URL,
    CONF_ALBUMS,
    DOMAIN,
)
from .coordinator import AlbumData, ImmichAlbumWatcherCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Immich Album Watcher sensors from a config entry."""
    coordinator: ImmichAlbumWatcherCoordinator = hass.data[DOMAIN][entry.entry_id]
    album_ids = entry.options.get(CONF_ALBUMS, [])

    entities: list[SensorEntity] = []
    for album_id in album_ids:
        entities.append(ImmichAlbumAssetCountSensor(coordinator, entry, album_id))
        entities.append(ImmichAlbumLastUpdatedSensor(coordinator, entry, album_id))

    async_add_entities(entities)


class ImmichAlbumBaseSensor(CoordinatorEntity[ImmichAlbumWatcherCoordinator], SensorEntity):
    """Base sensor for Immich album."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        album_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._album_id = album_id
        self._entry = entry

    @property
    def _album_data(self) -> AlbumData | None:
        """Get the album data from coordinator."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._album_id)

    @property
    def translation_placeholders(self) -> dict[str, str]:
        """Return translation placeholders."""
        if self._album_data:
            return {"album_name": self._album_data.name}
        return {"album_name": f"Album {self._album_id[:8]}"}

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self._album_data is not None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="Immich Album Watcher",
            manufacturer="Immich",
            entry_type="service",
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()


class ImmichAlbumAssetCountSensor(ImmichAlbumBaseSensor):
    """Sensor representing an Immich album asset count."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:image-album"
    _attr_translation_key = "album_asset_count"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        album_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, album_id)
        self._attr_unique_id = f"{entry.entry_id}_{album_id}_asset_count"

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
            ATTR_LAST_UPDATED: self._album_data.updated_at,
            ATTR_SHARED: self._album_data.shared,
            ATTR_OWNER: self._album_data.owner,
        }

        # Add thumbnail URL if available
        if self._album_data.thumbnail_asset_id:
            attrs[ATTR_THUMBNAIL_URL] = (
                f"{self.coordinator.immich_url}/api/assets/"
                f"{self._album_data.thumbnail_asset_id}/thumbnail"
            )

        return attrs


class ImmichAlbumLastUpdatedSensor(ImmichAlbumBaseSensor):
    """Sensor representing an Immich album last updated time."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-outline"
    _attr_translation_key = "album_last_updated"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        album_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, album_id)
        self._attr_unique_id = f"{entry.entry_id}_{album_id}_last_updated"

    @property
    def native_value(self) -> datetime | None:
        """Return the state of the sensor (last updated datetime)."""
        if self._album_data and self._album_data.updated_at:
            try:
                return datetime.fromisoformat(self._album_data.updated_at.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None
