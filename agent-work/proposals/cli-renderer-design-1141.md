# CLI Renderer Functions Design for #1141

**Issue**: CLI formatter now recognizes document_id and document_name fields, but output still lacks specialized rendering for KnowledgeEntity, KnowledgeClaim, Document, and Artifact objects. This design specifies four dedicated renderers to emit human-readable single-line summaries suitable for CLI list output.

**Status**: Design phase (pseudo-code, no implementation yet)

---

## Overview

Four dedicated renderer functions for KnowledgeEntity, KnowledgeClaim, Document, and Artifact — designed to emit human-readable single-line summaries suitable for CLI list output. Each supports `as_json=True` for structured JSON output.

All renderers follow a common pattern:
- Accept either Pydantic model or dict (struct-agnostic)
- Truncate long fields gracefully with ellipsis
- Align columns using fixed widths where applicable
- Support `as_json=False` (human) and `as_json=True` (JSON)
- Implement fallback chains for optional fields

---

## Design Patterns (Shared)

### 1. Truncation Helper

```python
def _truncate(text: str | None, width: int) -> str:
    """Truncate text to max width, append '...' if truncated.
    
    Args:
        text: Input text (None handled gracefully)
        width: Max character width
    
    Returns:
        Truncated text (e.g., "Colombia's capital..." for width=30)
    
    Examples:
        _truncate("Colombia's capital city", 20) → "Colombia's capita..."
        _truncate(None, 20) → ""
        _truncate("Short", 20) → "Short"
    """
    if not text:
        return ""
    text = str(text).strip()
    if len(text) > width:
        return text[:width - 3] + "..."
    return text
```

### 2. Column Alignment Helper

```python
def _align_columns(items: list[str], widths: list[int]) -> str:
    """Align multiple columns using ljust().
    
    Args:
        items: List of strings, one per column
        widths: Max width per column (left-justify padding)
    
    Returns:
        Single line with aligned columns separated by " | "
    
    Example:
        items = ["Bogotá", "location", "Colombia's capital..."]
        widths = [30, 15, 40]
        → "Bogotá                         | location        | Colombia's capital..."
    """
    if not items:
        return ""
    parts = []
    for i, item in enumerate(items):
        width = widths[i] if i < len(widths) else 0
        if isinstance(item, str):
            # Left-justify to width, then truncate if exceeded
            parts.append(item.ljust(width)[:width])
        else:
            parts.append(str(item))
    return " | ".join(parts).rstrip()
```

### 3. Union Type Handling

All renderers accept either Pydantic model or dict:

```python
def _to_dict(obj: BaseModel | dict) -> dict:
    """Convert Pydantic model to dict, pass through dicts.
    
    Args:
        obj: KnowledgeEntity, KnowledgeClaim, Document, Artifact (model or dict)
    
    Returns:
        dict representation suitable for .get() lookups
    """
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    return obj or {}
```

---

## Function 1: render_entity()

### Signature

```python
def render_entity(entity: KnowledgeEntity | dict, *, as_json: bool = False) -> str:
    """Render a KnowledgeEntity as human-readable summary or JSON.
    
    Human format:
        canonical_name | entity_type | description[:60]
    
    Example:
        Bogotá | location | Colombia's capital city, located in the And...
    
    JSON:
        {"id": "abc123", "canonical_name": "Bogotá", "entity_type": "location", ...}
    
    Args:
        entity: KnowledgeEntity model or dict representation
        as_json: If True, return full model_dump(mode="json"); else human summary
    
    Returns:
        Single-line human summary or JSON string
    """
```

### Implementation Notes

- **Field extraction:**
  - `canonical_name`: Use directly from model field (required)
  - `entity_type`: Get enum value from model, or string from dict; normalize to lowercase
  - `description`: Nullable; truncate to 60 chars if present
  
- **Column widths (fixed):**
  - Name: 30 chars
  - Type: 15 chars
  - Description: remainder (no fixed width, natural tail)

- **Handling missing fields:**
  - `description` null → empty string in description column
  - `entity_type` null → "unknown"
  - Both survive gracefully with blanks

- **Type conversion:**
  - Accept `KnowledgeEntity` model or plain dict
  - If dict, safely extract fields with `.get()`
  - If Pydantic model, extract via `_to_dict()`

- **JSON mode:**
  - Use `json.dumps(data, indent=2, sort_keys=True, default=str)`

### Example Input/Output

**Input (Pydantic model):**
```python
entity = KnowledgeEntity(
    id="abc123",
    canonical_name="Bogotá",
    entity_type=EntityType.location,
    description="Colombia's capital city, located in the Andean highlands."
)
```

**Human output:**
```
Bogotá                         | location        | Colombia's capital city, located in th...
```

**Input (dict):**
```python
entity_dict = {
    "id": "def456",
    "canonical_name": "Maria González",
    "entity_type": "person",
    "description": None
}
```

**Human output:**
```
Maria González                 | person          |
```

**JSON output** (`as_json=True`):
```json
{
  "canonical_name": "Bogotá",
  "created_at": "2026-05-17T...",
  "description": "Colombia's capital city, located in the Andean highlands.",
  "entity_type": "location",
  "id": "abc123",
  ...
}
```

---

## Function 2: render_claim()

### Signature

```python
def render_claim(claim: KnowledgeClaim | dict, *, as_json: bool = False) -> str:
    """Render a KnowledgeClaim as SVO triple or full text fallback.
    
    Human format:
        subject → predicate → object (from: source_document_id)
    
    Example (full SVO):
        Bogotá → located_in → Colombia (from: doc-abc123)
    
    Example (text fallback):
        The witness Pedro testified that Maria served as alcal... (from: doc-789)
    
    JSON:
        {"id": "claim-1", "text": "...", "subject_canonical": "...", ...}
    
    Args:
        claim: KnowledgeClaim model or dict
        as_json: If True, return full model_dump(); else human summary
    
    Returns:
        Single-line human summary (SVO or text fallback) or JSON string
    """
```

### Implementation Notes

- **SVO fields** (all nullable; missing field triggers fallback):
  - `subject_canonical`: Truncate to 25 chars
  - `predicate_verb`: Truncate to 25 chars (verb phrase only, not object_phrase)
  - `object_phrase`: Truncate to 25 chars
  
- **Fallback chain** (if any SVO field is None):
  1. Try SVO fields → render as "S → V → O (from: source_id)"
  2. If any part is None, fall back to full `text` field
  3. Truncate full text to 75 chars if needed
  4. Append source document ID in parentheses

- **Source reference:**
  - Always fetch `source_document_id` (required field)
  - Format: `(from: doc-abc123)` or `(from: source_id)`

- **Layout (SVO mode):**
  ```
  subject[25] → predicate[25] → object[25] (from: <doc_id>)
  ```

- **Layout (text fallback):**
  ```
  text[:75]... (from: <doc_id>)
  ```

- **Edge cases:**
  - All SVO parts null and text field also empty → render "(no claim text) (from: doc_id)"
  - Source ID is None → render "(from: None)" or "(from: orphaned)"
  - All SVO parts truncated independently, no padding

- **JSON mode:**
  - Return full model_dump(mode="json"), sorted

### Example Input/Output

**Input (full SVO present):**
```python
claim = KnowledgeClaim(
    id="claim-1",
    text="Bogotá is located in Colombia.",
    subject_canonical="Bogotá",
    predicate_verb="located_in",
    object_phrase="Colombia",
    source_document_id="doc-456"
)
```

**Human output:**
```
Bogotá → located_in → Colombia (from: doc-456)
```

**Input (partial SVO, fallback to text):**
```python
claim_dict = {
    "id": "claim-2",
    "text": "The witness Pedro testified that Maria served as alcalde from 1933 to 1937.",
    "subject_canonical": "Pedro",
    "predicate_verb": None,  # missing
    "object_phrase": None,   # missing
    "source_document_id": "doc-789"
}
```

**Human output (fallback to text):**
```
The witness Pedro testified that Maria served as alcal... (from: doc-789)
```

**Input (missing SVO, missing text):**
```python
claim_dict = {
    "id": "claim-3",
    "text": "",  # empty
    "subject_canonical": None,
    "source_document_id": "doc-999"
}
```

**Human output:**
```
(no claim text) (from: doc-999)
```

---

## Function 3: render_document()

### Signature

```python
def render_document(doc: Document | dict, *, as_json: bool = False) -> str:
    """Render a Document as filename + type + optional description.
    
    Human format:
        filename [doc_type] - description[:50]
    
    Example (with description):
        fieldnotes-2024.pdf [file] - Ethnographic fieldwork notes from...
    
    Example (no description):
        Archive Box 5 [folder]
    
    JSON:
        {"id": "doc-1", "name": "fieldnotes-2024.pdf", "doc_type": "file", ...}
    
    Args:
        doc: Document model or dict
        as_json: If True, return full model_dump(); else human summary
    
    Returns:
        Single-line human summary or JSON string
    """
```

### Implementation Notes

- **Field extraction:**
  - `name`: Primary label, required (or `filename` if looking in metadata)
  - `doc_type`: Enum value from model, string from dict
  - `description`: Nullable; truncate to 50 chars

- **Type normalization:**
  - `doc_type` is a `DocType` enum (folder, group, file, page, chunk)
  - In brackets, display as lowercase enum value: [folder], [file], [page]
  - Don't uppercase; [file] not [FILE]

- **Description handling:**
  - If description present and non-empty: separator is " - " (space-dash-space)
  - If description is None or empty: omit separator and description
  - Result: "filename [type]" or "filename [type] - description[:50]"

- **Edge cases:**
  - `name` null → "(unnamed)"
  - `doc_type` null → "[unknown]"
  - Description null → no separator, just "name [type]"

- **JSON mode:**
  - Full model_dump(mode="json"), sorted

### Example Input/Output

**Input (Pydantic, with description):**
```python
doc = Document(
    id="doc-1",
    name="fieldnotes-2024.pdf",
    doc_type=DocType.file,
    file_type=FileType.pdf,
    description="Ethnographic fieldwork notes from the Andean region."
)
```

**Human output:**
```
fieldnotes-2024.pdf [file] - Ethnographic fieldwork notes from the And...
```

**Input (dict, no description):**
```python
doc_dict = {
    "id": "doc-2",
    "name": "Archive Box 5",
    "doc_type": "folder",
    "description": None
}
```

**Human output:**
```
Archive Box 5 [folder]
```

**Input (dict, with description):**
```python
doc_dict = {
    "name": "Correspondence 1933",
    "doc_type": "group",
    "description": "Letters exchanged between the petitioner and the scribe during the land dispute."
}
```

**Human output:**
```
Correspondence 1933 [group] - Letters exchanged between the petitioner...
```

---

## Function 4: render_artifact()

### Signature

```python
def render_artifact(artifact: Artifact | dict, *, as_json: bool = False) -> str:
    """Render an Artifact as type + title or JSON.
    
    Human format:
        artifact_type: title [:40] (from doc: doc_id)
    
    Example:
        Transcription: Meeting notes April 2024 (from doc: doc-456)
    
    Example (from structured data):
        Entities: Extracted entities from letter (from doc: doc-789)
    
    JSON:
        {"id": "art-1", "artifact_type": "transcription", "content": "...", ...}
    
    Args:
        artifact: Artifact model or dict
        as_json: If True, return full model_dump(); else human summary
    
    Returns:
        Single-line human summary or JSON string
    """
```

### Implementation Notes

- **Field extraction:**
  - `artifact_type`: Machine-readable string (e.g., "transcription", "entities", "summary")
  - Title source (fallback chain):
    1. Look for `data["title"]` if `data` dict is present
    2. Look for `content` field (text artifacts)
    3. Fallback: "(no title)"
  - `document_id`: Reference to parent document (required field)

- **Type formatting:**
  - Normalize `artifact_type` to title case: "transcription" → "Transcription", "entities" → "Entities"
  - Join with colon and space: `"Transcription: Meeting notes..."`

- **Title/content truncation:**
  - Max 40 chars before ellipsis
  - Extract from `content` field if no title in `data`
  - Truncate independent of type string (e.g., "Transcription: " prefix not counted)

- **Reference format:**
  - `(from doc: {document_id})`
  - If `document_id` missing → `(from doc: orphaned)` or `(from doc: unknown)`

- **Full layout:**
  ```
  {Type}: {Title[:40]} (from doc: {doc_id})
  ```

- **Edge cases:**
  - `artifact_type` null → "(unknown type)"
  - Both `data.title` and `content` null → "(no artifact) (from doc: doc_id)"
  - `document_id` null → "(from doc: orphaned)"

- **JSON mode:**
  - Full model_dump(mode="json"), sorted

### Example Input/Output

**Input (Pydantic, content field):**
```python
artifact = Artifact(
    id="art-1",
    artifact_type="transcription",
    content="Meeting notes April 2024. Attendees discussed Q3 planning.",
    document_id="doc-456",
    provider="apple",
    model="apple-intelligence"
)
```

**Human output:**
```
Transcription: Meeting notes April 2024. Attendees discusse... (from doc: doc-456)
```

**Input (dict, structured data with title):**
```python
artifact_dict = {
    "id": "art-2",
    "artifact_type": "entities",
    "data": {"title": "Extracted entities from letter"},
    "document_id": "doc-789"
}
```

**Human output:**
```
Entities: Extracted entities from letter (from doc: doc-789)
```

**Input (missing content and data):**
```python
artifact_dict = {
    "id": "art-3",
    "artifact_type": "summary",
    "content": None,
    "data": None,
    "document_id": "doc-999"
}
```

**Human output:**
```
Summary: (no artifact) (from doc: doc-999)
```

---

## Integration into render() Call Path

### Current render() function (formatters.py, line 88)

```python
def render(data: Any, *, as_json: bool = False) -> str:
    """Render a backend response for display.
    
    Accepts plain dicts/lists OR Pydantic model instances (or nested
    combinations). Pydantic models are converted to JSON-shaped dicts at the
    boundary so the rest of the formatter stays purely structural.
    """
    data = _to_jsonable(data)
    if as_json:
        return json.dumps(data, indent=2, default=str, sort_keys=True)
    return _human(data).rstrip() or "(no data)"
```

### Updated _line() function (line 131)

Current implementation:
```python
def _line(item: Any, indent: int) -> str:
    pad = "  " * indent
    if not isinstance(item, dict):
        return f"{pad}- {item}"
    parts = [p for p in (_first(item, _ID_KEYS), _first(item, _LABEL_KEYS)) if p]
    text = "  ".join(parts) or "(item)"
    detail = _first(item, _DETAIL_KEYS)
    if detail:
        text += f"  [{detail}]"
    return f"{pad}- {text}"
```

New dispatch logic:
```python
def _line(item: Any, indent: int) -> str:
    pad = "  " * indent
    if not isinstance(item, dict):
        return f"{pad}- {item}"
    
    # NEW: Dispatch to specialized renderers based on detected type
    if _is_entity(item):
        return f"{pad}- {render_entity(item, as_json=False)}"
    elif _is_claim(item):
        return f"{pad}- {render_claim(item, as_json=False)}"
    elif _is_document(item):
        return f"{pad}- {render_document(item, as_json=False)}"
    elif _is_artifact(item):
        return f"{pad}- {render_artifact(item, as_json=False)}"
    
    # FALLBACK: existing generic logic for unknown types
    parts = [p for p in (_first(item, _ID_KEYS), _first(item, _LABEL_KEYS)) if p]
    text = "  ".join(parts) or "(item)"
    detail = _first(item, _DETAIL_KEYS)
    if detail:
        text += f"  [{detail}]"
    return f"{pad}- {text}"
```

### Type Detection Helpers

These heuristics identify what type of object a dict represents:

```python
def _is_entity(item: dict) -> bool:
    """Heuristic: looks like a KnowledgeEntity.
    
    A KnowledgeEntity always has canonical_name and entity_type fields.
    """
    return "canonical_name" in item and "entity_type" in item


def _is_claim(item: dict) -> bool:
    """Heuristic: looks like a KnowledgeClaim.
    
    A KnowledgeClaim has SVO fields (subject_canonical, predicate_verb, etc.).
    We check for either one, since both fields must coexist for SVO rendering.
    """
    return "subject_canonical" in item or "predicate_verb" in item


def _is_document(item: dict) -> bool:
    """Heuristic: looks like a Document.
    
    Documents always have doc_type and name fields.
    """
    return "doc_type" in item and "name" in item


def _is_artifact(item: dict) -> bool:
    """Heuristic: looks like an Artifact.
    
    Artifacts always have artifact_type and document_id fields.
    """
    return "artifact_type" in item and "document_id" in item
```

### Ordering of Checks

The dispatch order in `_line()` matters: check the most specific/rare types first.

1. **Entity** (has canonical_name + entity_type) — most specific
2. **Claim** (has subject_canonical or predicate_verb) — specific
3. **Document** (has doc_type + name) — specific
4. **Artifact** (has artifact_type + document_id) — specific
5. **Fallback** — generic logic

This order minimizes false positives. For example, a Document won't accidentally match Artifact if both have a "title" field.

---

## Testing Strategy

Each renderer needs comprehensive test coverage:

### 1. Happy Path
- Full data present, no truncation needed
- Example: entity with all fields, SVO claim, document with description, artifact with title

### 2. Truncation
- Fields exceed their width limits
- Verify ellipsis is appended correctly
- Example: entity with 100-char description, claim with 50-char subject, etc.

### 3. Null Fields
- One or more optional fields missing
- Verify graceful empty rendering (not crash)
- Example: entity with null description, claim with null SVO fields, artifact with null content

### 4. Fallback Chains
- SVO → text fallback for claims (when verb/object missing)
- Title → content → "(no title)" fallback for artifacts
- Example: claim with subject_canonical but null predicate_verb

### 5. Dict Input
- Ensure model-agnostic handling
- Pydantic models AND plain dicts should produce identical output
- Example: KnowledgeEntity model vs. dict with same data

### 6. JSON Output
- Verify `as_json=True` produces valid JSON
- Check that all fields are present in sorted order
- Example: json.loads(render_entity(..., as_json=True)) should not raise

### Test Location

`fichero-engine/tests/unit/test_cli_formatters.py` (new test file or section)

### Example Test Structure

```python
def test_render_entity_happy_path():
    """Entity with all fields renders correctly."""
    entity = KnowledgeEntity(
        canonical_name="Bogotá",
        entity_type=EntityType.location,
        description="Colombia's capital"
    )
    result = render_entity(entity)
    assert "Bogotá" in result
    assert "location" in result
    assert "Colombia's capital" in result


def test_render_entity_truncation():
    """Long descriptions are truncated at 60 chars."""
    entity = KnowledgeEntity(
        canonical_name="X",
        entity_type=EntityType.location,
        description="A" * 100
    )
    result = render_entity(entity)
    assert len(result.split("|")[2].strip()) <= 63  # 60 + "..."


def test_render_claim_fallback_svo_to_text():
    """When SVO incomplete, fall back to text field."""
    claim_dict = {
        "text": "The witness testified",
        "subject_canonical": "witness",
        "predicate_verb": None,  # missing
        "object_phrase": None,
        "source_document_id": "doc-1"
    }
    result = render_claim(claim_dict)
    assert "The witness testified" in result
    assert "→" not in result  # No SVO arrow


def test_render_document_no_description():
    """Document without description omits separator."""
    doc_dict = {
        "name": "Archive Box 5",
        "doc_type": "folder",
        "description": None
    }
    result = render_document(doc_dict)
    assert result == "Archive Box 5 [folder]"
    assert " - " not in result


def test_render_artifact_dict_vs_pydantic():
    """Dict and Pydantic model produce same human output."""
    artifact_model = Artifact(
        artifact_type="transcription",
        content="Meeting notes",
        document_id="doc-1"
    )
    artifact_dict = {
        "artifact_type": "transcription",
        "content": "Meeting notes",
        "document_id": "doc-1"
    }
    result_model = render_artifact(artifact_model)
    result_dict = render_artifact(artifact_dict)
    assert result_model == result_dict
```

---

## Summary

This design provides four focused renderers that:

1. **Emit clean, scannable single-line summaries** for CLI list output
2. **Support both Pydantic models and dicts** (struct-agnostic)
3. **Truncate gracefully** with ellipsis when fields exceed width limits
4. **Implement fallback chains** for optional fields (SVO → text, title → content)
5. **Support JSON output** for scripting and integration
6. **Integrate seamlessly** into the existing `_line()` dispatch in `formatters.py`
7. **Are thoroughly testable** with clear, independent test coverage

The renderers can be implemented incrementally and tested independently before wiring into the `_line()` dispatch.
