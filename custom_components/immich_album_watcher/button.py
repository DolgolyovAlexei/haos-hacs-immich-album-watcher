"""Button platform for Immich Album Watcher."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import (
    ATTR_ALBUM_ID,
    ATTR_ALBUM_PROTECTED_URL,
    CONF_ALBUM_ID,
    CONF_ALBUM_NAME,
    CONF_HUB_NAME,
    DEFAULT_SHARE_PASSWORD,
    DOMAIN,
)
from .coordinator import AlbumData, ImmichAlbumWatcherCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Immich Album Watcher button entities from a config entry."""
    # Iterate through all album subentries
    for subentry_id, subentry in entry.subentries.items():
        subentry_data = hass.data[DOMAIN][entry.entry_id]["subentries"].get(subentry_id)
        if not subentry_data:
            _LOGGER.error("Subentry data not found for %s", subentry_id)
            continue

        coordinator = subentry_data.coordinator

        async_add_entities(
            [
                ImmichCreateShareLinkButton(coordinator, entry, subentry),
                ImmichDeleteShareLinkButton(coordinator, entry, subentry),
                ImmichCreateProtectedLinkButton(coordinator, entry, subentry),
                ImmichDeleteProtectedLinkButton(coordinator, entry, subentry),
            ],
            config_subentry_id=subentry_id,
        )


class ImmichCreateShareLinkButton(
    CoordinatorEntity[ImmichAlbumWatcherCoordinator], ButtonEntity
):
    """Button entity for creating an unprotected share link."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:link-plus"
    _attr_translation_key = "create_share_link"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the button entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._subentry = subentry
        self._album_id = subentry.data[CONF_ALBUM_ID]
        self._album_name = subentry.data.get(CONF_ALBUM_NAME, "Unknown Album")
        self._hub_name = entry.data.get(CONF_HUB_NAME, "Immich")
        unique_id_prefix = slugify(f"{self._hub_name}_album_{self._album_name}")
        self._attr_unique_id = f"{unique_id_prefix}_create_share_link"

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
        """Return if entity is available.

        Only available when there is no unprotected link.
        """
        if not self.coordinator.last_update_success or self._album_data is None:
            return False
        # Only available if there's no unprotected link yet
        return not self.coordinator.has_unprotected_link()

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info - one device per album."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._subentry.subentry_id)},
            name=self._album_name,
            manufacturer="Immich",
            entry_type=DeviceEntryType.SERVICE,
                    )

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return extra state attributes."""
        if not self._album_data:
            return {}

        return {
            ATTR_ALBUM_ID: self._album_data.id,
        }

    async def async_press(self) -> None:
        """Handle button press - create share link."""
        if self.coordinator.has_unprotected_link():
            _LOGGER.warning(
                "Album %s already has an unprotected share link",
                self._album_name,
            )
            return

        success = await self.coordinator.async_create_shared_link()

        if success:
            await self.coordinator.async_refresh()
        else:
            _LOGGER.error("Failed to create share link for album %s", self._album_id)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()


class ImmichDeleteShareLinkButton(
    CoordinatorEntity[ImmichAlbumWatcherCoordinator], ButtonEntity
):
    """Button entity for deleting an unprotected share link."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:link-off"
    _attr_translation_key = "delete_share_link"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the button entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._subentry = subentry
        self._album_id = subentry.data[CONF_ALBUM_ID]
        self._album_name = subentry.data.get(CONF_ALBUM_NAME, "Unknown Album")
        self._hub_name = entry.data.get(CONF_HUB_NAME, "Immich")
        unique_id_prefix = slugify(f"{self._hub_name}_album_{self._album_name}")
        self._attr_unique_id = f"{unique_id_prefix}_delete_share_link"

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
        """Return if entity is available.

        Only available when there is an unprotected link.
        """
        if not self.coordinator.last_update_success or self._album_data is None:
            return False
        # Only available if there's an unprotected link to delete
        return self.coordinator.has_unprotected_link()

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info - one device per album."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._subentry.subentry_id)},
            name=self._album_name,
            manufacturer="Immich",
            entry_type=DeviceEntryType.SERVICE,
                    )

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return extra state attributes."""
        if not self._album_data:
            return {}

        attrs = {
            ATTR_ALBUM_ID: self._album_data.id,
        }

        public_url = self.coordinator.get_public_url()
        if public_url:
            attrs[ATTR_ALBUM_PROTECTED_URL] = public_url

        return attrs

    async def async_press(self) -> None:
        """Handle button press - delete share link."""
        link_id = self.coordinator.get_unprotected_link_id()
        if not link_id:
            _LOGGER.warning(
                "No unprotected share link found for album %s",
                self._album_name,
            )
            return

        success = await self.coordinator.async_delete_shared_link(link_id)

        if success:
            await self.coordinator.async_refresh()
        else:
            _LOGGER.error("Failed to delete share link for album %s", self._album_id)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()


class ImmichCreateProtectedLinkButton(
    CoordinatorEntity[ImmichAlbumWatcherCoordinator], ButtonEntity
):
    """Button entity for creating a protected (password) share link."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:link-lock"
    _attr_translation_key = "create_protected_link"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the button entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._subentry = subentry
        self._album_id = subentry.data[CONF_ALBUM_ID]
        self._album_name = subentry.data.get(CONF_ALBUM_NAME, "Unknown Album")
        self._hub_name = entry.data.get(CONF_HUB_NAME, "Immich")
        unique_id_prefix = slugify(f"{self._hub_name}_album_{self._album_name}")
        self._attr_unique_id = f"{unique_id_prefix}_create_protected_link"

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
        """Return if entity is available.

        Only available when there is no protected link.
        """
        if not self.coordinator.last_update_success or self._album_data is None:
            return False
        # Only available if there's no protected link yet
        return not self.coordinator.has_protected_link()

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info - one device per album."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._subentry.subentry_id)},
            name=self._album_name,
            manufacturer="Immich",
            entry_type=DeviceEntryType.SERVICE,
                    )

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return extra state attributes."""
        if not self._album_data:
            return {}

        return {
            ATTR_ALBUM_ID: self._album_data.id,
        }

    async def async_press(self) -> None:
        """Handle button press - create protected share link."""
        if self.coordinator.has_protected_link():
            _LOGGER.warning(
                "Album %s already has a protected share link",
                self._album_name,
            )
            return

        success = await self.coordinator.async_create_shared_link(
            password=DEFAULT_SHARE_PASSWORD
        )

        if success:
            await self.coordinator.async_refresh()
        else:
            _LOGGER.error(
                "Failed to create protected share link for album %s", self._album_id
            )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()


class ImmichDeleteProtectedLinkButton(
    CoordinatorEntity[ImmichAlbumWatcherCoordinator], ButtonEntity
):
    """Button entity for deleting a protected (password) share link."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:link-off"
    _attr_translation_key = "delete_protected_link"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the button entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._subentry = subentry
        self._album_id = subentry.data[CONF_ALBUM_ID]
        self._album_name = subentry.data.get(CONF_ALBUM_NAME, "Unknown Album")
        self._hub_name = entry.data.get(CONF_HUB_NAME, "Immich")
        unique_id_prefix = slugify(f"{self._hub_name}_album_{self._album_name}")
        self._attr_unique_id = f"{unique_id_prefix}_delete_protected_link"

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
        """Return if entity is available.

        Only available when there is a protected link.
        """
        if not self.coordinator.last_update_success or self._album_data is None:
            return False
        # Only available if there's a protected link to delete
        return self.coordinator.has_protected_link()

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info - one device per album."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._subentry.subentry_id)},
            name=self._album_name,
            manufacturer="Immich",
            entry_type=DeviceEntryType.SERVICE,
                    )

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return extra state attributes."""
        if not self._album_data:
            return {}

        attrs = {
            ATTR_ALBUM_ID: self._album_data.id,
        }

        protected_url = self.coordinator.get_protected_url()
        if protected_url:
            attrs[ATTR_ALBUM_PROTECTED_URL] = protected_url

        return attrs

    async def async_press(self) -> None:
        """Handle button press - delete protected share link."""
        link_id = self.coordinator.get_protected_link_id()
        if not link_id:
            _LOGGER.warning(
                "No protected share link found for album %s",
                self._album_name,
            )
            return

        success = await self.coordinator.async_delete_shared_link(link_id)

        if success:
            await self.coordinator.async_refresh()
        else:
            _LOGGER.error(
                "Failed to delete protected share link for album %s", self._album_id
            )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
