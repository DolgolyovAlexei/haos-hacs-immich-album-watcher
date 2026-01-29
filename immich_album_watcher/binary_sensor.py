"""Binary sensor platform for Immich Album Watcher."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_ADDED_COUNT,
    ATTR_ALBUM_ID,
    ATTR_ALBUM_NAME,
    CONF_ALBUMS,
    DOMAIN,
    NEW_ASSETS_RESET_DELAY,
)
from .coordinator import AlbumData, ImmichAlbumWatcherCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Immich Album Watcher binary sensors from a config entry."""
    coordinator: ImmichAlbumWatcherCoordinator = hass.data[DOMAIN][entry.entry_id]
    album_ids = entry.options.get(CONF_ALBUMS, [])

    entities = [
        ImmichAlbumNewAssetsSensor(coordinator, entry, album_id)
        for album_id in album_ids
    ]

    async_add_entities(entities)


class ImmichAlbumNewAssetsSensor(
    CoordinatorEntity[ImmichAlbumWatcherCoordinator], BinarySensorEntity
):
    """Binary sensor that turns on when new assets are detected in an album."""

    _attr_device_class = BinarySensorDeviceClass.UPDATE
    _attr_has_entity_name = True
    _attr_translation_key = "album_new_assets"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        album_id: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._album_id = album_id
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{album_id}_new_assets"
        self._reset_unsub = None

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
    def is_on(self) -> bool | None:
        """Return true if new assets were recently added."""
        if self._album_data is None:
            return None

        if not self._album_data.has_new_assets:
            return False

        # Check if we're still within the reset window
        if self._album_data.last_change_time:
            elapsed = datetime.now() - self._album_data.last_change_time
            if elapsed > timedelta(seconds=NEW_ASSETS_RESET_DELAY):
                # Auto-reset the flag
                self.coordinator.clear_new_assets_flag(self._album_id)
                return False

        return True

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self._album_data is not None

    @property
    def extra_state_attributes(self) -> dict[str, str | int | None]:
        """Return extra state attributes."""
        if not self._album_data:
            return {}

        attrs = {
            ATTR_ALBUM_ID: self._album_data.id,
            ATTR_ALBUM_NAME: self._album_data.name,
        }

        if self._album_data.last_change_time:
            attrs["last_change"] = self._album_data.last_change_time.isoformat()

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

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the sensor (clear new assets flag)."""
        self.coordinator.clear_new_assets_flag(self._album_id)
        self.async_write_ha_state()
