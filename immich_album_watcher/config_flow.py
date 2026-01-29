"""Config flow for Immich Album Watcher integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ALBUM_ID,
    CONF_ALBUM_NAME,
    CONF_API_KEY,
    CONF_HUB_NAME,
    CONF_IMMICH_URL,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SUBENTRY_TYPE_ALBUM,
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

    VERSION = 2

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._url: str | None = None
        self._api_key: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return ImmichAlbumWatcherOptionsFlow(config_entry)

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return supported subentry types."""
        return {SUBENTRY_TYPE_ALBUM: ImmichAlbumSubentryFlowHandler}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step - connection details."""
        errors: dict[str, str] = {}

        if user_input is not None:
            hub_name = user_input[CONF_HUB_NAME].strip()
            self._url = user_input[CONF_IMMICH_URL].rstrip("/")
            self._api_key = user_input[CONF_API_KEY]

            session = async_get_clientsession(self.hass)

            try:
                await validate_connection(session, self._url, self._api_key)

                # Set unique ID based on URL
                await self.async_set_unique_id(self._url)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=hub_name,
                    data={
                        CONF_HUB_NAME: hub_name,
                        CONF_IMMICH_URL: self._url,
                        CONF_API_KEY: self._api_key,
                    },
                    options={
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                    },
                )

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
                    vol.Required(CONF_HUB_NAME, default="Immich"): str,
                    vol.Required(CONF_IMMICH_URL): str,
                    vol.Required(CONF_API_KEY): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "docs_url": "https://immich.app/docs/features/command-line-interface#obtain-the-api-key"
            },
        )


class ImmichAlbumSubentryFlowHandler(ConfigSubentryFlow):
    """Handle subentry flow for adding albums."""

    def __init__(self) -> None:
        """Initialize the subentry flow."""
        super().__init__()
        self._albums: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle album selection."""
        errors: dict[str, str] = {}

        # Get parent config entry data
        config_entry = self._get_entry()

        url = config_entry.data[CONF_IMMICH_URL]
        api_key = config_entry.data[CONF_API_KEY]

        # Fetch available albums
        session = async_get_clientsession(self.hass)
        try:
            self._albums = await fetch_albums(session, url, api_key)
        except Exception:
            _LOGGER.exception("Failed to fetch albums")
            errors["base"] = "cannot_connect"
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({}),
                errors=errors,
            )

        if not self._albums:
            return self.async_abort(reason="no_albums")

        if user_input is not None:
            album_id = user_input[CONF_ALBUM_ID]

            # Check if album is already configured
            for subentry in config_entry.subentries.values():
                if subentry.data.get(CONF_ALBUM_ID) == album_id:
                    return self.async_abort(reason="album_already_configured")

            # Find album name
            album_name = "Unknown Album"
            for album in self._albums:
                if album["id"] == album_id:
                    album_name = album.get("albumName", "Unnamed")
                    break

            return self.async_create_entry(
                title=album_name,
                data={
                    CONF_ALBUM_ID: album_id,
                    CONF_ALBUM_NAME: album_name,
                },
            )

        # Get already configured album IDs
        configured_albums = set()
        for subentry in config_entry.subentries.values():
            if aid := subentry.data.get(CONF_ALBUM_ID):
                configured_albums.add(aid)

        # Build album selection list (excluding already configured)
        album_options = {
            album["id"]: f"{album.get('albumName', 'Unnamed')} ({album.get('assetCount', 0)} assets)"
            for album in self._albums
            if album["id"] not in configured_albums
        }

        if not album_options:
            return self.async_abort(reason="all_albums_configured")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ALBUM_ID): vol.In(album_options),
                }
            ),
            errors=errors,
        )


class ImmichAlbumWatcherOptionsFlow(OptionsFlow):
    """Handle options flow for Immich Album Watcher."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_SCAN_INTERVAL: user_input.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                },
            )

        current_interval = self._config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=current_interval
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
                }
            ),
        )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""
