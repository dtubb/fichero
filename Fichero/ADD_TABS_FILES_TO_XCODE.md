## Add Tabs & Windows Files to Xcode Project

**Files Created:**
1. `Fichero/Models/FicheroDocument.swift` - Document model for tabs
2. `Fichero/Models/ViewContexts.swift` - Context state for each tab type
3. `Fichero/Views/DocumentTabView.swift` - Main tab container
4. `Fichero/Views/Components/BackendConnectionView.swift` - Backend connection status view

**Status:** Files exist on disk but not in Xcode project

## Steps to Add Files in Xcode

### 1. Add Model Files
1. Open `Fichero.xcodeproj` in Xcode
2. In Project Navigator, navigate to `Fichero` → `Models`
3. Right-click on `Models` folder
4. Select "Add Files to 'Fichero'..."
5. Navigate to `Fichero/Models/`
6. Select **both** files:
   - `FicheroDocument.swift`
   - `ViewContexts.swift`
7. Make sure:
   - "Copy items if needed" is **UNCHECKED**
   - "Add to targets" has **Fichero** checked
8. Click "Add"

### 2. Add View Files
1. In Project Navigator, navigate to `Fichero` → `Views`
2. Right-click on `Views` folder
3. Select "Add Files to 'Fichero'..."
4. Navigate to `Fichero/Views/`
5. Select `DocumentTabView.swift`
6. Make sure:
   - "Copy items if needed" is **UNCHECKED**
   - "Add to targets" has **Fichero** checked
7. Click "Add"

### 3. Add Component File
1. In Project Navigator, navigate to `Fichero` → `Views` → `Components`
2. Right-click on `Components` folder
3. Select "Add Files to 'Fichero'..."
4. Navigate to `Fichero/Views/Components/`
5. Select `BackendConnectionView.swift`
6. Make sure:
   - "Copy items if needed" is **UNCHECKED**
   - "Add to targets" has **Fichero** checked
7. Click "Add"

### 4. Update Info.plist (IMPORTANT!)

The custom UTType for `.ficheroSession` files needs to be registered:

1. In Project Navigator, select the `Fichero` project (top level)
2. Select the `Fichero` target
3. Go to the "Info" tab
4. Under "Exported Type Identifiers", click the "+" button
5. Add a new type with:
   - **Identifier:** `ca.tubb.fichero.session`
   - **Conforms To:** `public.data`
   - **Description:** `Fichero Session`
   - **Icon:** (leave empty)
   - **Extensions:** `fichero-session`

OR manually edit `Fichero/Info.plist` and add:

```xml
<key>UTExportedTypeDeclarations</key>
<array>
    <dict>
        <key>UTTypeIdentifier</key>
        <string>ca.tubb.fichero.session</string>
        <key>UTTypeConformsTo</key>
        <array>
            <string>public.data</string>
        </array>
        <key>UTTypeDescription</key>
        <string>Fichero Session</string>
        <key>UTTypeTagSpecification</key>
        <dict>
            <key>public.filename-extension</key>
            <array>
                <string>fichero-session</string>
            </array>
        </dict>
    </dict>
</array>
```

### 5. Build and Verify

```bash
cd /Users/dtubb/code/fichero_main/fichero/Fichero
xcodebuild -project Fichero.xcodeproj -scheme Fichero -configuration Debug build
```

Should build successfully.

## What These Files Provide

### FicheroDocument.swift
- FileDocument conformance for native tabs/windows
- Saveable/restorable tab state
- Session persistence across app relaunches
- Custom UTType for `.fichero-session` files

### ViewContexts.swift
- LibraryContext - selected collection, documents, layout
- WorkflowContext - workflow ID, canvas position, zoom
- ChatContext - conversation ID, selected documents, provider
- SearchContext - query, saved search, results

### DocumentTabView.swift
- Main container for each tab/window
- Switches between Library, Workflow, Chat, Search views
- Loads appropriate context for each view mode
- Shows backend connection status when disconnected

### BackendConnectionView.swift
- Displays when Python backend isn't running
- Shows connection status and instructions
- Auto-retries connection every 5 seconds
- User can manually retry

## Next Step: Refactor FicheroApp.swift

After adding these files, we'll need to refactor `FicheroApp.swift` to use `DocumentGroup` instead of `WindowGroup`. This enables:

- Native macOS tabs (⌘T, ⌘W, ⌘{ / ⌘})
- Multiple windows
- Drag tab to new window
- Window > Merge All Windows
- Session persistence

The refactoring will be in the next step once these files are added and building successfully.
