"""Immich Album Watcher integration for Home Assistant."""

from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_ALBUM_ID,
    CONF_ALBUMS,
    CONF_API_KEY,
    CONF_IMMICH_URL,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
    SERVICE_GET_RECENT_ASSETS,
    SERVICE_REFRESH,
)
from .coordinator import ImmichAlbumWatcherCoordinator

_LOGGER = logging.getLogger(__name__)

# Service schemas
SERVICE_REFRESH_SCHEMA = vol.Schema({})

SERVICE_GET_RECENT_ASSETS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ALBUM_ID): cv.string,
        vol.Optional("count", default=10): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Immich Album Watcher from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    url = entry.data[CONF_IMMICH_URL]
    api_key = entry.data[CONF_API_KEY]
    album_ids = entry.options.get(CONF_ALBUMS, [])
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    coordinator = ImmichAlbumWatcherCoordinator(
        hass,
        url=url,
        api_key=api_key,
        album_ids=album_ids,
        scan_interval=scan_interval,
    )

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register update listener for options changes
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    # Register services (only once)
    await async_setup_services(hass)

    _LOGGER.info(
        "Immich Album Watcher set up successfully, watching %d albums",
        len(album_ids),
    )

    return True


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for Immich Album Watcher."""
    if hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        return  # Services already registered

    async def handle_refresh(call: ServiceCall) -> None:
        """Handle the refresh service call."""
        for coordinator in hass.data[DOMAIN].values():
            if isinstance(coordinator, ImmichAlbumWatcherCoordinator):
                await coordinator.async_refresh_now()

    async def handle_get_recent_assets(call: ServiceCall) -> ServiceResponse:
        """Handle the get_recent_assets service call."""
        album_id = call.data[ATTR_ALBUM_ID]
        count = call.data.get("count", 10)

        for coordinator in hass.data[DOMAIN].values():
            if isinstance(coordinator, ImmichAlbumWatcherCoordinator):
                if coordinator.data and album_id in coordinator.data:
                    assets = await coordinator.async_get_recent_assets(album_id, count)
                    return {"assets": assets}

        return {"assets": [], "error": f"Album {album_id} not found"}

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH,
        handle_refresh,
        schema=SERVICE_REFRESH_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_RECENT_ASSETS,
        handle_get_recent_assets,
        schema=SERVICE_GET_RECENT_ASSETS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    coordinator: ImmichAlbumWatcherCoordinator = hass.data[DOMAIN][entry.entry_id]

    album_ids = entry.options.get(CONF_ALBUMS, [])
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    coordinator.update_config(album_ids, scan_interval)

    # Reload the entry to update sensors
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    # Unregister services if no more entries
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, SERVICE_REFRESH)
        hass.services.async_remove(DOMAIN, SERVICE_GET_RECENT_ASSETS)

    return unload_ok
