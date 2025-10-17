# Comprehensive Audit Plan: Command System Migration

## Current Status

✅ **Fixed**:
- Async command handling in OutputView
- Command system core (CommandManager, CommandRegistry, ViewCommandMixin)
- Documentation and examples

🔄 **In Progress**:
- Native Toga toolbar integration for desktop views

## Audit Plan

### Phase 1: View Command Definitions

#### 1.1 LibraryView
**Location**: `src/fichero/windows/main/views/library/library_view.py`

**Current Toolbar Buttons** (from code analysis):
- Edit button (top right)
- Bottom toolbar: Settings, Processing, About, Activity, Prompts, Plans
- Edit mode: Export, Bulk Import, Import URLs, Import Files, Import Folders

**Action Items**:
- [ ] Define FicheroCommand objects for all buttons
- [ ] Register commands via ViewCommandMixin
- [ ] Desktop: Add to `MainWindow.toolbar` via CommandManager
- [ ] Mobile: Keep custom bottom toolbar
- [ ] Remove icon from About button on desktop only

#### 1.2 CollectionView
**Location**: `src/fichero/windows/main/views/collection/collection_view.py`

**Action Items**:
- [ ] Analyze current toolbar buttons
- [ ] Define FicheroCommand objects
- [ ] Register and route appropriately

#### 1.3 OutputView
**Location**: `src/fichero/windows/main/views/output/output_view.py`

**Current Status**: ✅ Commands already defined
**Action Items**:
- [ ] Verify commands work on desktop/mobile
- [ ] Add native toolbar for desktop if beneficial
- [ ] Currently uses custom toolbars (works well)

### Phase 2: MainWindow Integration

#### 2.1 Analyze MainWindow Structure
**Location**: `src/fichero/windows/main/main_window.py`

**Key Questions**:
- Where is `CommandManager` initialized?
- How to access `self.window` from views?
- Should toolbar be per-view or global?

**Recommendation**: Per-view toolbars
- LibraryView toolbar when showing library
- CollectionView toolbar when showing collection
- OutputView toolbar when showing output

#### 2.2 Toolbar Routing Strategy

**Desktop Approach**:
```python
# In MainWindow or view switching logic
def show_library_view(self):
    self.center_pane = library_view

    # Update native toolbar for current view
    if not self.is_mobile:
        self._update_toolbar_for_view("library")

def _update_toolbar_for_view(self, view_id):
    # Clear existing toolbar
    self.window.toolbar.clear()

    # Get commands for this view
    command_manager = CommandManager.get_instance(self.app)
    command_manager.build_native_toolbar(
        self.window,
        view_id=view_id  # Enhanced method needed
    )
```

**Mobile Approach**:
- Views handle their own custom toolbars (current system)
- No changes needed

### Phase 3: Command Definitions Per View

#### 3.1 Library View Commands

```python
# In LibraryView.define_commands()
self.commands = {
    # Top toolbar
    'edit': FicheroCommand(
        id='library.edit',
        label='Edit',
        action=self._on_edit_pressed,
        icon=None,  # Text only on desktop
        show_in_menu=False,
        show_in_toolbar=True,
        desktop_only=False
    ),

    # Bottom toolbar (normal mode)
    'settings': FicheroCommand(
        id='library.settings',
        label='Settings',
        action=self._on_open_settings_window,
        icon='resources/icons/toolbar/settings.png' if self.is_mobile else None,
        show_in_menu=False,
        show_in_toolbar=True
    ),

    'processing': FicheroCommand(
        id='library.processing',
        label='Processing',
        action=self._on_open_processing_window,
        icon='resources/icons/toolbar/process.png' if self.is_mobile else None,
        show_in_menu=False,
        show_in_toolbar=True
    ),

    'about': FicheroCommand(
        id='library.about',
        label='About',
        action=self._on_open_about_window,
        icon='resources/icons/toolbar/help.png' if self.is_mobile else None,  # Icon on mobile only!
        show_in_menu=False,
        show_in_toolbar=True
    ),

    # Edit mode commands
    'export': FicheroCommand(
        id='library.export',
        label='Export',
        action=self._on_export_collection,
        icon='resources/icons/toolbar/download.png' if self.is_mobile else None,
        show_in_menu=False,
        show_in_toolbar=True  # Only shown in edit mode
    ),

    # ... more commands
}
```

#### 3.2 Collection View Commands
- Analyze and define similarly

#### 3.3 Output View Commands
- ✅ Already defined and working

### Phase 4: Implementation Steps

#### Step 1: Enhance CommandManager
```python
# In CommandManager
def build_native_toolbar_for_view(self, window, view_id, context="normal"):
    """Build native toolbar with view's commands"""
    commands = self.get_toolbar_commands(view_id=view_id, context=context)

    # Clear existing
    window.toolbar.clear()

    # Add commands
    for cmd in commands:
        toga_cmd = self._create_toga_command(cmd)
        window.toolbar.add(toga_cmd)
```

#### Step 2: Update LibraryView
1. Add ViewCommandMixin
2. Define all commands in `define_commands()`
3. Call `register_commands()` in `__init__`
4. For desktop: trigger native toolbar build
5. For mobile: use existing custom toolbar system

#### Step 3: Update CollectionView
- Same pattern as LibraryView

#### Step 4: Update MainWindow
- Add view switching hook to update native toolbar
- Call `command_manager.build_native_toolbar_for_view()` when view changes

### Phase 5: Testing Matrix

| Platform | View | Test Items |
|----------|------|------------|
| Desktop  | Library | Native toolbar shows Edit, Settings, etc (no icons for text buttons like About) |
| Desktop  | Collection | Native toolbar shows collection commands |
| Desktop  | Output | Menu shortcuts work (Cmd+L, Cmd+R, etc) |
| Mobile   | Library | Custom bottom toolbar, About has icon |
| Mobile   | Collection | Custom toolbar |
| Mobile   | Output | Custom toolbar, edit buttons work |

### Phase 6: Migration Checklist

#### Library View
- [ ] Add `from fichero.shared.commands import ViewCommandMixin`
- [ ] Change class: `class LibraryView(BaseView, ViewCommandMixin)`
- [ ] Add `self.view_id = "library"` before `super().__init__()`
- [ ] Define `define_commands()` method
- [ ] Call `register_commands()` after command definition
- [ ] Update `_add_library_toolbar_buttons()` to use commands
- [ ] Handle desktop vs mobile toolbar differences

#### Collection View
- [ ] Same pattern as Library View

#### Output View
- [x] Already migrated
- [ ] Test navigation shortcuts
- [ ] Test zoom shortcuts
- [ ] Test edit shortcuts

#### Main Window
- [ ] Initialize CommandManager in `__init__`
- [ ] Add toolbar update hook in view switching
- [ ] Handle desktop/mobile differences

### Phase 7: Audit Report Template

```markdown
## View: {ViewName}

### Commands Defined
- ✅ Command 1 (menu/toolbar/both)
- ✅ Command 2 (menu/toolbar/both)
- ...

### Platform Testing
- Desktop:
  - [ ] Native toolbar shows correctly
  - [ ] Menu items work (if any)
  - [ ] Shortcuts work (if any)
  - [ ] Icons handled correctly
- Mobile:
  - [ ] Custom toolbar shows correctly
  - [ ] All buttons work
  - [ ] Icons present where needed

### Issues Found
- Issue 1: Description and fix
- Issue 2: Description and fix

### Migration Status
- [x] Commands defined
- [x] Commands registered
- [x] Desktop toolbar configured
- [x] Mobile toolbar configured
- [x] Tested on both platforms
```

## Key Decisions

### 1. Toolbar Strategy
**Decision**: Native Toga toolbar on desktop, custom toolbars on mobile

**Rationale**:
- Desktop users expect native toolbars with system integration
- Mobile needs custom toolbars for touch-optimized UI
- Command system bridges both approaches

### 2. Icon Handling
**Decision**: Conditional icons based on platform

**Pattern**:
```python
icon='path/to/icon.png' if self.is_mobile else None
```

**Rationale**:
- Desktop text buttons don't need icons (looks better)
- Mobile buttons need icons for touch targets
- About button specifically requested without icon on desktop

### 3. View Ownership
**Decision**: Views own their commands, MainWindow owns toolbar display

**Flow**:
1. View defines commands via ViewCommandMixin
2. Commands registered with CommandManager
3. MainWindow updates `window.toolbar` based on current view
4. Mobile views handle their own custom toolbars

## Implementation Timeline

**Immediate** (This Session):
1. Create this audit plan document
2. Fix OutputView async issues ✅
3. Document current state ✅

**Next Session**:
1. Implement LibraryView commands
2. Test on desktop and mobile
3. Implement CollectionView commands
4. Update MainWindow toolbar routing

**Future Sessions**:
1. Complete testing matrix
2. Generate audit reports per view
3. Clean up any legacy toolbar code
4. Final verification

## Success Criteria

✅ **Complete** when:
1. All views use ViewCommandMixin
2. All commands registered via CommandManager
3. Desktop uses native Toga toolbar
4. Mobile uses custom toolbars
5. All keyboard shortcuts work (desktop)
6. Platform-specific icons handled correctly
7. All tests pass on both platforms

## Notes

- LibraryView has many bottom toolbar buttons (Settings, Processing, About, Activity, Prompts, Plans)
- These make more sense in a menu on desktop than a toolbar
- Consider: Should these be menu items instead of toolbar items?
- About button specifically needs no icon on desktop, icon on mobile

## Questions to Resolve

1. Should Library's bottom toolbar buttons be menu items on desktop?
2. How to handle view-specific vs. global commands?
3. Should Edit mode trigger toolbar rebuild or just show/hide buttons?

## References

- Command System Docs: `src/fichero/shared/commands/COMMAND_SYSTEM.md`
- Quick Start: `src/fichero/shared/commands/QUICK_START.md`
- Example: `src/fichero/shared/commands/example_view.py`
- Fixes: `COMMAND_SYSTEM_FIXES.md`
