# Library Metadata Extraction - Implementation Plan

## Overview
Add a workflow step that extracts JSON metadata from the library database and makes it available to cataloguing steps.

## Goals
1. **Generic**: Work with any JSON metadata stored in library backend
2. **Optional**: Workflows work with or without metadata
3. **Decoupled**: Cataloguing tools don't depend on library
4. **Reusable**: Any workflow can use metadata extraction

---

## Component 1: Extract Library Metadata Tool

### File: `src/fichero/tools/extract_library_metadata.py`

**Purpose**: Query library database and extract metadata for files in manifest

**Function Signature**:
```python
def extract_metadata_batch(
    source_folder: Path,
    source_manifest: Path,
    output_folder: Path,
    library_db_path: Optional[Path] = None,
    collection_id: Optional[str] = None
) -> Dict[str, int]:
```

**Process**:
1. Read source manifest (e.g., `cleaned_manifest.jsonl`)
2. For each file in manifest:
   - Extract relative path from manifest
   - Query library database by source_path
   - Retrieve full item record including metadata dict
3. Create output manifest with merged data
4. Return statistics

**Input Manifest** (`assets/cleaned/cleaned_manifest.jsonl`):
```json
{"source": "documents/file1.jpg", "output": "cleaned/file1.txt"}
{"source": "documents/file2.jpg", "output": "cleaned/file2.txt"}
```

**Output Manifest** (`assets/library_metadata/metadata_manifest.jsonl`):
```json
{
  "source": "documents/file1.jpg",
  "library_metadata": {
    "item_id": "abc123",
    "item_name": "Historical Document 1",
    "collection_id": "coll-456",
    "collection_name": "Archive Collection A",
    "created_at": "2025-01-15T10:30:00",
    "updated_at": "2025-01-20T14:22:00",
    "storage_type": "external",
    "source_path": "/path/to/original/file1.jpg",
    "metadata": {
      "original_filename": "scan_001.jpg",
      "scan_date": "1850-03-15",
      "archive_reference": "BOX-12-FOLDER-3",
      "photographer": "John Smith",
      "dimensions": "4000x3000",
      "notes": "Damaged corner, water stain",
      "tags": ["legal", "correspondence", "1850s"],
      "custom_field_1": "value1"
    }
  }
}
```

**Database Query**:
```python
def get_item_metadata(db_path: Path, source_path: str, collection_id: str) -> Optional[Dict]:
    """Query library database for item metadata"""
    storage = LibraryStorage(db_path)

    # Get all items in collection
    items = storage.get_collection_items(collection_id)

    # Find matching item by source_path
    for item in items:
        if item.source_path == source_path or item.local_path == source_path:
            return {
                "item_id": item.id,
                "item_name": item.name,
                "collection_id": item.collection_id,
                "collection_name": get_collection_name(storage, item.collection_id),
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
                "storage_type": item.storage_type,
                "source_path": item.source_path,
                "metadata": item.metadata  # This is the user's JSON metadata dict
            }

    return None
```

**Error Handling**:
- If library database not accessible: Log warning, create empty metadata
- If item not found in library: Create stub with filename only
- If metadata field is empty: Use empty dict

**Skip Processing Mode**:
- Create manifest with placeholder metadata
- No database queries needed

---

## Component 2: Workflow Integration

### Update: `src/fichero/resources/config_defaults/plans/Generic_Catalogue.yml`

**Add new step** (between fuzzy_clean and catalogue_folder):

```yaml
  - name: extract_library_metadata
    worker_type: "io"
    help: "Extract metadata from library database for cataloguing"
    function: "fichero.tools.extract_library_metadata.extract_metadata_batch"
    args:
      source_folder: "assets/cleaned"
      source_manifest: "assets/cleaned/cleaned_manifest.jsonl"
      output_folder: "assets/library_metadata"
      library_db_path: "{library_db_path}"  # Passed from library integration
      collection_id: "{collection_id}"      # Passed from library integration
    outputs:
      - "assets/library_metadata"
      - "assets/library_metadata/metadata_manifest.jsonl"
```

**Updated workflow order**:
```yaml
workflows:
  Default:
    - build_documents_manifest
    - enhance
    - segment
    - transcribe_qwen_max_segmented
    - recombine_segments
    - fuzzy_clean
    - extract_library_metadata    # NEW
    - catalogue_folder             # Updated to use metadata
    - convert_to_word_segmented
    - catalogue_to_word
```

**Variable expansion**:
- `{library_db_path}` - Injected by director_integration
- `{collection_id}` - Injected by director_integration
- If not running in library context, these are empty/None

---

## Component 3: LLM Process Tool Updates

### Update: `src/fichero/tools/llm_process.py`

**Add metadata manifest support**:

```python
def process_documents_batch(
    source_folder: Path,
    source_manifest: Path,
    output_folder: Path,
    prompt_config: str,
    folder_mode: bool = False,
    metadata_manifest: Optional[Path] = None,  # NEW
    ...
):
    """
    Process documents with LLM prompts

    New parameter:
        metadata_manifest: Optional JSONL file with library metadata per file
    """

    # Load metadata if provided
    metadata_map = {}
    if metadata_manifest and metadata_manifest.exists():
        metadata_map = load_metadata_manifest(metadata_manifest)

    # When processing each document:
    for entry in manifest_entries:
        source_file = entry['source']

        # Get metadata for this file
        file_metadata = metadata_map.get(source_file, {})

        # Add metadata to prompt context
        context = build_prompt_context(
            text=transcription,
            metadata=file_metadata,
            page_numbers=page_numbers
        )
```

**Helper function**:
```python
def load_metadata_manifest(manifest_path: Path) -> Dict[str, Dict]:
    """Load metadata manifest into lookup dict"""
    metadata_map = {}
    with open(manifest_path, 'r') as f:
        for line in f:
            entry = json.loads(line)
            source = entry.get('source')
            metadata = entry.get('library_metadata', {})
            metadata_map[source] = metadata
    return metadata_map
```

**Prompt context builder**:
```python
def build_prompt_context(text: str, metadata: Dict, page_numbers: bool = True) -> str:
    """Build context string with optional metadata"""

    context_parts = []

    # Add metadata section if present
    if metadata:
        context_parts.append("=== SOURCE FILE METADATA ===")

        # Add item info
        if 'item_name' in metadata:
            context_parts.append(f"Item Name: {metadata['item_name']}")
        if 'collection_name' in metadata:
            context_parts.append(f"Collection: {metadata['collection_name']}")

        # Add user metadata if present
        if 'metadata' in metadata and metadata['metadata']:
            context_parts.append("\nFile Metadata:")
            for key, value in metadata['metadata'].items():
                context_parts.append(f"  {key}: {value}")

        context_parts.append("\n=== DOCUMENT TRANSCRIPTION ===")

    # Add transcription
    context_parts.append(text)

    return "\n".join(context_parts)
```

---

## Component 4: Update Catalogue Prompts

### Update: `src/fichero/resources/config_defaults/prompts/Generic_Catalogue.jsonl`

**Modify prompts to be metadata-aware**:

```json
{
  "name": "library_catalogue_entry",
  "prompt": "Using all the extracted information from previous steps, create a structured library catalogue entry.

If SOURCE FILE METADATA is provided at the beginning, use it to supplement the catalogue entry with:
- Original filenames and archive references
- Known dates from metadata
- Existing tags or classifications
- Technical information (dimensions, format, etc.)
- Any notes or contextual information

Focus on documenting WHAT IS IN THE DOCUMENTS, not analysis or interpretation.

The catalogue entry must include:
- Title (brief descriptive title based on document content)
- Description (use the summary from previous step - what the documents contain)
- Subject Keywords (use the tags from previous step, supplement with metadata tags if available)
- People (list of people mentioned in the documents)
- Places (list of locations mentioned in the documents)
- Organizations (list of organizations mentioned in the documents)
- Date Coverage (date range covered by the documents' content, in YYYY-MM-DD format)
- Document Type (e.g., correspondence, legal documents, reports, photographs, etc.)
- Source Information (archive reference, original filename, etc. from metadata if available)

Return as JSON exactly in this format:

{
  \"catalogue_entry\": {
    \"title\": \"brief descriptive title of document content\",
    \"description\": \"what the documents contain\",
    \"subject_keywords\": \"keyword1; keyword2; keyword3; ...\",
    \"people\": [\"person1\", \"person2\", \"person3\"],
    \"places\": [\"place1\", \"place2\", \"place3\"],
    \"organizations\": [\"org1\", \"org2\", \"org3\"],
    \"date_coverage\": {
      \"start\": \"YYYY-MM-DD or YYYY or null\",
      \"end\": \"YYYY-MM-DD or YYYY or null\"
    },
    \"document_type\": \"type of documents\",
    \"source_info\": {
      \"archive_reference\": \"from metadata if available\",
      \"original_filename\": \"from metadata if available\",
      \"notes\": \"from metadata if available\"
    }
  }
}

Return ONLY valid JSON. Say nothing else.",
  ...
}
```

---

## Component 5: Director Integration Updates

### Update: `src/fichero/library/director_integration.py`

**Pass library context to workflows**:

```python
def process_item(
    self,
    collection_id: str,
    item_id: str,
    plan_name: str,
    workflow_name: str = "Default"
) -> Optional[str]:
    """Process a library item through Director workflow"""

    # ... existing code ...

    # Get library database path
    library_db_path = str(self.library_manager.storage.db_path)

    # Prepare workflow with library context
    task_id = self.director.processing_coordinator.process_folders(
        folders=[{
            'output_folder': output_path,
            'documents_folder': documents_dir,
            'library_db_path': library_db_path,        # NEW
            'collection_id': collection_id,            # NEW
        }],
        plan_name=plan_name,
        workflow_name=workflow_name,
        backend='python'
    )
```

### Update: `src/fichero/director/processing_coordinator.py`

**Accept and pass library context**:

```python
def process_folders(
    self,
    folders: List[Dict[str, Any]],
    plan_name: str,
    workflow_name: str,
    backend: str = 'python'
) -> str:
    """
    Process folders with optional library context

    Folder dict can now include:
        - library_db_path: Path to library database
        - collection_id: Library collection ID
    """

    # Extract library context if present
    library_context = {}
    for folder in folders:
        if 'library_db_path' in folder:
            library_context['library_db_path'] = folder['library_db_path']
        if 'collection_id' in folder:
            library_context['collection_id'] = folder['collection_id']

    # Pass to workflow executor
    # ... existing code ...
```

---

## Component 6: Variable Substitution

### Update workflow executor to substitute library variables:

```python
def substitute_variables(self, args: Dict, context: Dict) -> Dict:
    """Substitute {variables} in workflow args"""

    substituted = {}
    for key, value in args.items():
        if isinstance(value, str):
            # Substitute library context variables
            value = value.replace('{library_db_path}', context.get('library_db_path', ''))
            value = value.replace('{collection_id}', context.get('collection_id', ''))
            # ... other substitutions ...
        substituted[key] = value

    return substituted
```

---

## Testing Strategy

### Phase 1: Test Generic Catalogue WITHOUT Metadata
- ✅ Test current Generic_Catalogue.yml plan
- Verify all steps work
- Check catalogue output quality

### Phase 2: Create Metadata Extraction Tool
- Create `extract_library_metadata.py`
- Add unit tests
- Test with sample library database

### Phase 3: Integrate Metadata Tool
- Update Generic_Catalogue.yml with new step
- Update llm_process.py to accept metadata
- Test metadata loading

### Phase 4: Update Prompts
- Modify catalogue prompts to use metadata
- Test with real library items
- Compare results with/without metadata

### Phase 5: End-to-End Testing
- Test full workflow from GUI
- Verify metadata flows correctly
- Check catalogue entries use metadata

---

## Benefits

✅ **Backwards Compatible**: Workflows work without metadata
✅ **Generic**: Works with any JSON metadata structure
✅ **Decoupled**: Tools don't require library dependency
✅ **Testable**: Each component can be tested independently
✅ **Flexible**: Users can add any metadata fields
✅ **Reusable**: Other workflows can use metadata extraction

---

## Files to Modify

**New Files**:
1. `src/fichero/tools/extract_library_metadata.py` - New tool

**Modified Files**:
1. `src/fichero/resources/config_defaults/plans/Generic_Catalogue.yml` - Add step
2. `src/fichero/tools/llm_process.py` - Add metadata support
3. `src/fichero/resources/config_defaults/prompts/Generic_Catalogue.jsonl` - Update prompts
4. `src/fichero/library/director_integration.py` - Pass library context
5. `src/fichero/director/processing_coordinator.py` - Accept library context

**Test Files**:
1. `tests/test_extract_library_metadata.py` - New tests
2. `tests/test_llm_process_with_metadata.py` - Updated tests

---

## Next Steps

1. **Wait for Generic Catalogue test results**
2. **Implement extract_library_metadata.py tool**
3. **Add metadata manifest parameter to catalogue_folder step**
4. **Update llm_process.py to use metadata**
5. **Test end-to-end with real library data**
