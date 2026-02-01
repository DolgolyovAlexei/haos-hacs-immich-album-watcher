"""Immich Album Watcher integration for Home Assistant."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ALBUM_ID,
    CONF_ALBUM_NAME,
    CONF_API_KEY,
    CONF_HUB_NAME,
    CONF_IMMICH_URL,
    CONF_SCAN_INTERVAL,
    CONF_TELEGRAM_CACHE_TTL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TELEGRAM_CACHE_TTL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import ImmichAlbumWatcherCoordinator
from .storage import ImmichAlbumStorage, TelegramFileCache

_LOGGER = logging.getLogger(__name__)


@dataclass
class ImmichHubData:
    """Data for the Immich hub."""

    name: str
    url: str
    api_key: str
    scan_interval: int
    telegram_cache_ttl: int


@dataclass
class ImmichAlbumRuntimeData:
    """Runtime data for an album subentry."""

    coordinator: ImmichAlbumWatcherCoordinator
    album_id: str
    album_name: str


type ImmichConfigEntry = ConfigEntry[ImmichHubData]


async def async_setup_entry(hass: HomeAssistant, entry: ImmichConfigEntry) -> bool:
    """Set up Immich Album Watcher hub from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    hub_name = entry.data.get(CONF_HUB_NAME, "Immich")
    url = entry.data[CONF_IMMICH_URL]
    api_key = entry.data[CONF_API_KEY]
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    telegram_cache_ttl = entry.options.get(CONF_TELEGRAM_CACHE_TTL, DEFAULT_TELEGRAM_CACHE_TTL)

    # Store hub data
    entry.runtime_data = ImmichHubData(
        name=hub_name,
        url=url,
        api_key=api_key,
        scan_interval=scan_interval,
        telegram_cache_ttl=telegram_cache_ttl,
    )

    # Create storage for persisting album state across restarts
    storage = ImmichAlbumStorage(hass, entry.entry_id)
    await storage.async_load()

    # Store hub reference
    hass.data[DOMAIN][entry.entry_id] = {
        "hub": entry.runtime_data,
        "subentries": {},
        "storage": storage,
    }

    # Track loaded subentries to detect changes
    hass.data[DOMAIN][entry.entry_id]["loaded_subentries"] = set(entry.subentries.keys())

    # Set up coordinators for all subentries (albums)
    for subentry_id, subentry in entry.subentries.items():
        await _async_setup_subentry_coordinator(hass, entry, subentry)

    # Forward platform setup once - platforms will iterate through subentries
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register update listener for options and subentry changes
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _LOGGER.info(
        "Immich Album Watcher hub set up successfully with %d albums",
        len(entry.subentries),
    )

    return True


async def _async_setup_subentry_coordinator(
    hass: HomeAssistant, entry: ImmichConfigEntry, subentry: ConfigSubentry
) -> None:
    """Set up coordinator for an album subentry."""
    hub_data: ImmichHubData = entry.runtime_data
    album_id = subentry.data[CONF_ALBUM_ID]
    album_name = subentry.data.get(CONF_ALBUM_NAME, "Unknown Album")
    storage: ImmichAlbumStorage = hass.data[DOMAIN][entry.entry_id]["storage"]

    _LOGGER.debug("Setting up coordinator for album: %s (%s)", album_name, album_id)

    # Create and load Telegram file cache for this album
    # TTL is in hours from config, convert to seconds
    cache_ttl_seconds = hub_data.telegram_cache_ttl * 60 * 60
    telegram_cache = TelegramFileCache(hass, album_id, ttl_seconds=cache_ttl_seconds)
    await telegram_cache.async_load()

    # Create coordinator for this album
    coordinator = ImmichAlbumWatcherCoordinator(
        hass,
        url=hub_data.url,
        api_key=hub_data.api_key,
        album_id=album_id,
        album_name=album_name,
        scan_interval=hub_data.scan_interval,
        hub_name=hub_data.name,
        storage=storage,
        telegram_cache=telegram_cache,
    )

    # Load persisted state before first refresh to detect changes during downtime
    await coordinator.async_load_persisted_state()

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    # Store subentry runtime data
    subentry_data = ImmichAlbumRuntimeData(
        coordinator=coordinator,
        album_id=album_id,
        album_name=album_name,
    )
    hass.data[DOMAIN][entry.entry_id]["subentries"][subentry.subentry_id] = subentry_data

    _LOGGER.info("Coordinator for album '%s' set up successfully", album_name)


async def _async_update_listener(
    hass: HomeAssistant, entry: ImmichConfigEntry
) -> None:
    """Handle config entry updates (options or subentry changes)."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    loaded_subentries = entry_data.get("loaded_subentries", set())
    current_subentries = set(entry.subentries.keys())

    # Check if subentries changed
    if loaded_subentries != current_subentries:
        _LOGGER.info(
            "Subentries changed (loaded: %d, current: %d), reloading entry",
            len(loaded_subentries),
            len(current_subentries),
        )
        await hass.config_entries.async_reload(entry.entry_id)
        return

    # Handle options-only update (scan interval change)
    new_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    # Update hub data
    entry.runtime_data.scan_interval = new_interval

    # Update all subentry coordinators
    subentries_data = entry_data["subentries"]
    for subentry_data in subentries_data.values():
        subentry_data.coordinator.update_scan_interval(new_interval)

    _LOGGER.info("Updated scan interval to %d seconds", new_interval)


async def async_unload_entry(hass: HomeAssistant, entry: ImmichConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload all platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Clean up hub data
        hass.data[DOMAIN].pop(entry.entry_id, None)
        _LOGGER.info("Immich Album Watcher hub unloaded")

    return unload_ok
