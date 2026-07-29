(AI generated. Not reviewed.)

# Bundling Python Backend Inside Fichero.app

This document explains how the Python backend is bundled inside the Swift macOS app using a **nested app bundle** approach with Briefcase.

## Architecture

```
Fichero.app/                           ← Swift app (user sees this)
└── Contents/
    ├── MacOS/
    │   └── Fichero                    ← Swift executable
    ├── Resources/
    │   └── FicheroBackend.app/        ← Briefcase Python app (nested)
    │       └── Contents/
    │           ├── MacOS/
    │           │   └── FicheroBackend ← Python backend executable
    │           └── Resources/
    │               └── app/           ← All Python code & dependencies
    │                   ├── fichero/
    │                   ├── fastapi/
    │                   ├── langchain/
    │                   └── ...
    └── Info.plist
```

**Key Points:**
- Single `.app` for users to install
- Briefcase handles ALL Python bundling (dependencies, code signing, etc.)
- Swift app launches nested backend app on startup
- Backend runs hidden (no Dock icon, no menu bar)

---

## Why This Approach?

### ✅ Advantages

1. **Briefcase does the heavy lifting**
   - Automatic dependency bundling
   - Code signing handled
   - Python framework included
   - Works on any Mac (Python bundled)

2. **Single app distribution**
   - User installs one `.app` file
   - No "start backend first" instructions
   - Professional user experience

3. **Clean separation**
   - Swift UI = frontend
   - Python backend = independent app
   - Can restart backend if needed

4. **Development flexibility**
   - Dev: Use external `uvicorn --reload` (hot-reload)
   - Prod: Use nested backend app (no hot-reload)

### ❌ Trade-offs

1. **Build process has two steps**
   - Build backend with Briefcase
   - Build Swift app with Xcode

2. **Larger app bundle**
   - Backend adds ~150-200MB
   - Includes Python + all dependencies

---

## Build Instructions

### Prerequisites

```bash
# Install Briefcase
pip install briefcase

# Ensure you have Apple Developer certificate
security find-identity -v -p codesigning
```

### Step 1: Build Backend Bundle

```bash

# Build backend with Briefcase
./fichero-server/scripts/build_backend_bundle.sh
```

**What this does:**
1. Runs `briefcase create macOS --app fichero-backend`
2. Runs `briefcase build macOS --app fichero-backend`
3. Runs `briefcase package macOS --app fichero-backend`
4. Output: `macOS/FicheroBackend.app` (complete, ready to embed)

### Step 2: Build Swift App

```bash
# Open Xcode
open fichero/fichero.xcodeproj

# Build (⌘B) or Run (⌘R)
```

**What happens during Xcode build:**
1. Compiles Swift code
2. Runs build script: `fichero-server/scripts/xcode_copy_backend.sh`
3. Copies `macOS/FicheroBackend.app` → `Fichero.app/Contents/Resources/`
4. Results in single `Fichero.app` with backend embedded

### Step 3: Run

```bash
# Just launch Fichero.app
# Swift app will:
# 1. Check if backend is running
# 2. Launch FicheroBackend.app if not running
# 3. Wait for backend to be ready
# 4. Start UI
```

---

## Development Workflow

### During Development (Hot-Reload)

```bash
# Terminal 1: Start backend with hot-reload
PYTHONPATH=fichero-server/src .venv/bin/uvicorn fichero_server.api.main:app --reload --port 8765

# Terminal 2: Run Swift app from Xcode
open fichero/fichero.xcodeproj
# Press ⌘R
```

**Swift app detects** external backend (DEBUG mode):
```swift
#if DEBUG
    // Use external backend (hot-reload enabled)
    logger.info("Using external backend on port 8765")
#else
    // Launch embedded backend (no hot-reload)
    try launchEmbeddedBackend()
#endif
```

### For Production Build

```bash
# 1. Build backend
./fichero-server/scripts/build_backend_bundle.sh

# 2. Archive Swift app in Xcode
# Product → Archive
# Distribute → Copy App

# Result: Fichero.app (with backend inside)
```

---

## How It Works at Runtime

### Startup Sequence

1. **User launches Fichero.app**
   ```swift
   // FicheroApp.swift
   .task {
       await backendService.start()
   }
   ```

2. **Swift checks backend health**
   ```swift
   let isRunning = await checkHealth()
   // GET http://127.0.0.1:8765/health
   ```

3. **If not running, launch nested app**
   ```swift
   let backendAppURL = Bundle.main.resourcePath + "/FicheroBackend.app"
   NSWorkspace.shared.launchApplication(
       at: backendAppURL,
       options: [.withoutActivation, .andHide],  // Hidden from Dock
       configuration: [:]
   )
   ```

4. **Wait for backend ready**
   ```swift
   // Poll health endpoint until 200 OK
   try await waitForBackend(timeout: 30)
   ```

5. **Start UI**
   ```swift
   // Backend ready, show main window
   ```

### Backend Runs Independently

Once launched, `FicheroBackend.app`:
- Runs as separate process
- Listens on `http://127.0.0.1:8765`
- Hidden from Dock (no icon)
- Continues running until quit

Swift app communicates via HTTP:
```swift
let response = await apiClient.listWorkflows()
// HTTP GET → http://127.0.0.1:8765/api/workflows
```

---

## Configuration Files

### pyproject.toml

```toml
[tool.briefcase.app.fichero-backend]
formal_name = "Fichero Backend"
console_app = true  # ← No window, background service
sources = ["src/fichero_server", "src/fichero_backend"]
requires = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    # ... all backend dependencies
]
```

### fichero-server/src/fichero_backend/__main__.py

```python
def main():
    uvicorn.run(
        "fichero_server.api.main:app",
        host="127.0.0.1",
        port=8765,
        reload=False,  # ← NO hot-reload in production
    )
```

### Xcode Build Phase

```bash
# Add to: Target → Build Phases → Run Script
${PROJECT_DIR}/../fichero-server/scripts/xcode_copy_backend.sh
```

---

## Troubleshooting

### "Backend app not found"

```
❌ Backend app not found at: .../Resources/FicheroBackend.app
```

**Fix:** Build backend first
```bash
./fichero-server/scripts/build_backend_bundle.sh
```

### "Backend failed to start"

Check logs in Console.app:
```
Subsystem: com.tubb.Fichero
Category: EmbeddedBackend
```

### Backend won't launch

Check if backend app is signed:
```bash
codesign -dv --verbose=4 "macOS/FicheroBackend.app"
```

### Port 8765 already in use

Kill existing backend:
```bash
lsof -ti:8765 | xargs kill -9
```

---

## Updating Backend Code

When you modify Python backend code:

```bash
# 1. Rebuild backend bundle
./fichero-server/scripts/build_backend_bundle.sh

# 2. Rebuild Swift app in Xcode (⌘B)
# Build script will copy new backend bundle automatically

# 3. Run
# New backend code is now embedded
```

**What about workflows?**
- Workflows are JSON data (not code)
- No rebuild needed when users create workflows
- MCP tools loaded dynamically (no rebuild needed)

---

## File Checklist

Created files for nested app bundling:

```
✅ pyproject.toml                              (backend app config)
✅ fichero-server/src/fichero_backend/__init__.py             (backend module)
✅ fichero-server/src/fichero_backend/__main__.py             (backend entry point)
✅ scripts/build_backend_bundle.sh             (Briefcase build script)
✅ fichero-server/scripts/xcode_copy_backend.sh   (Xcode build script)
✅ fichero/fichero/Services/EmbeddedBackendService.swift  (Swift launcher)
✅ docs/contributor/bundling-backend.md                    (this file)
```

---

## Next Steps

1. **Test backend build:**
   ```bash
   ./fichero-server/scripts/build_backend_bundle.sh
   ```

2. **Add Xcode build script:**
   - Open fichero/fichero.xcodeproj
   - Target → Build Phases → + → New Run Script Phase
   - Add: `${PROJECT_DIR}/../fichero-server/scripts/xcode_copy_backend.sh`

3. **Update FicheroApp.swift:**
   - Add `@StateObject var backendService = EmbeddedBackendService()`
   - Add startup task: `await backendService.start()`

4. **Test full build:**
   - Build in Xcode
   - Verify backend copied to Resources/
   - Run app, verify backend launches

5. **Archive for distribution:**
   - Product → Archive
   - Distribute → Copy App
   - Test on clean Mac
