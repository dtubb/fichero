(AI generated. Not reviewed.)

# Setup: Bundled Backend in Fichero.app

This guide walks you through the final setup steps to enable the embedded Python backend in Fichero.app.

## Current Status ✅

The following has been implemented:

- ✅ Backend entry point (`fichero-engine/src/engine/__init__.py`)
- ✅ Briefcase configuration in `pyproject.toml`
- ✅ Build script (`fichero-engine/scripts/build_backend_bundle.sh`)
- ✅ Xcode copy script (`fichero-engine/scripts/xcode_copy_backend.sh`)
- ✅ Swift backend service (`fichero/fichero/Services/EmbeddedBackendService.swift`)
- ✅ FicheroApp.swift updated to launch backend
- ✅ Backend successfully built with Briefcase

## Next Steps: Xcode Setup

### Step 1: Add EmbeddedBackendService.swift to Xcode

1. Open `fichero/fichero.xcodeproj` in Xcode
2. In Project Navigator, locate `fichero/fichero/Services/` folder
3. **Right-click on Services folder** → Add Files to "Fichero"
4. Navigate to: `fichero/fichero/Services/EmbeddedBackendService.swift`
5. **Make sure:** ✅ "Copy items if needed" is UNCHECKED
6. **Make sure:** ✅ "Fichero" target is CHECKED
7. Click "Add"

**Verify:** `EmbeddedBackendService.swift` should now appear in the Services folder in Xcode.

---

### Step 2: Add Build Script to Copy Backend

1. In Xcode, select **Fichero target** (blue icon at top of navigator)
2. Go to **Build Phases** tab
3. Click **+** button → **New Run Script Phase**
4. **Drag** the new "Run Script" phase to be **AFTER** "Copy Bundle Resources"
5. **Name it:** "Copy Backend Bundle" (click on "Run Script" to rename)
6. **In the script box, paste:**
   ```bash
   ${PROJECT_DIR}/../fichero-engine/scripts/xcode_copy_backend.sh
   ```
7. **Expand "Input Files"** and add:
   ```
   ${PROJECT_DIR}/../fichero-engine/build/fichero-backend/macos/app/FicheroBackend.app
   ```
8. **Expand "Output Files"** and add:
   ```
   ${BUILT_PRODUCTS_DIR}/${PRODUCT_NAME}.app/Contents/Resources/FicheroBackend.app
   ```

**Screenshot guide:**
```
Build Phases
├─ Dependencies
├─ Compile Sources
├─ Link Binary
├─ Copy Bundle Resources
├─ ✨ Copy Backend Bundle  ← NEW (your script)
└─ Embed Frameworks
```

---

### Step 3: Build Backend Bundle

Before building in Xcode, build the Python backend:

```bash
./fichero-engine/scripts/build_backend_bundle.sh
```

**Expected output:**
```
🔨 Building Fichero Backend with Briefcase
===========================================

[fichero-backend] Generating application template...
[fichero-backend] Installing support package...
[fichero-backend] Building App...

✅ Backend bundle ready!
   Location: build/fichero-backend/macos/app/FicheroBackend.app
   Size: 180M

Next steps:
1. Build Fichero.app in Xcode
2. Backend will be automatically copied into Resources/
3. Swift app will launch backend on startup
```

---

### Step 4: Build Fichero.app in Xcode

1. **Select Fichero scheme** (top toolbar)
2. **Select "My Mac" as destination**
3. **Build:** Press **⌘B** (or Product → Build)

**Watch for:**
- Build script output in the Build Log
- Should see: `📦 Copying backend bundle to Fichero.app...`
- Should see: `✅ Backend bundle copied successfully (180M)`

**If build fails with "Backend bundle not found":**
- Make sure you ran `./fichero-engine/scripts/build_backend_bundle.sh` first
- Check that `fichero-engine/build/fichero-backend/macos/app/FicheroBackend.app` exists

---

### Step 5: Run Fichero.app

1. **Press ⌘R** (or Product → Run)
2. **Watch Console logs** (View → Debug Area → Show Debug Area)
3. **Look for:**
   ```
   [EmbeddedBackend] Starting embedded backend...
   [EmbeddedBackend] Launching nested backend app at: .../FicheroBackend.app
   [EmbeddedBackend] Backend app launched successfully (PID: 12345)
   [EmbeddedBackend] Backend health check passed
   [FicheroApp] Backend started successfully
   ```

**If you see "DEBUG mode: Checking for external backend":**
- This means you're running in DEBUG configuration
- The app expects an external backend on port 8765
- **Either:** Start external backend: `PYTHONPATH=fichero-engine/src uvicorn fichero.api.main:app --reload`
- **Or:** Change to Release build configuration in Xcode

---

## Development vs Production

### Development Mode (DEBUG)

When running in DEBUG configuration:

```swift
#if DEBUG
    // Use external backend with hot-reload
    logger.info("Using external backend on port 8765")
#endif
```

**Start external backend:**
```bash
PYTHONPATH=fichero-engine/src .venv/bin/uvicorn fichero.api.main:app --reload --port 8765
```

**Benefits:**
- ✅ Hot-reload when you modify Python code
- ✅ Faster iteration
- ✅ Easy to debug backend

### Production Mode (RELEASE)

When running in RELEASE configuration or archived build:

```swift
#else
    // Launch embedded backend (no hot-reload)
    try launchEmbeddedBackend()
#endif
```

**Benefits:**
- ✅ Single app bundle
- ✅ No separate backend startup
- ✅ Professional user experience

**To test production mode in Xcode:**
1. Edit Scheme (Product → Scheme → Edit Scheme)
2. Select "Run" on left
3. Change "Build Configuration" from "Debug" to "Release"
4. Click "Close"
5. Run (⌘R)

---

## Verification Checklist

After setup, verify everything works:

### ✅ Backend Bundle Exists
```bash
ls -lh "fichero-engine/build/fichero-backend/macos/app/FicheroBackend.app"
```

### ✅ Backend Copied to App
```bash
# After building in Xcode
ls -lh ~/Library/Developer/Xcode/DerivedData/Fichero-*/Build/Products/Debug/Fichero.app/Contents/Resources/FicheroBackend.app
```

### ✅ Backend Launches
- Run Fichero.app in Xcode
- Check Activity Monitor for "Fichero Backend" process
- OR: `ps aux | grep "Fichero Backend"`

### ✅ Backend Responds
```bash
# While Fichero.app is running
curl http://127.0.0.1:8765/health
# Should return: {"status":"healthy"}
```

### ✅ UI Works
- Fichero.app window appears
- No "Backend not running" errors
- Workflows can be created and executed

---

## Troubleshooting

### "EmbeddedBackendService" type not found

**Fix:** Add `EmbeddedBackendService.swift` to Xcode project (Step 1)

### Build script not running

**Fix:** Make sure script is executable:
```bash
chmod +x fichero-engine/scripts/xcode_copy_backend.sh
```

### "Backend app not found in bundle"

**Fix:** Build backend first:
```bash
./fichero-engine/scripts/build_backend_bundle.sh
```

### Backend launches but app hangs

**Fix:** Check if backend started successfully:
```bash
# Check backend logs
log show --predicate 'subsystem == "com.tubb.Fichero" AND category == "EmbeddedBackend"' --last 1m
```

### Port 8765 already in use

**Fix:** Kill existing backend:
```bash
lsof -ti:8765 | xargs kill -9
```

---

## Next: Archiving for Distribution

Once everything works:

1. **Product → Archive** in Xcode
2. **Distribute App** → Choose distribution method
3. **Export** the app
4. **Result:** `Fichero.app` with backend embedded!

Users just need to:
1. Download `Fichero.app`
2. Drag to Applications folder
3. Launch
4. Backend starts automatically!

---

## File Reference

All files involved in bundling:

```
├── pyproject.toml                           # Briefcase config
├── src/
│   └── fichero_backend/
│       ├── __init__.py                      # Backend module
│       └── __main__.py                      # Backend entry point
├── scripts/
│   ├── build_backend_bundle.sh              # Build backend with Briefcase
│   └── xcode_copy_backend.sh                # Copy backend to app bundle
├── fichero/fichero/
│   ├── Services/
│   │   └── EmbeddedBackendService.swift     # Swift backend launcher
│   └── FicheroApp.swift                     # App entry (updated)
└── build/
    └── fichero-backend/
        └── macos/
            └── app/
                └── FicheroBackend.app      # Built by Briefcase
```

---

## Questions?

Refer to:
- `docs/contributor/bundling-backend.md` - Architecture overview
- `docs/contributor/setup-bundled-backend.md` - This file
- Build script output for diagnostics
- Xcode build logs for detailed errors
