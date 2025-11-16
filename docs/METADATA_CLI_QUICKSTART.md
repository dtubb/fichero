# Metadata CLI Quick Start Guide

This guide shows how to test the new metadata CLI commands with actual data.

## Prerequisites

- Fichero installed and working
- A collection with some documents
- Documents processed with at least one workflow

## Quick Test Workflow

### 1. List Your Collections

```bash
briefcase dev -- library list
```

Pick a collection ID that has been processed.

### 2. Check What Items Exist

```bash
briefcase dev -- library items <collection_id>
```

Note an item ID for testing.

### 3. Show Metadata for an Item

```bash
briefcase dev -- library metadata-show <item_id>
```

This will show all metadata stored for that item across all processing steps.

**Example Output:**
```json
{
  "crop": {
    "method": "yolo",
    "confidence": 0.92,
    "box": {"x1": 100, "y1": 50, "x2": 800, "y2": 1000}
  },
  "rotate": {
    "angle": -0.5,
    "found_lines": true
  }
}
```

### 4. Query Items by Metadata

```bash
# Find all items processed with a specific method
briefcase dev -- library metadata-query <collection_id> \
  --filter "crop.method=yolo"

# Find high-confidence results
briefcase dev -- library metadata-query <collection_id> \
  --filter "crop.confidence>=0.85"

# Combine multiple filters
briefcase dev -- library metadata-query <collection_id> \
  --filter "crop.method=yolo" \
  --filter "rotate.found_lines=true"
```

### 5. Export Metadata

```bash
# Export all metadata to JSON
briefcase dev -- library metadata-export <collection_id> metadata.json

# View the export
cat metadata.json | python3 -m json.tool | less
```

### 6. View Statistics

```bash
briefcase dev -- library metadata-stats <collection_id>
```

**Example Output:**
```
Metadata Statistics for 'My Collection':

Total Items: 25
Items with Metadata: 20
Coverage: 80.0%

┏━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━┓
┃ Step        ┃ Items ┃ Coverage ┃
┡━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━┩
│ crop        │    20 │   80.0%  │
│ rotate      │    18 │   72.0%  │
│ transcribe  │    15 │   60.0%  │
└─────────────┴───────┴──────────┘
```

### 7. View Version History

```bash
# See how metadata changed over time
briefcase dev -- library metadata-history <item_id> crop
```

## Creating Test Data

If you don't have a processed collection yet, here's how to create one:

### Option A: Using Existing Documents

```bash
# 1. Create collection
briefcase dev -- library add "Test Collection" \
  --type external \
  --source /path/to/your/documents

# 2. Process the collection
briefcase dev -- library process <collection_id> \
  --plan "Default Plan" \
  --workflow "default"

# 3. Wait for processing to complete
briefcase dev -- library status <collection_id>

# 4. Now test metadata commands
briefcase dev -- library metadata-stats <collection_id>
```

### Option B: Creating Test Metadata Programmatically

Create a file `create_test_metadata.py`:

```python
#!/usr/bin/env python3
import os
os.environ["TOGA_BACKEND"] = "toga_cocoa"

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent / "src"))

from unittest.mock import Mock
from datetime import datetime
from fichero.library.library_manager import LibraryManager
from fichero.library.models import Collection, CollectionItem

# Setup
mock_app = Mock()
mock_app.paths = Mock()
mock_app.paths.data = Path.home() / "Library" / "Application Support" / "ca.tubb.fichero"

lib = LibraryManager(mock_app)

# Create collection
collection = Collection(
    name="CLI Metadata Test",
    description="Test collection for metadata CLI",
    type="external",
    created_at=datetime.now(),
    updated_at=datetime.now()
)
collection_id = lib.storage.add_collection(collection)
print(f"Created collection: {collection_id}")

# Create item
item = CollectionItem(
    collection_id=collection_id,
    name="Test Document",
    type="file",
    source_path="/tmp/test.pdf",
    storage_type="external",
    status="pending",
    created_at=datetime.now(),
    updated_at=datetime.now()
)
item_id = lib.storage.add_item(item)
print(f"Created item: {item_id}")

# Add metadata
lib.metadata_api.save_step_metadata(
    item_id=item_id,
    step_name="crop",
    metadata={
        "method": "yolo",
        "confidence": 0.92,
        "box": {"x1": 100, "y1": 50, "x2": 800, "y2": 1000},
        "padding": 30
    },
    version=1
)

lib.metadata_api.save_step_metadata(
    item_id=item_id,
    step_name="rotate",
    metadata={
        "angle": -0.5,
        "found_lines": True,
        "num_lines": 3
    },
    version=1
)

print("Added metadata!")
print(f"\nTest commands:")
print(f"  briefcase dev -- library metadata-show {item_id}")
print(f"  briefcase dev -- library metadata-query {collection_id} --filter 'crop.method=yolo'")
print(f"  briefcase dev -- library metadata-stats {collection_id}")
```

Run it:
```bash
python3 create_test_metadata.py
```

Then use the displayed commands to test.

## Advanced Usage

### Filter Examples

```bash
# Text equality
--filter "crop.method=yolo"

# Numeric comparison
--filter "crop.confidence>=0.90"
--filter "rotate.angle<=-0.5"

# Boolean values
--filter "rotate.found_lines=true"
--filter "transcribe.has_content=false"

# Multiple filters (AND logic)
--filter "crop.method=yolo" \
--filter "crop.confidence>=0.85" \
--filter "rotate.found_lines=true"
```

### JSON Output

All commands support `--json` flag for machine-readable output:

```bash
# Query with JSON output
briefcase dev -- library metadata-query <collection_id> \
  --filter "crop.method=yolo" \
  --json | jq .

# Show with JSON output
briefcase dev -- library metadata-show <item_id> --json | jq .

# Stats with JSON output
briefcase dev -- library metadata-stats <collection_id> --json | jq .
```

### Exporting Specific Steps

```bash
# Export only crop metadata
briefcase dev -- library metadata-export <collection_id> crop_data.json \
  --step crop

# Export in compact format
briefcase dev -- library metadata-export <collection_id> metadata.json \
  --compact
```

### Import from JSONL

Create a JSONL file with metadata:

```jsonl
{"step_name": "enhance", "metadata": {"brightness": 1.2, "contrast": 1.1}}
{"step_name": "denoise", "metadata": {"strength": 0.8, "method": "nlmeans"}}
```

Import it:

```bash
# Dry run first
briefcase dev -- library metadata-import <item_id> metadata.jsonl --dry-run

# Actually import
briefcase dev -- library metadata-import <item_id> metadata.jsonl
```

## Troubleshooting

### No Metadata Found

If `metadata-show` returns no metadata:

1. Check if the item was actually processed:
   ```bash
   briefcase dev -- library history <item_id>
   ```

2. Check collection status:
   ```bash
   briefcase dev -- library status <collection_id>
   ```

3. Verify items exist:
   ```bash
   briefcase dev -- library items <collection_id>
   ```

### Query Returns No Results

If `metadata-query` returns no items:

1. Verify metadata exists:
   ```bash
   briefcase dev -- library metadata-stats <collection_id>
   ```

2. Check your filter syntax:
   ```bash
   # Wrong: missing quotes
   --filter crop.method=yolo

   # Right: with quotes
   --filter "crop.method=yolo"
   ```

3. Check the actual field names:
   ```bash
   briefcase dev -- library metadata-show <item_id>
   ```

### Import Fails

If `metadata-import` fails:

1. Validate your JSONL file:
   ```bash
   cat metadata.jsonl | while read line; do
     echo "$line" | python3 -m json.tool > /dev/null || echo "Invalid: $line"
   done
   ```

2. Check required fields:
   - Each line must be valid JSON
   - Must have `step_name` or use `--step` option
   - Must have `metadata` dict

## Next Steps

- Try different filter combinations
- Export metadata for external analysis
- Create custom JSONL manifests for bulk imports
- Use JSON output with `jq` for advanced filtering

## Getting Help

All commands have detailed help:

```bash
briefcase dev -- library metadata-query --help
briefcase dev -- library metadata-show --help
briefcase dev -- library metadata-export --help
briefcase dev -- library metadata-stats --help
briefcase dev -- library metadata-import --help
briefcase dev -- library metadata-history --help
```
