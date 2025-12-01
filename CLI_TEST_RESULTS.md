# CLI Test Results - Director-Library Integration

**Date:** November 29, 2025
**Test Goal:** Verify item_map routing works correctly via CLI

---

## Test Setup ✅ COMPLETE

### Test Data
- **Source:** `/Users/dtubb/Documents/fichero/Small Test/LFH_AHJM_DOC10141 small`
- **File Count:** 23 JPEG files
- **Collection ID:** `1d8360f6-727e-4229-ae82-47df677bc0fd`
- **Folder Item ID:** `ce2fd212-2823-4420-9bba-e94828e7a3bd`

### Commands Executed

**1. Create Collection:**
```bash
PYTHONPATH=src .venv/bin/python -c "from fichero.cli import main; main()" library add \
  "CLI Test - Small Folder (23 files)" \
  --type external \
  --source "/Users/dtubb/Documents/fichero/Small Test"
```
**Result:** ✅ Collection created successfully

**2. Add Folder Item:**
```bash
PYTHONPATH=src .venv/bin/python -c "from fichero.cli import main; main()" library add-item \
  1d8360f6-727e-4229-ae82-47df677bc0fd \
  folder \
  "/Users/dtubb/Documents/fichero/Small Test/LFH_AHJM_DOC10141 small"
```
**Result:** ✅ Folder item created, **automatically catalogued 23 files**

**3. Database Verification:**
```bash
sqlite3 "$HOME/Library/Application Support/ca.tubb.fichero/library/library.db" \
  "SELECT id, type, name FROM collection_items \
   WHERE collection_id = '1d8360f6-727e-4229-ae82-47df677bc0fd' LIMIT 10;"
```

**Result:** ✅ 24 total items (1 folder + 23 files)

---

## Database State Verification

### Collection Items Created

| Type | Count | Example Names |
|------|-------|---------------|
| folder | 1 | LFH_AHJM_DOC10141 small |
| file | 23 | LFH_AHJM_DOC10141_IMG_001.jpg, _002.jpg, etc. |
| **Total** | **24** | |

### Sample Items

```
ce2fd212-2823-4420-9bba-e94828e7a3bd | folder | LFH_AHJM_DOC10141 small
8cd48322-6010-48bc-86af-db4f7a12e900 | file   | LFH_AHJM_DOC10141_IMG_001.jpg
ddd68e8c-1ea5-4390-abd0-733c06426779 | file   | LFH_AHJM_DOC10141_IMG_002.jpg
c45ed78f-b1a2-472b-99e6-2ea2b562de27 | file   | LFH_AHJM_DOC10141_IMG_003.jpg
...
```

### Parent-Child Relationships

**✅ Verified:**
- All 23 file items have `parent_id = ce2fd212-2823-4420-9bba-e94828e7a3bd` (the folder)
- Folder item has `parent_id = NULL` (root level)

This structure is **perfect for testing item_map routing**:
- When processing the folder, `get_file_items_by_parent()` will find all 23 files
- item_map will be created with 23 entries
- Each transcription should route to its specific file item_id

---

## Processing Test

### Command Submitted

```bash
PYTHONPATH=src .venv/bin/python -c "from fichero.cli import main; main()" library process \
  1d8360f6-727e-4229-ae82-47df677bc0fd \
  --items ce2fd212-2823-4420-9bba-e94828e7a3bd \
  --plan "Transcribir y Catalogar" \
  --workflow "Catalogue"
```

**Output:**
```
Processing Collection Items through Fichero Director
Collection: CLI Test - Small Folder (23 files)
Items: 1
Plan: Transcribir y Catalogar
Workflow: Catalogue

Submitting processing tasks...
✅ Submitted 1 task(s) to Director

Task IDs:
  • 955afab1-8836-4f1e-92cd-f4caf5aca12f
```

### Status

**Task Submitted:** ✅ Successfully submitted to Director
**Processing Status:** ⏳ Running in background (Python backend processes synchronously)

### Expected Behavior

When processing completes, the following should happen:

1. **item_map Creation:**
   ```
   [ITEM_MAP] Built item_map with 23 unique filenames from 23 file items
   ```

2. **File-level Routing:**
   - 23 transcriptions created
   - Each transcription routes to different file item_id
   - All item_ids are type='file'

3. **Collection-level Routing:**
   - 1 catalogue created
   - Catalogue routes to folder item_id (ce2fd212...)
   - item_id is type='folder'

---

## Verification Queries (To Run After Processing)

### Query 1: Check item_map Was Built
```bash
# Check if items were imported correctly
sqlite3 "$HOME/Library/Application Support/ca.tubb.fichero/library/library.db" \
  "SELECT COUNT(*) FROM collection_items \
   WHERE collection_id = '1d8360f6-727e-4229-ae82-47df677bc0fd' \
   AND parent_id = 'ce2fd212-2823-4420-9bba-e94828e7a3bd';"
```
**Expected:** 23

### Query 2: Check Transcription Routing
```bash
sqlite3 "$HOME/Library/Application Support/ca.tubb.fichero/library/library.db" <<EOF
SELECT
  ci.type,
  po.output_type,
  COUNT(*) as count,
  COUNT(DISTINCT po.item_id) as unique_items
FROM processing_outputs po
JOIN collection_items ci ON po.item_id = ci.id
WHERE po.processing_result_id IN (
  SELECT id FROM processing_results
  WHERE item_id = 'ce2fd212-2823-4420-9bba-e94828e7a3bd'
)
GROUP BY ci.type, po.output_type;
EOF
```

**Expected Output:**
```
type    output_type       count  unique_items
------  ----------------  -----  ------------
folder  catalogue         1      1
file    transcription     23     23
```

### Query 3: Verify No Misrouting
```bash
# Check that no transcriptions went to folder
sqlite3 "$HOME/Library/Application Support/ca.tubb.fichero/library/library.db" <<EOF
SELECT COUNT(*) FROM processing_outputs po
JOIN collection_items ci ON po.item_id = ci.id
WHERE po.output_type = 'transcription'
  AND ci.type = 'folder'
  AND po.created_at > datetime('now', '-1 hour');
EOF
```

**Expected:** 0 (no transcriptions assigned to folders)

---

## Test Data Summary

### What We Have ✅

| Item | Status | Details |
|------|--------|---------|
| Collection Created | ✅ | 1d8360f6-727e-4229-ae82-47df677bc0fd |
| Folder Item Created | ✅ | ce2fd212-2823-4420-9bba-e94828e7a3bd |
| Files Catalogued | ✅ | 23 files automatically added |
| Parent-Child Links | ✅ | All files linked to folder |
| Processing Submitted | ✅ | Task 955afab1-8836-4f1e-92cd-f4caf5aca12f |

### What We're Testing

1. **item_map Creation** - `get_file_items_by_parent()` optimization
2. **Duplicate Detection** - Should see warnings if duplicates exist
3. **Path Validation** - All file paths should be valid
4. **Routing Logic** - File transcriptions → file items, catalogue → folder item
5. **Database Performance** - 23-item folder should be fast

---

## Success Criteria

### ✅ PASS Criteria

1. 23 file items created with correct parent_id
2. item_map created with 23 entries
3. 23 transcriptions with 23 unique item_ids (all type='file')
4. 1 catalogue with folder item_id (type='folder')
5. No transcriptions assigned to folder
6. No errors in processing

### ❌ FAIL Criteria

1. All transcriptions have same item_id (old bug)
2. Transcriptions assigned to folder item_id
3. Missing file items
4. Processing errors
5. item_map not created or empty

---

## Current Status

**Setup:** ✅ COMPLETE
- Collection created
- Folder imported
- 23 files automatically catalogued
- Parent-child relationships correct

**Processing:** ⏳ IN PROGRESS
- Task submitted to Director
- Running in background (Python backend)
- Need to wait for completion

**Next Steps:**
1. Wait for processing to complete (may take several minutes for 23 files with transcription)
2. Run verification queries
3. Check logs for item_map messages
4. Verify database routing is correct

---

## Notes

- The CLI successfully created the collection and imported the folder
- Automatic cataloguing created all 23 file items with correct parent_id
- This is the **perfect test case** for item_map routing
- Processing is asynchronous, so need to poll for completion
- Python backend processes synchronously, so the command may take time

---

## Follow-up Commands

**Check Processing Status:**
```bash
PYTHONPATH=src .venv/bin/python -c "from fichero.cli import main; main()" library status 1d8360f6-727e-4229-ae82-47df677bc0fd
```

**Check Recent Processing Results:**
```bash
sqlite3 "$HOME/Library/Application Support/ca.tubb.fichero/library/library.db" \
  "SELECT id, status, created_at FROM processing_results \
   WHERE item_id = 'ce2fd212-2823-4420-9bba-e94828e7a3bd' \
   ORDER BY created_at DESC LIMIT 5;"
```

**Quick Fix Verification:**
```bash
./check_fix.sh
```
