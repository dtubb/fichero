# Quick Start: Phase 0.6 Testing

**5-Minute Guide to Start Testing**

---

## Step 1: Start Backend (1 minute)

Open Terminal and run:

```bash
cd /Users/dtubb/code/fichero_main/fichero
PYTHONPATH=src .venv/bin/uvicorn fichero.api.main:app --port 8765
```

**Wait for**:
```
INFO:     Uvicorn running on http://127.0.0.1:8765
```

**✅ Verify** (in a new terminal):
```bash
curl http://127.0.0.1:8765/health
```

**Expected**:
```json
{"status":"healthy","backend_version":"0.1.0","active_libraries":0}
```

If you see this, backend is ready! ✅

---

## Step 2: Quick Backend Smoke Test (2 minutes)

### Test 1: Create Document

```bash
curl -X POST http://127.0.0.1:8765/api/documents \
  -H "Content-Type: application/json" \
  -H "X-Fichero-Library-Path: $HOME/Desktop/Test.fichero" \
  -d '{"name":"Test Folder","documentType":"folder"}'
```

**Expected**: Returns document with ID ✅

### Test 2: List Documents

```bash
curl -H "X-Fichero-Library-Path: $HOME/Desktop/Test.fichero" \
  http://127.0.0.1:8765/api/documents
```

**Expected**: Shows "Test Folder" ✅

### Test 3: Verify Package Created

```bash
ls -la ~/Desktop/Test.fichero/
```

**Expected**: See `fichero.duckdb` file ✅

If all three pass, backend is working! ✅

---

## Step 3: Run Swift App (2 minutes)

### Open in Xcode

```bash
open /Users/dtubb/code/fichero_main/fichero/Fichero/Fichero.xcodeproj
```

### Run App

1. Press **⌘R** (or click Run button)
2. Wait for app to launch
3. Check Console (⌘⇧Y) for:

```
[AppState] Backend connected: v0.1.0, 0 active libraries
```

If you see this, frontend is connected! ✅

---

## Step 4: Quick Frontend Test (Optional)

In the running app:

1. **File > New** (⌘N) - Create a new library
2. Save as `TestLibrary.fichero` on Desktop
3. Check Console for "Library loaded" message
4. Verify Sidebar shows empty library

If you see the empty library view, frontend is working! ✅

---

## That's It!

**You've verified**:
- ✅ Backend starts and responds
- ✅ Database routing works (Test.fichero created)
- ✅ Frontend connects to backend
- ✅ Library creation works

**Next Steps**:

For comprehensive testing, see:
- **Backend**: `PHASE_0.6_BACKEND_TEST_PLAN.md` (29 tests)
- **Frontend**: `PHASE_0.6_FRONTEND_TEST_PLAN.md` (UI tests)

---

## Troubleshooting

### Backend Won't Start

**Error**: `ModuleNotFoundError: No module named 'fichero'`

**Fix**:
```bash
# Make sure you're in the right directory
cd /Users/dtubb/code/fichero_main/fichero

# Check virtual environment
ls .venv/bin/python3

# Set PYTHONPATH and try again
PYTHONPATH=src .venv/bin/uvicorn fichero.api.main:app --port 8765
```

---

### Health Check Fails

**Error**: `curl: (7) Failed to connect to 127.0.0.1 port 8765`

**Fix**:
- Backend isn't running
- Check terminal for errors
- Make sure port 8765 is not in use:
  ```bash
  lsof -i :8765
  ```

---

### Frontend Won't Build

**Error**: Build fails in Xcode

**Fix**:
```bash
# Clean build folder
xcodebuild -project Fichero/Fichero.xcodeproj \
  -scheme Fichero -configuration Debug clean

# Rebuild
open Fichero/Fichero.xcodeproj
# Press ⌘⇧K (Clean), then ⌘B (Build)
```

---

### Frontend Shows "Backend Not Running"

**Fixes**:
1. ✅ Make sure backend is running (Step 1)
2. ✅ Check health endpoint works (Step 1 verify)
3. ✅ Restart frontend app (⌘Q, then ⌘R)
4. ✅ Check Xcode Console for actual error

---

## Expected Files After Testing

After running the quick tests, you should see:

```
~/Desktop/
├── Test.fichero/             ← Created by backend test
│   └── fichero.duckdb        ← Database file
└── TestLibrary.fichero/      ← Created by frontend test (optional)
    └── document.json         ← Library metadata
```

Clean up when done:
```bash
rm -rf ~/Desktop/Test.fichero ~/Desktop/TestLibrary.fichero
```

---

## Status Check

After completing the quick start:

**Backend**:
- [ ] Backend starts without errors
- [ ] Health check returns correct format
- [ ] Can create documents
- [ ] Database file created in package

**Frontend**:
- [ ] App builds successfully
- [ ] App launches without errors
- [ ] Console shows backend connection
- [ ] Can create new library (optional)

**If all checked**: ✅ Ready for full testing!

**If any failed**: See Troubleshooting above or `PHASE_0.6_PREFLIGHT_CHECKLIST.md`

---

## Full Testing

Once quick start passes, proceed to:

1. **Backend Testing** (~1-2 hours)
   - Open `PHASE_0.6_BACKEND_TEST_PLAN.md`
   - Execute all 29 tests
   - Document results

2. **Frontend Testing** (~1 hour)
   - Open `PHASE_0.6_FRONTEND_TEST_PLAN.md`
   - Test UI functionality
   - Verify multi-library support

---

**Ready? Let's test!** 🚀

Start with Step 1 above ⬆️
