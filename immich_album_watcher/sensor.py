"""Sensor platform for Immich Album Watcher."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
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

    entities = [
        ImmichAlbumSensor(coordinator, entry, album_id)
        for album_id in album_ids
    ]

    async_add_entities(entities)


class ImmichAlbumSensor(CoordinatorEntity[ImmichAlbumWatcherCoordinator], SensorEntity):
    """Sensor representing an Immich album."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "assets"
    _attr_icon = "mdi:image-album"

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

        # Entity IDs and names will be set when data is available
        self._attr_unique_id = f"{entry.entry_id}_{album_id}"
        self._attr_has_entity_name = True

    @property
    def _album_data(self) -> AlbumData | None:
        """Get the album data from coordinator."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._album_id)

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        if self._album_data:
            return self._album_data.name
        return f"Album {self._album_id[:8]}"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor (asset count)."""
        if self._album_data:
            return self._album_data.asset_count
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self._album_data is not None

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
