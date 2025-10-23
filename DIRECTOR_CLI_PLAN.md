# Fichero Director CLI Enhancement Plan

## Overview
Comprehensive enhancement of the CLI and Director integration to support flexible processing scenarios, dry-run testing, and robust output management.

## Current State Analysis

### Existing CLI Commands
- `briefcase dev -- process INPUT_FOLDER` - Process folders with Director
- `briefcase dev -- library process COLLECTION_ID` - Process library collections

### Current Limitations
1. **No dry-run mode** - Can't test workflow without actually processing
2. **Rigid processing structure** - Expects specific folder structures
3. **Limited flexibility** - Can't easily process arbitrary sets of files/folders
4. **Output tracking** - Library doesn't fully parse Director's per-file outputs
5. **No cleanup tools** - Intermediate files accumulate
6. **Step navigation** - Can't view/edit/rerun individual workflow steps

## Implementation Phases

---

## PHASE 1: Add Dry-Run Mode to Director
**Goal:** Test workflows without actual processing

### Tasks:
1. **Add `--dry-run` flag to Director**
   - Location: `src/fichero/director/workflow_executor.py`
   - Behavior: Execute workflow structure validation only
   - Output: Show what WOULD be processed, estimated time, disk usage

2. **Implement dry-run in tools**
   - Location: `src/fichero/tools/utils/tool_logger.py`
   - Add context flag for dry-run mode
   - Tools check flag and skip actual processing

3. **Update CLI commands**
   - `briefcase dev -- process INPUT --dry-run`
   - `briefcase dev -- library process COLLECTION_ID --dry-run`

### Testing:
```bash
# Test with Tiny Test
briefcase dev -- process "/Users/dtubb/Documents/fichero/Tiny Test" --dry-run

# Test with library
briefcase dev -- library add "Test Collection" --source "/Users/dtubb/Documents/fichero/Tiny Test"
briefcase dev -- library process <collection_id> --dry-run
```

### Success Criteria:
- [  ] Dry-run shows all workflow steps
- [  ] No actual files are created/modified
- [  ] Estimates file counts and output sizes
- [  ] Unit tests pass

---

## PHASE 2: Fix Workflow Configuration
**Goal:** Workflows scan current directory instead of hardcoded "documents" folder

### Tasks:
1. **Update plan files** ✅ DONE
   - Changed `source_folder: "documents"` → `source_folder: "."`
   - Files: Default.yml, Enhance_Images_and_Catalogue.yml

2. **Test with real data**
   - Verify recursive scanning works
   - Test with Tiny Test structure

3. **Clean up failed processing**
   ```bash
   rm -rf /Users/dtubb/Downloads/EAP1740_NP_T19_1700/assets/*
   ```

### Testing:
```bash
# Test basic processing
briefcase dev -- process "/Users/dtubb/Documents/fichero/Tiny Test" -o "/tmp/test_output"

# Verify it finds all files recursively
briefcase dev -- process "/Users/dtubb/Documents/fichero/Tiny Test" --dry-run
```

### Success Criteria:
- [  ] Finds all files in subdirectories
- [  ] Creates correct manifest
- [  ] Processing completes successfully

---

## PHASE 3: Flexible Input Support
**Goal:** Process arbitrary files/folders, not just structured directories

### Tasks:
1. **Add `process-files` command**
   - Accept list of file paths
   - Create temporary manifest
   - Process as batch

2. **Add `process-list` command**
   - Accept text file with paths
   - Support mix of files and folders
   - Process each according to type

3. **Update DirectorIntegrationService**
   - Support non-contiguous file sets
   - Track individual file outputs

### CLI Examples:
```bash
# Process specific files
briefcase dev -- process-files file1.tif file2.tif file3.tif -o output/

# Process from list
briefcase dev -- process-list files.txt -o output/

# Library: process specific items
briefcase dev -- library process COLLECTION_ID --items "id1,id2,id3"
```

### Testing:
```bash
# Create test file list
echo "/Users/dtubb/Documents/fichero/Tiny Test/file1.jpg" > /tmp/test_files.txt
echo "/Users/dtubb/Documents/fichero/Small Test/file2.jpg" >> /tmp/test_files.txt

# Test processing
briefcase dev -- process-list /tmp/test_files.txt --dry-run
```

### Success Criteria:
- [  ] Can process non-contiguous files
- [  ] Works with mix of files and folders
- [  ] Outputs tracked per-file
- [  ] Unit tests pass

---

## PHASE 4: Enhanced Output Tracking
**Goal:** Library understands Director's per-file outputs

### Tasks:
1. **Enhance DirectorOutputParser**
   - Location: `src/fichero/library/director_output_parser.py`
   - Parse step-by-step outputs for each file
   - Create FileOutputRecord with all steps

2. **Add output database schema**
   - Table: `file_outputs`
   - Columns: file_id, step_name, output_path, metadata
   - Index by file for fast lookup

3. **Update GUI Output View**
   - Show per-file, per-step outputs
   - Allow navigation between steps
   - Display intermediate results

### Data Structure:
```python
class FileOutputRecord:
    file_id: str
    original_path: Path
    steps: Dict[str, StepOutput]  # step_name -> output

class StepOutput:
    step_name: str
    output_path: Path
    manifest_entry: dict
    timestamp: datetime
    metadata: dict
```

### Testing:
```bash
# Process and verify tracking
briefcase dev -- process "/Users/dtubb/Documents/fichero/Tiny Test" -o "/tmp/test"

# Inspect outputs
briefcase dev -- library inspect-outputs "/tmp/test"

# Show specific file's outputs
briefcase dev -- library show-file-outputs <file_id>
```

### Success Criteria:
- [  ] All intermediate outputs tracked
- [  ] Can query outputs by file
- [  ] Can query outputs by step
- [  ] GUI shows step-by-step results

---

## PHASE 5: Step Editing and Reprocessing
**Goal:** Edit outputs and rerun from specific steps

### Tasks:
1. **Add step resumption to Director**
   - Skip completed steps
   - Start from specified step
   - Use existing outputs as input

2. **Add CLI commands**
   ```bash
   briefcase dev -- resume TASK_ID --from-step transcribe
   briefcase dev -- library resume-item ITEM_ID --from-step catalogue
   ```

3. **Add edit workflow**
   - Export step output to editable format
   - Import edited version
   - Resume from next step

### Testing:
```bash
# Process tiny test
briefcase dev -- process "Tiny Test" -o "/tmp/test1"

# Edit transcription manually
vim /tmp/test1/assets/transcriptions/file1.json

# Resume from catalogue step
briefcase dev -- resume <task_id> --from-step catalogue_folder
```

### Success Criteria:
- [  ] Can resume from any step
- [  ] Edited outputs are used
- [  ] Workflow completes correctly

---

## PHASE 6: Cleanup Tools
**Goal:** Manage intermediate files and disk usage

### Tasks:
1. **Add cleanup categories**
   - **Keep**: transcripts, final edits, text files, catalogues
   - **Clean**: crops, rotated, enhanced, background_removed, prepared

2. **Add cleanup commands**
   ```bash
   briefcase dev -- library cleanup COLLECTION_ID --mode conservative
   briefcase dev -- library cleanup COLLECTION_ID --mode aggressive --keep-finals
   briefcase dev -- cleanup-outputs OUTPUT_PATH --dry-run
   ```

3. **Cleanup modes**
   - `conservative`: Remove only intermediate image files
   - `moderate`: Remove all except transcripts and finals
   - `aggressive`: Remove all except specified types

4. **Add cleanup config**
   - User can specify what to keep
   - Configurable per plan/workflow
   - Safety checks before deletion

### Testing:
```bash
# Show what would be cleaned
briefcase dev -- library cleanup <id> --mode conservative --dry-run

# Actually clean
briefcase dev -- library cleanup <id> --mode conservative

# Verify important files kept
ls /path/to/output/assets/transcriptions/  # Should still exist
ls /path/to/output/assets/enhanced/  # Should be gone
```

### Success Criteria:
- [  ] Dry-run shows what will be deleted
- [  ] Important files never deleted
- [  ] Cleanup recovers significant disk space
- [  ] Can configure retention policy

---

## PHASE 7: Comprehensive Testing
**Goal:** Unit tests for all scenarios

### Test Matrix:

| Scenario | Input Type | Structure | Expected |
|----------|-----------|-----------|----------|
| Single file | 1 file | Flat | Process 1 file |
| Multiple files (same dir) | 5 files | Flat | Batch process |
| Multiple files (diff dirs) | 5 files | Scattered | Individual process |
| Single folder | 1 folder | With subfolders | Process all recursively |
| Folder of folders | Parent folder | Multiple subfolders | Detect and process each |
| Collection (all items) | Collection | Mixed | Process all |
| Collection (selected) | Collection | Mixed | Process selected |
| Resume from step | Partial output | Existing | Continue processing |

### Test Locations:
- `tests/test_director_cli.py` - CLI command tests
- `tests/test_director_integration.py` - Library-Director integration
- `tests/test_output_tracking.py` - Output parsing and tracking
- `tests/test_cleanup.py` - Cleanup functionality

### Test Data:
- Use `/Users/dtubb/Documents/fichero/Tiny Test` for fast tests
- Use `/Users/dtubb/Documents/fichero/Small Test` for thorough tests
- Use mocked Director for unit tests (no actual processing)

---

## Implementation Order

### Week 1: Foundation
- [  ] Phase 1: Dry-run mode
- [  ] Phase 2: Fix workflow config (DONE)
- [  ] Initial testing with Tiny Test

### Week 2: Flexibility
- [  ] Phase 3: Flexible input support
- [  ] Testing with various file/folder combinations

### Week 3: Tracking
- [  ] Phase 4: Enhanced output tracking
- [  ] Database schema updates
- [  ] GUI integration

### Week 4: Advanced Features
- [  ] Phase 5: Step editing and reprocessing
- [  ] Phase 6: Cleanup tools

### Week 5: Testing & Polish
- [  ] Phase 7: Comprehensive testing
- [  ] Documentation
- [  ] Bug fixes

---

## Safety Considerations

1. **Never modify tools/utils code** - It's proven and stable
2. **Always test with --dry-run first**
3. **Use Tiny Test for initial testing** - Fast iteration
4. **Backup test data** before running new code
5. **Processing can take time** - Be patient with larger test sets

---

## Success Metrics

- [  ] All 8 scenarios in test matrix pass
- [  ] Dry-run accurately predicts results
- [  ] Cleanup recovers >80% of disk space
- [  ] Can resume from any workflow step
- [  ] Library correctly tracks all outputs
- [  ] GUI shows per-file, per-step outputs
- [  ] All unit tests pass
- [  ] Integration tests with real data pass

---

## Next Immediate Steps

1. Start with Phase 1 (Dry-run)
2. Test with Tiny Test
3. Verify no regressions
4. Move to Phase 3 (skip 2, already done)
5. Iterate slowly and test thoroughly
