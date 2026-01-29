"""Binary sensor platform for Immich Album Watcher."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import (
    ATTR_ALBUM_ID,
    ATTR_ALBUM_NAME,
    CONF_ALBUM_ID,
    CONF_ALBUM_NAME,
    CONF_HUB_NAME,
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
    # Iterate through all album subentries
    for subentry_id, subentry in entry.subentries.items():
        subentry_data = hass.data[DOMAIN][entry.entry_id]["subentries"].get(subentry_id)
        if not subentry_data:
            _LOGGER.error("Subentry data not found for %s", subentry_id)
            continue

        coordinator = subentry_data.coordinator

        async_add_entities(
            [ImmichAlbumNewAssetsSensor(coordinator, entry, subentry)],
            config_subentry_id=subentry_id,
        )


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
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._subentry = subentry
        self._album_id = subentry.data[CONF_ALBUM_ID]
        self._album_name = subentry.data.get(CONF_ALBUM_NAME, "Unknown Album")
        self._hub_name = entry.data.get(CONF_HUB_NAME, "Immich")
        unique_id_prefix = slugify(f"{self._hub_name}_album_{self._album_name}")
        self._attr_unique_id = f"{unique_id_prefix}_new_assets"

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
                self.coordinator.clear_new_assets_flag()
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

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the sensor (clear new assets flag)."""
        self.coordinator.clear_new_assets_flag()
        self.async_write_ha_state()
