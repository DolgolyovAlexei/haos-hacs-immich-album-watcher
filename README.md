# HAOS Integrations

A collection of custom Home Assistant integrations.

## Integrations

### Immich Album Watcher

<img src="immich_album_watcher/icon.png" alt="Immich" width="64" height="64">

Monitors [Immich](https://immich.app/) photo/video library albums for changes and exposes them as Home Assistant sensors with event-firing capabilities.

#### Features

- **Album Monitoring** - Watch selected Immich albums for asset additions and removals
- **Sensor Integration** - Creates Home Assistant sensors showing current asset count per album
- **Event Firing** - Fires Home Assistant events when albums change:
  - `immich_album_watcher_album_changed` - General album changes
  - `immich_album_watcher_assets_added` - When new assets are added
  - `immich_album_watcher_assets_removed` - When assets are removed
- **Configurable Polling** - Adjustable scan interval (10-3600 seconds)
- **Rich Metadata** - Provides detailed album info including:
  - Album name and ID
  - Asset count
  - Owner information
  - Shared status
  - Thumbnail URL
  - Last updated timestamp

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

#### Requirements

- Home Assistant 2024.1.0 or newer
- Immich server with API access
- Valid Immich API key

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
