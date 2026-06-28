# Fichero Release Process

Every `0.x.y` release ships exactly one testable feature end-to-end.
The process is the same regardless of whether the work is new code or enabling an existing feature gate.

---

## Release Sequence

```
Claim milestone issues
        ↓
Backend: implement + test
        ↓
Frontend: enable flag + integrate
        ↓
Automated tests (Claude)
        ↓
Visual tests (Peekaboo)
        ↓
Human test (Daniel)
        ↓
Fix bugs → repeat from Automated tests
        ↓
Tag + ship
```

---

## Step 1 — Backend Tests

Run before any frontend work begins. The backend must be green before wiring.

```bash
# Unit tests
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ \
  --ignore=fichero-engine/tests/unit/_archived -q

# Lint
ruff check fichero-engine/src/
```

**Pass criteria:** All tests pass, lint clean.

---

## Step 2 — Frontend: Enable + Integrate

1. Enable the feature flag in `FeatureManager.swift` (or `resetToV0X()` tier)
2. Verify Xcode build compiles without errors:
   ```bash
   xcodebuild -project fichero/fichero.xcodeproj \
     -scheme fichero -configuration Debug build \
     CODE_SIGN_IDENTITY="" CODE_SIGNING_REQUIRED=NO \
     2>&1 | grep -E "error:|BUILD SUCCEEDED|BUILD FAILED"
   ```
3. Run SwiftLint:
   ```bash
   swiftlint lint fichero/fichero/
   ```
4. Verify Xcode Previews compile for the feature's views (open in Xcode, check Preview canvas)

**Pass criteria:** Build succeeds, SwiftLint clean, Previews render.

---

## Step 3 — Automated API Tests (Claude)

Claude calls the backend API directly via MCP tools to verify the feature's endpoints work correctly.

**Pattern per feature:**
```
1. Start backend: PYTHONPATH=fichero-engine/src .venv/bin/uvicorn fichero.api.main:app --port 8765
2. Call each relevant endpoint via Fichero MCP
3. Verify: correct response shape, correct data, correct error codes for bad input
4. Verify: feature flag toggle affects endpoint availability
```

Results recorded as a comment on the release gate issue.

---

## Step 4 — Visual Tests (Peekaboo)

With the app running and the feature enabled, Claude uses Peekaboo to take screenshots.

**Minimum screenshots per release:**
1. Feature in empty state (no data yet)
2. Feature with data loaded
3. Feature in an error/edge state (if applicable)
4. Overall app with feature visible in navigation

Screenshots attached to the release gate issue as evidence.

---

## Step 5 — Human Test (Daniel)

Each release gate issue contains a **Daniel Test Checklist** — specific steps to follow in the running app.

**Format:**
```
- [ ] Step 1: Do X → expect Y
- [ ] Step 2: Do A → expect B
- [ ] Edge case: try Z → should not crash
```

Daniel marks each item ✅ or files a bug with `/bug`.
When all items are checked and no P0 bugs remain open: release is approved.

---

## Step 6 — Bug Loop

Bugs found during Steps 3–5 are filed via `/bug` skill.
Each bug gets a GitHub issue with label `type:bug` + current milestone.
Claude fixes bugs, re-runs Steps 3–5 for affected areas.

---

## Step 7 — Tag + Ship

Once Daniel approves:
```bash
/release 0.x.y
```

The `/release` skill:
1. Verifies all milestone issues are closed or deferred
2. Tags the commit
3. Creates GitHub release with changelog
4. Updates STATE.md with next milestone

---

## Parallel Release Workflow

While Daniel tests release N, agents can work on N+1 in a separate git worktree:

```
Daniel testing:  current candidate
Agent building:  next milestone branch
Queued:          0.0.5, 0.0.6, ...
```

Rules:

1. Worktrees live only under `~/code/fichero-worktrees/<name>`.
2. Agents commit directly to the milestone branch for that worktree; no per-task branches.
3. Daniel must explicitly approve the release command before tagging or merging forward.
4. After release, the next lane resets/rebases from the approved mainline before continuing.

Never create or remove bare `~/code/fichero-*` sibling directories for release lanes.

---

## Filing Bugs During Testing

```
/bug
```

The `/bug` skill asks: what happened, what was expected, repro steps.
It files a GitHub issue with branch context and area label.
Claude picks it up in the next autonomous loop.

---

## Release Gate Issues

Every milestone has one **release gate issue** (label: `release-gate`).
It is the last issue closed before the milestone ships.
It contains:
- Feature description
- Automated test evidence (from Step 3)
- Peekaboo screenshot links (from Step 4)
- Daniel's human test checklist (Step 5)
- Sign-off line: "Daniel approved on [date]"

---

## Milestone Health Check

Run `/milestone-check` at any time to see:
- Open issues remaining
- Test status
- Whether the release gate issue is ready for Daniel

---

## File Size Limits

| Language | Soft limit | Hard limit |
|---|---|---|
| Python (.py) | 400 lines | 1000 lines |
| Swift (.swift) | 300 lines | 600 lines |

Files over the soft limit should be split before merging to main.
Files over the hard limit **must** be split before merging.
