# Menu Structure Design for Fichero

## Overview
This document outlines the menu structure for Fichero, including:
- macOS Menu Bar (Application Menu)
- Sidebar Contextual Menu
- Keyboard Shortcuts

## 1. macOS Menu Bar Structure

### File Menu
- **Import Files...** (`Cmd+O`) - Import individual files
- **Import Folder...** (`Cmd+Shift+O`) - Import entire folder
- **New Search...** (`Cmd+Shift+S`) - Create new search
- **New Chat...** (`Cmd+Shift+C`) - Create new chat
- **New Workflow...** (`Cmd+Shift+W`) - Create new workflow
- **---** (Separator)
- **Providers...** - Manage AI providers
- **Add Provider...** - Add new AI provider
- **---** (Separator)
- **Quit Fichero** (`Cmd+Q`) - Quit application

### Edit Menu (Standard)
- Undo, Redo, Cut, Copy, Paste, Select All

### View Menu (Already Implemented)
- Sidebar modes (Navigate, Search, Chat, Workflows, Activity)
- Browser view modes (Icons, List, Table, Map)
- Preview modes (None, Standard, Widescreen)
- Quick Look toggle
- Inspector toggle

### Window Menu (Standard)
- Minimize, Zoom, Arrange All

### Help Menu
- Fichero Help
- Check for Updates...

## 2. Sidebar Contextual Menu Structure

### For Documents
- **Rename...** - Rename document
- **Duplicate** - Create copy of document
- **---** (Separator)
- **New Folder...** - Create new folder
- **---** (Separator)
- **Delete** - Remove document

### For Saved Searches
- **Rename...** - Rename search
- **Duplicate** - Create copy of search
- **---** (Separator)
- **New Folder...** - Create new folder
- **---** (Separator)
- **Delete** - Remove search

### For Conversations (Chat)
- **Rename...** - Rename conversation
- **Duplicate** - Create copy of conversation
- **---** (Separator)
- **New Folder...** - Create new folder
- **---** (Separator)
- **Delete** - Remove conversation

### For Workflows
- **Rename...** - Rename workflow
- **Duplicate** - Create copy of workflow
- **Import...** - Import workflow from file
- **Export...** - Export workflow to file
- **---** (Separator)
- **New Folder...** - Create new folder
- **---** (Separator)
- **Delete** - Remove workflow

## 3. Keyboard Shortcuts

### Global Shortcuts
- `Cmd+O` - Import Files
- `Cmd+Shift+O` - Import Folder
- `Cmd+Shift+S` - New Search
- `Cmd+Shift+C` - New Chat
- `Cmd+Shift+W` - New Workflow
- `Cmd+Q` - Quit

### View Mode Shortcuts
- `Cmd+1` - Icons view
- `Cmd+2` - List view
- `Cmd+3` - Table view
- `Cmd+4` - Map view
- `Cmd+5` - No preview
- `Cmd+6` - Standard preview
- `Cmd+7` - Widescreen preview
- `Cmd+Y` - Quick Look
- `Cmd+Option+I` - Toggle Inspector

### Sidebar Navigation Shortcuts
- `Cmd+Control+1` - Navigate mode
- `Cmd+Control+2` - Search mode
- `Cmd+Control+3` - Chat mode
- `Cmd+Control+4` - Workflows mode
- `Cmd+Control+5` - Activity mode

## 4. API Endpoints Required

### Documents
- `POST /api/documents` - Create document
- `GET /api/documents/{id}` - Get document
- `PUT /api/documents/{id}` - Update document
- `DELETE /api/documents/{id}` - Delete document
- `POST /api/documents/{id}/duplicate` - Duplicate document

### Saved Searches
- `POST /api/search/saved` - Create search
- `GET /api/search/saved/{id}` - Get search
- `PUT /api/search/saved/{id}` - Update search
- `DELETE /api/search/saved/{id}` - Delete search
- `POST /api/search/saved/{id}/duplicate` - Duplicate search

### Conversations
- `POST /api/chat/conversations` - Create conversation
- `GET /api/chat/conversations/{id}` - Get conversation
- `PUT /api/chat/conversations/{id}` - Update conversation
- `DELETE /api/chat/conversations/{id}` - Delete conversation
- `POST /api/chat/conversations/{id}/duplicate` - Duplicate conversation

### Workflows
- `POST /api/workflows` - Create workflow
- `GET /api/workflows/{id}` - Get workflow
- `PUT /api/workflows/{id}` - Update workflow
- `DELETE /api/workflows/{id}` - Delete workflow
- `POST /api/workflows/{id}/duplicate` - Duplicate workflow
- `POST /api/workflows/import` - Import workflow
- `POST /api/workflows/{id}/export` - Export workflow

## 5. Implementation Plan

### Phase 1: Menu Bar Implementation
1. Add File menu items for New Search, New Chat, New Workflow
2. Add keyboard shortcuts
3. Connect to API endpoints

### Phase 2: Contextual Menu Implementation
1. Complete document CRUD operations
2. Complete search CRUD operations
3. Complete conversation CRUD operations
4. Complete workflow CRUD operations (including import/export)

### Phase 3: Testing
1. Add unit tests for menu actions
2. Add integration tests for API calls
3. Manual testing of all shortcuts and menus
