# STATE — autonomous manager session (2026-06-20, Daniel out / iPhone demo for Ann tonight)

Branch `0.0.2`, in sync with origin. Goal: iPhone-ready demo via Tailscale tonight —
multiple libraries on iOS + swipe nav + good UI; ICANH transcripts at page level.

## ✅ Landed + pushed this session (all build-green via Xcode MCP)
- Recovered dead Codex manager's toolbar work; worktrees 23→1; Mac deploy target → **macOS 26**
  (min-26 all platforms → unguarded Liquid Glass); mini-toolbar glyphs scale w/ Dynamic Type.
- **iOS demo shell (Lane B, opus) MERGED + pushed (`3e5431c7`), compiles (Xcode build 0 errors):**
  - Multiple libraries on iOS via `KnownLibraryRegistryStore` + new `iOSLibraryPickerMenu`
    (top-bar menu) + `LibraryManager.switchToRemoteLibrary` (#2394).
  - Compact shell launches on the **sidebar/library list** (`preferredCompactColumn = .sidebar`,
    manager-flipped from worker's `.detail` to honor Daniel's "see the sidebar on launch"),
    then drill in: library → doc list → reader → swipe to inspector (#2329/#2334/#2100).
  - `SplittablePane` already desktop/regular-width only; inspector adaptive sheet on compact.
- Bugs filed #2391–#2398 (incl. #2398 AR/immersive Spaces — place images on real walls/floor,
  + single-item floor projection mode).

## 🔄 Lanes running now (workers implement, manager builds via Xcode MCP)
- `f_lane_perpage` (sonnet) — per-page transcription/content scope #2303/#2395/#2396. First
  sonnet attempt STALLED (40s CPU/25min, no output) → killed + restarted with sharp file hints.
  Worktree ~/code/fichero-worktrees/perpage-transcription.
- `f_lane_glass` (sonnet) — native Liquid Glass on mini-toolbar + bars (#2041), demo polish.
  Worktree ~/code/fichero-worktrees/liquid-glass.

## Operating rules (Daniel, this session)
- Min OS **26 everywhere**, no back-deployment. Universal app iOS/iPad/vision/tv/Mac, native
  Liquid Glass, custom UIKit/AppKit only where needed, Mac shell stays flexible.
- Model tiering kimi→haiku→sonnet→opus (codex/OpenAI RATE-LIMITED till Jun 25 → using claude
  sonnet/opus tmux workers). Workers do NOT build — manager builds (Xcode MCP `BuildProject`,
  tab `windowtab5`) + runs verify_all/pytest as the batch gate. Lots of tests, not happy-path.
- Verify-before-push: only push when build/suite green. Iterate never replace. External
  worktrees only. Issues tracked on GitHub w/ status:in-progress claims.

## Next (manager loop)
1. Integrate per-page (#2303/#2395/#2396) when it lands → run backend pytest as gate.
2. Integrate Liquid Glass when it lands → Xcode build gate.
3. After a batch: full `verify_all.sh` (OK while Daniel away — spawns GUI), push only if green.
4. Remaining demo-adjacent: #2394 remote library access depends on `.local` TLS cert covering
   the hostname (cert is loopback-only → change-stream `-9807` drops) — #2382/#2157/#2162.
   For a Tailscale demo the host cert must cover the tailnet name.
