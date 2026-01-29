"""Constants for the Immich Album Watcher integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "immich_album_watcher"

# Configuration keys
CONF_IMMICH_URL: Final = "immich_url"
CONF_API_KEY: Final = "api_key"
CONF_ALBUMS: Final = "albums"
CONF_SCAN_INTERVAL: Final = "scan_interval"

# Defaults
DEFAULT_SCAN_INTERVAL: Final = 60  # seconds

# Events
EVENT_ALBUM_CHANGED: Final = f"{DOMAIN}_album_changed"
EVENT_ASSETS_ADDED: Final = f"{DOMAIN}_assets_added"
EVENT_ASSETS_REMOVED: Final = f"{DOMAIN}_assets_removed"

# Attributes
ATTR_ALBUM_ID: Final = "album_id"
ATTR_ALBUM_NAME: Final = "album_name"
ATTR_ASSET_COUNT: Final = "asset_count"
ATTR_ADDED_COUNT: Final = "added_count"
ATTR_REMOVED_COUNT: Final = "removed_count"
ATTR_ADDED_ASSETS: Final = "added_assets"
ATTR_REMOVED_ASSETS: Final = "removed_assets"
ATTR_CHANGE_TYPE: Final = "change_type"
ATTR_LAST_UPDATED: Final = "last_updated"
ATTR_THUMBNAIL_URL: Final = "thumbnail_url"
ATTR_SHARED: Final = "shared"
ATTR_OWNER: Final = "owner"

# Platforms
PLATFORMS: Final = ["sensor"]
