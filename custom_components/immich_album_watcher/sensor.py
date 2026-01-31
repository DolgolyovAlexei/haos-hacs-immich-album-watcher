"""Sensor platform for Immich Album Watcher."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import voluptuous as vol

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant, ServiceResponse, SupportsResponse, callback
from homeassistant.helpers import entity_platform
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import (
    ATTR_ALBUM_ID,
    ATTR_ALBUM_PROTECTED_URL,
    ATTR_ALBUM_URLS,
    ATTR_ASSET_COUNT,
    ATTR_CREATED_AT,
    ATTR_LAST_UPDATED,
    ATTR_OWNER,
    ATTR_PEOPLE,
    ATTR_PHOTO_COUNT,
    ATTR_SHARED,
    ATTR_THUMBNAIL_URL,
    ATTR_VIDEO_COUNT,
    CONF_ALBUM_ID,
    CONF_ALBUM_NAME,
    CONF_HUB_NAME,
    CONF_TELEGRAM_BOT_TOKEN,
    DOMAIN,
    SERVICE_GET_RECENT_ASSETS,
    SERVICE_REFRESH,
    SERVICE_SEND_TELEGRAM_NOTIFICATION,
)
from .coordinator import AlbumData, ImmichAlbumWatcherCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Immich Album Watcher sensors from a config entry."""
    # Iterate through all album subentries
    for subentry_id, subentry in entry.subentries.items():
        subentry_data = hass.data[DOMAIN][entry.entry_id]["subentries"].get(subentry_id)
        if not subentry_data:
            _LOGGER.error("Subentry data not found for %s", subentry_id)
            continue

        coordinator = subentry_data.coordinator

        entities: list[SensorEntity] = [
            ImmichAlbumIdSensor(coordinator, entry, subentry),
            ImmichAlbumAssetCountSensor(coordinator, entry, subentry),
            ImmichAlbumPhotoCountSensor(coordinator, entry, subentry),
            ImmichAlbumVideoCountSensor(coordinator, entry, subentry),
            ImmichAlbumLastUpdatedSensor(coordinator, entry, subentry),
            ImmichAlbumCreatedSensor(coordinator, entry, subentry),
            ImmichAlbumPublicUrlSensor(coordinator, entry, subentry),
            ImmichAlbumProtectedUrlSensor(coordinator, entry, subentry),
            ImmichAlbumProtectedPasswordSensor(coordinator, entry, subentry),
        ]

        async_add_entities(entities, config_subentry_id=subentry_id)

    # Register entity services
    platform = entity_platform.async_get_current_platform()

    platform.async_register_entity_service(
        SERVICE_REFRESH,
        {},
        "async_refresh_album",
    )

    platform.async_register_entity_service(
        SERVICE_GET_RECENT_ASSETS,
        {
            vol.Optional("count", default=10): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=100)
            ),
        },
        "async_get_recent_assets",
        supports_response=SupportsResponse.ONLY,
    )

    platform.async_register_entity_service(
        SERVICE_SEND_TELEGRAM_NOTIFICATION,
        {
            vol.Optional("bot_token"): str,
            vol.Required("chat_id"): vol.Coerce(str),
            vol.Optional("urls"): list,
            vol.Optional("caption"): str,
            vol.Optional("reply_to_message_id"): vol.Coerce(int),
            vol.Optional("disable_web_page_preview"): bool,
            vol.Optional("parse_mode", default="HTML"): str,
            vol.Optional("max_group_size", default=10): vol.All(
                vol.Coerce(int), vol.Range(min=2, max=10)
            ),
            vol.Optional("chunk_delay", default=0): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=60000)
            ),
            vol.Optional("wait_for_response", default=True): bool,
        },
        "async_send_telegram_notification",
        supports_response=SupportsResponse.OPTIONAL,
    )


class ImmichAlbumBaseSensor(CoordinatorEntity[ImmichAlbumWatcherCoordinator], SensorEntity):
    """Base sensor for Immich album."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._subentry = subentry
        self._album_id = subentry.data[CONF_ALBUM_ID]
        self._album_name = subentry.data.get(CONF_ALBUM_NAME, "Unknown Album")
        self._hub_name = entry.data.get(CONF_HUB_NAME, "Immich")
        # Generate unique_id prefix: {hub_name}_album_{album_name}
        self._unique_id_prefix = slugify(f"{self._hub_name}_album_{self._album_name}")

    @property
    def _album_data(self) -> AlbumData | None:
        """Get the album data from coordinator."""
        return self.coordinator.data

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self._album_data is not None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info - one device per album."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._subentry.subentry_id)},
            name=self._album_name,
            manufacturer="Immich",
            entry_type=DeviceEntryType.SERVICE,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    async def async_refresh_album(self) -> None:
        """Refresh data for this album."""
        await self.coordinator.async_refresh_now()

    async def async_get_recent_assets(self, count: int = 10) -> ServiceResponse:
        """Get recent assets for this album."""
        assets = await self.coordinator.async_get_recent_assets(count)
        return {"assets": assets}

    async def async_send_telegram_notification(
        self,
        chat_id: str,
        urls: list[dict[str, str]] | None = None,
        bot_token: str | None = None,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
        disable_web_page_preview: bool | None = None,
        parse_mode: str = "HTML",
        max_group_size: int = 10,
        chunk_delay: int = 0,
        wait_for_response: bool = True,
        max_asset_data_size: int | None = None,
        send_large_photos_as_documents: bool = False,
    ) -> ServiceResponse:
        """Send notification to Telegram.

        Supports:
        - Empty URLs: sends a simple text message
        - Single photo: uses sendPhoto API
        - Single video: uses sendVideo API
        - Multiple items: uses sendMediaGroup API (splits into multiple groups if needed)

        Each item in urls should be a dict with 'url' and 'type' (photo/video).
        Downloads media and uploads to Telegram to bypass CORS restrictions.

        If wait_for_response is False, the task will be executed in the background
        and the service will return immediately.
        """
        # If non-blocking mode, create a background task and return immediately
        if not wait_for_response:
            self.hass.async_create_task(
                self._execute_telegram_notification(
                    chat_id=chat_id,
                    urls=urls,
                    bot_token=bot_token,
                    caption=caption,
                    reply_to_message_id=reply_to_message_id,
                    disable_web_page_preview=disable_web_page_preview,
                    parse_mode=parse_mode,
                    max_group_size=max_group_size,
                    chunk_delay=chunk_delay,
                    max_asset_data_size=max_asset_data_size,
                    send_large_photos_as_documents=send_large_photos_as_documents,
                )
            )
            return {"success": True, "status": "queued", "message": "Notification queued for background processing"}

        # Blocking mode - execute and return result
        return await self._execute_telegram_notification(
            chat_id=chat_id,
            urls=urls,
            bot_token=bot_token,
            caption=caption,
            reply_to_message_id=reply_to_message_id,
            disable_web_page_preview=disable_web_page_preview,
            parse_mode=parse_mode,
            max_group_size=max_group_size,
            chunk_delay=chunk_delay,
            max_asset_data_size=max_asset_data_size,
            send_large_photos_as_documents=send_large_photos_as_documents,
        )

    async def _execute_telegram_notification(
        self,
        chat_id: str,
        urls: list[dict[str, str]] | None = None,
        bot_token: str | None = None,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
        disable_web_page_preview: bool | None = None,
        parse_mode: str = "HTML",
        max_group_size: int = 10,
        chunk_delay: int = 0,
        max_asset_data_size: int | None = None,
        send_large_photos_as_documents: bool = False,
    ) -> ServiceResponse:
        """Execute the Telegram notification (internal method)."""
        import json
        import aiohttp
        from aiohttp import FormData
        from homeassistant.helpers.aiohttp_client import async_get_clientsession

        # Get bot token from parameter or config
        token = bot_token or self._entry.options.get(CONF_TELEGRAM_BOT_TOKEN)
        if not token:
            return {
                "success": False,
                "error": "No bot token provided. Set it in integration options or pass as parameter.",
            }

        session = async_get_clientsession(self.hass)

        # Handle empty URLs - send simple text message
        if not urls:
            return await self._send_telegram_message(
                session, token, chat_id, caption or "", reply_to_message_id, disable_web_page_preview, parse_mode
            )

        # Handle single photo
        if len(urls) == 1 and urls[0].get("type", "photo") == "photo":
            return await self._send_telegram_photo(
                session, token, chat_id, urls[0].get("url"), caption, reply_to_message_id, parse_mode,
                max_asset_data_size, send_large_photos_as_documents
            )

        # Handle single video
        if len(urls) == 1 and urls[0].get("type") == "video":
            return await self._send_telegram_video(
                session, token, chat_id, urls[0].get("url"), caption, reply_to_message_id, parse_mode, max_asset_data_size
            )

        # Handle multiple items - send as media group(s)
        return await self._send_telegram_media_group(
            session, token, chat_id, urls, caption, reply_to_message_id, max_group_size, chunk_delay, parse_mode,
            max_asset_data_size, send_large_photos_as_documents
        )

    async def _send_telegram_message(
        self,
        session: Any,
        token: str,
        chat_id: str,
        text: str,
        reply_to_message_id: int | None = None,
        disable_web_page_preview: bool | None = None,
        parse_mode: str = "HTML",
    ) -> ServiceResponse:
        """Send a simple text message to Telegram."""
        import aiohttp

        telegram_url = f"https://api.telegram.org/bot{token}/sendMessage"

        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text or "Notification from Home Assistant",
            "parse_mode": parse_mode,
        }

        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id

        if disable_web_page_preview is not None:
            payload["disable_web_page_preview"] = disable_web_page_preview

        try:
            _LOGGER.debug("Sending text message to Telegram")
            async with session.post(telegram_url, json=payload) as response:
                result = await response.json()
                _LOGGER.debug("Telegram API response: status=%d, ok=%s", response.status, result.get("ok"))
                if response.status == 200 and result.get("ok"):
                    return {
                        "success": True,
                        "message_id": result.get("result", {}).get("message_id"),
                    }
                else:
                    _LOGGER.error("Telegram API error: %s", result)
                    return {
                        "success": False,
                        "error": result.get("description", "Unknown Telegram error"),
                        "error_code": result.get("error_code"),
                    }
        except aiohttp.ClientError as err:
            _LOGGER.error("Telegram message send failed: %s", err)
            return {"success": False, "error": str(err)}

    def _check_telegram_photo_limits(
        self,
        data: bytes,
    ) -> tuple[bool, str | None, int | None, int | None]:
        """Check if photo data exceeds Telegram photo limits.

        Telegram limits for photos:
        - Max file size: 10 MB
        - Max dimension sum: ~10,000 pixels (width + height)

        Returns:
            Tuple of (exceeds_limits, reason, width, height)
            - exceeds_limits: True if photo exceeds limits
            - reason: Human-readable reason (None if within limits)
            - width: Image width in pixels (None if PIL not available)
            - height: Image height in pixels (None if PIL not available)
        """
        TELEGRAM_MAX_PHOTO_SIZE = 10 * 1024 * 1024  # 10 MB
        TELEGRAM_MAX_DIMENSION_SUM = 10000

        # Check file size
        if len(data) > TELEGRAM_MAX_PHOTO_SIZE:
            return True, f"size {len(data)} bytes exceeds {TELEGRAM_MAX_PHOTO_SIZE} bytes limit", None, None

        # Try to check dimensions using PIL
        try:
            from PIL import Image
            import io

            img = Image.open(io.BytesIO(data))
            width, height = img.size
            dimension_sum = width + height

            if dimension_sum > TELEGRAM_MAX_DIMENSION_SUM:
                return True, f"dimensions {width}x{height} (sum={dimension_sum}) exceed {TELEGRAM_MAX_DIMENSION_SUM} limit", width, height

            return False, None, width, height
        except ImportError:
            # PIL not available, can't check dimensions
            _LOGGER.debug("PIL not available, skipping dimension check")
            return False, None, None, None
        except Exception as e:
            # Failed to check dimensions
            _LOGGER.debug("Failed to check photo dimensions: %s", e)
            return False, None, None, None

    def _downsize_photo(
        self,
        data: bytes,
        max_dimension_sum: int = 10000,
        max_file_size: int = 9 * 1024 * 1024,  # 9 MB to be safe
    ) -> tuple[bytes | None, str | None]:
        """Downsize photo to fit within Telegram limits.

        Args:
            data: Original photo bytes
            max_dimension_sum: Maximum sum of width + height
            max_file_size: Maximum file size in bytes

        Returns:
            Tuple of (downsized_data, error)
            - downsized_data: Downsized photo bytes (None if failed)
            - error: Error message (None if successful)
        """
        try:
            from PIL import Image
            import io

            img = Image.open(io.BytesIO(data))
            width, height = img.size
            dimension_sum = width + height

            # Calculate scale factor based on dimensions
            if dimension_sum > max_dimension_sum:
                scale = max_dimension_sum / dimension_sum
                new_width = int(width * scale)
                new_height = int(height * scale)

                _LOGGER.info(
                    "Downsizing photo from %dx%d to %dx%d to fit Telegram limits",
                    width, height, new_width, new_height
                )

                # Resize with high-quality Lanczos resampling
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Save with progressive quality reduction until size fits
            output = io.BytesIO()
            quality = 95

            while quality >= 50:
                output.seek(0)
                output.truncate()
                img.save(output, format='JPEG', quality=quality, optimize=True)
                output_size = output.tell()

                if output_size <= max_file_size:
                    _LOGGER.debug(
                        "Photo downsized successfully: %d bytes (quality=%d)",
                        output_size, quality
                    )
                    return output.getvalue(), None

                quality -= 5

            # If we can't get it small enough, return error
            return None, f"Unable to downsize photo below {max_file_size} bytes (final size: {output_size} bytes at quality {quality + 5})"

        except ImportError:
            return None, "PIL not available, cannot downsize photo"
        except Exception as e:
            _LOGGER.error("Failed to downsize photo: %s", e)
            return None, f"Failed to downsize photo: {e}"

    async def _send_telegram_photo(
        self,
        session: Any,
        token: str,
        chat_id: str,
        url: str | None,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
        parse_mode: str = "HTML",
        max_asset_data_size: int | None = None,
        send_large_photos_as_documents: bool = False,
    ) -> ServiceResponse:
        """Send a single photo to Telegram."""
        import aiohttp
        from aiohttp import FormData

        if not url:
            return {"success": False, "error": "Missing 'url' for photo"}

        try:
            # Download the photo
            _LOGGER.debug("Downloading photo from %s", url[:80])
            async with session.get(url) as resp:
                if resp.status != 200:
                    return {
                        "success": False,
                        "error": f"Failed to download photo: HTTP {resp.status}",
                    }
                data = await resp.read()
                _LOGGER.debug("Downloaded photo: %d bytes", len(data))

            # Check if photo exceeds max size limit (user-defined limit)
            if max_asset_data_size is not None and len(data) > max_asset_data_size:
                _LOGGER.warning(
                    "Photo size (%d bytes) exceeds max_asset_data_size limit (%d bytes), skipping",
                    len(data), max_asset_data_size
                )
                return {
                    "success": False,
                    "error": f"Photo size ({len(data)} bytes) exceeds max_asset_data_size limit ({max_asset_data_size} bytes)",
                    "skipped": True,
                }

            # Check if photo exceeds Telegram's photo limits
            exceeds_limits, reason, width, height = self._check_telegram_photo_limits(data)
            if exceeds_limits:
                if send_large_photos_as_documents:
                    # Send as document instead
                    _LOGGER.info("Photo %s, sending as document", reason)
                    return await self._send_telegram_document(
                        session, token, chat_id, data, "photo.jpg",
                        caption, reply_to_message_id, parse_mode
                    )
                else:
                    # Try to downsize the photo
                    _LOGGER.info("Photo %s, attempting to downsize", reason)
                    downsized_data, error = self._downsize_photo(data)
                    if downsized_data:
                        data = downsized_data
                    else:
                        return {
                            "success": False,
                            "error": f"Photo exceeds Telegram limits and downsize failed: {error}",
                        }

            # Build multipart form
            form = FormData()
            form.add_field("chat_id", chat_id)
            form.add_field("photo", data, filename="photo.jpg", content_type="image/jpeg")
            form.add_field("parse_mode", parse_mode)

            if caption:
                form.add_field("caption", caption)

            if reply_to_message_id:
                form.add_field("reply_to_message_id", str(reply_to_message_id))

            # Send to Telegram
            telegram_url = f"https://api.telegram.org/bot{token}/sendPhoto"

            _LOGGER.debug("Uploading photo to Telegram")
            async with session.post(telegram_url, data=form) as response:
                result = await response.json()
                _LOGGER.debug("Telegram API response: status=%d, ok=%s", response.status, result.get("ok"))
                if response.status == 200 and result.get("ok"):
                    return {
                        "success": True,
                        "message_id": result.get("result", {}).get("message_id"),
                    }
                else:
                    _LOGGER.error("Telegram API error: %s", result)
                    return {
                        "success": False,
                        "error": result.get("description", "Unknown Telegram error"),
                        "error_code": result.get("error_code"),
                    }
        except aiohttp.ClientError as err:
            _LOGGER.error("Telegram photo upload failed: %s", err)
            return {"success": False, "error": str(err)}

    async def _send_telegram_video(
        self,
        session: Any,
        token: str,
        chat_id: str,
        url: str | None,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
        parse_mode: str = "HTML",
        max_asset_data_size: int | None = None,
    ) -> ServiceResponse:
        """Send a single video to Telegram."""
        import aiohttp
        from aiohttp import FormData

        if not url:
            return {"success": False, "error": "Missing 'url' for video"}

        try:
            # Download the video
            _LOGGER.debug("Downloading video from %s", url[:80])
            async with session.get(url) as resp:
                if resp.status != 200:
                    return {
                        "success": False,
                        "error": f"Failed to download video: HTTP {resp.status}",
                    }
                data = await resp.read()
                _LOGGER.debug("Downloaded video: %d bytes", len(data))

            # Check if video exceeds max size limit
            if max_asset_data_size is not None and len(data) > max_asset_data_size:
                _LOGGER.warning(
                    "Video size (%d bytes) exceeds max_asset_data_size limit (%d bytes), skipping",
                    len(data), max_asset_data_size
                )
                return {
                    "success": False,
                    "error": f"Video size ({len(data)} bytes) exceeds max_asset_data_size limit ({max_asset_data_size} bytes)",
                    "skipped": True,
                }

            # Build multipart form
            form = FormData()
            form.add_field("chat_id", chat_id)
            form.add_field("video", data, filename="video.mp4", content_type="video/mp4")
            form.add_field("parse_mode", parse_mode)

            if caption:
                form.add_field("caption", caption)

            if reply_to_message_id:
                form.add_field("reply_to_message_id", str(reply_to_message_id))

            # Send to Telegram
            telegram_url = f"https://api.telegram.org/bot{token}/sendVideo"

            _LOGGER.debug("Uploading video to Telegram")
            async with session.post(telegram_url, data=form) as response:
                result = await response.json()
                _LOGGER.debug("Telegram API response: status=%d, ok=%s", response.status, result.get("ok"))
                if response.status == 200 and result.get("ok"):
                    return {
                        "success": True,
                        "message_id": result.get("result", {}).get("message_id"),
                    }
                else:
                    _LOGGER.error("Telegram API error: %s", result)
                    return {
                        "success": False,
                        "error": result.get("description", "Unknown Telegram error"),
                        "error_code": result.get("error_code"),
                    }
        except aiohttp.ClientError as err:
            _LOGGER.error("Telegram video upload failed: %s", err)
            return {"success": False, "error": str(err)}

    async def _send_telegram_document(
        self,
        session: Any,
        token: str,
        chat_id: str,
        data: bytes,
        filename: str = "photo.jpg",
        caption: str | None = None,
        reply_to_message_id: int | None = None,
        parse_mode: str = "HTML",
    ) -> ServiceResponse:
        """Send a photo as a document to Telegram (for oversized photos)."""
        import aiohttp
        from aiohttp import FormData

        try:
            # Build multipart form
            form = FormData()
            form.add_field("chat_id", chat_id)
            form.add_field("document", data, filename=filename, content_type="image/jpeg")
            form.add_field("parse_mode", parse_mode)

            if caption:
                form.add_field("caption", caption)

            if reply_to_message_id:
                form.add_field("reply_to_message_id", str(reply_to_message_id))

            # Send to Telegram
            telegram_url = f"https://api.telegram.org/bot{token}/sendDocument"

            _LOGGER.debug("Uploading oversized photo as document to Telegram (%d bytes)", len(data))
            async with session.post(telegram_url, data=form) as response:
                result = await response.json()
                _LOGGER.debug("Telegram API response: status=%d, ok=%s", response.status, result.get("ok"))
                if response.status == 200 and result.get("ok"):
                    return {
                        "success": True,
                        "message_id": result.get("result", {}).get("message_id"),
                    }
                else:
                    _LOGGER.error("Telegram API error: %s", result)
                    return {
                        "success": False,
                        "error": result.get("description", "Unknown Telegram error"),
                        "error_code": result.get("error_code"),
                    }
        except aiohttp.ClientError as err:
            _LOGGER.error("Telegram document upload failed: %s", err)
            return {"success": False, "error": str(err)}

    async def _send_telegram_media_group(
        self,
        session: Any,
        token: str,
        chat_id: str,
        urls: list[dict[str, str]],
        caption: str | None = None,
        reply_to_message_id: int | None = None,
        max_group_size: int = 10,
        chunk_delay: int = 0,
        parse_mode: str = "HTML",
        max_asset_data_size: int | None = None,
        send_large_photos_as_documents: bool = False,
    ) -> ServiceResponse:
        """Send media URLs to Telegram as media group(s).

        If urls list exceeds max_group_size, splits into multiple media groups.
        For chunks with single items, uses sendPhoto/sendVideo APIs.
        Applies chunk_delay (in milliseconds) between groups if specified.
        """
        import json
        import asyncio
        import aiohttp
        from aiohttp import FormData

        # Split URLs into chunks based on max_group_size
        chunks = [urls[i:i + max_group_size] for i in range(0, len(urls), max_group_size)]
        all_message_ids = []

        _LOGGER.debug("Sending %d media items in %d chunk(s) of max %d items (delay: %dms)",
                      len(urls), len(chunks), max_group_size, chunk_delay)

        for chunk_idx, chunk in enumerate(chunks):
            # Add delay before sending subsequent chunks
            if chunk_idx > 0 and chunk_delay > 0:
                delay_seconds = chunk_delay / 1000
                _LOGGER.debug("Waiting %dms (%ss) before sending chunk %d/%d",
                             chunk_delay, delay_seconds, chunk_idx + 1, len(chunks))
                await asyncio.sleep(delay_seconds)

            # Optimize: Use single-item APIs for chunks with 1 item
            if len(chunk) == 1:
                item = chunk[0]
                media_type = item.get("type", "photo")
                url = item.get("url")

                # Only apply caption and reply_to to the first chunk
                chunk_caption = caption if chunk_idx == 0 else None
                chunk_reply_to = reply_to_message_id if chunk_idx == 0 else None

                if media_type == "photo":
                    _LOGGER.debug("Sending chunk %d/%d as single photo", chunk_idx + 1, len(chunks))
                    result = await self._send_telegram_photo(
                        session, token, chat_id, url, chunk_caption, chunk_reply_to, parse_mode,
                        max_asset_data_size, send_large_photos_as_documents
                    )
                else:  # video
                    _LOGGER.debug("Sending chunk %d/%d as single video", chunk_idx + 1, len(chunks))
                    result = await self._send_telegram_video(
                        session, token, chat_id, url, chunk_caption, chunk_reply_to, parse_mode, max_asset_data_size
                    )

                if not result.get("success"):
                    result["failed_at_chunk"] = chunk_idx + 1
                    return result

                all_message_ids.append(result.get("message_id"))
                continue
            # Multi-item chunk: use sendMediaGroup
            _LOGGER.debug("Sending chunk %d/%d as media group (%d items)", chunk_idx + 1, len(chunks), len(chunk))

            # Download all media files for this chunk
            media_files: list[tuple[str, bytes, str]] = []
            oversized_photos: list[tuple[bytes, str | None]] = []  # For send_large_photos_as_documents=true
            skipped_count = 0

            for i, item in enumerate(chunk):
                url = item.get("url")
                media_type = item.get("type", "photo")

                if not url:
                    return {
                        "success": False,
                        "error": f"Missing 'url' in item {chunk_idx * max_group_size + i}",
                    }

                if media_type not in ("photo", "video"):
                    return {
                        "success": False,
                        "error": f"Invalid type '{media_type}' in item {chunk_idx * max_group_size + i}. Must be 'photo' or 'video'.",
                    }

                try:
                    _LOGGER.debug("Downloading media %d from %s", chunk_idx * max_group_size + i, url[:80])
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            return {
                                "success": False,
                                "error": f"Failed to download media {chunk_idx * max_group_size + i}: HTTP {resp.status}",
                            }
                        data = await resp.read()
                        _LOGGER.debug("Downloaded media %d: %d bytes", chunk_idx * max_group_size + i, len(data))

                        # Check if media exceeds max_asset_data_size limit (user-defined limit for skipping)
                        if max_asset_data_size is not None and len(data) > max_asset_data_size:
                            _LOGGER.warning(
                                "Media %d size (%d bytes) exceeds max_asset_data_size limit (%d bytes), skipping",
                                chunk_idx * max_group_size + i, len(data), max_asset_data_size
                            )
                            skipped_count += 1
                            continue

                        # For photos, check Telegram limits
                        if media_type == "photo":
                            exceeds_limits, reason, width, height = self._check_telegram_photo_limits(data)
                            if exceeds_limits:
                                if send_large_photos_as_documents:
                                    # Separate this photo to send as document later
                                    # Caption only on first item of first chunk
                                    photo_caption = caption if chunk_idx == 0 and i == 0 and len(media_files) == 0 else None
                                    oversized_photos.append((data, photo_caption))
                                    _LOGGER.info("Photo %d %s, will send as document", i, reason)
                                    continue
                                else:
                                    # Try to downsize the photo
                                    _LOGGER.info("Photo %d %s, attempting to downsize", i, reason)
                                    downsized_data, error = self._downsize_photo(data)
                                    if downsized_data:
                                        data = downsized_data
                                    else:
                                        _LOGGER.error("Failed to downsize photo %d: %s, skipping", i, error)
                                        skipped_count += 1
                                        continue

                        ext = "jpg" if media_type == "photo" else "mp4"
                        filename = f"media_{chunk_idx * max_group_size + i}.{ext}"
                        media_files.append((media_type, data, filename))
                except aiohttp.ClientError as err:
                    return {
                        "success": False,
                        "error": f"Failed to download media {chunk_idx * max_group_size + i}: {err}",
                    }

            # Skip this chunk if all files were filtered out
            if not media_files and not oversized_photos:
                _LOGGER.info("Chunk %d/%d: all %d media items skipped",
                            chunk_idx + 1, len(chunks), len(chunk))
                continue

            # Send media group if we have normal-sized files
            if media_files:
                # Build multipart form
                form = FormData()
                form.add_field("chat_id", chat_id)

                # Only use reply_to_message_id for the first chunk
                if chunk_idx == 0 and reply_to_message_id:
                    form.add_field("reply_to_message_id", str(reply_to_message_id))

                # Build media JSON with attach:// references
                media_json = []
                for i, (media_type, data, filename) in enumerate(media_files):
                    attach_name = f"file{i}"
                    media_item: dict[str, Any] = {
                        "type": media_type,
                        "media": f"attach://{attach_name}",
                    }
                    # Only add caption to the first item of the first chunk (if no oversized photos with caption)
                    if chunk_idx == 0 and i == 0 and caption and not oversized_photos:
                        media_item["caption"] = caption
                        media_item["parse_mode"] = parse_mode
                    media_json.append(media_item)

                    content_type = "image/jpeg" if media_type == "photo" else "video/mp4"
                    form.add_field(attach_name, data, filename=filename, content_type=content_type)

                form.add_field("media", json.dumps(media_json))

                # Send to Telegram
                telegram_url = f"https://api.telegram.org/bot{token}/sendMediaGroup"

                try:
                    _LOGGER.debug("Uploading media group chunk %d/%d (%d files) to Telegram",
                                 chunk_idx + 1, len(chunks), len(media_files))
                    async with session.post(telegram_url, data=form) as response:
                        result = await response.json()
                        _LOGGER.debug("Telegram API response: status=%d, ok=%s", response.status, result.get("ok"))
                        if response.status == 200 and result.get("ok"):
                            chunk_message_ids = [
                                msg.get("message_id") for msg in result.get("result", [])
                            ]
                            all_message_ids.extend(chunk_message_ids)
                        else:
                            _LOGGER.error("Telegram API error for chunk %d: %s", chunk_idx + 1, result)
                            return {
                                "success": False,
                                "error": result.get("description", "Unknown Telegram error"),
                                "error_code": result.get("error_code"),
                                "failed_at_chunk": chunk_idx + 1,
                            }
                except aiohttp.ClientError as err:
                    _LOGGER.error("Telegram upload failed for chunk %d: %s", chunk_idx + 1, err)
                    return {
                        "success": False,
                        "error": str(err),
                        "failed_at_chunk": chunk_idx + 1,
                    }

            # Send oversized photos as documents
            for i, (data, photo_caption) in enumerate(oversized_photos):
                _LOGGER.debug("Sending oversized photo %d/%d as document", i + 1, len(oversized_photos))
                result = await self._send_telegram_document(
                    session, token, chat_id, data, f"photo_{i}.jpg",
                    photo_caption, None, parse_mode
                )
                if result.get("success"):
                    all_message_ids.append(result.get("message_id"))
                else:
                    _LOGGER.error("Failed to send oversized photo as document: %s", result.get("error"))
                    # Continue with other photos even if one fails

        return {
            "success": True,
            "message_ids": all_message_ids,
            "chunks_sent": len(chunks),
        }


class ImmichAlbumIdSensor(ImmichAlbumBaseSensor):
    """Sensor exposing the Immich album ID."""

    _attr_icon = "mdi:identifier"
    _attr_translation_key = "album_id"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, subentry)
        self._attr_unique_id = f"{self._unique_id_prefix}_album_id"

    @property
    def native_value(self) -> str | None:
        """Return the album ID."""
        if self._album_data:
            return self._album_data.id
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self._album_data:
            return {}

        attrs: dict[str, Any] = {
            "album_name": self._album_data.name,
        }

        # Primary share URL (prefers public, falls back to protected)
        share_url = self.coordinator.get_any_url()
        if share_url:
            attrs["share_url"] = share_url

        return attrs


class ImmichAlbumAssetCountSensor(ImmichAlbumBaseSensor):
    """Sensor representing an Immich album asset count."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:image-album"
    _attr_translation_key = "album_asset_count"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, subentry)
        self._attr_unique_id = f"{self._unique_id_prefix}_asset_count"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor (asset count)."""
        if self._album_data:
            return self._album_data.asset_count
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self._album_data:
            return {}

        attrs = {
            ATTR_ALBUM_ID: self._album_data.id,
            ATTR_ASSET_COUNT: self._album_data.asset_count,
            ATTR_PHOTO_COUNT: self._album_data.photo_count,
            ATTR_VIDEO_COUNT: self._album_data.video_count,
            ATTR_LAST_UPDATED: self._album_data.updated_at,
            ATTR_CREATED_AT: self._album_data.created_at,
            ATTR_SHARED: self._album_data.shared,
            ATTR_OWNER: self._album_data.owner,
            ATTR_PEOPLE: list(self._album_data.people),
        }

        if self._album_data.thumbnail_asset_id:
            attrs[ATTR_THUMBNAIL_URL] = (
                f"{self.coordinator.immich_url}/api/assets/"
                f"{self._album_data.thumbnail_asset_id}/thumbnail"
            )

        return attrs


class ImmichAlbumPhotoCountSensor(ImmichAlbumBaseSensor):
    """Sensor representing an Immich album photo count."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:image"
    _attr_translation_key = "album_photo_count"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, subentry)
        self._attr_unique_id = f"{self._unique_id_prefix}_photo_count"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor (photo count)."""
        if self._album_data:
            return self._album_data.photo_count
        return None


class ImmichAlbumVideoCountSensor(ImmichAlbumBaseSensor):
    """Sensor representing an Immich album video count."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:video"
    _attr_translation_key = "album_video_count"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, subentry)
        self._attr_unique_id = f"{self._unique_id_prefix}_video_count"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor (video count)."""
        if self._album_data:
            return self._album_data.video_count
        return None


class ImmichAlbumLastUpdatedSensor(ImmichAlbumBaseSensor):
    """Sensor representing an Immich album last updated time."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-outline"
    _attr_translation_key = "album_last_updated"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, subentry)
        self._attr_unique_id = f"{self._unique_id_prefix}_last_updated"

    @property
    def native_value(self) -> datetime | None:
        """Return the state of the sensor (last updated datetime)."""
        if self._album_data and self._album_data.updated_at:
            try:
                return datetime.fromisoformat(
                    self._album_data.updated_at.replace("Z", "+00:00")
                )
            except ValueError:
                return None
        return None


class ImmichAlbumCreatedSensor(ImmichAlbumBaseSensor):
    """Sensor representing an Immich album creation date."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:calendar-plus"
    _attr_translation_key = "album_created"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, subentry)
        self._attr_unique_id = f"{self._unique_id_prefix}_created"

    @property
    def native_value(self) -> datetime | None:
        """Return the state of the sensor (creation datetime)."""
        if self._album_data and self._album_data.created_at:
            try:
                return datetime.fromisoformat(
                    self._album_data.created_at.replace("Z", "+00:00")
                )
            except ValueError:
                return None
        return None


class ImmichAlbumPublicUrlSensor(ImmichAlbumBaseSensor):
    """Sensor representing an Immich album public URL."""

    _attr_icon = "mdi:link-variant"
    _attr_translation_key = "album_public_url"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, subentry)
        self._attr_unique_id = f"{self._unique_id_prefix}_public_url"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor (public URL)."""
        if self._album_data:
            return self.coordinator.get_public_url()
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self._album_data:
            return {}

        attrs = {
            ATTR_ALBUM_ID: self._album_data.id,
            ATTR_SHARED: self._album_data.shared,
        }

        all_urls = self.coordinator.get_public_urls()
        if len(all_urls) > 1:
            attrs[ATTR_ALBUM_URLS] = all_urls

        links_info = self.coordinator.get_shared_links_info()
        if links_info:
            attrs["shared_links"] = links_info

        return attrs


class ImmichAlbumProtectedUrlSensor(ImmichAlbumBaseSensor):
    """Sensor representing an Immich album password-protected URL."""

    _attr_icon = "mdi:link-lock"
    _attr_translation_key = "album_protected_url"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, subentry)
        self._attr_unique_id = f"{self._unique_id_prefix}_protected_url"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor (protected URL)."""
        if self._album_data:
            return self.coordinator.get_protected_url()
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self._album_data:
            return {}

        attrs = {
            ATTR_ALBUM_ID: self._album_data.id,
        }

        all_urls = self.coordinator.get_protected_urls()
        if len(all_urls) > 1:
            attrs["protected_urls"] = all_urls

        return attrs


class ImmichAlbumProtectedPasswordSensor(ImmichAlbumBaseSensor):
    """Sensor representing an Immich album protected link password."""

    _attr_icon = "mdi:key"
    _attr_translation_key = "album_protected_password"

    def __init__(
        self,
        coordinator: ImmichAlbumWatcherCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, subentry)
        self._attr_unique_id = f"{self._unique_id_prefix}_protected_password"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor (protected link password)."""
        if self._album_data:
            return self.coordinator.get_protected_password()
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self._album_data:
            return {}

        return {
            ATTR_ALBUM_ID: self._album_data.id,
            ATTR_ALBUM_PROTECTED_URL: self.coordinator.get_protected_url(),
        }
