# Immich Album Watcher

<img src="custom_components/immich_album_watcher/icon.png" alt="Immich" width="64" height="64">

A Home Assistant custom integration that monitors [Immich](https://immich.app/) photo/video library albums for changes and exposes them as Home Assistant entities with event-firing capabilities.

## Features

- **Album Monitoring** - Watch selected Immich albums for asset additions and removals
- **Rich Sensor Data** - Multiple sensors per album:
  - Asset count (total)
  - Photo count
  - Video count
  - People count (detected faces)
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

## Entities Created (per album)

| Entity Type | Name | Description |
|-------------|------|-------------|
| Sensor | Asset Count | Total number of assets in the album |
| Sensor | Photo Count | Number of photos in the album |
| Sensor | Video Count | Number of videos in the album |
| Sensor | People Count | Number of unique people detected |
| Sensor | Last Updated | When the album was last modified |
| Sensor | Created | When the album was created |
| Sensor | Public URL | Public share link URL (accessible links without password) |
| Sensor | Protected URL | Password-protected share link URL (if any exist) |
| Sensor | Protected Password | Password for the protected share link (read-only) |
| Binary Sensor | New Assets | On when new assets were recently added |
| Camera | Thumbnail | Album cover image |
| Text | Share Password | Editable password for the protected share link |

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
data:
  album_id: "your-album-id-here"
  count: 10
```

## Events

Use these events in your automations:

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
```

### Event Data

| Field | Description |
|-------|-------------|
| `album_id` | Album ID |
| `album_name` | Album name |
| `album_url` | Public URL to view the album (only present if album has a shared link) |
| `change_type` | Type of change (assets_added, assets_removed, changed) |
| `added_count` | Number of assets added |
| `removed_count` | Number of assets removed |
| `added_assets` | List of added assets with details (see below) |
| `removed_assets` | List of removed asset IDs |
| `people` | List of all people detected in the album |

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
| `sharedLink.edit` | Optional | Edit shared link passwords via the Text entity |

> **Note:** If you don't grant `sharedLink.edit` permission, the "Share Password" text entity will not be able to update passwords but will still display the current password.

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
