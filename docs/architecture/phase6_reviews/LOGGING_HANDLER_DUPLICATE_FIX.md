# Logging Handler Duplicate Fix

**Date:** November 16, 2025
**Issue:** Duplicate log entries appearing throughout application
**Root Cause:** Multiple logging handlers added without clearing existing ones
**Status:** ✅ FIXED

## Problem

Every log entry appeared twice during application startup:

```
INFO:fichero.core.app_initializer:📁 File logging configured: /Users/dtubb/Library/Application Support/ca.tubb.fichero/logs/fichero_20251116_093222.log
INFO:fichero.core.app_initializer:📁 File logging configured: /Users/dtubb/Library/Application Support/ca.tubb.fichero/logs/fichero_20251116_093222.log
INFO:fichero.core.app_initializer:📝 GUI logging configured at INFO level
INFO:fichero.core.app_initializer:📝 GUI logging configured at INFO level
```

## Root Cause

In `src/fichero/core/app_initializer.py`, the `_setup_file_logging()` method was adding new handlers to the root logger without first removing existing handlers.

**Flow:**
1. Python's root logger starts with default handlers (or handlers from previous setup)
2. `_setup_file_logging()` creates file_handler and console_handler
3. Adds them to root logger WITHOUT clearing existing handlers
4. Result: Root logger has BOTH old and new handlers
5. Each log message gets processed by MULTIPLE handlers → duplicate output

**Code Before Fix (lines 213-230):**
```python
def _setup_file_logging(self, log_level=logging.INFO):
    # ... create log file path ...

    # Create handlers
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(log_level)
    file_handler.setFormatter(...)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(...)

    # Store handlers for cleanup
    self.log_handlers = [file_handler, console_handler]

    # Configure logging
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(file_handler)      # ❌ Doesn't clear existing!
    root_logger.addHandler(console_handler)   # ❌ Adds on top of old handlers!
```

## Solution

Clear all existing handlers BEFORE adding new ones:

**Code After Fix (lines 213-237):**
```python
def _setup_file_logging(self, log_level=logging.INFO):
    # ... create log file path ...

    # Get root logger and clear any existing handlers to prevent duplicates
    root_logger = logging.getLogger()

    # Remove all existing handlers
    for handler in root_logger.handlers[:]:
        handler.close()
        root_logger.removeHandler(handler)

    # Create handlers explicitly so we can track them for cleanup
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(log_level)
    file_handler.setFormatter(...)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(...)

    # Store handlers for cleanup
    self.log_handlers = [file_handler, console_handler]

    # Configure logging
    root_logger.setLevel(log_level)
    root_logger.addHandler(file_handler)      # ✅ Now clean slate
    root_logger.addHandler(console_handler)   # ✅ Only our handlers
```

**Key Changes:**
1. Get root logger reference FIRST
2. Iterate over existing handlers (using `handlers[:]` to avoid mutation during iteration)
3. Close each handler properly
4. Remove each handler from root logger
5. THEN add our new handlers

## Testing

### Before Fix
```
INFO:fichero.core.app_initializer:📁 File logging configured: /Users/dtubb/.../fichero_20251116_093222.log
INFO:fichero.core.app_initializer:📁 File logging configured: /Users/dtubb/.../fichero_20251116_093222.log
INFO:fichero.core.app_initializer:📝 GUI logging configured at INFO level
INFO:fichero.core.app_initializer:📝 GUI logging configured at INFO level
INFO:fichero.config.core.settings_manager:App paths: data=/Users/dtubb/Library/Application Support/ca.tubb.fichero, app=/Users/dtubb/code/fichero_main/fichero/src/fichero, config=/Users/dtubb/Library/Preferences/ca.tubb.fichero
INFO:fichero.config.core.settings_manager:App paths: data=/Users/dtubb/Library/Application Support/ca.tubb.fichero, app=/Users/dtubb/code/fichero_main/fichero/src/fichero, config=/Users/dtubb/Library/Preferences/ca.tubb.fichero
```

Every line appeared TWICE.

### After Fix
```
INFO:fichero.core.app_initializer:📁 File logging configured: /Users/dtubb/Library/Application Support/ca.tubb.fichero/logs/fichero_20251116_093252.log
INFO:fichero.core.app_initializer:📝 GUI logging configured at INFO level
INFO:fichero.core.app_initializer:📋 App preferences initialized
INFO:fichero.config.core.settings_manager:App paths: data=/Users/dtubb/Library/Application Support/ca.tubb.fichero, app=/Users/dtubb/code/fichero_main/fichero/src/fichero, config=/Users/dtubb/Library/Preferences/ca.tubb.fichero
INFO:fichero.config.core.settings_manager:User settings path: /Users/dtubb/Library/Application Support/ca.tubb.fichero/settings/settings.yml
INFO:fichero.config.core.settings_manager:Looking for user settings at: /Users/dtubb/Library/Application Support/ca.tubb.fichero/settings/settings.yml
```

Each line appears ONCE. ✅

## Why This Happened

### Python Logging Handler Accumulation

Python's logging module maintains a **global root logger** that persists across module reloads and re-initialization:

1. **First initialization:** Root logger has 0 handlers
2. **After first `_setup_file_logging()`:** Root logger has 2 handlers (file + console)
3. **If called again (hot reload, testing, etc.):** Root logger NOW has 4 handlers (2 old + 2 new)
4. **Each message:** Processed by ALL 4 handlers → duplicates

**This is a common Python logging pitfall!**

### Why `force=True` Wasn't Enough

The `_setup_logging()` method (line 188) uses:
```python
logging.basicConfig(..., force=True)
```

But this only applies to the development path (line 185). For GUI apps (line 182), we call `_setup_file_logging()` directly, which BYPASSES `basicConfig()`.

**Solution:** Manually clear handlers in `_setup_file_logging()`.

## Related Fixes

This fix completes the duplicate log elimination work:

1. **Session Nov 15:** Fixed duplicate logs in LibraryView.show() (DUPLICATE_LOGS_FIX.md)
2. **Session Nov 15:** Fixed duplicate event subscriptions (COLLECTION_DELETE_EVENT_DEDUPLICATION.md)
3. **Session Nov 16:** Fixed logging handler accumulation (THIS FIX)

All three sources of duplicate logs are now resolved.

## Files Modified

- `src/fichero/core/app_initializer.py` (lines 213-237)

## Impact

**Before:**
- ❌ Every log appeared 2x (or more with multiple app restarts)
- ❌ Log files bloated with duplicates
- ❌ Confusing debugging experience
- ❌ Performance impact (2x log I/O)

**After:**
- ✅ Each log appears exactly once
- ✅ Clean log files
- ✅ Clear debugging output
- ✅ 50% reduction in log I/O

## Best Practices

### For Logging Setup

**DO:**
```python
# Clear existing handlers first
root_logger = logging.getLogger()
for handler in root_logger.handlers[:]:
    handler.close()
    root_logger.removeHandler(handler)

# Then add your handlers
root_logger.addHandler(new_handler)
```

**DON'T:**
```python
# Just blindly add handlers
root_logger = logging.getLogger()
root_logger.addHandler(new_handler)  # ❌ Accumulates!
```

### For Handler Cleanup

**DO:**
```python
# Track handlers for cleanup
self.log_handlers = [file_handler, console_handler]

# Clean up on shutdown
for handler in self.log_handlers:
    handler.close()
    logging.getLogger().removeHandler(handler)
```

**DON'T:**
```python
# Leave handlers dangling
# (causes ResourceWarning on exit)
```

## Conclusion

Duplicate logs are now completely eliminated by properly clearing existing logging handlers before adding new ones. This is a fundamental Python logging best practice that prevents handler accumulation.

**Status:** ✅ COMPLETE - No more duplicate logs

**Related Documents:**
- DUPLICATE_LOGS_FIX.md (LibraryView.show() fix)
- PHASE1_EMERGENCY_FIXES_COMPLETE.md (Complete Phase 1 summary)
- SESSION_SUMMARY_NOV15.md (Previous session summary)
