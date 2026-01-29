"""Immich Album Watcher integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ALBUMS,
    CONF_API_KEY,
    CONF_IMMICH_URL,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import ImmichAlbumWatcherCoordinator

_LOGGER = logging.getLogger(__name__)


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

    _LOGGER.info(
        "Immich Album Watcher set up successfully, watching %d albums",
        len(album_ids),
    )

    return True


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

    return unload_ok
