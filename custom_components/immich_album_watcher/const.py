"""Constants for the Immich Album Watcher integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "immich_album_watcher"

# Configuration keys
CONF_HUB_NAME: Final = "hub_name"
CONF_IMMICH_URL: Final = "immich_url"
CONF_API_KEY: Final = "api_key"
CONF_ALBUMS: Final = "albums"
CONF_ALBUM_ID: Final = "album_id"
CONF_ALBUM_NAME: Final = "album_name"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_TELEGRAM_BOT_TOKEN: Final = "telegram_bot_token"

# Subentry type
SUBENTRY_TYPE_ALBUM: Final = "album"

# Defaults
DEFAULT_SCAN_INTERVAL: Final = 60  # seconds
NEW_ASSETS_RESET_DELAY: Final = 300  # 5 minutes
DEFAULT_SHARE_PASSWORD: Final = "immich123"

# Events
EVENT_ALBUM_CHANGED: Final = f"{DOMAIN}_album_changed"
EVENT_ASSETS_ADDED: Final = f"{DOMAIN}_assets_added"
EVENT_ASSETS_REMOVED: Final = f"{DOMAIN}_assets_removed"
EVENT_ALBUM_RENAMED: Final = f"{DOMAIN}_album_renamed"
EVENT_ALBUM_DELETED: Final = f"{DOMAIN}_album_deleted"
EVENT_ALBUM_SHARING_CHANGED: Final = f"{DOMAIN}_album_sharing_changed"

# Attributes
ATTR_HUB_NAME: Final = "hub_name"
ATTR_ALBUM_ID: Final = "album_id"
ATTR_ALBUM_NAME: Final = "album_name"
ATTR_ALBUM_URL: Final = "album_url"
ATTR_ALBUM_URLS: Final = "album_urls"
ATTR_ALBUM_PROTECTED_URL: Final = "album_protected_url"
ATTR_ALBUM_PROTECTED_PASSWORD: Final = "album_protected_password"
ATTR_ASSET_COUNT: Final = "asset_count"
ATTR_PHOTO_COUNT: Final = "photo_count"
ATTR_VIDEO_COUNT: Final = "video_count"
ATTR_ADDED_COUNT: Final = "added_count"
ATTR_REMOVED_COUNT: Final = "removed_count"
ATTR_ADDED_ASSETS: Final = "added_assets"
ATTR_REMOVED_ASSETS: Final = "removed_assets"
ATTR_CHANGE_TYPE: Final = "change_type"
ATTR_LAST_UPDATED: Final = "last_updated"
ATTR_CREATED_AT: Final = "created_at"
ATTR_THUMBNAIL_URL: Final = "thumbnail_url"
ATTR_SHARED: Final = "shared"
ATTR_OWNER: Final = "owner"
ATTR_PEOPLE: Final = "people"
ATTR_OLD_NAME: Final = "old_name"
ATTR_NEW_NAME: Final = "new_name"
ATTR_OLD_SHARED: Final = "old_shared"
ATTR_NEW_SHARED: Final = "new_shared"
ATTR_ASSET_TYPE: Final = "asset_type"
ATTR_ASSET_FILENAME: Final = "asset_filename"
ATTR_ASSET_CREATED: Final = "asset_created"
ATTR_ASSET_OWNER: Final = "asset_owner"
ATTR_ASSET_OWNER_ID: Final = "asset_owner_id"
ATTR_ASSET_URL: Final = "asset_url"
ATTR_ASSET_DOWNLOAD_URL: Final = "asset_download_url"
ATTR_ASSET_PLAYBACK_URL: Final = "asset_playback_url"
ATTR_ASSET_DESCRIPTION: Final = "asset_description"

# Asset types
ASSET_TYPE_IMAGE: Final = "IMAGE"
ASSET_TYPE_VIDEO: Final = "VIDEO"

# Platforms
PLATFORMS: Final = ["sensor", "binary_sensor", "camera", "text", "button"]

# Services
SERVICE_REFRESH: Final = "refresh"
SERVICE_GET_RECENT_ASSETS: Final = "get_recent_assets"
SERVICE_SEND_TELEGRAM_NOTIFICATION: Final = "send_telegram_notification"
