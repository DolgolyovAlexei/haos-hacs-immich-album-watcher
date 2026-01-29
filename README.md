# HAOS Integrations

A collection of custom integrations for Home Assistant.

## Repository Structure

```
haos-integrations/
├── immich_album_watcher/    # Immich Album Watcher integration
│   ├── __init__.py
│   ├── binary_sensor.py
│   ├── camera.py
│   ├── config_flow.py
│   ├── const.py
│   ├── coordinator.py
│   ├── manifest.json
│   ├── sensor.py
│   ├── services.yaml
│   ├── strings.json
│   ├── icon.png
│   ├── README.md
│   └── translations/
│       ├── en.json
│       └── ru.json
├── .gitignore
├── LICENSE
└── README.md
```

## Available Integrations

| Integration | Description | Documentation |
|-------------|-------------|---------------|
| [Immich Album Watcher](immich_album_watcher/) | Monitor Immich albums for changes with sensors, events, and face recognition | [README](immich_album_watcher/README.md) |

## Installation

### Manual Installation

1. Download or clone this repository
2. Copy the desired integration folder (e.g., `immich_album_watcher`) to your Home Assistant `custom_components` directory
3. Restart Home Assistant
4. Add the integration via **Settings** → **Devices & Services** → **Add Integration**

### HACS Installation

1. Open HACS in Home Assistant
2. Go to **Integrations** → **Custom repositories**
3. Add this repository URL
4. Install the desired integration
5. Restart Home Assistant

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
