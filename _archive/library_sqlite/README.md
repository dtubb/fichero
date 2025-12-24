# Fichero Library System

A robust library management system for Fichero that tracks collections, items, and processing history.

## Overview

The library system provides:
- **Collection Management**: Create, organize, and track document collections
- **Flexible Storage**: Support for local, external, and URL-based collections
- **Item Tracking**: Monitor individual files, folders, and resources
- **Processing History**: Track all workflow executions and results
- **Import/Export**: Portable collection format using ZIP + JSONL
- **UI Integration**: Hooks into existing UI components without breaking changes

## Architecture

```
LibraryManager (Core)
├── Storage (SQLite)
├── Models (Collections, Items, Results)
├── Import/Export (ZIP + JSONL)
└── UI Integration Layer
    ├── UI Integration
    ├── UI Hooks
    └── Integration Example
```

## Quick Start

### 1. Initialize Library System

```python
from fichero.library.library_manager import LibraryManager

# Initialize with Toga app
library_manager = LibraryManager(app)
```

### 2. Add Collections

```python
# Add external collection
collection_id = await library_manager.add_collection(
    name="Historical Documents",
    collection_type="external",
    source_path="/Volumes/External/HistoricalDocs"
)

# Add URL collection
collection_id = await library_manager.add_collection(
    name="Web Resources",
    collection_type="url",
    source_path="https://example.com/resources"
)
```

### 3. Add Items to Collections

```python
# Add folder to collection
item_id = await library_manager.add_item_to_collection(
    collection_id=collection_id,
    item_type="folder",
    source="/path/to/folder",
    name="Important Documents",
    operation="link"  # or "copy", "move"
)

# Add file to collection
item_id = await library_manager.add_item_to_collection(
    collection_id=collection_id,
    item_type="file",
    source="/path/to/file.pdf",
    name="Document.pdf",
    operation="copy"
)
```

### 4. Track Processing Results

```python
# Add processing result
result_id = await library_manager.add_processing_result(
    item_id=item_id,
    workflow="default",
    status="success",
    output_paths=["/path/to/output.docx"],
    logs_path="/path/to/logs"
)
```

## UI Integration

### Hook into Existing UI

```python
from fichero.library.ui_hooks import LibraryUIHooks
from fichero.library.ui_integration import LibraryUIIntegration

# Create integration layer
ui_integration = LibraryUIIntegration(library_manager)
ui_hooks = LibraryUIHooks(ui_integration)

# Hook into existing library pane
ui_hooks.hook_into_library_pane(library_pane)

# Hook into collection view
ui_hooks.hook_into_collection_view(collection_view)

# Hook into toolbars
ui_hooks.hook_into_toolbar(library_toolbar, "library")
ui_hooks.hook_into_toolbar(collection_toolbar, "collection")
```

### Quick Integration

```python
from fichero.library.integration_example import integrate_library_with_main_window

# Integrate with main window
integration = integrate_library_with_main_window(app, main_window)
if integration:
    # Library system is now integrated
    collections = await integration.get_collections()
    print(f"Found {len(collections)} collections")
```

## Collection Types

### Local Collections
- Files copied to library directory
- Stored in `app.paths.data/library/collections/`
- Fully portable and self-contained

### External Collections
- Reference external locations
- Monitor availability (mounted/unmounted)
- No data copying, just metadata

### URL Collections
- Web resources and cloud storage
- No local storage required
- Perfect for mobile platforms

### Hybrid Collections
- Mix of local and external content
- Flexible organization options

## Storage Strategy

### SQLite Database
- Located at `app.paths.data/library/library.db`
- Stores only metadata and references
- No actual file content stored

### File Organization
```
app.paths.data/library/
├── library.db              # SQLite database
├── collections/            # Local collection files
│   └── collection_name/
│       ├── files/         # Copied files
│       ├── folders/       # Copied folders
│       └── captured/      # Camera/audio content
├── processing/             # Processing outputs
└── exports/                # Collection exports
```

## Import/Export Format

### Collection Export (ZIP + JSONL)
```jsonl
{"type": "collection", "id": "uuid", "name": "Collection Name", "type": "external", "source_path": "/path/to/source"}
{"type": "item", "collection_id": "uuid", "type": "folder", "source_path": "documents", "name": "Documents", "status": "completed"}
{"type": "processing", "item_id": "uuid", "workflow": "default", "status": "success", "output_paths": ["output.docx"], "completed_at": "2025-01-27T10:00:00Z"}
{"type": "export_metadata", "exported_at": "2025-01-27T10:00Z", "export_version": "1.0"}
```

### Benefits
- **Portable**: Can be shared between systems
- **Human Readable**: JSONL format for easy inspection
- **Version Control Friendly**: Can be tracked in git
- **Cross-Platform**: Works everywhere without dependencies

## Processing Integration

### Director Commands
The library system can generate director commands for processing:

```python
# Get collection for processing
collection = await library_manager.get_collection(collection_id)

# Generate director command
if collection.type == "external":
    command = f"director process {collection.source_path} --workflow default"
else:
    items = await library_manager.get_collection_items(collection_id)
    paths = [item.source_path for item in items if item.source_path]
    command = f"director process {' '.join(paths)} --workflow default"
```

### Status Tracking
- Monitor processing progress
- Track workflow results
- Link outputs back to source items

## Platform Considerations

### Desktop (macOS, Windows, Linux)
- Full file system access
- External drive monitoring
- Local file operations

### Mobile (iOS, Android)
- Limited file system access
- URL collections preferred
- Cloud storage integration

### Cross-Platform
- SQLite database (built-in)
- JSON import/export
- Platform-agnostic paths

## Best Practices

### 1. Collection Organization
- Use descriptive names
- Group related content
- Consider processing workflows

### 2. Storage Strategy
- Link external content when possible
- Copy only essential files locally
- Monitor external path availability

### 3. Processing Workflows
- Track all processing attempts
- Store output paths and logs
- Link results back to source items

### 4. UI Integration
- Hook into existing components
- Maintain current functionality
- Add library features gradually

## Troubleshooting

### Common Issues

1. **Collection Not Found**
   - Check collection ID
   - Verify database connection
   - Refresh collections list

2. **External Path Unavailable**
   - Check drive mounting
   - Verify network connectivity
   - Update path status

3. **Import/Export Failures**
   - Check file permissions
   - Verify ZIP file integrity
   - Check JSONL format

### Debug Information

```python
# Get library statistics
stats = await library_manager.get_library_stats()
print(f"Library stats: {stats}")

# Check external collection status
status = await library_manager.scan_external_collections()
print(f"External status: {status}")

# Get hook information
hook_info = ui_hooks.get_hook_info()
print(f"Hook info: {hook_info}")
```

## Future Enhancements

### Planned Features
- **Volume Monitoring**: Real-time drive availability
- **Cloud Integration**: iCloud, Google Drive, Dropbox
- **Advanced Search**: Full-text search across collections
- **Workflow Templates**: Predefined processing configurations
- **Collaboration**: Shared collections and permissions

### Extension Points
- **Custom Storage Backends**: Database, cloud, etc.
- **Processing Plugins**: Custom workflow steps
- **UI Customization**: Theme and layout options
- **API Integration**: REST API for external tools

## Support

For questions or issues:
1. Check the logs for error messages
2. Verify database and file permissions
3. Test with simple collections first
4. Review the integration examples

The library system is designed to be robust and extensible while maintaining compatibility with your existing UI components. 