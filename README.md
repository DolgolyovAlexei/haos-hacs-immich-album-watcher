# Immich Album Watcher

<img src="custom_components/immich_album_watcher/icon.png" alt="Immich" width="64" height="64">

A Home Assistant custom integration that monitors [Immich](https://immich.app/) photo/video library albums for changes and exposes them as Home Assistant entities with event-firing capabilities.

## Features

- **Album Monitoring** - Watch selected Immich albums for asset additions and removals
- **Rich Sensor Data** - Multiple sensors per album:
  - Album ID (with share URL attribute)
  - Asset count (with detected people list)
  - Photo count
  - Video count
  - Last updated timestamp
  - Creation date
- **Camera Entity** - Album thumbnail displayed as a camera entity for dashboards
- **Binary Sensor** - "New Assets" indicator that turns on when assets are added
- **Face Recognition** - Detects and lists people recognized in album photos
- **Event Firing** - Fires Home Assistant events when albums change:
  - `immich_album_watcher_album_changed` - General album changes
  - `immich_album_watcher_assets_added` - When new assets are added
  - `immich_album_watcher_assets_removed` - When assets are removed
- **Enhanced Event Data** - Events include detailed asset info:
  - Asset type (photo/video)
  - Filename
  - Creation date
  - Asset owner (who uploaded the asset)
  - Asset description/caption
  - Public URL (if album has a shared link)
  - Detected people in the asset
- **Services** - Custom service calls:
  - `immich_album_watcher.refresh` - Force immediate data refresh
  - `immich_album_watcher.get_recent_assets` - Get recent assets from an album
  - `immich_album_watcher.send_telegram_notification` - Send text, photo, video, or media group to Telegram
- **Share Link Management** - Button entities to create and delete share links:
  - Create/delete public (unprotected) share links
  - Create/delete password-protected share links
  - Edit protected link passwords via Text entity
- **Configurable Polling** - Adjustable scan interval (10-3600 seconds)

## Installation

### HACS Installation (Recommended)

1. Open HACS in Home Assistant
2. Click on the three dots in the top right corner
3. Select **Custom repositories**
4. Add this repository URL: `https://github.com/DolgolyovAlexei/haos-hacs-immich-album-watcher`
5. Select **Integration** as the category
6. Click **Add**
7. Search for "Immich Album Watcher" in HACS and install it
8. Restart Home Assistant
9. Add the integration via **Settings** → **Devices & Services** → **Add Integration**

### Manual Installation

1. Download or clone this repository
2. Copy the `custom_components/immich_album_watcher` folder to your Home Assistant `config/custom_components` directory
3. Restart Home Assistant
4. Add the integration via **Settings** → **Devices & Services** → **Add Integration**

> **Tip:** For the best experience, use this integration with the [Immich Album Watcher Blueprint](https://github.com/DolgolyovAlexei/haos-blueprints/blob/main/Common/Immich%20Album%20Watcher.yaml) to easily create automations for album change notifications.

## Configuration

| Option | Description | Default |
|--------|-------------|---------|
| Server URL | Your Immich server URL (e.g., `https://immich.example.com`) | Required |
| API Key | Your Immich API key | Required |
| Albums | Albums to monitor | Required |
| Scan Interval | How often to check for changes (seconds) | 60 |
| Telegram Bot Token | Bot token for sending media to Telegram (optional) | - |

## Entities Created (per album)

| Entity Type | Name | Description |
|-------------|------|-------------|
| Sensor | Album ID | Album identifier with `album_name` and `share_url` attributes |
| Sensor | Asset Count | Total number of assets (includes `people` list in attributes) |
| Sensor | Photo Count | Number of photos in the album |
| Sensor | Video Count | Number of videos in the album |
| Sensor | Last Updated | When the album was last modified |
| Sensor | Created | When the album was created |
| Sensor | Public URL | Public share link URL (accessible links without password) |
| Sensor | Protected URL | Password-protected share link URL (if any exist) |
| Sensor | Protected Password | Password for the protected share link (read-only) |
| Binary Sensor | New Assets | On when new assets were recently added |
| Camera | Thumbnail | Album cover image |
| Text | Protected Password | Editable password for the protected share link |
| Button | Create Share Link | Creates an unprotected public share link |
| Button | Delete Share Link | Deletes the unprotected public share link |
| Button | Create Protected Link | Creates a password-protected share link |
| Button | Delete Protected Link | Deletes the password-protected share link |

## Services

### Refresh

Force an immediate refresh of all album data:

```yaml
service: immich_album_watcher.refresh
```

### Get Recent Assets

Get the most recent assets from a specific album (returns response data):

```yaml
service: immich_album_watcher.get_recent_assets
target:
  entity_id: sensor.album_name_asset_count
data:
  count: 10
```

### Send Telegram Notification

Send notifications to Telegram. Supports multiple formats:

- **Text message** - When `urls` is empty or not provided
- **Single photo** - When `urls` contains one photo
- **Single video** - When `urls` contains one video
- **Media group** - When `urls` contains multiple items

The service downloads media from Immich and uploads it to Telegram, bypassing any CORS restrictions. Large lists of media are automatically split into multiple media groups based on the `max_group_size` parameter (default: 10 items per group).

**Examples:**

Text message:

```yaml
service: immich_album_watcher.send_telegram_notification
target:
  entity_id: sensor.album_name_asset_count
data:
  chat_id: "-1001234567890"
  caption: "Check out the new album!"
  disable_web_page_preview: true
```

Single photo:

```yaml
service: immich_album_watcher.send_telegram_notification
target:
  entity_id: sensor.album_name_asset_count
data:
  chat_id: "-1001234567890"
  urls:
    - url: "https://immich.example.com/api/assets/xxx/thumbnail?key=yyy"
      type: photo
  caption: "Beautiful sunset!"
```

Media group:

```yaml
service: immich_album_watcher.send_telegram_notification
target:
  entity_id: sensor.album_name_asset_count
data:
  chat_id: "-1001234567890"
  urls:
    - url: "https://immich.example.com/api/assets/xxx/thumbnail?key=yyy"
      type: photo
    - url: "https://immich.example.com/api/assets/zzz/video/playback?key=yyy"
      type: video
  caption: "New photos from the album!"
  reply_to_message_id: 123
```

HTML formatting:

```yaml
service: immich_album_watcher.send_telegram_notification
target:
  entity_id: sensor.album_name_asset_count
data:
  chat_id: "-1001234567890"
  caption: |
    <b>Album Updated!</b>
    New photos by <i>{{ trigger.event.data.added_assets[0].asset_owner }}</i>
    <a href="https://immich.example.com/album">View Album</a>
  parse_mode: "HTML"  # Default, can be omitted
```

Non-blocking mode (fire-and-forget):

```yaml
service: immich_album_watcher.send_telegram_notification
target:
  entity_id: sensor.album_name_asset_count
data:
  chat_id: "-1001234567890"
  urls:
    - url: "https://immich.example.com/api/assets/xxx/thumbnail?key=yyy"
      type: photo
  caption: "Quick notification"
  wait_for_response: false  # Automation continues immediately
```

| Field | Description | Required |
|-------|-------------|----------|
| `chat_id` | Telegram chat ID to send to | Yes |
| `urls` | List of media items with `url` and `type` (photo/video). Empty for text message. | No |
| `bot_token` | Telegram bot token (uses configured token if not provided) | No |
| `caption` | For media: caption applied to first item. For text: the message text. Supports HTML formatting by default. | No |
| `reply_to_message_id` | Message ID to reply to | No |
| `disable_web_page_preview` | Disable link previews in text messages | No |
| `parse_mode` | How to parse caption/text. Options: `HTML`, `Markdown`, `MarkdownV2`, or empty string for plain text. Default: `HTML` | No |
| `max_group_size` | Maximum media items per group (2-10). Large lists split into multiple groups. Default: 10 | No |
| `chunk_delay` | Delay in milliseconds between sending multiple groups (0-60000). Useful for rate limiting. Default: 0 | No |
| `wait_for_response` | Wait for Telegram to finish processing. Set to `false` for fire-and-forget (automation continues immediately). Default: `true` | No |
| `max_asset_data_size` | Maximum asset size in bytes. Assets exceeding this limit will be skipped. Default: no limit | No |
| `send_large_photos_as_documents` | Handle photos exceeding Telegram limits (10MB or 10000px dimension sum). If `true`, send as documents. If `false`, downsize to fit. Default: `false` | No |

The service returns a response with `success` status and `message_id` (single message), `message_ids` (media group), or `groups_sent` (number of groups when split). When `wait_for_response` is `false`, the service returns immediately with `{"success": true, "status": "queued"}` while processing continues in the background.

## Events

The integration fires multiple event types that you can use in your automations:

### Available Events

| Event Type | Description | When Fired |
|------------|-------------|------------|
| `immich_album_watcher_album_changed` | General album change event | Fired for any album change |
| `immich_album_watcher_assets_added` | Assets were added to the album | When new photos/videos are added |
| `immich_album_watcher_assets_removed` | Assets were removed from the album | When photos/videos are removed |
| `immich_album_watcher_album_renamed` | Album name was changed | When the album is renamed |
| `immich_album_watcher_album_deleted` | Album was deleted | When the album is deleted from Immich |
| `immich_album_watcher_album_sharing_changed` | Album sharing status changed | When album is shared or unshared |

### Example Usage

```yaml
automation:
  - alias: "New photos added to album"
    trigger:
      - platform: event
        event_type: immich_album_watcher_assets_added
    action:
      - service: notify.mobile_app
        data:
          title: "New Photos"
          message: "{{ trigger.event.data.added_count }} new photos in {{ trigger.event.data.album_name }}"

  - alias: "Album renamed"
    trigger:
      - platform: event
        event_type: immich_album_watcher_album_renamed
    action:
      - service: notify.mobile_app
        data:
          title: "Album Renamed"
          message: "Album '{{ trigger.event.data.old_name }}' renamed to '{{ trigger.event.data.new_name }}'"

  - alias: "Album deleted"
    trigger:
      - platform: event
        event_type: immich_album_watcher_album_deleted
    action:
      - service: notify.mobile_app
        data:
          title: "Album Deleted"
          message: "Album '{{ trigger.event.data.album_name }}' was deleted"
```

### Event Data

| Field | Description | Available In |
|-------|-------------|--------------|
| `hub_name` | Hub name configured in integration | All events |
| `album_id` | Album ID | All events |
| `album_name` | Current album name | All events |
| `album_url` | Public URL to view the album (only present if album has a shared link) | All events except `album_deleted` |
| `change_type` | Type of change (assets_added, assets_removed, album_renamed, album_sharing_changed, changed) | All events except `album_deleted` |
| `shared` | Current sharing status of the album | All events except `album_deleted` |
| `added_count` | Number of assets added | `album_changed`, `assets_added` |
| `removed_count` | Number of assets removed | `album_changed`, `assets_removed` |
| `added_assets` | List of added assets with details (see below) | `album_changed`, `assets_added` |
| `removed_assets` | List of removed asset IDs | `album_changed`, `assets_removed` |
| `people` | List of all people detected in the album | All events except `album_deleted` |
| `old_name` | Previous album name | `album_renamed` |
| `new_name` | New album name | `album_renamed` |
| `old_shared` | Previous sharing status | `album_sharing_changed` |
| `new_shared` | New sharing status | `album_sharing_changed` |

### Added Assets Fields

Each item in the `added_assets` list contains the following fields:

| Field | Description |
|-------|-------------|
| `id` | Unique asset ID |
| `asset_type` | Type of asset (`IMAGE` or `VIDEO`) |
| `asset_filename` | Original filename of the asset |
| `asset_created` | Date/time when the asset was originally created |
| `asset_owner` | Display name of the user who owns the asset |
| `asset_owner_id` | Unique ID of the user who owns the asset |
| `asset_description` | Description/caption of the asset (from EXIF data) |
| `asset_url` | Public URL to view the asset (only present if album has a shared link) |
| `people` | List of people detected in this specific asset |

Example accessing asset owner in an automation:

```yaml
automation:
  - alias: "Notify when someone adds photos"
    trigger:
      - platform: event
        event_type: immich_album_watcher_assets_added
    action:
      - service: notify.mobile_app
        data:
          title: "New Photos"
          message: >
            {{ trigger.event.data.added_assets[0].asset_owner }} added
            {{ trigger.event.data.added_count }} photos to {{ trigger.event.data.album_name }}
```

## Requirements

- Home Assistant 2024.1.0 or newer
- Immich server with API access
- Valid Immich API key with the following permissions:

### Required API Permissions

| Permission | Required | Description |
| ---------- | -------- | ----------- |
| `album.read` | Yes | Read album data and asset lists |
| `asset.read` | Yes | Read asset details (type, filename, creation date) |
| `user.read` | Yes | Resolve asset owner names |
| `person.read` | Yes | Read face recognition / people data |
| `sharedLink.read` | Yes | Read shared links for public/protected URL sensors |
| `sharedLink.create` | Optional | Create share links via the Button entities |
| `sharedLink.edit` | Optional | Edit shared link passwords via the Text entity |
| `sharedLink.delete` | Optional | Delete share links via the Button entities |

> **Note:** Without optional permissions, the corresponding entities will be unavailable or non-functional.

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
