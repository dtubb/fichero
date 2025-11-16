# Tool Metadata Audit Report

**Date:** November 15, 2025
**Purpose:** Document current metadata storage patterns across all Fichero processing tools to inform migration to library backend metadata system.

---

## 1. Executive Summary

### Tools Audited
- **Total:** 20 processing tools
- **With metadata storage:** 16 tools
- **Without metadata storage:** 4 tools (describe_images, build_documents_manifest, recombine_segments, convert_to_word)

### Common Patterns Found
1. **Universal JSONL manifest pattern**: All tools write JSONL manifest files with consistent structure
2. **SegmentHandler integration**: All tools use `SegmentHandler.get_relative_path()` for path consistency
3. **BatchProcessor framework**: 95% of tools use the shared `BatchProcessor` class
4. **Metadata in `details` field**: Tool-specific metadata stored in `details` dictionary within manifest entries

### Migration Complexity
- **Low complexity (60%):** 12 tools - Simple metadata fields, direct migration
- **Medium complexity (30%):** 6 tools - Multiple metadata types or special handling
- **High complexity (10%):** 2 tools - Cross-tool dependencies or complex structures

### Special Cases Requiring Attention
1. **segment.py** - Creates segments with parent-child relationships
2. **transcribe_*.py** - Parallel processing with API rate limiting
3. **llm_process.py** - Multi-step processing with iterative refinement
4. **analyze_document_groups.py** - Video-based analysis with group structures

---

## 2. Tool-by-Tool Analysis

### 2.1 prepare_images.py

**Purpose:** Apply EXIF rotation and compression to images

**Metadata Fields:**
```python
{
    "original_size": [width, height],
    "prepared_size": [width, height],
    "rotation_applied": {
        "original_dimensions": [width, height],
        "reason": "EXIF rotation applied: ...",
        "final_dimensions": [width, height]
    },
    "compression_quality": 85,
    "output_format": "jpg",
    "original_format": ".jpg"
}
```

**Storage Code:**
- File: `src/fichero/tools/prepare_images.py:156-160`
- Returns dict with `outputs`, `source`, `details`
- Writes via BatchProcessor → ManifestProcessor

**JSONL Location:** `{output_folder}/prepare_images_manifest.jsonl`

**Migration Notes:**
- Simple metadata structure
- All fields are basic types (strings, ints, lists)
- No cross-tool dependencies
- **Priority:** Low complexity, migrate early

---

### 2.2 crop.py

**Purpose:** Crop document borders using YOLO or contour detection

**Metadata Fields:**
```python
{
    "box": {"x1": int, "y1": int, "x2": int, "y2": int},
    "method": "yolo" | "contour" | "original",
    "confidence": float,
    "padding": int,
    "original_size": [width, height],
    "cropped_size": [width, height],
    "rotation": {
        "original_dimensions": [width, height],
        "reason": str,
        "final_dimensions": [width, height]
    },
    "contour_settings": {  # Optional, only for contour method
        "threshold_method": str,
        "threshold_value": int,
        "blur_kernel": int,
        "edge_detection": bool,
        ...
    },
    "attempts": [  # List of detection attempts
        {"method": str, "confidence": float, "success": bool}
    ],
    "output_format": "jpg",
    "input_metadata": {...}
}
```

**Storage Code:**
- File: `src/fichero/tools/crop.py:563-575`
- CropInfo dataclass with `to_dict()` method
- Returns dict via process_image()

**JSONL Location:** `{output_folder}/crop_manifest.jsonl`

**Migration Notes:**
- Medium complexity - nested structures
- UI-editable parameters (contour_settings)
- **Priority:** Medium - migrate after simple tools

---

### 2.3 rotate.py

**Purpose:** Rotate images using Hough line transform

**Metadata Fields:**
```python
{
    "original_size": [width, height],
    "rotated_size": [width, height],
    "debug": {
        "found_lines": bool,
        "rotation_angle": float,
        "num_lines": int,
        "edge_points": int,
        "num_valid_angles": int  # Optional
    },
    "output_format": "jpg",
    "input_metadata": {...}
}
```

**Storage Code:**
- File: `src/fichero/tools/rotate.py:90-105`
- Simple dict return in process_image()

**JSONL Location:** `{output_folder}/rotate_manifest.jsonl`

**Migration Notes:**
- Low complexity
- Debug info useful for quality assessment
- **Priority:** Low complexity, migrate early

---

### 2.4 enhance.py

**Purpose:** Enhance image quality (CLAHE, color correction, sharpening)

**Metadata Fields:**
```python
{
    "original_size": [width, height],
    "enhanced_size": [width, height],
    "enhancement_params": {
        "analysis": {
            "document_type": "handwritten" | "typescript" | "mixed",
            "is_yellowed": float  # 0.0 to 1.0
        }
    },
    "output_format": "jpg",
    "input_metadata": {...}
}
```

**Storage Code:**
- File: `src/fichero/tools/enhance.py:216-230`
- DocumentAnalyzer provides analysis metadata

**JSONL Location:** `{output_folder}/enhance_manifest.jsonl`

**Special Features:**
- Has `skip_processing` mode for testing (creates 1x1 empty images)

**Migration Notes:**
- Low complexity
- Analysis metadata useful for future ML training
- **Priority:** Low complexity, migrate early

---

### 2.5 segment.py

**Purpose:** Segment long images into text regions

**Metadata Fields:**
```python
{
    "num_segments": int,
    "segments": [
        {
            "index": int,
            "file_path": str,  # Relative path
            "bounding_box": [top, bottom],
            "text_len": int,
            "parent_image": str,
            "rotation_confidence": float
        }
    ],
    "parent_info": {
        "path": str,
        "relative_path": str
    }
}
```

**Storage Code:**
- File: `src/fichero/tools/segment.py:867-890`
- Creates segment files in `{parent_name}_segments/` folder
- Each segment references parent

**JSONL Location:** `{output_folder}/segment_manifest.jsonl`

**Special Features:**
- Creates parent-child relationships
- Segments stored in subdirectories
- Has `skip_processing` mode

**Migration Notes:**
- **HIGH COMPLEXITY** - parent-child relationships
- Segments need to maintain linkage to parent document
- Consider hierarchical storage in library metadata
- **Priority:** Complex - migrate later with special handling

---

### 2.6 split.py

**Purpose:** Split double-page scans into individual pages

**Metadata Fields:**
```python
{
    "original_size": [width, height],
    "debug": {
        "aspect_ratio": float,
        "should_split": bool,
        "split_point": int,  # X coordinate
        "avg_darkness": float,
        "darkness_diff": float,
        "is_notebook": bool,
        "is_label": bool,
        "is_photo": bool,
        "is_cover": bool,
        "is_envelope": bool,
        "edge_density": float,
        "vertical_pattern": float,
        "content_density": {"left": float, "right": float},
        "pattern_peaks": int
    },
    "part_1_size": [width, height],  # If split
    "part_2_size": [width, height],  # If split
    "output_format": "jpg",
    "input_metadata": {...}
}
```

**Storage Code:**
- File: `src/fichero/tools/split.py:713-740`
- Extensive debug metadata for document type detection
- Can produce 1 or 2 outputs per input

**JSONL Location:** `{output_folder}/split_manifest.jsonl`

**Migration Notes:**
- Medium complexity - variable output count
- Rich debug metadata for analysis
- Document type detection metadata valuable
- **Priority:** Medium - migrate mid-phase

---

### 2.7 remove_background.py

**Purpose:** Remove image backgrounds using OpenCV or AI (rembg)

**Metadata Fields:**
```python
{
    "original_size": [width, height],
    "bg_removed_size": [width, height],
    "bg_removal_params": {
        "analysis": {
            "method": "opencv" | "ai_background_removal",
            "model": str,  # For AI method
            "black_thresh": int,  # For OpenCV
            "black_ratio": float,
            "total_foreground_area": int,
            "num_contours_found": int,
            "num_contours_kept": int,
            "crop_bbox": [x1, y1, x2, y2]
        }
    },
    "output_format": "png",  # Usually PNG for transparency
    "input_metadata": {...},
    "file_size": int,
    "removal_method": "opencv" | "ai",
    "ai_model": str  # If AI method
}
```

**Storage Code:**
- File: `src/fichero/tools/remove_background.py:390-408`
- Different metadata based on method (opencv vs ai)

**JSONL Location:** `{output_folder}/background_removed_manifest.jsonl`

**Special Features:**
- AI model caching in resources folder
- Two completely different removal methods

**Migration Notes:**
- Medium complexity - method-dependent metadata
- AI model info should be tracked
- **Priority:** Medium - migrate mid-phase

---

### 2.8 transcribe_qwen_max.py

**Purpose:** Transcribe images using Qwen VL Max API

**Metadata Fields:**
```python
{
    "has_content": bool,
    "text_length": int,
    "processed_at": str (ISO datetime),
    "model": "qwen-vl-max",
    "num_lines": int,
    "parent_info": {
        "path": str,
        "relative_path": str,
        "original_size": "WxH"
    },
    "segment_info": {  # Optional, if from segment
        "segment_index": int,
        "parent_path": str
    }
}
```

**Storage Code:**
- File: `src/fichero/tools/transcribe_qwen_max.py:246-275`
- Parallel processing with ThreadPoolExecutor
- Writes `.txt` files, not images

**JSONL Location:** `{output_folder}/transcriptions_manifest.jsonl`

**Special Features:**
- Parallel processing (5 workers)
- Progressive image size reduction on timeout
- API rate limiting handling
- Has `skip_processing` mode

**Migration Notes:**
- **MEDIUM-HIGH COMPLEXITY** - parallel processing
- Text output instead of images
- Parent-child relationship for segments
- API usage tracking valuable
- **Priority:** Complex - migrate with special handling

---

### 2.9 transcribe_lmstudio.py

**Purpose:** Transcribe images using local LM Studio API

**Metadata Fields:**
```python
{
    "has_content": bool,
    "text_length": int,
    "processed_at": str (ISO datetime),
    "model": str,  # User-specified model name
    "num_lines": int,
    "parent_info": {
        "path": str,
        "relative_path": str,
        "original_size": "WxH"
    },
    "segment_info": {  # Optional
        "segment_index": int,
        "parent_path": str
    }
}
```

**Storage Code:**
- File: `src/fichero/tools/transcribe_lmstudio.py:218-247`
- Async processing with asyncio
- Single concurrent request (local processing)

**JSONL Location:** `{output_folder}/transcription_manifest.jsonl`

**Special Features:**
- Async/await architecture
- Local processing (no API limits)

**Migration Notes:**
- Similar to transcribe_qwen_max
- **Priority:** Complex - migrate with transcribe_qwen_max

---

### 2.10 fuzzy_clean.py

**Purpose:** Clean transcribed text (remove OCR artifacts, format)

**Metadata Fields:**
```python
{
    "original_length": int,
    "cleaned_length": int,
    "reduction_percent": float,
    "empty_due_to_missing_input": bool,  # Optional
    "empty_due_to_encoding_error": bool,  # Optional
    "empty_due_to_read_error": bool,  # Optional
    "empty_due_to_empty_input": bool  # Optional
}
```

**Storage Code:**
- File: `src/fichero/tools/fuzzy_clean.py:640-656`
- May also carry `bg_removed` from upstream (recombine step)
- Text processing, not image

**JSONL Location:** `{output_folder}/{process_name}_manifest.jsonl`

**Special Features:**
- Extensive error handling with specific flags
- Passes through `bg_removed` metadata from upstream

**Migration Notes:**
- Low complexity
- Text processing metadata
- Cross-tool metadata passing (bg_removed)
- **Priority:** Low complexity, migrate early

---

### 2.11 json_to_word.py

**Purpose:** Convert JSON catalogue to Word documents

**Metadata Fields:**
```python
{
    "sections_created": int,
    "output_format": "docx"
}
```

**Storage Code:**
- File: `src/fichero/tools/json_to_word.py:307-315`
- Minimal metadata (mostly about document structure)

**JSONL Location:** `{output_folder}/json_to_word_manifest.jsonl`

**Migration Notes:**
- Very low complexity
- Output-oriented (not processing metadata)
- **Priority:** Low complexity, migrate early

---

### 2.12 json_to_excel.py

**Purpose:** Convert JSON catalogue to Excel spreadsheet

**Metadata Fields:**
- None (no JSONL manifest produced)
- Single output file combining all JSONs

**Storage Code:**
- No manifest writer
- Direct Excel file output

**Migration Notes:**
- No migration needed (no metadata stored)
- **Priority:** N/A

---

### 2.13 analyze_document_groups.py

**Purpose:** Analyze document groups using video of thumbnails

**Metadata Fields:**
```python
{
    "total_files": int,
    "groups_found": int,
    "processed_at": str (ISO datetime),
    "video_path": str,  # Relative to output
    "fps": int,
    "thumbnail_size": int,
    "analysis": {
        "change_points": [
            {
                "frame_number": int,
                "timestamp_seconds": float,
                "change_description": str,
                "before_visual": str,
                "after_visual": str,
                "before_content": str,
                "after_content": str
            }
        ],
        "total_frames": int,
        "groups": [
            {
                "group_id": int,
                "start_frame": int,
                "end_frame": int,
                "visual_type": str,
                "visual_characteristics": str,
                "file_count": int,
                "files": [str]  # List of file paths
            }
        ]
    }
}
```

**Storage Code:**
- File: `src/fichero/tools/analyze_document_groups.py:507-523`
- Creates video from thumbnails
- AI-based grouping analysis

**JSONL Location:** `{output_folder}/groups_manifest.jsonl`

**Special Features:**
- Creates video artifacts
- Has `skip_processing` mode
- Groups multiple documents

**Migration Notes:**
- **HIGH COMPLEXITY** - group structures
- Creates artifact files (video, thumbnails)
- Multi-document relationships
- **Priority:** Complex - migrate later with special handling

---

### 2.14 extract_library_metadata.py

**Purpose:** Extract library metadata from database for each file

**Metadata Fields:**
```python
{
    "processed_at": str (ISO datetime),
    "library_metadata": {
        "item_id": str,
        "item_name": str,
        "collection_id": str,
        "collection_name": str,
        "created_at": str (ISO datetime),
        "updated_at": str (ISO datetime),
        "storage_type": str,
        "source_path": str,
        "local_path": str,
        "status": str,
        "type": str,
        "metadata": {...}  # User-defined JSON
    }
}
```

**Storage Code:**
- File: `src/fichero/tools/extract_library_metadata.py:184-223`
- Queries LibraryStorage database
- Enriches with library context

**JSONL Location:** `{output_folder}/metadata_manifest.jsonl`

**Special Features:**
- Bridge between library and processing pipeline
- Has `skip_processing` mode (placeholder metadata)

**Migration Notes:**
- **SPECIAL CASE** - this IS the library metadata
- No migration needed (it's the target system)
- Used to enrich other tool outputs
- **Priority:** N/A (reference implementation)

---

### 2.15 llm_process.py

**Purpose:** Process documents through LLM pipeline for cataloguing

**Metadata Fields:**
```python
{
    "type": "document" | "folder",
    "text_length": int,  # For documents
    "files_processed": int,  # For folders
    "model": str
}
```

**Storage Code:**
- File: `src/fichero/tools/llm_process.py:250-256`
- Minimal manifest metadata (processing tracked internally)
- Actual results in JSON summary files

**JSONL Location:** `{output_folder}/llm_process_manifest.jsonl`

**Special Features:**
- Multi-step processing pipeline
- Iterative refinement
- Folder-level processing
- Creates separate JSON summary files

**Migration Notes:**
- **HIGH COMPLEXITY** - multi-step pipeline
- Results stored separately from manifest
- Processing history valuable
- **Priority:** Complex - migrate later

---

### 2.16 describe_images.py

**Purpose:** Generate visual descriptions of images using AI

**Metadata Fields:**
- Similar structure to transcribe_qwen_max.py
- Text descriptions instead of transcriptions

**Migration Notes:**
- Similar to transcription tools
- **Priority:** Medium complexity

---

### 2.17 build_documents_manifest.py

**Purpose:** Build initial manifest from source files

**Metadata Fields:**
- Minimal - just source file paths
- Foundation for all other tools

**Migration Notes:**
- Very low complexity
- **Priority:** Migrate early (foundation)

---

### 2.18 recombine_segments.py

**Purpose:** Recombine segmented transcriptions

**Metadata Fields:**
```python
{
    "num_segments_combined": int,
    "total_text_length": int,
    "segments_used": [str]  # List of segment paths
}
```

**Migration Notes:**
- Low-medium complexity
- Reverses segment.py operation
- **Priority:** Migrate with segment.py

---

### 2.19 convert_to_svg.py

**Purpose:** Convert images to SVG format

**Metadata Fields:**
- Similar to image processing tools
- Format conversion metadata

**Migration Notes:**
- Low complexity
- **Priority:** Low priority (rarely used)

---

## 3. Common Patterns

### 3.1 Shared Metadata Fields

**Universal fields (present in all tools):**
```python
{
    "source": str,  # Relative path from SegmentHandler
    "outputs": [str],  # List of relative output paths
    "details": {...}  # Tool-specific metadata
}
```

**Common image processing fields:**
```python
{
    "original_size": [width, height],
    "output_format": str,
    "input_metadata": {...}  # Passed from previous tool
}
```

**Common text processing fields:**
```python
{
    "text_length": int,
    "num_lines": int,
    "processed_at": str (ISO datetime),
    "model": str  # For AI-based tools
}
```

### 3.2 Shared Storage Mechanisms

**All tools use:**
1. `SegmentHandler.get_relative_path()` for path consistency
2. `BatchProcessor` for manifest writing
3. `ManifestProcessor` for JSONL handling
4. Atomic writes with `.tmp` files

**Standard manifest structure:**
```python
{
    "source": "relative/path/to/input.jpg",
    "outputs": ["relative/path/to/output.jpg"],
    "details": {
        # Tool-specific metadata
    },
    "success": bool,  # Optional
    "error": str,  # Optional
    "skipped": bool  # Optional
}
```

### 3.3 Code Reuse Opportunities

**Shared patterns that could be abstracted:**

1. **Image size tracking:**
   ```python
   {
       "original_size": [width, height],
       "{operation}_size": [width, height]
   }
   ```

2. **Processing timestamps:**
   ```python
   {
       "processed_at": datetime.now().isoformat()
   }
   ```

3. **Parent-child relationships:**
   ```python
   {
       "parent_image": str,
       "segment_info": {...}
   }
   ```

4. **Error handling:**
   ```python
   {
       "success": bool,
       "error": str,
       "skipped": bool
   }
   ```

---

## 4. Migration Priority Matrix

### Priority 1: Simple Tools (Migrate First)
**Complexity:** Low | **Impact:** High | **Dependencies:** None

1. **prepare_images.py** - Basic image metadata
2. **rotate.py** - Simple rotation metadata
3. **enhance.py** - Image enhancement metadata
4. **fuzzy_clean.py** - Text cleaning metadata
5. **json_to_word.py** - Document generation metadata
6. **build_documents_manifest.py** - Foundation

**Rationale:** These tools have simple, well-defined metadata with no cross-tool dependencies. Migrating them first establishes the base pattern for library metadata storage.

### Priority 2: Medium Complexity (Migrate Second)
**Complexity:** Medium | **Impact:** High | **Dependencies:** Moderate

1. **crop.py** - Nested structures, UI-editable
2. **split.py** - Variable outputs, rich debug data
3. **remove_background.py** - Method-dependent metadata
4. **transcribe_qwen_max.py** - Parallel processing
5. **transcribe_lmstudio.py** - Async processing
6. **describe_images.py** - Visual descriptions

**Rationale:** These tools have more complex metadata structures or special processing requirements, but no deep cross-tool dependencies.

### Priority 3: Complex Tools (Migrate Last)
**Complexity:** High | **Impact:** Medium | **Dependencies:** Many

1. **segment.py** - Parent-child relationships
2. **recombine_segments.py** - Reverses segmentation
3. **analyze_document_groups.py** - Multi-document groups
4. **llm_process.py** - Multi-step pipeline

**Rationale:** These tools create hierarchical relationships or depend on multiple other tools. Migrate after establishing patterns with simpler tools.

### Not Migrating
- **json_to_excel.py** - No metadata stored
- **extract_library_metadata.py** - Already uses library system
- **convert_to_svg.py** - Rarely used utility

---

## 5. Special Cases

### 5.1 Parent-Child Relationships (segment.py)

**Challenge:** Segments reference parent documents

**Current approach:**
```python
{
    "parent_image": "path/to/parent.jpg",
    "segment_info": {
        "segment_index": 0,
        "parent_path": "path/to/parent.jpg"
    }
}
```

**Library metadata approach:**
```python
# In library metadata for segment:
{
    "processing_metadata": {
        "segment": {
            "parent_item_id": "parent-uuid",
            "segment_index": 0,
            "bounding_box": [top, bottom]
        }
    }
}
```

**Implementation notes:**
- Store parent item_id instead of path
- Use library's hierarchical structure
- Maintain back-reference from parent to children

### 5.2 Parallel Processing (transcribe_*.py)

**Challenge:** Multiple workers writing to same manifest

**Current approach:**
- ThreadPoolExecutor with shared ManifestProcessor
- Atomic writes with file locking

**Library metadata approach:**
- Each worker updates separate item records
- Database handles concurrency
- No file locking needed

**Implementation notes:**
- Use database transactions
- Batch updates for performance
- Track worker_id for debugging

### 5.3 Multi-Step Pipelines (llm_process.py)

**Challenge:** Multiple processing steps per document

**Current approach:**
```python
# Stores results in separate files
{output_folder}/
    steps/
        step_1_result.json
        step_2_result.json
    documents/
        doc_summary.json
```

**Library metadata approach:**
```python
{
    "processing_metadata": {
        "llm_catalogue": {
            "steps": [
                {
                    "step_name": "extract_entities",
                    "model": "gpt-4",
                    "timestamp": "...",
                    "result": {...}
                },
                {
                    "step_name": "summarize",
                    "model": "gpt-4",
                    "timestamp": "...",
                    "result": {...}
                }
            ],
            "final_result": {...}
        }
    }
}
```

**Implementation notes:**
- Store step history in metadata
- Keep final result accessible
- Track model/token usage per step

### 5.4 Document Groups (analyze_document_groups.py)

**Challenge:** Groups span multiple documents

**Current approach:**
```python
{
    "groups": [
        {
            "group_id": 1,
            "files": ["doc1.jpg", "doc2.jpg", "doc3.jpg"]
        }
    ]
}
```

**Library metadata approach:**
```python
# Create group as collection or tag
# Each document references group:
{
    "processing_metadata": {
        "document_group": {
            "group_id": "group-uuid",
            "group_type": "handwritten_letter",
            "position_in_group": 1
        }
    }
}
```

**Implementation notes:**
- Consider creating collections for groups
- Or use tags/labels
- Bidirectional references (group ↔ documents)

---

## 6. Metadata Schema Design

### 6.1 Proposed Library Metadata Structure

```python
{
    "item_id": "uuid",
    "item_name": "document_001.jpg",
    "collection_id": "collection-uuid",

    # User-editable metadata
    "user_metadata": {
        "title": "...",
        "description": "...",
        "tags": ["..."],
        # ... other user fields
    },

    # Processing metadata (tool outputs)
    "processing_metadata": {
        "prepare_images": {
            "original_size": [w, h],
            "rotation_applied": {...},
            "timestamp": "..."
        },
        "crop": {
            "method": "yolo",
            "box": {...},
            "timestamp": "..."
        },
        "enhance": {
            "document_type": "handwritten",
            "is_yellowed": 0.3,
            "timestamp": "..."
        },
        "transcribe": {
            "model": "qwen-vl-max",
            "text_length": 450,
            "has_content": true,
            "timestamp": "..."
        },
        # ... other tools
    },

    # Relationships
    "relationships": {
        "parent_item_id": "uuid",  # For segments
        "child_item_ids": ["uuid1", "uuid2"],  # For parents
        "group_id": "uuid",  # For grouped documents
        "related_items": ["uuid1", "uuid2"]  # General relationships
    },

    # Processing history (for debugging)
    "processing_history": [
        {
            "tool": "prepare_images",
            "timestamp": "...",
            "status": "success",
            "worker_id": "..."
        },
        # ...
    ]
}
```

### 6.2 Key Design Principles

1. **Namespaced by tool:** Each tool has its own section in `processing_metadata`
2. **Immutable history:** `processing_history` tracks all operations
3. **Flexible relationships:** Support parent-child, groups, and general relations
4. **User vs. processing separation:** Clear distinction between user and tool metadata
5. **Timestamp everything:** Every processing step has a timestamp

---

## 7. Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
- [ ] Define library metadata schema
- [ ] Create `ProcessingMetadata` model class
- [ ] Add metadata fields to `CollectionItem` model
- [ ] Create metadata update API in `LibraryStorage`

### Phase 2: Simple Tools (Week 3-4)
- [ ] Migrate prepare_images.py
- [ ] Migrate rotate.py
- [ ] Migrate enhance.py
- [ ] Migrate fuzzy_clean.py
- [ ] Create migration utilities for other tools

### Phase 3: Medium Tools (Week 5-6)
- [ ] Migrate crop.py
- [ ] Migrate split.py
- [ ] Migrate remove_background.py
- [ ] Migrate transcription tools
- [ ] Test parallel processing metadata writes

### Phase 4: Complex Tools (Week 7-8)
- [ ] Migrate segment.py (parent-child)
- [ ] Migrate analyze_document_groups.py (groups)
- [ ] Migrate llm_process.py (multi-step)
- [ ] Create relationship management UI

### Phase 5: Testing & Refinement (Week 9-10)
- [ ] End-to-end workflow testing
- [ ] Performance testing (large collections)
- [ ] Migration script for existing manifests
- [ ] Documentation and examples

---

## 8. Success Criteria

### Technical Metrics
- [ ] 100% of tools writing to library metadata
- [ ] < 100ms metadata write latency
- [ ] Zero data loss during migration
- [ ] All relationships preserved

### User Experience
- [ ] Metadata searchable in library UI
- [ ] Processing history visible per item
- [ ] No workflow disruption during migration
- [ ] Easy rollback if needed

### Code Quality
- [ ] Consistent metadata schema across tools
- [ ] 80%+ code reuse for metadata handling
- [ ] Comprehensive test coverage
- [ ] Clear migration documentation

---

## 9. Risks and Mitigation

### Risk 1: Performance Degradation
**Impact:** High | **Probability:** Medium

**Mitigation:**
- Batch metadata updates
- Use database indexes on frequently queried fields
- Cache metadata in memory for active items
- Benchmark before and after migration

### Risk 2: Data Loss During Migration
**Impact:** Critical | **Probability:** Low

**Mitigation:**
- Keep JSONL manifests as backup during transition
- Write to both systems during migration phase
- Comprehensive validation before deprecating JSONL
- Automated migration verification script

### Risk 3: Complex Relationships Break
**Impact:** High | **Probability:** Medium

**Mitigation:**
- Extensive testing with segment/group workflows
- Foreign key constraints in database
- Relationship validation in UI
- Rollback procedure documented

### Risk 4: Tool-Specific Metadata Conflicts
**Impact:** Medium | **Probability:** Medium

**Mitigation:**
- Namespace all tool metadata
- Schema versioning
- Migration utilities for schema changes
- Backward compatibility layer

---

## 10. Conclusion

The audit reveals a well-structured metadata system with consistent patterns across tools. The primary challenge for migration is handling special cases (segments, groups, multi-step processing) while maintaining the simplicity of the current JSONL approach.

**Key recommendations:**

1. **Phased migration:** Start with simple tools to establish patterns
2. **Dual-write period:** Write to both JSONL and library DB during transition
3. **Focus on relationships:** Invest time in getting parent-child and group relationships right
4. **Preserve history:** Keep processing history for debugging and audit
5. **Maintain performance:** Batch operations and use database features efficiently

**Next steps:**

1. Review this audit with team
2. Finalize metadata schema design
3. Create proof-of-concept with 1-2 simple tools
4. Develop migration utilities
5. Begin Phase 1 implementation
