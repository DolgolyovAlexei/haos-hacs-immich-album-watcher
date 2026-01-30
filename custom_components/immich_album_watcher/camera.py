"""Camera platform for Immich Album Watcher."""

from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import CONF_ALBUM_ID, CONF_ALBUM_NAME, CONF_HUB_NAME, DOMAIN
from .coordinator import AlbumData, ImmichAlbumWatcherCoordinator

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=60)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Immich Album Watcher cameras from a config entry."""
    # Iterate through all album subentries
    for subentry_id, subentry in entry.subentries.items():
        subentry_data = hass.data[DOMAIN][entry.entry_id]["subentries"].get(subentry_id)
        if not subentry_data:
            _LOGGER.error("Subentry data not found for %s", subentry_id)
            continue

        coordinator = subentry_data.coordinator

        async_add_entities(
            [ImmichAlbumThumbnailCamera(coordinator, entry, subentry)],
            config_subentry_id=subentry_id,
        )


class ImmichAlbumThumbnailCamera(
    CoordinatorEntity[ImmichAlbumWatcherCoordinator], Camera
):
    """Camera entity showing the album thumbnail."""

    _attr_has_entity_name = True
    _attr_translation_key = "album_thumbnail"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the camera."""
        CoordinatorEntity.__init__(self, coordinator)
        Camera.__init__(self)
        self._entry = entry
        self._subentry = subentry
        self._album_id = subentry.data[CONF_ALBUM_ID]
        self._album_name = subentry.data.get(CONF_ALBUM_NAME, "Unknown Album")
        self._hub_name = entry.data.get(CONF_HUB_NAME, "Immich")
        unique_id_prefix = slugify(f"{self._hub_name}_album_{self._album_name}")
        self._attr_unique_id = f"{unique_id_prefix}_thumbnail"
        self._cached_image: bytes | None = None
        self._last_thumbnail_id: str | None = None

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
        return (
            self.coordinator.last_update_success
            and self._album_data is not None
            and self._album_data.thumbnail_asset_id is not None
        )

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

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return extra state attributes."""
        if not self._album_data:
            return {}

        return {
            "album_id": self._album_data.id,
            "album_name": self._album_data.name,
            "thumbnail_asset_id": self._album_data.thumbnail_asset_id,
        }

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return bytes of camera image."""
        if not self._album_data or not self._album_data.thumbnail_asset_id:
            return None

        # Check if thumbnail changed
        if self._album_data.thumbnail_asset_id == self._last_thumbnail_id:
            if self._cached_image:
                return self._cached_image

        # Fetch new thumbnail
        session = async_get_clientsession(self.hass)
        headers = {"x-api-key": self.coordinator.api_key}

        thumbnail_url = (
            f"{self.coordinator.immich_url}/api/assets/"
            f"{self._album_data.thumbnail_asset_id}/thumbnail"
        )

        try:
            async with session.get(thumbnail_url, headers=headers) as response:
                if response.status == 200:
                    self._cached_image = await response.read()
                    self._last_thumbnail_id = self._album_data.thumbnail_asset_id
                    return self._cached_image
                else:
                    _LOGGER.warning(
                        "Failed to fetch thumbnail for album %s: HTTP %s",
                        self._album_data.name,
                        response.status,
                    )
        except aiohttp.ClientError as err:
            _LOGGER.error("Error fetching thumbnail: %s", err)

        return self._cached_image

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Clear cache if thumbnail changed
        if self._album_data and self._album_data.thumbnail_asset_id != self._last_thumbnail_id:
            self._cached_image = None
        self.async_write_ha_state()
