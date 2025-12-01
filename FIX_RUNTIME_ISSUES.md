# Fix Runtime Issues

## Issues Identified

### Issue 1: Cached Bytecode (catalog vs catalogue spelling)
**Error:** `'LibraryManager' object has no attribute 'get_item_catalog_data'`
**Cause:** Python cached `.pyc` files have old method name with American spelling

### Issue 2: Old Processing Data
**Error:** Transcription path points to folder instead of `.txt` file
**Cause:** Data processed before item_map fix was applied (Nov 24)

## Solutions

### Quick Fix: Clear Cache and Restart

```bash
cd /Users/dtubb/code/fichero_main/fichero

# Clear all Python cache
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null

# Restart the application
briefcase dev
```

### Verify Fix is Working

Check recent processing outputs in database:
```bash
sqlite3 "$HOME/Library/Application Support/ca.tubb.fichero/library/library.db" \
  "SELECT item_id, output_type, output_path FROM processing_outputs
   WHERE created_at > '2025-11-26'
   ORDER BY created_at DESC LIMIT 10;"
```

**Expected:** Paths should point to actual `.txt` files inside `assets/transcriptions/`, not to folders.

## Notes

- ✅ The item_map fix IS working for NEW processing (after Nov 26)
- ⚠️ Old data from Nov 24 has wrong paths (before fix was applied)
- 🔄 Clearing cache will fix the catalog/catalogue method name issue
- 📁 Old incorrect data can be ignored or manually corrected if needed

## If Issues Persist

1. **Check Python process:** Make sure old Python process is killed
   ```bash
   pkill -f "briefcase dev"
   pkill -f "fichero"
   ```

2. **Clean build:**
   ```bash
   briefcase clean
   briefcase dev
   ```

3. **Verify code changes saved:**
   ```bash
   grep "get_item_catalogue_data" src/fichero/library/library_manager.py
   # Should show the method (British spelling)
   ```
