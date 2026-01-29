"""Config flow for Immich Album Watcher integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_ALBUMS,
    CONF_API_KEY,
    CONF_IMMICH_URL,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def validate_connection(
    session: aiohttp.ClientSession, url: str, api_key: str
) -> dict[str, Any]:
    """Validate the Immich connection and return server info."""
    headers = {"x-api-key": api_key}
    async with session.get(
        f"{url.rstrip('/')}/api/server/ping", headers=headers
    ) as response:
        if response.status == 401:
            raise InvalidAuth
        if response.status != 200:
            raise CannotConnect
        return await response.json()


async def fetch_albums(
    session: aiohttp.ClientSession, url: str, api_key: str
) -> list[dict[str, Any]]:
    """Fetch all albums from Immich."""
    headers = {"x-api-key": api_key}
    async with session.get(
        f"{url.rstrip('/')}/api/albums", headers=headers
    ) as response:
        if response.status != 200:
            raise CannotConnect
        return await response.json()


class ImmichAlbumWatcherConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Immich Album Watcher."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._url: str | None = None
        self._api_key: str | None = None
        self._albums: list[dict[str, Any]] = []

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return ImmichAlbumWatcherOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - connection details."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._url = user_input[CONF_IMMICH_URL].rstrip("/")
            self._api_key = user_input[CONF_API_KEY]

            session = async_get_clientsession(self.hass)

            try:
                await validate_connection(session, self._url, self._api_key)
                self._albums = await fetch_albums(session, self._url, self._api_key)

                if not self._albums:
                    errors["base"] = "no_albums"
                else:
                    return await self.async_step_albums()

            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_IMMICH_URL): str,
                    vol.Required(CONF_API_KEY): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "docs_url": "https://immich.app/docs/features/command-line-interface#obtain-the-api-key"
            },
        )

    async def async_step_albums(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle album selection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_albums = user_input.get(CONF_ALBUMS, [])

            if not selected_albums:
                errors["base"] = "no_albums_selected"
            else:
                # Create unique ID based on URL
                await self.async_set_unique_id(self._url)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title="Immich Album Watcher",
                    data={
                        CONF_IMMICH_URL: self._url,
                        CONF_API_KEY: self._api_key,
                    },
                    options={
                        CONF_ALBUMS: selected_albums,
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                    },
                )

        # Build album selection list
        album_options = {
            album["id"]: f"{album.get('albumName', 'Unnamed')} ({album.get('assetCount', 0)} assets)"
            for album in self._albums
        }

        return self.async_show_form(
            step_id="albums",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ALBUMS): cv.multi_select(album_options),
                }
            ),
            errors=errors,
        )


class ImmichAlbumWatcherOptionsFlow(OptionsFlow):
    """Handle options flow for Immich Album Watcher."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self._albums: list[dict[str, Any]] = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        # Fetch current albums from Immich
        session = async_get_clientsession(self.hass)
        url = self._config_entry.data[CONF_IMMICH_URL]
        api_key = self._config_entry.data[CONF_API_KEY]

        try:
            self._albums = await fetch_albums(session, url, api_key)
        except Exception:
            _LOGGER.exception("Failed to fetch albums")
            errors["base"] = "cannot_connect"

        if user_input is not None and not errors:
            return self.async_create_entry(
                title="",
                data={
                    CONF_ALBUMS: user_input.get(CONF_ALBUMS, []),
                    CONF_SCAN_INTERVAL: user_input.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                },
            )

        # Build album selection list
        album_options = {
            album["id"]: f"{album.get('albumName', 'Unnamed')} ({album.get('assetCount', 0)} assets)"
            for album in self._albums
        }

        current_albums = self._config_entry.options.get(CONF_ALBUMS, [])
        current_interval = self._config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ALBUMS, default=current_albums): cv.multi_select(
                        album_options
                    ),
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=current_interval
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
                }
            ),
            errors=errors,
        )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""
