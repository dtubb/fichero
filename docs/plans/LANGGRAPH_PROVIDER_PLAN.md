# Fichero LangGraph + Provider Integration Plan

## Current Status (2025-12-11)

### Completed

| Component | Status | Notes |
|-----------|--------|-------|
| Views folder structure | ✅ Done | `views/library/`, `views/workflow/`, `views/search/` |
| LibraryEditor | ✅ Done | Moved from `editor.py`, working |
| LibraryInspector | ✅ Done | Moved from `inspector.py`, showing |
| WorkflowEditor | ✅ Placeholder | Basic NSView container |
| WorkflowInspector | ✅ Placeholder | Provider/Model dropdowns (not connected) |
| SearchEditor | ✅ Placeholder | Basic NSView container |
| SearchInspector | ✅ Placeholder | Query/Results fields |
| ProviderSheet | ✅ Done | Mac Mail-style flow (not tested) |
| View switching logic | ✅ Done | `window.py` has `switch_view()` |
| Deprecation shims | ✅ Done | Old imports still work |

### UI Issues to Fix

From screenshot review (2025-12-11 6:48 AM):

| Issue | Description | Reference |
|-------|-------------|-----------|
| **Sidebar: Remove TOOLS/PROVIDERS** | These sections shouldn't be in sidebar | Fichero screenshot |
| **Sidebar: Auto-expand SEARCHES/WORKFLOWS** | Should be expanded by default | - |
| **Sidebar: Width too narrow** | Doesn't fill allocated space | Fichero screenshot |
| **Sidebar: Font too large** | Text is bigger than standard macOS | Mail screenshot |
| **Sidebar: Folder icons should be outlines** | Currently filled, should be line art | Mail screenshot |
| **Sidebar: Add toggle button** | Like Mail's sidebar toggle in toolbar | Mail screenshot |
| **Toolbar: Floating/no background** | May be "glass" style issue | Fichero screenshot |
| **Toolbar: Position wrong** | Should be above browser, not floating | Finder screenshot |
| **Inspector: White text above it** | Stray text element | Fichero screenshot |
| **Inspector: Wrong background** | Should be white like Finder preview | Finder screenshot |
| **Inspector: Add top button** | Like Finder's preview pane | Finder screenshot |

### Architecture Reference

```
Current file structure:
src/fichero/app/main_window/
├── views/
│   ├── library/          ← Working
│   │   ├── editor.py
│   │   ├── inspector.py
│   │   └── viewers/
│   ├── workflow/         ← Placeholder
│   │   ├── editor.py
│   │   └── inspector.py
│   └── search/           ← Placeholder
│       ├── editor.py
│       └── inspector.py
├── sheets/
│   └── provider_sheet.py ← Done (untested)
├── window.py             ← Has view switching
├── sidebar.py            ← Needs UI fixes
├── browser.py
├── toolbar.py            ← Needs positioning fix
└── menu.py
```

---

## Design Philosophy

**Core Principles:**

1. **Pythonic** - Simple, readable code. No Java-style abstractions.
2. **Easy to edit** - Anyone can jump in and modify
3. **Open source friendly** - Clear, commented, no magic
4. **Data-centric** - Pydantic models ↔ DuckDB, that's it
5. **No over-engineering** - No managers, coordinators, factories, registries
6. **Use the platform** - Let macOS do the work (system fonts, KVO, etc.)

**What we avoid:**
- `AbstractBaseManagerFactory` style classes
- Deep inheritance hierarchies
- Dependency injection frameworks
- Complex state machines
- Anything that makes you read 5 files to understand one feature

**What we embrace:**
- Functions over classes when possible
- Dataclasses for structured data
- Simple callbacks (`on_select`, `on_change`)
- Direct database calls: `db.save(doc)`, `db.get(Document, id)`
- System-provided behaviors (accessibility, theming, etc.)

**Font Example - Let macOS Handle It:**
```python
# ❌ Hardcoded - ignores user accessibility settings
tf.font = NSFont.systemFontOfSize_(13)

# ✓ System-aware - respects user's accessibility text size
tf.font = NSFont.systemFontOfSize_(NSFont.smallSystemFontSize)

# ✓ Even better - use text styles (macOS 11+)
NSFontTextStyle = ObjCClass("NSFontTextStyle")  # Not needed, use string
tf.font = NSFont.preferredFontForTextStyle_("subheadline")
```

The system font sizes automatically scale with user's accessibility settings.

---

## Code Review (2025-12-11)

### Architecture Summary

The app uses a clean 4-layer architecture:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  GUI Layer (Cocoa/rubicon-objc)                                         │
│  toolbar.py, sidebar_native.py, browser.py, views/library/inspector.py  │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼─────────────────────────────────────┐
│  Window Controller (window.py)                                          │
│  - MainWindowController orchestrates all panes                          │
│  - NSSplitViewController for native 4-pane layout                       │
│  - View switching: library/workflow/search modes                        │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼─────────────────────────────────────┐
│  Data Layer (Pydantic + DuckDB)                                         │
│  models.py: Document, Artifact, Workflow, Provider, etc.                │
│  db.py: Database class wrapping DuckDB + LanceDB                        │
│  keychain.py: macOS Keychain for API keys                               │
└─────────────────────────────────────────────────────────────────────────┘
```

### What's Working Well

**1. Pythonic Data Layer (db.py + models.py)**
- Clean CRUD API: `db.save()`, `db.get()`, `db.query()`, `db.delete()`
- Automatic table creation from Pydantic models
- JSON serialization for dict/list/tuple fields
- LanceDB integration for vector embeddings
- Type-safe with generics: `db.get(Document, id)` returns `Document | None`

**2. KVO Integration (sidebar_native.py)**
- Proper NSTreeController binding for sidebar data
- KVO observer for selection changes (`_SelectionObserver`)
- Clean cleanup in `__del__` to remove observers
- Excellent documentation explaining KVO for Python developers

**3. Declarative UI (toolbar.py)**
- Dataclass-based toolbar definition (`Button`, `Dropdown`, `Search`)
- Match statement for clean item building
- SF Symbol integration with proper configuration
- Built-in macOS items used correctly (`TOGGLE_SIDEBAR`, `SIDEBAR_SEPARATOR`)

**4. View Components (browser.py, inspector.py)**
- Pure view components - receive data, don't query database
- Clean separation: Browser shows Documents, Inspector shows metadata
- Proper delegate patterns for callbacks

### Issues Found

**1. Sidebar: TOOLS/PROVIDERS Sections (sidebar_native.py:363-369)**
```python
# This builds all 5 sections but user only wants 3:
return [
    _build_library_section(),
    _build_searches_section(),
    _build_workflows_section(),
    _build_tools_section(),      # ❌ Remove
    _build_providers_section(),  # ❌ Remove (providers go in Inspector)
]
```
**Fix:** Remove `_build_tools_section()` and `_build_providers_section()` from `build_sidebar_tree()`.

**2. Sidebar: IDs Have Prefixes (sidebar_native.py:394, etc.)**
```python
document_id=f"doc:{doc.id}",     # Returns "doc:abc123"
document_id=f"search:{search.id}",
document_id=f"workflow:{wf.id}",
```
But `window.py:297-313` calls `db.get(Document, document_id)` expecting raw IDs.
**Fix:** Either strip prefixes in `_on_sidebar_select()` or don't add them in tree building.

**3. Sidebar: Font Size (sidebar_native.py:614)**
```python
tf.font = NSFont.systemFontOfSize_(13)  # Standard size
```
Should be smaller for Mail-style sidebar:
```python
tf.font = NSFont.systemFontOfSize_(11)  # Smaller like Mail
```

**4. Sidebar: Filled Icons (sidebar_native.py:209)**
```python
ICON_FOR_DOC_TYPE = {
    "collection": "folder.fill",  # ❌ filled
    "folder": "folder",           # ✓ outline
    ...
}
```
**Fix:** Use outline icons consistently: `folder` not `folder.fill`.

**5. Inspector: Background Color (views/library/inspector.py:149)**
```python
self._scroll.backgroundColor = NSColor.windowBackgroundColor
```
Should be white like Finder's preview pane:
```python
self._scroll.backgroundColor = NSColor.whiteColor  # Or controlBackgroundColor
```

**6. Toolbar: Position/Background**
The toolbar is attached correctly but may need window style adjustments for proper background appearance. The "glass" effect may be from `titlebarAppearsTransparent = True` in window.py:125.

**7. Unused Section Colors (sidebar_native.py:195-201)**
```python
SECTION_COLORS = {
    "LIBRARY": (0.0, 0.478, 1.0, 1.0),
    "SEARCHES": (0.96, 0.65, 0.14, 1.0),
    ...
}
```
These are defined but icons use template mode (accent color) by default. The color logic at line 627-640 only applies if `section` is set and in `SECTION_COLORS`.

### KVO System Explained

The sidebar uses Apple's **Key-Value Observing (KVO)** pattern:

```
NSTreeController.selectionIndexPaths  ──KVO──▶  _SelectionObserver.observeValue...()
                                                        │
                                                        ▼
                                                sidebar.on_select(doc_id)
                                                        │
                                                        ▼
                                                window._on_sidebar_select()
```

This is REQUIRED because NSTreeController has no delegate callback for selection changes. The implementation in `sidebar_native.py` is correct:

1. Observer created as ObjC object (required for KVO)
2. Registered with `addObserver_forKeyPath_options_context_`
3. Callback in `observeValueForKeyPath_ofObject_change_context_`
4. Cleanup in `__del__` with `removeObserver_forKeyPath_`

### Data Flow Summary

```
User clicks sidebar item
        │
        ▼
NSTreeController.selectionIndexPaths changes
        │
        ▼ (KVO notification)
_SelectionObserver.observeValueForKeyPath_...()
        │
        ▼
NativeSidebar.selected_document_id  ──▶  "doc:abc123"
        │
        ▼
on_select callback(document_id)
        │
        ▼
window._on_sidebar_select("doc:abc123")
        │
        ▼  (need to strip "doc:" prefix)
db.get(Document, "abc123")
        │
        ▼
db.query(Document, parent_id=doc.id)
        │
        ▼
browser.items = [child documents]
```

### Recommendations

1. **Remove TOOLS/PROVIDERS from sidebar** - Providers managed in Inspector workflow section
2. **Strip ID prefixes** in `_on_sidebar_select()` before calling `db.get()`
3. **Reduce sidebar font** from 13pt to 11pt
4. **Use outline icons** (`folder` not `folder.fill`)
5. **White inspector background** - match Finder preview pane
6. **Review toolbar window styling** - may need to adjust titlebar transparency

---

## Overview

Integrate LangGraph workflow execution with the new data layer (Pydantic models + DuckDB) and add Mac Mail-style provider setup flow.

**Key decisions made:**
- New LangGraph executor (not adapting old Director)
- Providers added via Inspector "Add Provider" button (NOT in Settings)
- Missing API key → Block with prompt dialog

---

## Architecture: 4-Pane Layout

From `UNIFIED_DATA_LAYER_PLAN.md`:

```
┌──────────┬─────────────────────┬──────────────────┬──────────┐
│ SIDEBAR  │      BROWSER        │      EDITOR      │INSPECTOR │
│          │                     │                  │          │
│ Library  │  Grid/List of       │  Preview image   │ Metadata │
│ - Docs   │  items from         │  (top half)      │ Tags     │
│ - Folders│  selected node      │                  │ Status   │
│          │                     │  Metadata form   │ Actions  │
│ Workflows│  + Search bar       │  (bottom half)   │ ─────────│
│ Searches │                     │                  │ WORKFLOW │
│          │                     │                  │ Provider │
│          │                     │                  │ Model    │
│          │                     │                  │[+Add]    │
└──────────┴─────────────────────┴──────────────────┴──────────┘
```

The **Inspector** (right pane) has a **Workflow section** where providers are managed.

---

## Data Layer (Already Done)

| File | Status |
|------|--------|
| `src/fichero/models.py` | ✅ Has Provider, Model, Workflow, Run, Artifact, Trace |
| `src/fichero/db.py` | ✅ Has CRUD: `db.save()`, `db.get()`, `db.query()` |
| `src/fichero/keychain.py` | ✅ Has `get_api_key()`, `set_api_key()`, `has_api_key()` |
| `src/fichero/storage.py` | ✅ Has thumbnail/display generation |
| `src/fichero/settings.py` | ✅ User preferences (NOT provider config) |

---

## Provider Setup Flow (Mac Mail-style)

### Location in UI

Providers are added from the **Inspector pane** (right side), in a **Workflow section**:

```
┌─────────────────────────────────────────┐
│ INSPECTOR                               │
├─────────────────────────────────────────┤
│ ▼ Metadata                              │
│   Name: letter_001.jpg                  │
│   Created: 2024-01-15                   │
│   Size: 2.4 MB                          │
│                                         │
│ ▼ Tags                                  │
│   [Archive] [Letters] [1920s]           │
│                                         │
│ ▼ Workflow                              │
│   ┌─────────────────────────────────┐   │
│   │ Provider: [DashScope ▾]         │   │
│   │ Model:    [Qwen VL Max ▾]       │   │
│   │                                 │   │
│   │ [+ Add Provider]                │   │
│   └─────────────────────────────────┘   │
│                                         │
│ ▼ Processing                            │
│   [▶ Run Workflow]                      │
│   Status: Ready                         │
└─────────────────────────────────────────┘
```

### Add Provider Flow

**Step 1: Choose Provider Type** (Sheet)

```
┌─────────────────────────────────────────────┐
│            Add AI Provider                   │
├─────────────────────────────────────────────┤
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │ 🔷 DashScope (Qwen)                │    │
│  │    Alibaba's Qwen VL models         │    │
│  └─────────────────────────────────────┘    │
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │ 🔷 OpenAI                           │    │
│  │    GPT-4 Vision, GPT-4o             │    │
│  └─────────────────────────────────────┘    │
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │ 🔷 Anthropic                        │    │
│  │    Claude 3 with vision             │    │
│  └─────────────────────────────────────┘    │
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │ 🔷 Ollama (Local)                   │    │
│  │    Run models locally               │    │
│  └─────────────────────────────────────┘    │
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │ 🔷 LM Studio (Local)                │    │
│  │    Local inference server           │    │
│  └─────────────────────────────────────┘    │
│                                             │
│  ─────────────────────────────────────────  │
│  Add Other Provider...                      │
│                                             │
├─────────────────────────────────────────────┤
│  [?]                          [Cancel]      │
└─────────────────────────────────────────────┘
```

**Step 2a: Cloud Provider Sign-In** (Sheet)

```
┌─────────────────────────────────────────────┐
│  ┌──────┐                                   │
│  │  🔷  │  Sign in to DashScope             │
│  └──────┘                                   │
│                                             │
│  Get an API key at:                         │
│  https://dashscope.console.aliyun.com       │
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │ API Key                             │    │
│  │ ●●●●●●●●●●●●●●●●                    │    │
│  └─────────────────────────────────────┘    │
│                                             │
│  ☑ Save in Keychain                         │
│                                             │
│                                             │
│                    [Cancel]    [Connect]    │
└─────────────────────────────────────────────┘
```

**Step 2b: Local Provider Setup** (Sheet)

```
┌─────────────────────────────────────────────┐
│  ┌──────┐                                   │
│  │  🦙  │  Connect to Ollama                │
│  └──────┘                                   │
│                                             │
│  Make sure Ollama is running locally.       │
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │ Server URL                          │    │
│  │ http://localhost:11434              │    │
│  └─────────────────────────────────────┘    │
│                                             │
│  [Test Connection]   ✓ Connected            │
│                                             │
│                                             │
│                    [Cancel]    [Connect]    │
└─────────────────────────────────────────────┘
```

---

## What Happens on "Connect"

```python
# 1. Validate credentials
if provider_type == "dashscope":
    valid = await validate_dashscope_key(api_key)
elif provider_type == "ollama":
    valid = await test_ollama_connection(server_url)

if not valid:
    show_error("Could not connect. Check your credentials.")
    return

# 2. Save Provider to DuckDB
provider = Provider(
    name="DashScope",
    provider_type=ProviderType.dashscope,
    api_base=None,  # Use default
    enabled=True
)
db.save(provider)

# 3. Save API key to Keychain (cloud providers only)
if api_key:
    set_api_key("dashscope", api_key)

# 4. Fetch available models
models = await fetch_models(provider_type, api_key or server_url)

# 5. Save Models to DuckDB
for model_info in models:
    model = Model(
        provider_id=provider.id,
        name=model_info["display_name"],
        model_id=model_info["api_id"],
        capabilities=model_info.get("capabilities", []),
        is_default=(model_info["api_id"] == "qwen-vl-max")
    )
    db.save(model)

# 6. Refresh Inspector dropdown
inspector.refresh_providers()
```

---

## Missing API Key Flow

When user tries to run a workflow but the selected provider has no API key:

```
┌─────────────────────────────────────────────┐
│  ⚠️ API Key Required                        │
├─────────────────────────────────────────────┤
│                                             │
│  DashScope requires an API key to run.      │
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │ API Key                             │    │
│  │                                     │    │
│  └─────────────────────────────────────┘    │
│                                             │
│  ☑ Save in Keychain                         │
│                                             │
│  Get a key at:                              │
│  https://dashscope.console.aliyun.com       │
│                                             │
│            [Cancel]    [Save & Run]         │
└─────────────────────────────────────────────┘
```

---

## Workflow Editor View

When user clicks on a Workflow in the sidebar, the **Editor pane** shows a **node-based canvas**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ EDITOR: Workflow "Full Analysis"                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        NODE CANVAS                                   │    │
│  │                                                                     │    │
│  │   ┌──────────┐      ┌──────────┐      ┌──────────┐                 │    │
│  │   │  START   │──────│TRANSCRIBE│──────│ ENTITIES │─────┐           │    │
│  │   │          │      │          │      │          │     │           │    │
│  │   │ 50 docs  │      │ Qwen VL  │      │ GPT-4o   │     │           │    │
│  │   └──────────┘      └──────────┘      └──────────┘     │           │    │
│  │                                                         │           │    │
│  │                                       ┌──────────┐     │           │    │
│  │                                       │ SUMMARIZE│◄────┘           │    │
│  │                                       │          │                 │    │
│  │                                       │ Claude 3 │                 │    │
│  │                                       └────┬─────┘                 │    │
│  │                                            │                       │    │
│  │                                       ┌────▼─────┐                 │    │
│  │                                       │   END    │                 │    │
│  │                                       │          │                 │    │
│  │                                       │  Export  │                 │    │
│  │                                       └──────────┘                 │    │
│  │                                                                     │    │
│  │  [+ Add Step]                                         [▶ Run]      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ STEP EDITOR (when step selected)                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│  Step: TRANSCRIBE                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ Tool:     [Transcribe OCR ▾]                                        │    │
│  │ Provider: [DashScope ▾]         Model: [Qwen VL Max ▾]              │    │
│  │ Prompt:   [Default transcription prompt...                     ]    │    │
│  │ Options:  ☐ Skip existing  ☑ High concurrency (30 requests)        │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Workflow Execution View (Animated)

When **[▶ Run]** is clicked, the canvas **animates** showing progress through nodes:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ RUNNING: Workflow "Full Analysis"                    [⏹ Stop] [⏸ Pause]    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        NODE CANVAS (animated)                        │    │
│  │                                                                     │    │
│  │   ┌──────────┐      ┌──────────┐      ┌──────────┐                 │    │
│  │   │  ✓ DONE  │━━━━━▶│🔄 RUNNING│- - - │ PENDING  │                 │    │
│  │   │  START   │      │TRANSCRIBE│      │ ENTITIES │                 │    │
│  │   │ 50/50    │      │ 23/50    │      │ 0/50     │                 │    │
│  │   └──────────┘      └──────────┘      └──────────┘                 │    │
│  │       ✓                 🔄                 ○                        │    │
│  │                                                                     │    │
│  │   Progress: ████████████░░░░░░░░░░░░░░░░░░ 46%                     │    │
│  │   ETA: 2m 15s remaining                                            │    │
│  │                                                                     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ OUTPUT (columnar log)                                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│ Document              │ Transcribe    │ Entities      │ Summarize     │    │
│───────────────────────┼───────────────┼───────────────┼───────────────│    │
│ letter_001.jpg        │ ✓ 2.3s        │ ✓ 1.1s        │ ○ pending     │    │
│ letter_002.jpg        │ ✓ 2.1s        │ ✓ 0.9s        │ ○ pending     │    │
│ letter_003.jpg        │ ✓ 3.5s        │ 🔄 running    │ ○ pending     │    │
│ letter_004.jpg        │ 🔄 running    │ ○ pending     │ ○ pending     │    │
│ letter_005.jpg        │ 🔄 running    │ ○ pending     │ ○ pending     │    │
│ letter_006.jpg        │ ○ queued      │ ○ pending     │ ○ pending     │    │
│ ...                   │               │               │               │    │
├───────────────────────┴───────────────┴───────────────┴───────────────┤    │
│ ✓ 23 completed │ 🔄 5 running │ ○ 22 pending │ ⚠ 0 failed            │    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Animation Details:

1. **Node pulses** when it's the active step
2. **Connector arrows animate** (flowing dots) showing data flow
3. **Progress bar** fills as work completes
4. **Status icons** in nodes update:
   - ○ Pending (grey)
   - 🔄 Running (blue, animated spinner)
   - ✓ Done (green checkmark)
   - ✗ Failed (red X)

---

## Output Log (Bottom Panel)

The bottom panel shows **columnar output** - one column per workflow step:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ OUTPUT LOG                                          [Export CSV] [Clear]   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│ ┌──────────────────┬───────────────┬───────────────┬───────────────┐       │
│ │ Document         │ 1. Transcribe │ 2. Entities   │ 3. Summarize  │       │
│ │                  │    (Qwen)     │    (GPT-4o)   │    (Claude)   │       │
│ ├──────────────────┼───────────────┼───────────────┼───────────────┤       │
│ │ letter_001.jpg   │ ✓ 2.3s $0.002 │ ✓ 1.1s $0.01  │ ✓ 0.8s $0.003 │       │
│ │                  │ 847 tokens    │ 234 tokens    │ 156 tokens    │       │
│ ├──────────────────┼───────────────┼───────────────┼───────────────┤       │
│ │ letter_002.jpg   │ ✓ 2.1s $0.002 │ ✓ 0.9s $0.008 │ 🔄 running... │       │
│ │                  │ 623 tokens    │ 187 tokens    │               │       │
│ ├──────────────────┼───────────────┼───────────────┼───────────────┤       │
│ │ letter_003.jpg   │ ✗ ERROR       │ ○ skipped     │ ○ skipped     │       │
│ │                  │ Rate limited  │               │               │       │
│ │                  │ [Retry]       │               │               │       │
│ ├──────────────────┼───────────────┼───────────────┼───────────────┤       │
│ │ letter_004.jpg   │ 🔄 running... │ ○ pending     │ ○ pending     │       │
│ │                  │               │               │               │       │
│ └──────────────────┴───────────────┴───────────────┴───────────────┘       │
│                                                                             │
│ TOTALS: 23 ✓ completed │ 5 🔄 running │ 22 ○ pending │ 1 ✗ failed          │
│         $0.47 spent │ 12,456 tokens │ ETA: 2m 15s                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Clicking a Cell:

When you click on a completed cell, shows the **artifact preview**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Artifact: letter_001.jpg → Transcription                      [✓] [Copy]   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Dear Mary,                                                                 │
│                                                                             │
│  I am writing to you from Liverpool. The journey was long but I arrived    │
│  safely yesterday evening. The weather here is quite cold, much colder     │
│  than I expected for this time of year.                                    │
│                                                                             │
│  I have found lodgings near the docks as you suggested. The landlady is    │
│  a kind woman named Mrs. Henderson who reminds me somewhat of your         │
│  mother...                                                                  │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ Provider: Qwen VL Max │ Tokens: 847 │ Cost: $0.002 │ Confidence: 0.94      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## LangGraph Integration

The visual nodes map directly to LangGraph StateGraph:

```python
# src/fichero/workflows/executor.py

from langgraph.graph import StateGraph, START, END

class WorkflowExecutor:
    """Execute workflows using LangGraph with visual feedback."""

    def build_graph(self, workflow: Workflow) -> StateGraph:
        """Build LangGraph from Workflow model."""

        builder = StateGraph(WorkflowState)

        # Add nodes from workflow steps
        for step in workflow.steps:
            builder.add_node(step["name"], self._make_node(step))

        # Chain nodes: START → step1 → step2 → ... → END
        steps = workflow.steps
        builder.add_edge(START, steps[0]["name"])
        for i in range(len(steps) - 1):
            builder.add_edge(steps[i]["name"], steps[i + 1]["name"])
        builder.add_edge(steps[-1]["name"], END)

        return builder.compile()

    def _make_node(self, step: dict):
        """Create a node function that processes documents."""

        async def node_fn(state: WorkflowState) -> WorkflowState:
            provider = db.get(Provider, step["provider_id"])
            model = db.get(Model, step["model_id"])
            api_key = get_api_key(provider.name)

            if not api_key and provider.provider_type not in ["ollama", "lmstudio"]:
                raise MissingAPIKeyError(provider.name)

            # Process documents
            for doc_id in state["pending_docs"]:
                # Emit progress event (for UI animation)
                self._emit_progress(step["name"], doc_id, "running")

                result = await self._process_doc(doc_id, step, api_key, model)

                # Save artifact
                artifact = Artifact(
                    document_id=doc_id,
                    artifact_type=step["artifact_type"],
                    content=result["content"],
                    provider=provider.name,
                    model=model.model_id,
                    run_id=state["run_id"]
                )
                db.save(artifact)

                self._emit_progress(step["name"], doc_id, "completed")

            return state

        return node_fn
```

---

## File Structure

### Current Structure (before)
```
src/fichero/app/main_window/
├── editor.py           # EditorContainer (swaps editors)
├── inspector.py        # Single inspector for documents
├── editors/
│   ├── base.py
│   ├── image_viewer.py
│   ├── text_viewer.py
│   └── table_viewer.py
```

### New Structure (after)
```
src/fichero/app/main_window/
├── views/                          # Mode-specific view pairs
│   ├── __init__.py
│   │
│   ├── library/                    # Library browsing mode
│   │   ├── __init__.py
│   │   ├── editor.py               # EditorContainer (image/text/table)
│   │   ├── inspector.py            # Document metadata inspector
│   │   └── viewers/                # Sub-viewers for editor
│   │       ├── __init__.py
│   │       ├── base.py
│   │       ├── image_viewer.py
│   │       ├── text_viewer.py
│   │       └── table_viewer.py
│   │
│   ├── workflow/                   # Workflow editing/running mode
│   │   ├── __init__.py
│   │   ├── editor.py               # Node canvas + step editor + output log
│   │   ├── inspector.py            # Provider/Model dropdowns + Add Provider
│   │   ├── canvas.py               # Node graph canvas
│   │   ├── step_editor.py          # Step configuration panel
│   │   └── output_log.py           # Columnar execution log
│   │
│   └── search/                     # Search mode
│       ├── __init__.py
│       ├── editor.py               # Search results preview
│       └── inspector.py            # Search filters/facets
│
├── sheets/                         # Modal sheets
│   ├── __init__.py
│   └── provider_sheet.py           # Mac Mail-style Add Provider
│
├── window.py                       # MainWindowController - switches views
├── sidebar.py                      # Unchanged
├── browser.py                      # Unchanged
├── menu.py                         # Unchanged
└── toolbar.py                      # Unchanged
```

### Migration Plan

| Current File | Action | New Location |
|--------------|--------|--------------|
| `editor.py` | MOVE | `views/library/editor.py` |
| `inspector.py` | MOVE | `views/library/inspector.py` |
| `editors/base.py` | MOVE | `views/library/viewers/base.py` |
| `editors/image_viewer.py` | MOVE | `views/library/viewers/image_viewer.py` |
| `editors/text_viewer.py` | MOVE | `views/library/viewers/text_viewer.py` |
| `editors/table_viewer.py` | MOVE | `views/library/viewers/table_viewer.py` |
| - | CREATE | `views/workflow/editor.py` |
| - | CREATE | `views/workflow/inspector.py` |
| - | CREATE | `views/workflow/canvas.py` |
| - | CREATE | `views/workflow/step_editor.py` |
| - | CREATE | `views/workflow/output_log.py` |
| - | CREATE | `views/search/editor.py` |
| - | CREATE | `views/search/inspector.py` |
| - | CREATE | `sheets/provider_sheet.py` |

### How Views Are Switched

The `window.py` (MainWindowController) manages which view is active:

```python
class MainWindowController:
    def __init__(self):
        # View pairs (editor + inspector)
        self._views = {
            'library': (LibraryEditor(), LibraryInspector()),
            'workflow': (WorkflowEditor(), WorkflowInspector()),
            'search': (SearchEditor(), SearchInspector()),
        }
        self._current_view = 'library'

    def switch_view(self, view_name: str):
        """Switch to library/workflow/search view."""
        editor, inspector = self._views[view_name]

        # Swap editor pane content
        self._editor_pane.setContentView_(editor.native)

        # Swap inspector pane content
        self._inspector_pane.setContentView_(inspector.native)

        self._current_view = view_name
```

Sidebar selection triggers view switching:
- Select a Collection/Folder → `switch_view('library')`
- Select a Workflow → `switch_view('workflow')`
- Select "Search" → `switch_view('search')`

---

## Files Already Done (Data Layer)

| File | Status |
|------|--------|
| `src/fichero/models.py` | ✅ Has Provider, Model, Workflow, Run, Artifact, Trace |
| `src/fichero/db.py` | ✅ Has CRUD operations |
| `src/fichero/keychain.py` | ✅ Has get/set/has API key |
| `src/fichero/storage.py` | ✅ Has thumbnail generation |

---

## Implementation Order

### Phase 1: Create views/ structure
1. Create `views/` folder with `__init__.py`
2. Create `views/library/` and move existing editor + inspector + viewers
3. Update imports in `window.py`
4. Verify library view still works

### Phase 2: Create workflow view skeleton
1. Create `views/workflow/` with `__init__.py`
2. Create `views/workflow/editor.py` - basic container
3. Create `views/workflow/inspector.py` - Provider/Model dropdowns
4. Wire up view switching in `window.py`

### Phase 3: Workflow Inspector (Provider management)
1. Add Provider dropdown (from DuckDB)
2. Add Model dropdown (filtered by provider)
3. Add "Add Provider" button
4. Create `sheets/provider_sheet.py` - Mac Mail-style flow

### Phase 4: Workflow Editor components
1. Create `canvas.py` - node graph with START/END + step nodes
2. Create `step_editor.py` - tool/provider/model/prompt config
3. Create `output_log.py` - columnar execution display

### Phase 5: Search view (stub)
1. Create `views/search/` with placeholder editor + inspector
2. Wire up to sidebar

Note: LangGraph executor is **separate** - will be done later by hand.

---

## Data Flow Summary

```
┌─────────────────────────────────────────────────────────────────┐
│ USER ACTIONS                                                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Click "Add Provider"  ──────►  Provider Sheet                  │
│                                      │                          │
│                                      ▼                          │
│                               Validate API Key                  │
│                                      │                          │
│                                      ▼                          │
│                              ┌──────────────┐                   │
│                              │   DuckDB     │                   │
│                              │  - Provider  │                   │
│                              │  - Model     │                   │
│                              └──────────────┘                   │
│                                      │                          │
│                                      ▼                          │
│                              ┌──────────────┐                   │
│                              │   Keychain   │                   │
│                              │  - API Key   │                   │
│                              └──────────────┘                   │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Click "Run Workflow"  ──────►  Check has_api_key()             │
│                                      │                          │
│                           No ◄───────┴───────► Yes              │
│                            │                    │               │
│                            ▼                    ▼               │
│                    "API Key Required"    Build LangGraph        │
│                         Sheet                   │               │
│                            │                    ▼               │
│                            ▼              Execute Graph         │
│                      Save & Retry              │               │
│                                                ▼               │
│                                         Emit Progress           │
│                                         Events (UI)             │
│                                                │               │
│                                                ▼               │
│                                         Save Artifacts          │
│                                          to DuckDB              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Summary

This plan creates a Mac Mail-style provider setup flow integrated with LangGraph workflow execution:

1. **Providers** added via Inspector button (not Settings)
2. **API keys** stored in macOS Keychain
3. **Provider/Model config** stored in DuckDB
4. **Workflow editor** shows node canvas with step editor
5. **Execution** animates canvas + shows columnar output
6. **LangGraph** executes workflows with progress events for UI

The design matches the existing 4-pane layout from `UNIFIED_DATA_LAYER_PLAN.md` and uses the Pydantic models from `models.py`.
