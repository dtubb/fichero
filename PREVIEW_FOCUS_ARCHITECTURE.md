# Preview System Focus Architecture

## IMPORTANT: There Are TWO Focus Systems!

### Focus System 1: Main Window Column Focus (UniversalLayoutManager)
**Location:** `shared/navigation/layout_manager.py`
**What it focuses:** Which COLUMN in the main 5-column layout (Library, Collection, Preview, Adjust)
**Visual indicator:** **Light blue background (`#E3F2FD`)** around entire column
**THIS IS WHAT YOU'RE SEEING IN THE SCREENSHOT** ← The blue around entire preview area

### Focus System 2: OutputPane Focus (Within Preview)
**Location:** `windows/main/views/preview/output_pane.py`
**What it focuses:** Which PANE within the Preview column (when split)
**Visual indicator:** **Dark blue border (`rgb(0, 122, 204)`)** around individual pane
**This is what we just built** ← Should appear when you split panes

---

# Preview System Focus Architecture

## Current Implementation (What We Built)

```
PreviewView (preview_view.py)
│
├── content_area (Box - horizontal)
│   │
│   ├── LayoutManager.get_container() ← Returns ScrollContainer
│   │   │
│   │   └── _columns_container (Box - horizontal)
│   │       │
│   │       ├── ColumnContainer 1
│   │       │   └── column.container (Box - vertical)
│   │       │       ├── OutputPane 1
│   │       │       │   ├── _outer_box ← FOCUS BORDER SHOULD BE HERE
│   │       │       │   └── _container
│   │       │       │       ├── _webview
│   │       │       │       └── PathBar
│   │       │       │
│   │       │       └── OutputPane 2 (if split vertically)
│   │       │           ├── _outer_box ← FOCUS BORDER SHOULD BE HERE
│   │       │           └── _container
│   │       │
│   │       └── ColumnContainer 2 (if split horizontally)
│   │           └── column.container (Box - vertical)
│   │               └── OutputPane 3
│   │                   ├── _outer_box ← FOCUS BORDER SHOULD BE HERE
│   │                   └── _container
│   │
│   └── inspector_panel (if shown)
│
└── StatusBar
```

## What You're Seeing (Problem)

**Blue border around entire preview area** suggests:
- Focus border is being applied to `content_area` or `LayoutManager.get_container()`
- NOT being applied to individual `OutputPane._outer_box`

## Expected Behavior (How It Should Work)

### When Single Pane:
```
┌─────────────────────────────────────┐
│ PreviewView                         │
│ ┌─────────────────────────────────┐ │
│ │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │ │
│ │ ▓ OutputPane 1 (FOCUSED)      ▓ │ │ ← Blue border (3px)
│ │ ▓ ┌─────────────────────────┐ ▓ │ │
│ │ ▓ │ WebView                 │ ▓ │ │
│ │ ▓ │ [Image content]         │ ▓ │ │
│ │ ▓ └─────────────────────────┘ ▓ │ │
│ │ ▓ PathBar: Collection › Item  ▓ │ │
│ │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │ │
│ └─────────────────────────────────┘ │
│ Status: Column 1/1 • Pane 1/1       │
└─────────────────────────────────────┘
```

### When Split (2 columns):
```
┌─────────────────────────────────────────────────┐
│ PreviewView                                     │
│ ┌──────────────────┬──────────────────────────┐ │
│ │ OutputPane 1     │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │ │
│ │ [Image 1]        │ ▓ OutputPane 2 (FOCUS) ▓ │ │ ← Blue border only on Pane 2
│ │                  │ ▓ ┌──────────────────┐ ▓ │ │
│ │                  │ ▓ │ WebView          │ ▓ │ │
│ │                  │ ▓ │ [Image 2]        │ ▓ │ │
│ │                  │ ▓ └──────────────────┘ ▓ │ │
│ │ PathBar: Item 1  │ ▓ PathBar: Item 2      ▓ │ │
│ │                  │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │ │
│ └──────────────────┴──────────────────────────┘ │
│ Status: Column 2/2 • Pane 1/1                   │
└─────────────────────────────────────────────────┘
```

## Focus System Components

### 1. OutputPane._outer_box (output_pane.py:124-127)
```python
self._outer_box = toga.Box(
    style=Pack(direction='column', flex=1)
)
self._outer_box.add(self._container)
```
**This is where focus border SHOULD appear**

### 2. OutputPane.set_focused() (output_pane.py:645-675)
```python
if is_focused:
    self._outer_box.style.background_color = rgb(0, 122, 204)  # Blue
    self._container.style.padding = 3  # Creates border effect
    self._container.style.background_color = rgb(255, 255, 255)  # White
```
**This is what SHOULD create the blue border**

### 3. LayoutManager._update_all_focus_indicators() (layout_manager.py:701-722)
```python
for col_idx, column in enumerate(self.columns):
    for pane_idx, pane in enumerate(column.panes):
        is_focused = (col_idx == self.focused_column_index and
                     pane_idx == self.focused_pane_index)
        pane.set_focused(is_focused)  # ← Calls OutputPane.set_focused()
```
**This SHOULD update all panes, focusing only one**

## Possible Problems

### Problem 1: OutputPane.as_box() Returns Wrong Container

Check `output_pane.py` - what does `as_box()` return?

**If it returns `_outer_box`:** ✅ Correct - focus border will show
**If it returns `_container`:** ❌ Wrong - focus border won't show

### Problem 2: ColumnContainer Not Using OutputPane._outer_box

Check `layout_manager.py` - how are panes added to columns?

```python
# ColumnContainer.rebuild_layout() (layout_manager.py:45-67)
for pane in self.panes:
    pane_box = pane.as_box()  # ← What does this return?
    self.container.add(pane_box)
```

### Problem 3: Focus Being Set on Wrong Element

The blue border you see around the ENTIRE preview area suggests:
- `set_focused()` might be called on PreviewView.content_area
- OR the focus border is being set at LayoutManager level
- NOT at individual OutputPane level

## Debug Steps

### 1. Check what `as_box()` returns:
```python
# In output_pane.py - search for "def as_box"
def as_box(self):
    return self._outer_box  # ✅ Should be this
    # return self._container  # ❌ NOT this
```

### 2. Add logging to see which element gets focus:
```python
# In output_pane.py set_focused()
def set_focused(self, is_focused: bool):
    if is_focused:
        self.logger.info(f"✨ Setting focus on OutputPane {id(self)}")
        self.logger.info(f"   _outer_box: {id(self._outer_box)}")
        self.logger.info(f"   _container: {id(self._container)}")
```

### 3. Check column layout:
```python
# In layout_manager.py ColumnContainer.rebuild_layout()
for pane in self.panes:
    pane_box = pane.as_box()
    logger.info(f"Adding pane_box {id(pane_box)} to column")
    self.container.add(pane_box)
```

## Expected Fix

**Most likely issue:** `OutputPane.as_box()` is returning the wrong container.

**Should return:** `_outer_box` (which has the focus border)
**Currently returns:** Possibly `_container` or `content_area`

Check `output_pane.py` around line 550-600 for the `as_box()` method definition.
