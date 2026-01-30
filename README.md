# Immich Album Watcher

A custom Home Assistant integration to monitor Immich albums for changes with sensors, events, and face recognition.

For detailed documentation, see the [integration README](custom_components/immich_album_watcher/README.md).

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

> **Tip:** For the best experience, use this integration with the [Immich Album Watcher Blueprint](https://github.com/DolgolyovAlexei/haos-blueprints/blob/main/Common/Immich%20Album%20Watcher.yaml) to easily create automations for album change notifications.

### Manual Installation

1. Download or clone this repository
2. Copy the `custom_components/immich_album_watcher` folder to your Home Assistant `config/custom_components` directory
3. Restart Home Assistant
4. Add the integration via **Settings** → **Devices & Services** → **Add Integration**

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
