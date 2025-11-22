# Fichero Metadata CLI - Quick Reference

## Search Commands

### Basic Search
```bash
# Simple search
fichero library search "your query here"

# Search with schema filter
fichero library search "text" --schema transcription
fichero library search "text" --schema catalogue
fichero library search "text" --schema translation

# Search with source filter
fichero library search "text" --source ai_qwen
fichero library search "text" --source human_corrected

# Search specific collection
fichero library search "text" --collection <collection_id>

# Search with confidence threshold
fichero library search "text" --confidence-min 0.8

# Search with language filter
fichero library search "documento" --language es

# Paginated results
fichero library search "text" --limit 50 --offset 0
```

### Advanced Search Syntax
```bash
# Phrase search (exact match)
fichero library search '"colonial archive"'

# Boolean operators
fichero library search "term1 AND term2"
fichero library search "term1 OR term2"
fichero library search "term1 NOT term2"

# Prefix matching
fichero library search "archiv*"

# Combined
fichero library search '"John Smith" AND letter* NOT draft'
```

### Search Utilities
```bash
# Get facet counts
fichero library search-facets "query" --facet schema_type --facet source_label

# Show search statistics
fichero library search-stats
fichero library search-stats --json

# Query suggestions (autocomplete)
fichero library suggest "arc"
fichero library suggest "doc" --limit 20

# Rebuild search index
fichero library rebuild-index
fichero library rebuild-index --collection <id>
```

## Bulk Operations

### Export/Import
```bash
# Export all metadata
fichero library bulk-export-metadata <collection_id> output.json

# Export specific schema
fichero library bulk-export-metadata <collection_id> transcriptions.json --schema transcription

# Export specific source
fichero library bulk-export-metadata <collection_id> qwen_data.json --source ai_qwen

# Export with all versions
fichero library bulk-export-metadata <collection_id> full.json --versions

# Import metadata
fichero library bulk-import-metadata input.json
fichero library bulk-import-metadata input.json --dry-run
fichero library bulk-import-metadata input.json --collection <new_collection_id>
fichero library bulk-import-metadata input.json --skip-existing
```

### Update Operations
```bash
# Update source labels in bulk
fichero library bulk-update-source <collection_id> old_source new_source
fichero library bulk-update-source <collection_id> ai_qwen ai_qwen_v2 --dry-run
fichero library bulk-update-source <collection_id> ai_gpt human_corrected --schema transcription
```

### Delete Operations
```bash
# Delete by schema
fichero library bulk-delete-metadata <collection_id> --schema transcription --dry-run
fichero library bulk-delete-metadata <collection_id> --schema transcription --force

# Delete by source
fichero library bulk-delete-metadata <collection_id> --source ai_qwen --dry-run

# Delete specific version
fichero library bulk-delete-metadata <collection_id> --version 1 --dry-run

# Delete with multiple filters
fichero library bulk-delete-metadata <collection_id> \
    --schema transcription \
    --source ai_qwen \
    --version 1 \
    --dry-run
```

### Validation
```bash
# Validate all metadata
fichero library bulk-validate <collection_id>

# Validate specific schema
fichero library bulk-validate <collection_id> --schema transcription

# Validate and export report
fichero library bulk-validate <collection_id> --json > validation_report.json

# Attempt to fix errors
fichero library bulk-validate <collection_id> --fix
```

### Version Management
```bash
# Merge versions (keep newest)
fichero library bulk-merge-versions <collection_id> transcription --strategy newest

# Merge versions (keep highest confidence)
fichero library bulk-merge-versions <collection_id> transcription --strategy highest_confidence

# Preview merge
fichero library bulk-merge-versions <collection_id> catalogue --dry-run
```

### Index Maintenance
```bash
# Reindex specific collection
fichero library bulk-reindex --collection <collection_id>

# Reindex entire library
fichero library bulk-reindex --force
```

## Metadata Query Commands (Old API)

### Query by Metadata
```bash
# Simple equality filter
fichero library metadata-query <collection_id> --filter "crop.method=yolo"

# Comparison filters
fichero library metadata-query <collection_id> --filter "crop.confidence>=0.85"
fichero library metadata-query <collection_id> --filter "rotate.angle>=-1"

# Multiple filters (AND logic)
fichero library metadata-query <collection_id> \
    --filter "crop.method=yolo" \
    --filter "crop.confidence>=0.85"

# Show full metadata for matches
fichero library metadata-query <collection_id> \
    --filter "crop.method=yolo" \
    --show-metadata
```

### View Metadata
```bash
# Show all metadata for item
fichero library metadata-show <item_id>

# Show specific step
fichero library metadata-show <item_id> --step crop

# Show specific version
fichero library metadata-show <item_id> --step crop --version 2

# JSON output
fichero library metadata-show <item_id> --json
```

### Export Metadata
```bash
# Export all metadata for collection
fichero library metadata-export <collection_id> output.json

# Export specific step
fichero library metadata-export <collection_id> crop_data.json --step crop

# Compact JSON (no pretty print)
fichero library metadata-export <collection_id> output.json --compact
```

### Metadata Statistics
```bash
# Show statistics
fichero library metadata-stats <collection_id>

# JSON output
fichero library metadata-stats <collection_id> --json
```

### Import Manifest
```bash
# Import JSONL manifest
fichero library metadata-import <item_id> manifest.jsonl

# Import with specific step name
fichero library metadata-import <item_id> results.jsonl --step crop

# Dry run
fichero library metadata-import <item_id> manifest.jsonl --dry-run
```

### Version History
```bash
# Show version history for step
fichero library metadata-history <item_id> crop

# JSON output
fichero library metadata-history <item_id> rotate --json
```

## Common Workflows

### Workflow 1: Search and Export
```bash
# 1. Search for content
fichero library search "colonial documents" --schema transcription --source ai_qwen

# 2. Export matching collection
fichero library bulk-export-metadata <collection_id> export.json --schema transcription

# 3. Review/edit JSON file
# (Manual step: open export.json in editor)

# 4. Import corrections
fichero library bulk-import-metadata export_corrected.json --increment-versions
```

### Workflow 2: Quality Control
```bash
# 1. Validate metadata
fichero library bulk-validate <collection_id> --json > report.json

# 2. Review validation report
# (Manual step: check report.json for errors)

# 3. Fix issues and re-validate
fichero library bulk-validate <collection_id> --fix

# 4. Verify with search stats
fichero library search-stats
```

### Workflow 3: Version Management
```bash
# 1. Check what versions exist
fichero library metadata-stats <collection_id>

# 2. Preview merge
fichero library bulk-merge-versions <collection_id> transcription --strategy newest --dry-run

# 3. Execute merge
fichero library bulk-merge-versions <collection_id> transcription --strategy newest

# 4. Verify
fichero library metadata-stats <collection_id>
```

### Workflow 4: Migration/Cleanup
```bash
# 1. Export current state
fichero library bulk-export-metadata <collection_id> backup.json --versions

# 2. Update source labels
fichero library bulk-update-source <collection_id> old_source new_source --dry-run
fichero library bulk-update-source <collection_id> old_source new_source --force

# 3. Delete old versions
fichero library bulk-delete-metadata <collection_id> --version 1 --dry-run
fichero library bulk-delete-metadata <collection_id> --version 1 --force

# 4. Rebuild search index
fichero library bulk-reindex --collection <collection_id>
```

## Schema Types

Available schema types for filtering:
- `transcription` - Transcribed text
- `translation` - Translated text
- `catalogue` - Catalogue metadata
- `named_entities` - Named entity recognition
- `external_iiif` - IIIF manifest data
- `file_info` - File technical metadata
- `step_result` - Processing step results
- `crop_params` - Crop tool parameters

## Source Labels

Common source labels:
- `ai_qwen` - Alibaba Qwen model
- `ai_gpt` - OpenAI GPT model
- `ai_claude` - Anthropic Claude model
- `ai_lmstudio` - LM Studio local model
- `human_corrected` - Manually corrected
- `yolo_v8` - YOLO object detection
- `paddleocr` - PaddleOCR text detection

## Output Formats

Most commands support `--json` flag for machine-readable output:
```bash
fichero library search "query" --json | jq .
fichero library metadata-show <item_id> --json | jq .
fichero library search-stats --json | jq .
```

## Tips

1. **Always use --dry-run first** for destructive operations
2. **Export backups** before bulk operations
3. **Use JSON output** for scripting and automation
4. **Filter searches** to get relevant results faster
5. **Check search-stats** to understand your indexed content
6. **Validate regularly** to catch schema issues early
7. **Use version management** to track metadata evolution

## Troubleshooting

### Search not finding results
```bash
# Check if content is indexed
fichero library search-stats

# Rebuild index if needed
fichero library bulk-reindex --collection <id>

# Verify metadata exists
fichero library metadata-stats <collection_id>
```

### Validation errors
```bash
# Get detailed error report
fichero library bulk-validate <collection_id> --json > errors.json

# Review schema definitions
# Check src/fichero/library/metadata_schemas.py
```

### Slow searches
```bash
# Check index size
fichero library search-stats

# Consider rebuilding index
fichero library bulk-reindex --force

# Use more specific filters
fichero library search "query" --schema transcription --collection <id>
```
