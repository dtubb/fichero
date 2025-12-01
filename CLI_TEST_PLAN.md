# CLI Test Plan - Director-Library Integration

**Date:** November 27, 2025
**Goal:** Verify item_map routing works correctly via CLI

---

## Test Data Available

**Location:** `/Users/dtubb/Documents/fichero/`

| Folder | File Count | Description |
|--------|------------|-------------|
| Tiny Test | ~3 files | Single folder with few images |
| Small Test | 23 files | LFH_AHJM_DOC10141 small folder |
| Medium Test | ~150 files | Two folders with many images |
| Large Test | Unknown | Larger dataset |
| Huge Test | Unknown | Very large dataset |

---

## Test Plan

### Test 1: Single File Processing ⏸️ SKIP
**Reason:** File-level processing doesn't use item_map (only folder processing does)

### Test 2: Small Folder (23 files) ✅ PRIMARY TEST
**Input:** `/Users/dtubb/Documents/fichero/Small Test/LFH_AHJM_DOC10141 small`
**Expected:**
- item_map created with 23 entries
- Each transcription routes to individual file item
- Catalogue routes to folder item
- Database shows 23 unique item_ids for transcriptions

**Verification:**
- Check logs for `[ITEM_MAP] Built item_map with 23 unique filenames`
- Query database for transcription outputs
- Verify each transcription has different item_id

### Test 3: Medium Folder (150+ files) ✅ PERFORMANCE TEST
**Input:** `/Users/dtubb/Documents/fichero/Medium Test/`
**Expected:**
- item_map creation fast (< 1 second)
- All files get individual transcriptions
- No duplicate filename warnings (unless duplicates exist)

**Verification:**
- Check performance logs
- Verify database routing

### Test 4: Check for Duplicate Filenames ✅ EDGE CASE
**Input:** Any folder
**Expected:**
- If duplicates exist, see `[ITEM_MAP] Duplicate filename in folder` warning
- Latest item_id is used

---

## Commands to Run

### Setup: Check Available Workflows
```bash
cd /Users/dtubb/code/fichero_main/fichero
PYTHONPATH=src .venv/bin/python -m fichero.cli.main library plans
```

### Test 2: Process Small Folder (23 files)

**Step 1: Create Collection**
```bash
PYTHONPATH=src .venv/bin/python -m fichero.cli.main library add \
  "CLI Test - Small Folder" \
  --type external \
  --source "/Users/dtubb/Documents/fichero/Small Test"
```

**Step 2: Import Folder**
```bash
# Get collection ID from previous command output
COLLECTION_ID="<from-step-1>"

PYTHONPATH=src .venv/bin/python -m fichero.cli.main library add-item \
  "$COLLECTION_ID" \
  folder \
  "/Users/dtubb/Documents/fichero/Small Test/LFH_AHJM_DOC10141 small"
```

**Step 3: Process Folder**
```bash
# Get item ID from previous command output
ITEM_ID="<from-step-2>"

PYTHONPATH=src .venv/bin/python -m fichero.cli.main library process \
  "$COLLECTION_ID" \
  --item-id "$ITEM_ID" \
  --plan "Transcribir y Catalogar" \
  --workflow "Catalogue"
```

**Step 4: Verify Results**
```bash
# Check logs
tail -100 ~/Library/Application\ Support/ca.tubb.fichero/logs/fichero_*.log | grep ITEM_MAP

# Check database
./check_fix.sh
```

### Verification Queries

**Query 1: Check item_map was built**
```bash
grep "Built item_map" ~/Library/Application\ Support/ca.tubb.fichero/logs/fichero_*.log | tail -5
```

**Query 2: Check transcription routing**
```bash
sqlite3 "$HOME/Library/Application Support/ca.tubb.fichero/library/library.db" <<EOF
SELECT
  ci.type,
  ci.name,
  po.output_type,
  COUNT(*) as count
FROM processing_outputs po
JOIN collection_items ci ON po.item_id = ci.id
WHERE po.created_at > datetime('now', '-1 hour')
GROUP BY ci.type, po.output_type
ORDER BY po.output_type;
EOF
```

**Expected Output:**
```
type    name                  output_type       count
------  --------------------  ---------------   -----
folder  LFH_AHJM_DOC10141...  catalogue         1
file    LFH_AHJM_DOC10141_... transcription     23
```

**Query 3: Verify unique item_ids**
```bash
sqlite3 "$HOME/Library/Application Support/ca.tubb.fichero/library/library.db" <<EOF
SELECT
  output_type,
  COUNT(DISTINCT item_id) as unique_items,
  COUNT(*) as total_outputs
FROM processing_outputs
WHERE created_at > datetime('now', '-1 hour')
  AND output_type = 'transcription'
GROUP BY output_type;
EOF
```

**Expected:** `unique_items = 23, total_outputs = 23`

---

## Success Criteria

✅ **PASS if:**
1. item_map log shows 23 unique filenames
2. Database shows 23 transcriptions with 23 unique item_ids
3. Database shows 1 catalogue with folder item_id
4. All transcription item_ids are type='file'
5. Catalogue item_id is type='folder'
6. No errors in logs

❌ **FAIL if:**
1. All transcriptions have same item_id (old bug)
2. Transcriptions assigned to folder item_id
3. Errors during processing
4. item_map not created

---

## Cleanup After Testing

```bash
# Optional: Remove test collection
PYTHONPATH=src .venv/bin/python -m fichero.cli.main library delete "$COLLECTION_ID"
```

---

## Notes

- Use fresh collection for clean test
- Monitor logs in real-time: `tail -f ~/Library/Application\ Support/ca.tubb.fichero/logs/fichero_*.log`
- Clear cache before testing: `./clear_cache.sh`
