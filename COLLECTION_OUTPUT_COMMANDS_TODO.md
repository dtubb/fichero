# CollectionView and OutputView Command Migration

## Issue

Currently, no commands are showing in Toga's native toolbar on desktop because:
- CollectionView hasn't been migrated to the command system
- OutputView hasn't been migrated to the command system
- Both views are still creating toolbar buttons manually instead of declaring commands

## CollectionView Commands Needed

Based on the existing manual button creation in `_add_collection_toolbar_buttons()`:

```python
def define_commands(self):
    """Define all commands for CollectionView"""
    self.view_id = "collection"

    self.commands = {
        # Process command - always visible
        'process': FicheroCommand(
            id='collection.process',
            label=_("Process"),
            action=self._on_process_requested,
            icon='resources/icons/toolbar/process.png',  # If icon exists
            description=_("Process items with Fichero Director"),
            show_in_menu=False,
            show_in_bottom_toolbar=True,  # Shows in native toolbar on desktop
            toolbar_position='center',
            context='normal'  # Always visible
        ),

        # Add File - for collection items
        'add_file': FicheroCommand(
            id='collection.add_file',
            label=_("Add File"),
            action=self._on_add_file,
            icon='resources/icons/toolbar/document.png',
            description=_("Add file to collection"),
            show_in_menu=False,
            show_in_bottom_toolbar=True,
            toolbar_position='center',
            context='normal'
        ),

        # Add Folder - for collection items
        'add_folder': FicheroCommand(
            id='collection.add_folder',
            label=_("Add Folder"),
            action=self._on_add_folder,
            icon='resources/icons/toolbar/folder@10x.png',
            description=_("Add folder to collection"),
            show_in_menu=False,
            show_in_bottom_toolbar=True,
            toolbar_position='center',
            context='normal'
        ),
    }
```

## OutputView Commands Needed

OutputView should have editing commands that are ALWAYS visible:

```python
def define_commands(self):
    """Define all commands for OutputView"""
    self.view_id = "output"

    self.commands = {
        'rotate_left': FicheroCommand(
            id='output.rotate_left',
            label=_("Rotate Left"),
            action=self._on_rotate_left,
            icon='resources/icons/toolbar/rotate_left.png',  # If exists
            description=_("Rotate image counter-clockwise"),
            show_in_menu=False,
            show_in_bottom_toolbar=True,  # Desktop native toolbar + mobile bottom toolbar
            shortcut=toga.Key.MOD_1 + 'l',  # Cmd+L
            context='normal'
        ),

        'rotate_right': FicheroCommand(
            id='output.rotate_right',
            label=_("Rotate Right"),
            action=self._on_rotate_right,
            icon='resources/icons/toolbar/rotate_right.png',
            description=_("Rotate image clockwise"),
            show_in_menu=False,
            show_in_bottom_toolbar=True,
            shortcut=toga.Key.MOD_1 + 'r',  # Cmd+R
            context='normal'
        ),

        'crop': FicheroCommand(
            id='output.crop',
            label=_("Crop"),
            action=self._on_crop,
            icon='resources/icons/toolbar/crop.png',
            description=_("Crop image"),
            show_in_menu=False,
            show_in_bottom_toolbar=True,
            context='normal'
        ),

        'reset': FicheroCommand(
            id='output.reset',
            label=_("Reset"),
            action=self._on_reset,
            icon='resources/icons/toolbar/reset.png',
            description=_("Reset all changes"),
            show_in_menu=False,
            show_in_bottom_toolbar=True,
            context='normal'
        ),
    }
```

## Migration Steps

### For CollectionView:

1. **Add imports**:
   ```python
   from fichero.shared.commands import FicheroCommand, ViewCommandMixin
   ```

2. **Add ViewCommandMixin to class**:
   ```python
   class CollectionView(BaseView, ViewCommandMixin):
   ```

3. **Add view_id in __init__ BEFORE super().__init__()**:
   ```python
   self.view_id = "collection"
   ```

4. **Initialize ViewCommandMixin and register commands**:
   ```python
   super().__init__(app, is_mobile)
   ViewCommandMixin.__init__(self)

   # Define and register commands
   self.define_commands()
   self.register_commands()
   ```

5. **Remove manual toolbar button creation**:
   - Delete `_add_collection_toolbar_buttons()` method
   - Remove call to this method in `_create_toolbars()`

6. **Update `_create_toolbars()` to use auto-population**:
   ```python
   def _create_toolbars(self):
       self.top_toolbar = TopToolbar(...)
       self.bottom_toolbar = BottomToolbar(...)

       # Auto-populate from commands
       self.set_toolbars(self.top_toolbar, self.bottom_toolbar)
   ```

### For OutputView:

Same steps as CollectionView, plus:

7. **Remove any manual setup_native_toolbar() calls** - the system handles this automatically

## Testing

After migration:

```bash
# Desktop test
briefcase dev

# Expected:
# - LibraryView: Native toolbar with Add File/Folder/URL
# - CollectionView: Native toolbar with Process, Add File, Add Folder
# - OutputView: Native toolbar with Rotate Left/Right, Crop, Reset
```

```bash
# Mobile test
FORCE_MOBILE_UI=true briefcase dev

# Expected:
# - LibraryView: Bottom toolbar with add commands + window nav
# - CollectionView: Bottom toolbar with collection commands
# - OutputView: Bottom toolbar with editing commands
```

## Why This Works

1. **Views are declarative**: Just define commands with metadata
2. **MainWindow manages toolbars**: Calls `build_native_toolbar()` when showing views
3. **BaseView auto-populates**: Calls `populate_from_commands()` for mobile
4. **CommandManager filters**: Uses `toolbar_type="native"` to get right commands

No manual toolbar management needed!
