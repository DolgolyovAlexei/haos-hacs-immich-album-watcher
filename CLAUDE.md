# Project Guidelines

## Version Management

Update the integration version in `custom_components/immich_album_watcher/manifest.json` only when changes are made to the **integration content** (files inside `custom_components/immich_album_watcher/`).

Do NOT bump version for:

- Repository setup (hacs.json, root README.md, LICENSE, CLAUDE.md)
- CI/CD configuration
- Other repository-level changes

Use semantic versioning:
- **MAJOR** (x.0.0): Breaking changes
- **MINOR** (0.x.0): New features, backward compatible
- **PATCH** (0.0.x): Bug fixes, integration documentation updates
