# NSTabView Migration Proposal

## Current State

The tabs system uses ~1000 lines of custom code:
- `tabs.py` (458 lines) - Custom TabBar with NSSegmentedControl
- `tab_controller.py` (582 lines) - Custom state management

## Problems

### 1. Reinvents Native Components
Apple provides `NSTabView` and `NSTabViewController` that handle:
- Tab UI rendering
- Keyboard navigation (Cmd+1, Cmd+2, arrow keys)
- Tab reordering via drag
- Accessibility
- Memory management

### 2. Code Smells
- Manual dataclass reconstruction instead of `dataclasses.replace()`
- Direct manipulation of private callbacks (`_tab_bar._on_select = ...`)
- Memory leak in item cache (never cleaned)

### 3. Missing Features
Current custom implementation lacks:
- Tab drag-drop reordering
- Native animations
- Proper keyboard shortcuts

## Proposed Solution

Replace with `NSTabViewController`:

```python
"""Native Tab System using NSTabViewController."""
from rubicon.objc import ObjCClass, objc_method, objc_property

NSTabViewController = ObjCClass("NSTabViewController")
NSTabViewItem = ObjCClass("NSTabViewItem")
NSViewController = ObjCClass("NSViewController")

class NativeTabController:
    """Mail/Safari-style tabs using NSTabViewController."""

    def __init__(self, on_select=None):
        self._on_select = on_select
        self._tab_vc = NSTabViewController.alloc().init()

        # Safari-style (tabs in toolbar)
        self._tab_vc.tabStyle = 2  # NSTabViewControllerTabStyleToolbar

    @property
    def native(self):
        return self._tab_vc

    def add_tab(self, title: str, view_controller, identifier: str = None):
        """Add a tab with content."""
        item = NSTabViewItem.alloc().initWithIdentifier_(identifier or title)
        item.label = title
        item.viewController = view_controller
        self._tab_vc.addTabViewItem_(item)

    def remove_tab(self, identifier: str):
        """Remove tab by identifier."""
        for i in range(self._tab_vc.tabViewItems.count):
            item = self._tab_vc.tabViewItems[i]
            if str(item.identifier) == identifier:
                self._tab_vc.removeTabViewItem_(item)
                break

    def select_tab(self, identifier: str):
        """Select tab by identifier."""
        for i in range(self._tab_vc.tabViewItems.count):
            item = self._tab_vc.tabViewItems[i]
            if str(item.identifier) == identifier:
                self._tab_vc.selectedTabViewItemIndex = i
                break

    @property
    def selected_identifier(self) -> str | None:
        """Currently selected tab identifier."""
        item = self._tab_vc.tabView.selectedTabViewItem
        return str(item.identifier) if item else None
```

## NSTabViewControllerTabStyle Options

| Style | Value | Description |
|-------|-------|-------------|
| Automatic | 0 | System decides |
| SegmentedControlOnTop | 1 | Tabs above content |
| **Toolbar** | 2 | Safari-style (tabs in toolbar) |
| UnspecifiedUnspecified | 3 | No visible tabs |

## Benefits of Migration

1. **Less code**: ~1000 lines → ~200 lines
2. **Native behavior**: Keyboard shortcuts, accessibility, drag-drop
3. **Consistent UX**: Matches Mail.app, Safari, Finder
4. **Maintenance**: Apple handles edge cases

## Migration Steps

1. Create `native_tabs.py` with NSTabViewController wrapper
2. Each tab content is an `NSViewController` wrapping our views
3. Replace window.py tab_bar usage
4. Delete old tabs.py and tab_controller.py
5. Update tests

## Alternative: Keep Current with Fixes

If migration is too much work, fix the current code:

```python
# tabs.py:374 - Use dataclasses.replace()
from dataclasses import replace
def update_tab(self, tab_id: str, **kwargs) -> None:
    for i, tab in enumerate(self._tabs):
        if tab.id == tab_id:
            valid_fields = {k: v for k, v in kwargs.items()
                          if hasattr(tab, k) and v is not None}
            self._tabs[i] = replace(tab, **valid_fields)
            self._update_segments()
            return

# tab_controller.py:171 - Use public API
class TabBar:
    def set_callbacks(self, on_select=None, on_close=None):
        self._on_select = on_select
        self._on_close = on_close

# tab_controller.py:168 - Add cache cleanup
def _cleanup_cache(self):
    """Remove items not referenced by any tab."""
    used_ids = {state.item_id for state in self._states.values()}
    used_ids.update(id for state in self._states.values()
                    for id in state.browser_doc_ids)
    self._items = {k: v for k, v in self._items.items() if k in used_ids}
```

## Recommendation

For a proper Mail/Safari-style app: **Migrate to NSTabViewController**

The native component handles everything correctly and reduces maintenance burden.
