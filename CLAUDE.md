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

## Documentation Updates

**IMPORTANT**: Always keep the README.md synchronized with integration changes.

When modifying the integration interface, you MUST update the corresponding documentation:

- **Service parameters**: Update parameter tables and examples in README.md
- **New events**: Add event documentation with examples and field descriptions
- **New entities**: Document entity types, attributes, and usage
- **Configuration options**: Update configuration documentation
- **Translation files**: Add translations for new parameters/entities in `en.json` and `ru.json`
- **services.yaml**: Keep service definitions in sync with implementation

The README is the primary user-facing documentation and must accurately reflect the current state of the integration.
