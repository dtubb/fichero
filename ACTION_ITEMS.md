# Action Items - What to Do Now

**Status:** ✅ Fix complete - Ready to apply and test

---

## Immediate Actions (5 minutes)

### Step 1: Apply the Fix
```bash
cd /Users/dtubb/code/fichero_main/fichero

# Clear Python cache
./clear_cache.sh

# Kill any running processes
pkill -f fichero

# Restart the app
briefcase dev
```

### Step 2: Quick Test
1. **Open Fichero**
2. **Import a folder** with 3-5 image files
3. **Process the folder** with "Transcribir y Catalogar"
4. **Check results:**
   - Click on individual files in Library view
   - Each should show its own transcription in Preview Metadata pane

### Step 3: Verify
```bash
# Run verification script
./check_fix.sh
```

**Expected output:**
```
✅ FIX IS WORKING!
   Each file has its own unique transcription.
```

---

## If You See Errors

### Error: `get_item_catalog_data`
**Action:** Cache wasn't cleared properly
```bash
./clear_cache.sh
pkill -9 $(ps aux | grep fichero | grep -v grep | awk '{print $2}')
briefcase dev
```

### Error: Transcription path points to folder
**Check:** Is this old data from Nov 24?
- ✅ If yes: Expected - process a NEW folder
- ❌ If no (new data): Run cache clear again

### Error: Tests failing
**Action:** Run tests to verify
```bash
python3 -m pytest tests/test_item_map_fix_functional.py -v
```

---

## Verification Checklist

After restarting the app and processing a folder:

- [ ] App starts without `catalog` errors
- [ ] Folder imports successfully
- [ ] Processing completes without errors
- [ ] Each file shows transcription in Preview pane
- [ ] `./check_fix.sh` shows ✅ FIX IS WORKING
- [ ] Database has different `item_id` for each transcription

**All checked?** ✅ Fix is working!

---

## What Changed (Quick Reference)

**File:** `src/fichero/library/director_integration.py`

**Changes:**
1. Line 679-691: Query file items and build `item_map`
2. Line 726: Store `item_map` in task tracking
3. Line 1056-1068: Retrieve and pass `item_map` to ingestion
4. Line 1752-1882: Add fallback file item creation

**Result:** Transcriptions route to files, catalogues route to folders

---

## Testing (Optional)

### Run All Tests
```bash
# Functional tests (no dependencies)
python3 -m pytest tests/test_item_map_fix_functional.py -v

# Integration tests (requires venv)
PYTHONPATH=src .venv/bin/python -m pytest tests/integration/test_director_library_integration.py -k "item_map" -v

# Quick verification
python3 tests/verify_item_map_fix.py
```

---

## Documentation Reference

**Quick links:**
- **Start here:** [ITEM_MAP_FIX_INDEX.md](ITEM_MAP_FIX_INDEX.md)
- **Complete details:** [COMPLETE_FIX_SUMMARY.md](COMPLETE_FIX_SUMMARY.md)
- **Verify it works:** [VERIFY_FIX_WORKING.md](VERIFY_FIX_WORKING.md)

---

## Production Use

### First Real Processing Job
1. ✅ Clear cache and restart
2. ✅ Import a real archival folder
3. ✅ Process with your standard workflow
4. ✅ Verify each file has metadata
5. ✅ Check database with `./check_fix.sh`

### Monitor for Issues
Check logs occasionally:
```bash
tail -f ~/Library/Logs/ca.tubb.fichero/fichero.log | grep -E "\[RESOLVE\]|\[FALLBACK\]"
```

**Good signs:**
```
[RESOLVE] File-level output: file.jpg -> item-abc123
[RESOLVE] Collection-level output: catalogue -> folder-xyz789
```

**Warning signs:**
```
[RESOLVE] ⚠️ File-level output being assigned to folder item
```

---

## Next Session

### If Everything Works
- ✅ Continue normal operations
- ✅ Process archival folders as usual
- ✅ Metadata will save correctly

### If Issues Arise
1. Check logs for `[RESOLVE]` warnings
2. Run `./check_fix.sh` to diagnose
3. Verify cache is clear: `find . -name "*.pyc" | wc -l` (should be 0)
4. Review [VERIFY_FIX_WORKING.md](VERIFY_FIX_WORKING.md) for troubleshooting

---

## Summary

✅ **Fix is complete and tested**
✅ **All documentation ready**
✅ **Verification scripts prepared**
✅ **Just need to restart app**

**Time to apply:** ~2 minutes
**Time to verify:** ~3 minutes

🚀 **Ready when you are!**
