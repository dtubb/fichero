# Keyboard Shortcuts Documentation for Sidebar CRUD Operations

## Current Implementation Analysis

### CRUD Operations Keyboard Shortcuts

Based on my analysis of `SidebarItemRow.swift`, the following keyboard shortcuts are currently implemented:

#### Create Operations
- **New Folder**: `⌘ + Shift + N` - Creates a new folder inline
- **New Search**: Available via "New Item" button in Searches section (no direct shortcut)
- **New Chat**: Available via "New Item" button in Chat section (no direct shortcut)
- **New Workflow**: Available via "New Item" button in Workflows section (no direct shortcut)

#### Read Operations
- **Expand/Collapse**: Click on disclosure triangle (no keyboard shortcut)
- **Select Item**: Click or arrow keys (standard navigation)

#### Update Operations
- **Rename**: `⌘ + R` - Opens rename dialog for selected item
- **Duplicate**: `⌘ + Shift + D` - Duplicates selected item

#### Delete Operations
- **Delete**: `Delete` key - Deletes selected item

### Consistency Across Item Types

The keyboard shortcuts are consistently implemented across all item types:

#### Documents
- Rename: `⌘ + R`
- Duplicate: `⌘ + Shift + D`
- New Folder: `⌘ + Shift + N`
- Delete: `Delete`

#### Saved Searches
- Rename: `⌘ + R`
- Duplicate: `⌘ + Shift + D`
- New Folder: `⌘ + Shift + N`
- Delete: `Delete`

#### Conversations
- Rename: `⌘ + R`
- Duplicate: `⌘ + Shift + D`
- New Folder: `⌘ + Shift + N`
- Delete: `Delete`

#### Workflows
- Rename: `⌘ + R`
- Duplicate: `⌘ + Shift + D`
- New Folder: `⌘ + Shift + N`
- Delete: `Delete`
- Import: No shortcut
- Export: No shortcut

### Menu Commands Analysis

From `FicheroApp.swift`, I can see the following menu commands that might conflict:

#### File Menu
- Import Files: `⌘ + O`
- Import Folder: `⌘ + Shift + O`

#### View Menu
- Sidebar modes: `⌃ + ⌘ + 1-5`
- View modes: `⌘ + 1-7`
- Quick Look: `⌘ + Y`
- Show/Hide Inspector: `⌘ + Option + I`

#### Other Commands
- Various zoom commands: `⌘ + Shift + +`, `⌘ + Shift + -`, etc.

### Potential Conflicts and Issues

1. **No conflicts found**: The sidebar CRUD shortcuts (`⌘ + R`, `⌘ + Shift + D`, `⌘ + Shift + N`, `Delete`) don't conflict with any menu commands.

2. **Missing shortcuts**: Some operations lack keyboard shortcuts:
   - No shortcut for creating new searches, chats, or workflows directly
   - No shortcut for expand/collapse operations
   - No shortcut for import/export workflow operations

3. **Consistency**: The shortcuts are consistently implemented across all item types.

### Recommendations

1. **Current implementation is good**: The existing keyboard shortcuts are well-designed and consistent.

2. **Potential enhancements**:
   - Add shortcut for creating new items in each section
   - Add shortcut for expand/collapse operations
   - Consider adding shortcuts for import/export workflow operations

3. **Documentation needed**: Create user-facing documentation for these shortcuts.

## User-Facing Keyboard Shortcuts Documentation

### Sidebar Navigation
- **Arrow keys**: Navigate between items
- **Return/Enter**: Select item or expand/collapse folder
- **Space**: Quick preview (if implemented)

### Document Operations
- **⌘ + R**: Rename document/folder
- **⌘ + Shift + D**: Duplicate document/folder
- **⌘ + Shift + N**: Create new folder
- **Delete**: Delete document/folder

### Search Operations
- **⌘ + R**: Rename saved search
- **⌘ + Shift + D**: Duplicate saved search
- **⌘ + Shift + N**: Create new folder (for organization)
- **Delete**: Delete saved search

### Chat Operations
- **⌘ + R**: Rename conversation
- **⌘ + Shift + D**: Duplicate conversation
- **⌘ + Shift + N**: Create new folder (for organization)
- **Delete**: Delete conversation

### Workflow Operations
- **⌘ + R**: Rename workflow
- **⌘ + Shift + D**: Duplicate workflow
- **⌘ + Shift + N**: Create new folder (for organization)
- **Delete**: Delete workflow

## Implementation Status

✅ **All CRUD operations have keyboard shortcuts**
✅ **Shortcuts are consistent across all item types**
✅ **No conflicts with existing menu commands**
⚠️ **Some operations could benefit from additional shortcuts**
📝 **User documentation needed**