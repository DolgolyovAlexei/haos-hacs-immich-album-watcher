"""Text platform for Immich Album Watcher."""

from __future__ import annotations

import logging

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_ALBUM_ID,
    ATTR_ALBUM_PROTECTED_URL,
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
    """Set up Immich Album Watcher text entities from a config entry."""
    coordinator: ImmichAlbumWatcherCoordinator = hass.data[DOMAIN][entry.entry_id]
    album_ids = entry.options.get(CONF_ALBUMS, [])

    entities: list[TextEntity] = []
    for album_id in album_ids:
        entities.append(ImmichAlbumProtectedPasswordText(coordinator, entry, album_id))

    async_add_entities(entities)


class ImmichAlbumProtectedPasswordText(
    CoordinatorEntity[ImmichAlbumWatcherCoordinator], TextEntity
):
    """Text entity for editing an Immich album's protected link password."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:key-variant"
    _attr_translation_key = "album_protected_password_edit"
    _attr_mode = TextMode.PASSWORD
    _attr_native_max = 100

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        album_id: str,
    ) -> None:
        """Initialize the text entity."""
        super().__init__(coordinator)
        self._album_id = album_id
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{album_id}_protected_password_edit"

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
        """Return if entity is available.

        Only available when the album has a protected shared link.
        """
        if not self.coordinator.last_update_success or self._album_data is None:
            return False
        # Only available if there's a protected link to edit
        return self.coordinator.get_album_protected_link_id(self._album_id) is not None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="Immich Album Watcher",
            manufacturer="Immich",
            entry_type="service",
        )

    @property
    def native_value(self) -> str | None:
        """Return the current password value."""
        if self._album_data:
            return self.coordinator.get_album_protected_password(self._album_id)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return extra state attributes."""
        if not self._album_data:
            return {}

        attrs = {
            ATTR_ALBUM_ID: self._album_data.id,
        }

        protected_url = self.coordinator.get_album_protected_url(self._album_id)
        if protected_url:
            attrs[ATTR_ALBUM_PROTECTED_URL] = protected_url

        return attrs

    async def async_set_value(self, value: str) -> None:
        """Set the password for the protected shared link."""
        link_id = self.coordinator.get_album_protected_link_id(self._album_id)
        if not link_id:
            _LOGGER.error(
                "Cannot set password: no protected link found for album %s",
                self._album_id,
            )
            return

        # Empty string means remove password
        password = value if value else None

        success = await self.coordinator.async_set_shared_link_password(
            link_id, password
        )

        if success:
            # Trigger a coordinator update to refresh the state
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to update password for album %s", self._album_id)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
