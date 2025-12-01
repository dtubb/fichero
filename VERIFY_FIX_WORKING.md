# How to Verify the item_map Fix is Working

## Quick Verification Steps

### 1. Clear Cache and Restart
```bash
cd /Users/dtubb/code/fichero_main/fichero
./clear_cache.sh
pkill -f fichero
briefcase dev
```

### 2. Test with a Real Folder

#### A. Import a folder with multiple files
1. Open Fichero
2. Go to Library view
3. Click "New Collection"
4. Click "Import Folder"
5. Select a folder with 3-5 image files

#### B. Process the folder
1. Select the imported folder in Library
2. Click "Process" button
3. Choose workflow (e.g., "Transcribir y Catalogar")
4. Wait for processing to complete

#### C. Verify the results

**Check in UI:**
1. In Library view, expand the folder
2. Click on individual files
3. Preview Metadata pane should show transcription for each file
4. Each file should have its own transcription text

**Check in Database:**
```bash
# Get the collection ID (last created collection)
COLLECTION_ID=$(sqlite3 "$HOME/Library/Application Support/ca.tubb.fichero/library/library.db" \
  "SELECT id FROM collections ORDER BY created_at DESC LIMIT 1;" 2>/dev/null)

echo "Collection ID: $COLLECTION_ID"

# Check processing outputs
sqlite3 "$HOME/Library/Application Support/ca.tubb.fichero/library/library.db" <<EOF
.mode column
.headers on

SELECT
  item_id,
  output_type,
  SUBSTR(output_path, 1, 80) as output_path
FROM processing_outputs
WHERE collection_id = '$COLLECTION_ID'
  AND output_type = 'transcription'
ORDER BY created_at DESC;
EOF
```

### 3. Expected Results ✅

**What you should see:**

1. **Multiple item_ids for transcriptions**
   - Each file has a different `item_id`
   - NOT all the same `item_id` (that would be the folder)

2. **Correct file paths**
   - Paths end in `.txt` (e.g., `assets/transcriptions/documents/file.txt`)
   - NOT pointing to folders

3. **Metadata in UI**
   - Each file shows its own transcription
   - Transcription text is different for each file
   - Preview pane loads without errors

### 4. Bad Results (Old Bug) ❌

**What the old bug looked like:**

1. **Same item_id for all transcriptions**
   - All transcriptions have folder's `item_id`
   - No individual file items get metadata

2. **Wrong paths**
   - Paths point to folders
   - Missing the actual `.txt` file

3. **No metadata in UI**
   - Individual files show no transcription
   - Or error when clicking transcription

## Detailed Database Verification

### Query 1: Check item_map was used
```bash
sqlite3 "$HOME/Library/Application Support/ca.tubb.fichero/library/library.db" <<EOF
.mode line

-- Get recent folder processing
SELECT
  pr.id as processing_result_id,
  pr.item_id as folder_item_id,
  pr.workflow,
  pr.status,
  COUNT(DISTINCT po.item_id) as unique_item_ids,
  COUNT(po.id) as total_outputs
FROM processing_results pr
LEFT JOIN processing_outputs po ON pr.id = po.processing_result_id
WHERE pr.created_at > datetime('now', '-1 hour')
  AND po.output_type = 'transcription'
GROUP BY pr.id
ORDER BY pr.created_at DESC
LIMIT 1;
EOF
```

**Expected:** `unique_item_ids` should equal `total_outputs`
- If you processed 3 files: `unique_item_ids = 3, total_outputs = 3`
- NOT: `unique_item_ids = 1, total_outputs = 3` (old bug)

### Query 2: Check file vs folder routing
```bash
sqlite3 "$HOME/Library/Application Support/ca.tubb.fichero/library/library.db" <<EOF
.mode column
.headers on

-- Show item types for recent outputs
SELECT
  po.output_type,
  ci.type as item_type,
  ci.name as item_name,
  COUNT(*) as count
FROM processing_outputs po
JOIN collection_items ci ON po.item_id = ci.id
WHERE po.created_at > datetime('now', '-1 hour')
GROUP BY po.output_type, ci.type
ORDER BY po.output_type, ci.type;
EOF
```

**Expected:**
```
output_type      item_type    item_name    count
--------------   ----------   ----------   -----
catalogue        folder       MyFolder     1
transcription    file         doc1.jpg     1
transcription    file         doc2.jpg     1
transcription    file         doc3.jpg     1
```

**NOT (old bug):**
```
output_type      item_type    item_name    count
--------------   ----------   ----------   -----
catalogue        folder       MyFolder     1
transcription    folder       MyFolder     3    ← BAD!
```

### Query 3: Check metadata extraction
```bash
sqlite3 "$HOME/Library/Application Support/ca.tubb.fichero/library/library.db" <<EOF
.mode column
.headers on

-- Show extracted metadata by item type
SELECT
  ci.type as item_type,
  em.schema_type,
  COUNT(*) as metadata_records
FROM extracted_metadata em
JOIN collection_items ci ON em.item_id = ci.id
WHERE em.created_at > datetime('now', '-1 hour')
GROUP BY ci.type, em.schema_type
ORDER BY ci.type, em.schema_type;
EOF
```

**Expected:**
```
item_type    schema_type      metadata_records
----------   --------------   ----------------
file         transcription    3
folder       catalogue        1
```

## Log Verification

Check the logs for routing decisions:

```bash
tail -n 1000 ~/Library/Logs/ca.tubb.fichero/fichero.log | grep "\[RESOLVE\]"
```

**Look for:**
```
[RESOLVE] File-level output: doc1.jpg -> file-item-001
[RESOLVE] File-level output: doc2.jpg -> file-item-002
[RESOLVE] Collection-level output: catalogue -> folder-item-123
```

**Warning signs:**
```
[RESOLVE] ⚠️ File-level output (transcription) being assigned to folder item
```

## Troubleshooting

### Issue: All transcriptions still going to folder

**Cause:** Cache not cleared or old code running

**Fix:**
```bash
./clear_cache.sh
pkill -9 $(ps aux | grep fichero | grep -v grep | awk '{print $2}')
briefcase dev
```

### Issue: No item_map in logs

**Cause:** Processed single file instead of folder

**Fix:** Make sure you're processing a folder with multiple files, not individual files

### Issue: Old data showing wrong behavior

**Cause:** Looking at data from before Nov 26

**Fix:** Process NEW folder after clearing cache

## Success Indicators ✅

You'll know the fix is working when:

1. ✅ Multiple `item_id` values for transcriptions in same folder
2. ✅ Logs show `[RESOLVE]` messages with different item_ids
3. ✅ Each file in UI shows its own transcription
4. ✅ Database queries show `item_type = 'file'` for transcriptions
5. ✅ No `[RESOLVE] ⚠️` warnings in logs
6. ✅ Output paths end in `.txt`, not folder names

## Quick Check Script

Save this as `check_fix.sh`:

```bash
#!/bin/bash
DB="$HOME/Library/Application Support/ca.tubb.fichero/library/library.db"

echo "🔍 Checking recent processing..."
echo ""

# Get latest processing
LATEST=$(sqlite3 "$DB" "SELECT id FROM processing_results ORDER BY created_at DESC LIMIT 1;")

if [ -z "$LATEST" ]; then
    echo "❌ No processing results found"
    exit 1
fi

echo "Processing Result ID: $LATEST"
echo ""

# Check routing
UNIQUE=$(sqlite3 "$DB" "SELECT COUNT(DISTINCT item_id) FROM processing_outputs WHERE processing_result_id = '$LATEST' AND output_type = 'transcription';")
TOTAL=$(sqlite3 "$DB" "SELECT COUNT(*) FROM processing_outputs WHERE processing_result_id = '$LATEST' AND output_type = 'transcription';")

echo "Transcription outputs:"
echo "  Unique items: $UNIQUE"
echo "  Total outputs: $TOTAL"
echo ""

if [ "$UNIQUE" -eq "$TOTAL" ] && [ "$TOTAL" -gt 0 ]; then
    echo "✅ FIX IS WORKING! Each file has unique transcription."
elif [ "$UNIQUE" -eq 1 ] && [ "$TOTAL" -gt 1 ]; then
    echo "❌ BUG PRESENT! All transcriptions going to same item (folder)."
else
    echo "⚠️  Check manually - unexpected results"
fi
```

Run with: `chmod +x check_fix.sh && ./check_fix.sh`
