# Icons Needed for Fichero

## Summary
- **Add Window Features**: 2 new icons needed
- **Library Management**: 13-15 new icons needed
- **Total**: ~15-17 new icons to create

## Add Window Icons (2 needed)

### High Priority
- **`camera.png`** - Camera/photo capture (CameraAddView)
  - SF Symbol: `camera.fill`
- **`link.png`** - URL/website links (URLAddView, WebsiteAddView)
  - SF Symbol: `link`

## Library Management Icons (13-15 needed)

### Collection Management
- **`duplicate.png`** - Duplicate collection
  - SF Symbol: `doc.on.doc`
- **`rename.png`** - Rename collection
  - SF Symbol: `pencil`
- **`reorder.png`** - Reorder collections
  - SF Symbol: `arrow.up.arrow.down`

### Import/Export
- **`import.png`** - Import collection from path
  - SF Symbol: `square.and.arrow.down`
- **`bulk_import.png`** - Bulk import from text file
  - SF Symbol: `doc.badge.plus`
- **`clipboard.png`** - Import from clipboard
  - SF Symbol: `doc.on.clipboard`

### Processing & Analysis
- **`status.png`** - Processing status
  - SF Symbol: `info.circle`
- **`history.png`** - Processing history
  - SF Symbol: `clock.arrow.circlepath`
- **`stats.png`** - Library statistics
  - SF Symbol: `chart.bar`
- **`steps.png`** - Processing steps list
  - SF Symbol: `list.number`
- **`structure.png`** - Preview collection structure
  - SF Symbol: `doc.text.magnifyingglass`

### System Operations
- **`scan.png`** - Scan external collections
  - SF Symbol: `arrow.clockwise`

### Item Management (Optional/Lower Priority)
- **`remove_item.png`** - Remove item from collection
  - SF Symbol: `minus.circle`
- **`update_item.png`** - Update item status/metadata
  - SF Symbol: `pencil.circle`
- **`view_content.png`** - View file content
  - SF Symbol: `doc.plaintext`

## Implementation Status

### ✅ Already Implemented (GUI Available)
- **Search**: ❌ CLI only (`briefcase dev -- library search-items`)
- **Filter**: ❌ Not visible in GUI toolbars yet
- **Import**: ✅ CLI command exists (`briefcase dev -- library import`)
- **Export**: ✅ CLI command exists (`briefcase dev -- library export`)
- **Statistics**: ✅ CLI command exists (`briefcase dev -- library stats`)
- **Processing Status**: ✅ CLI command exists (`briefcase dev -- library status`)

### 📋 CLI Commands Available (Need GUI Icons)
```bash
# These work in CLI but need GUI buttons/icons:
briefcase dev -- library search-items "query"           # Search items
briefcase dev -- library import path "Collection Name"  # Import collection
briefcase dev -- library export collection_id path     # Export collection
briefcase dev -- library stats                         # Show statistics
briefcase dev -- library status collection_id          # Processing status
briefcase dev -- library history item_id               # Processing history
briefcase dev -- library scan                          # Scan external collections
briefcase dev -- library duplicate collection_id       # Duplicate collection
briefcase dev -- library rename collection_id "new"    # Rename collection
briefcase dev -- library reorder collection_id pos     # Reorder collections
```

## File Location
Save all icons to: `/src/fichero/resources/icons/toolbar/`

## Icon Specifications
- **Format**: PNG
- **Size**: Typically 24x24 or 32x32 pixels
- **Style**: Match existing SF Symbols style in the `/toolbar/` directory
- **Naming**: Use lowercase with underscores (e.g., `bulk_import.png`)

## Priority Order
1. **camera.png** - Needed for add functionality
2. **link.png** - Needed for add functionality
3. **import.png** - High-use library feature
4. **stats.png** - High-use library feature
5. **status.png** - Processing feedback
6. **history.png** - Processing feedback
7. Rest as needed for complete feature coverage