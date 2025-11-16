# Metadata CLI Commands - Example Output

This document shows example output from the metadata CLI commands to help users understand what to expect.

## metadata-query

### Example 1: Simple Equality Filter

**Command:**
```bash
briefcase dev -- library metadata-query abc-123 --filter "crop.method=yolo"
```

**Output:**
```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━┓
┃ ID                               ┃ Name                ┃ Type   ┃ Status  ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━┩
│ item-456-abc-789                 │ Document_001.pdf    │ file   │ pending │
│ item-457-def-012                 │ Document_002.pdf    │ file   │ pending │
│ item-458-ghi-345                 │ Document_003.pdf    │ file   │ pending │
└──────────────────────────────────┴─────────────────────┴────────┴─────────┘

Found 3 item(s) matching filters
```

### Example 2: Comparison Filter

**Command:**
```bash
briefcase dev -- library metadata-query abc-123 --filter "crop.confidence>=0.90"
```

**Output:**
```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━┓
┃ ID                               ┃ Name                ┃ Type   ┃ Status  ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━┩
│ item-456-abc-789                 │ Document_001.pdf    │ file   │ pending │
│ item-457-def-012                 │ Document_002.pdf    │ file   │ pending │
└──────────────────────────────────┴─────────────────────┴────────┴─────────┘

Found 2 item(s) matching filters
```

### Example 3: Multiple Filters with Metadata Display

**Command:**
```bash
briefcase dev -- library metadata-query abc-123 \
  --filter "crop.method=yolo" \
  --filter "rotate.found_lines=true" \
  --show-metadata
```

**Output:**
```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━┓
┃ ID                               ┃ Name                ┃ Type   ┃ Status  ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━┩
│ item-456-abc-789                 │ Document_001.pdf    │ file   │ pending │
└──────────────────────────────────┴─────────────────────┴────────┴─────────┘

Found 1 item(s) matching filters

Metadata for matching items:

Document_001.pdf (item-456-abc-789):
{
  "crop": {
    "method": "yolo",
    "confidence": 0.92,
    "box": {
      "x1": 100,
      "y1": 50,
      "x2": 800,
      "y2": 1000
    }
  },
  "rotate": {
    "angle": -0.5,
    "found_lines": true,
    "num_lines": 3
  }
}
```

### Example 4: JSON Output

**Command:**
```bash
briefcase dev -- library metadata-query abc-123 --filter "crop.method=yolo" --json
```

**Output:**
```json
{
  "collection_id": "abc-123",
  "filters": [
    "crop.method=yolo"
  ],
  "matching_items": [
    {
      "id": "item-456-abc-789",
      "name": "Document_001.pdf",
      "type": "file",
      "status": "pending",
      "source_path": "/path/to/Document_001.pdf"
    },
    {
      "id": "item-457-def-012",
      "name": "Document_002.pdf",
      "type": "file",
      "status": "pending",
      "source_path": "/path/to/Document_002.pdf"
    }
  ]
}
```

## metadata-show

### Example 1: Show All Metadata

**Command:**
```bash
briefcase dev -- library metadata-show item-456-abc-789
```

**Output:**
```
Metadata for 'Document_001.pdf' (latest):

{
  "crop": {
    "method": "yolo",
    "confidence": 0.92,
    "box": {
      "x1": 100,
      "y1": 50,
      "x2": 800,
      "y2": 1000
    },
    "padding": 30
  },
  "rotate": {
    "angle": -0.5,
    "found_lines": true,
    "num_lines": 3,
    "method": "line_detection"
  },
  "transcribe": {
    "text_length": 450,
    "model": "qwen-vl-max",
    "has_content": true,
    "num_lines": 15
  }
}
```

### Example 2: Show Specific Step

**Command:**
```bash
briefcase dev -- library metadata-show item-456-abc-789 --step crop
```

**Output:**
```
Metadata for 'Document_001.pdf' (latest):

{
  "crop": {
    "method": "yolo",
    "confidence": 0.92,
    "box": {
      "x1": 100,
      "y1": 50,
      "x2": 800,
      "y2": 1000
    },
    "padding": 30
  }
}
```

### Example 3: Show Specific Version

**Command:**
```bash
briefcase dev -- library metadata-show item-456-abc-789 --step crop --version 1
```

**Output:**
```
Metadata for 'Document_001.pdf' (version 1):

{
  "crop": {
    "method": "yolo",
    "confidence": 0.85,
    "box": {
      "x1": 90,
      "y1": 45,
      "x2": 790,
      "y2": 995
    },
    "padding": 20
  }
}
```

### Example 4: JSON Output

**Command:**
```bash
briefcase dev -- library metadata-show item-456-abc-789 --json
```

**Output:**
```json
{
  "item_id": "item-456-abc-789",
  "item_name": "Document_001.pdf",
  "version": "latest",
  "metadata": {
    "crop": {
      "method": "yolo",
      "confidence": 0.92,
      "box": {
        "x1": 100,
        "y1": 50,
        "x2": 800,
        "y2": 1000
      },
      "padding": 30
    },
    "rotate": {
      "angle": -0.5,
      "found_lines": true,
      "num_lines": 3,
      "method": "line_detection"
    }
  }
}
```

## metadata-stats

### Example 1: Table Format

**Command:**
```bash
briefcase dev -- library metadata-stats abc-123
```

**Output:**
```
Metadata Statistics for 'My Document Collection':

Total Items: 25
Items with Metadata: 20
Coverage: 80.0%

┏━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━┓
┃ Step        ┃ Items ┃ Coverage ┃
┡━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━┩
│ crop        │    20 │   80.0%  │
│ rotate      │    18 │   72.0%  │
│ transcribe  │    15 │   60.0%  │
│ enhance     │    12 │   48.0%  │
└─────────────┴───────┴──────────┘

┏━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Field                   ┃ Count ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━┩
│ crop.confidence         │    20 │
│ crop.method             │    20 │
│ crop.box                │    20 │
│ rotate.angle            │    18 │
│ rotate.found_lines      │    18 │
│ transcribe.text_length  │    15 │
│ transcribe.model        │    15 │
│ transcribe.has_content  │    15 │
│ enhance.brightness      │    12 │
│ enhance.contrast        │    12 │
└─────────────────────────┴───────┘
```

### Example 2: JSON Format

**Command:**
```bash
briefcase dev -- library metadata-stats abc-123 --json
```

**Output:**
```json
{
  "collection_id": "abc-123",
  "collection_name": "My Document Collection",
  "total_items": 25,
  "items_with_metadata": 20,
  "coverage_percentage": 80.0,
  "steps": {
    "crop": 20,
    "rotate": 18,
    "transcribe": 15,
    "enhance": 12
  },
  "fields": {
    "crop.confidence": 20,
    "crop.method": 20,
    "crop.box": 20,
    "rotate.angle": 18,
    "rotate.found_lines": 18,
    "transcribe.text_length": 15,
    "transcribe.model": 15,
    "transcribe.has_content": 15,
    "enhance.brightness": 12,
    "enhance.contrast": 12
  }
}
```

## metadata-export

### Example: Export File

**Command:**
```bash
briefcase dev -- library metadata-export abc-123 metadata.json
```

**Output (Console):**
```
✅ Exported metadata for 20 item(s) to metadata.json
```

**Output (File: metadata.json):**
```json
{
  "collection_id": "abc-123",
  "collection_name": "My Document Collection",
  "export_timestamp": 1731686400.0,
  "items": [
    {
      "item_id": "item-456-abc-789",
      "item_name": "Document_001.pdf",
      "metadata": {
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
    },
    {
      "item_id": "item-457-def-012",
      "item_name": "Document_002.pdf",
      "metadata": {
        "crop": {
          "method": "yolo",
          "confidence": 0.95,
          "box": {"x1": 50, "y1": 100, "x2": 900, "y2": 1200}
        }
      }
    }
  ]
}
```

## metadata-import

### Example 1: Dry Run

**Command:**
```bash
briefcase dev -- library metadata-import item-456-abc-789 manifest.jsonl --dry-run
```

**Output:**
```
Would import enhance: ['brightness', 'contrast', 'method']
Would import denoise: ['strength', 'method']

Dry run complete. Would import 2 entries.
```

### Example 2: Actual Import

**Command:**
```bash
briefcase dev -- library metadata-import item-456-abc-789 manifest.jsonl
```

**Output:**
```
✅ Imported 2 metadata entries for item 'Document_001.pdf'
```

## metadata-history

### Example 1: Table Format

**Command:**
```bash
briefcase dev -- library metadata-history item-456-abc-789 crop
```

**Output:**
```
Version History for 'crop' on 'Document_001.pdf':

┏━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Version ┃ Changed At          ┃ Changed By ┃ Reason            ┃ Fields                   ┃
┡━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│       1 │ 2025-11-15 10:30:00 │ tool       │ processing_step   │ method, confidence, box  │
│       2 │ 2025-11-15 14:45:00 │ user       │ manual_update     │ method, confidence, box  │
│       3 │ 2025-11-15 16:20:00 │ user       │ manual_update     │ method, confidence, box  │
└─────────┴─────────────────────┴────────────┴───────────────────┴──────────────────────────┘

Found 3 version(s)
```

### Example 2: JSON Format

**Command:**
```bash
briefcase dev -- library metadata-history item-456-abc-789 crop --json
```

**Output:**
```json
{
  "item_id": "item-456-abc-789",
  "item_name": "Document_001.pdf",
  "step": "crop",
  "history": [
    {
      "version": 1,
      "changed_at": "2025-11-15T10:30:00",
      "changed_by": "tool",
      "change_reason": "processing_step",
      "metadata": {
        "method": "yolo",
        "confidence": 0.85,
        "box": {"x1": 90, "y1": 45, "x2": 790, "y2": 995}
      }
    },
    {
      "version": 2,
      "changed_at": "2025-11-15T14:45:00",
      "changed_by": "user",
      "change_reason": "manual_update",
      "metadata": {
        "method": "yolo",
        "confidence": 0.92,
        "box": {"x1": 100, "y1": 50, "x2": 800, "y2": 1000}
      }
    }
  ]
}
```

## Error Examples

### No Metadata Found

**Command:**
```bash
briefcase dev -- library metadata-show item-999
```

**Output:**
```
No metadata found for item item-999
```

### No Matching Items

**Command:**
```bash
briefcase dev -- library metadata-query abc-123 --filter "crop.method=nonexistent"
```

**Output:**
```
No items found matching filters
```

### Invalid Filter Syntax

**Command:**
```bash
briefcase dev -- library metadata-query abc-123 --filter "invalid filter"
```

**Output:**
```
⚠️  Invalid filter format: invalid filter
```

### Item Not Found

**Command:**
```bash
briefcase dev -- library metadata-show does-not-exist
```

**Output:**
```
Item not found: does-not-exist
```

## Tips for Reading Output

1. **Color Coding**: In terminal, colors indicate:
   - Cyan: IDs and field names
   - Magenta: Names and values
   - Green: Successful operations
   - Yellow: Warnings
   - Red: Errors

2. **Table Format**: Best for human reading
3. **JSON Format**: Best for scripting and automation
4. **Syntax Highlighting**: JSON output includes color-coded syntax

5. **Pipe to jq**: For advanced JSON filtering:
   ```bash
   briefcase dev -- library metadata-show <item_id> --json | jq '.metadata.crop.confidence'
   ```
