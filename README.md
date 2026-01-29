# HAOS Integrations

A collection of custom Home Assistant integrations.

## Integrations

### Immich Album Watcher

<img src="immich_album_watcher/icon.png" alt="Immich" width="64" height="64">

Monitors [Immich](https://immich.app/) photo/video library albums for changes and exposes them as Home Assistant entities with event-firing capabilities.

#### Features

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
  - Detected people in the asset
- **Services** - Custom service calls:
  - `immich_album_watcher.refresh` - Force immediate data refresh
  - `immich_album_watcher.get_recent_assets` - Get recent assets from an album
- **Configurable Polling** - Adjustable scan interval (10-3600 seconds)

#### Entities Created (per album)

| Entity Type | Name | Description |
|-------------|------|-------------|
| Sensor | Asset Count | Total number of assets in the album |
| Sensor | Photo Count | Number of photos in the album |
| Sensor | Video Count | Number of videos in the album |
| Sensor | People Count | Number of unique people detected |
| Sensor | Last Updated | When the album was last modified |
| Sensor | Created | When the album was created |
| Binary Sensor | New Assets | On when new assets were recently added |
| Camera | Thumbnail | Album cover image |

#### Installation

1. Copy the `immich_album_watcher` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Go to **Settings** → **Devices & Services** → **Add Integration**
4. Search for "Immich Album Watcher"
5. Enter your Immich server URL and API key
6. Select the albums you want to monitor

#### Configuration

| Option | Description | Default |
|--------|-------------|---------|
| Server URL | Your Immich server URL (e.g., `https://immich.example.com`) | Required |
| API Key | Your Immich API key | Required |
| Albums | Albums to monitor | Required |
| Scan Interval | How often to check for changes (seconds) | 60 |

#### Services

##### Refresh

Force an immediate refresh of all album data:

```yaml
service: immich_album_watcher.refresh
```

##### Get Recent Assets

Get the most recent assets from a specific album (returns response data):

```yaml
service: immich_album_watcher.get_recent_assets
data:
  album_id: "your-album-id-here"
  count: 10
```

#### Events

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

Event data includes:
- `album_id` - Album ID
- `album_name` - Album name
- `change_type` - Type of change (assets_added, assets_removed, changed)
- `added_count` - Number of assets added
- `removed_count` - Number of assets removed
- `added_assets` - List of added assets with details (type, filename, created date, people)
- `removed_assets` - List of removed asset IDs
- `people` - List of all people detected in the album

#### Requirements

- Home Assistant 2024.1.0 or newer
- Immich server with API access
- Valid Immich API key with `album.read` and `asset.read` permissions

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
