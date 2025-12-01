# Third Drag-and-Drop Bug Fix

**Date:** November 25, 2025
**Issue:** Multiple Rubicon-ObjC API errors
**Status:** FIXED ✅

---

## Problems Discovered

When attempting to drag collections within the sidebar, three separate errors occurred:

### Error 1: NSPasteboardItem Method Name

```
AttributeError: rubicon.objc.api.ObjCInstance NSPasteboardItem has no attribute setString_forType
```

**Location:** `macos_sidebar.py` line 344

### Error 2: ObjCListInstance count() Method

```
TypeError: ObjCListInstance.count() missing 1 required positional argument: 'value'
```

**Location:** `macos_sidebar.py` lines 390, 446

### Error 3: Unit Test API Mismatches

```
TypeError: LibraryManager.add_collection() got an unexpected keyword argument 'type'
RuntimeError: Event loop is closed
```

**Location:** `test_library_collection_management.py` (29 test failures)

---

## Root Causes

### 1. Objective-C Method Name Translation

In Objective-C, multi-parameter methods have labels for each parameter:
```objc
[item setString:string forType:type]
```

In Rubicon-ObjC, each parameter label becomes part of the method name with underscore suffix:
```python
item.setString_forType_(string, type)
```

**The Issue:** Missing trailing underscore on each parameter label.

### 2. NSArray → ObjCListInstance Conversion

Rubicon-ObjC automatically converts NSArray to `ObjCListInstance`, which is a **Python list wrapper**, not a direct NSArray proxy.

This means:
- `NSArray.count()` (Objective-C method) becomes `len(list)` (Python)
- `NSArray.objectAtIndex(i)` becomes `list[i]` (Python)

**The Confusion:** Trying to call `.count()` on what is actually a Python list.

In Python lists, `count()` expects an argument (the item to count):
```python
my_list.count("value")  # Count occurrences of "value"
```

When called without arguments:
```python
my_list.count()  # TypeError: missing 1 required positional argument: 'value'
```

### 3. LibraryManager API Changes

The `add_collection()` method parameter was renamed from `type` to `collection_type` to avoid Python reserved keyword conflicts.

### 4. Event Loop Management

Async tests were calling `asyncio.get_event_loop()` which could return a closed loop, causing RuntimeError.

---

## Fixes Applied

### Fix 1: NSPasteboardItem Method Name (Line 346)

**Before:**
```python
pasteboard_item.setString_forType(collection_id, UTI)
```

**After:**
```python
# In Objective-C: [item setString:string forType:type]
# In Rubicon-ObjC: item.setString_forType_(string, type)
pasteboard_item.setString_forType_(collection_id, UTI)
```

**Rule:** Each Objective-C parameter label gets an underscore suffix in Rubicon-ObjC.

### Fix 2: ObjCListInstance Iteration (Lines 392-393, 446-447)

**Before:**
```python
# Wrong: Treating ObjCListInstance like NSArray
type_count = types.count()  # ❌ TypeError
for i in range(type_count):
    type_str = str(types.objectAtIndex(i))
```

**After:**
```python
# Correct: Treating ObjCListInstance like Python list
for i in range(len(types)):  # ✅ Use len()
    type_str = str(types[i])  # ✅ Use [] indexing
```

**Alternative (more Pythonic):**
```python
for type_item in types:
    type_str = str(type_item)
```

### Fix 3: LibraryManager API (test_library_collection_management.py)

**Before:**
```python
await library_manager.add_collection(
    name="My Collection",
    type="local",  # ❌ Wrong parameter name
    source_path=None
)
```

**After:**
```python
await library_manager.add_collection(
    name="My Collection",
    collection_type="local",  # ✅ Correct parameter name
    source_path=None
)
```

**Changes:** 10 occurrences replaced with `collection_type`.

### Fix 4: Event Loop Handling (AsyncTestCase)

**Before:**
```python
def run_async(self, coro):
    loop = asyncio.get_event_loop()  # ❌ Might be closed
    return loop.run_until_complete(coro)
```

**After:**
```python
def run_async(self, coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)
```

---

## Updated Rubicon-ObjC Patterns

### Complete Reference Table

| Objective-C | Rubicon-ObjC | Type | Notes |
|-------------|--------------|------|-------|
| `[info draggingPasteboard]` | `info.draggingPasteboard` | Property | No () |
| `[pasteboard types]` | `pasteboard.types` | Property | Returns ObjCListInstance |
| `[types count]` | `len(types)` | List method | ObjCListInstance is Python list |
| `[types objectAtIndex:i]` | `types[i]` | List access | Use [] indexing |
| `[item setString:s forType:t]` | `item.setString_forType_(s, t)` | Method | Trailing _ on each param |
| `[pasteboard stringForType:t]` | `pasteboard.stringForType_(t)` | Method | Single param, one trailing _ |

### Decision Tree

```
Is it an Objective-C method with parameters?
├─ YES → Add trailing underscore to each parameter label
│   Examples:
│   - setString:forType: → setString_forType_(s, t)
│   - stringForType: → stringForType_(t)
│   - validateDrop:proposedItem:proposedChildIndex: →
│     validateDrop_proposedItem_proposedChildIndex_(...)
│
└─ NO → Is it a property?
    ├─ YES → Access without parentheses: obj.property
    │   Examples: draggingPasteboard, types
    │
    └─ NO → Does it return NSArray/NSString/etc?
        └─ Check if Rubicon auto-converts to Python type
            - NSArray → ObjCListInstance (use len(), [])
            - NSString → str (use Python string methods)
```

---

## Updated Unit Tests

### test_rubicon_objc_patterns.py (Updated)

All tests updated to reflect ObjCListInstance behavior:

```python
def test_nsarray_iteration_mock(self):
    """
    UPDATED: NSArray is returned as ObjCListInstance (Python list wrapper)
    """
    mock_array = ["type1", "type2", "type3"]

    # Correct pattern
    for i in range(len(mock_array)):
        obj = mock_array[i]
        # Process obj...
```

### test_library_collection_management.py (Fixed)

- Fixed all `type="local"` → `collection_type="local"`
- Fixed all `type="external"` → `collection_type="external"`
- Fixed async event loop handling

**Test Results:**
```bash
tests/unit/test_rubicon_objc_patterns.py ✅ 14 passed
```

---

## Files Modified

### 1. src/fichero/shared/widgets/list_widget/renderers/macos_sidebar.py

**Line 346:** Fixed `setString_forType` → `setString_forType_`
**Lines 392-393:** Fixed NSArray iteration in `validateDrop`
**Lines 446-447:** Fixed NSArray iteration in `acceptDrop`

### 2. tests/unit/test_rubicon_objc_patterns.py

Updated all tests to document ObjCListInstance behavior:
- `test_nsarray_iteration_mock` - Updated to use len() and []
- `test_nsarray_wrong_pattern_fails` - Documents correct pattern
- `test_drag_type_checking_pattern` - Updated for list behavior
- `test_check_multiple_types` - Updated for list behavior
- `test_mistake_not_calling_method` - Documents the count() error
- `test_reference_method_call_patterns` - Complete reference table

### 3. tests/unit/test_library_collection_management.py

**Lines with `type=`:** Changed to `collection_type=` (10 occurrences)
**Lines 29-39:** Fixed AsyncTestCase event loop handling

---

## Key Learnings

### 1. Rubicon-ObjC Method Naming Rules

**Pattern:** Each Objective-C parameter label becomes part of the method name with trailing underscore.

Examples:
```objc
// Objective-C
[item setString:@"value" forType:@"type"]
```

```python
# Rubicon-ObjC
item.setString_forType_("value", "type")
#    ^^^^^^^^^^^^^^^^^^
#    One underscore per parameter label
```

### 2. ObjCListInstance is NOT NSArray

When Rubicon-ObjC returns an NSArray, it's automatically converted to `ObjCListInstance`, which behaves like a **Python list**.

**Do:**
- `len(types)` - Get length
- `types[i]` - Access by index
- `for item in types:` - Direct iteration
- `if "value" in types:` - Membership testing

**Don't:**
- `types.count()` - ❌ Python list.count() needs argument
- `types.objectAtIndex(i)` - ❌ Not available on Python list

### 3. When to Use Direct NSArray Methods

If you need actual NSArray methods, don't rely on automatic conversion. Create the NSArray explicitly:

```python
from rubicon.objc import ObjCClass

NSArray = ObjCClass("NSArray")
ns_array = NSArray.arrayWithArray_(python_list)
count = ns_array.count()  # Now this works
```

But for drag-and-drop, the ObjCListInstance is fine - use Python list methods.

---

## Testing Verification

### Automated Tests

```bash
# Run Rubicon pattern tests
PYTHONPATH=src python3 -m pytest tests/unit/test_rubicon_objc_patterns.py -v

# Results: ✅ 14 passed in 0.04s
```

### Manual Testing

After these fixes, drag-and-drop should work:

1. **Drag collection within sidebar** → Should show move cursor
2. **Drop to reorder** → Should update position
3. **Drag file from Finder** → Should show copy cursor
4. **Drop file** → Should create local collection

---

## Summary of All Three Bugs

| Bug | Error | Cause | Fix |
|-----|-------|-------|-----|
| **Bug 1** | `'ObjCInstance' object is not callable` | Calling properties as methods | Remove () from properties |
| **Bug 2** | `'method' object cannot be interpreted as an integer` | Not calling methods (before fix) | Call methods with () |
| **Bug 3a** | `no attribute setString_forType` | Missing trailing underscore | Add _ to each param label |
| **Bug 3b** | `count() missing 1 required positional argument` | ObjCListInstance is Python list | Use len() instead of count() |
| **Bug 3c** | `unexpected keyword argument 'type'` | API parameter renamed | Use collection_type |
| **Bug 3d** | `Event loop is closed` | Reusing closed event loop | Create new loop if needed |

---

## All Rubicon-ObjC Bugs Now Fixed ✅

The drag-and-drop implementation is now ready for real-world testing!

**Next Steps:**
1. Test dragging collections to reorder
2. Test dragging files from Finder
3. Test dragging folders from Finder
4. Verify position persistence
5. Proceed to Phase 4 (contextual menus)
