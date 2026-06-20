# STATE — manager handoff (2026-06-20)

Branch `0.0.2`, **in sync with origin** (pushed `ba2a782a`). Recovered from a
Codex *manager* session that ran out of tokens mid-edit. Workspace cleaned to a
fresh footing per Daniel: `~/code/fichero` (main) + ONE live worktree
(`cli-pairing-2388`). All other worker worktrees/branches consolidated or deleted.

## ✅ Done this session (manager)
- **Recovered Codex's in-flight slice** → `e2486816` *feat(shell): platform-aware
  mini-toolbar sizing + larger iOS/tvOS touch targets (#2098 #883)*:
  `MiniToolbarMetricPolicy` (testable per-platform metrics Mac 44/28, touch 52/44,
  tvOS 64/44) + 44pt min hit targets; tvOS capture guards; `EditorView` empty-state
  → "No selection"; `MiniToolbarMetricPolicyTests` (3 cases).
- **Worktree cleanup: 23 → 1.** Removed all merged/superseded lanes. Key calls:
  - chat (#2336/#2338/#2340/#2345), connection-capture (#2376) branches were
    **superseded** — 0.0.2 already shipped them via unified/newer commits
    (`478d4a95`, `437f7519`+follow-ups). Deleted.
  - #2351 + #2377 security branches were **stale** (net −9000/−3347 lines; would
    delete shipped Settings files). #2351/#2377 fully shipped to 0.0.2. Deleted.
  - Merged in: visionos-watchdog #2375 (docs), narrow-shell-collapse #2372 (UI).
- **Pushed** — origin/0.0.2 == 0.0.2. swiftlint clean (only pre-existing warnings).

## ▶ Active direction (Daniel)
**Shared codebase, platform idioms per device.** iPhone/iPad UX is the pain:
- iPhone vertical splits don't work → **swiping columns** (native
  `NavigationSplitView` adaptive collapse, NOT custom `HSplitView`/`SplittablePane`).
- touch targets too small (started in `e2486816`).
- **iOS slowdowns** → #2307 (computed sort/filter inside `var body`),
  SidebarItemBuilder rebuild storm, change-stream main-thread apply (#1973).

Work the existing **ready-for-test cluster** — already filed, don't re-file:
- Adaptive nav: **#2329** (preferredCompactColumn), **#2333** (SplittablePane
  desktop-only), **#2334**/**#2100** (compact stack), **#2331** (adaptive inspector),
  **#2332** (compact reading), **#2342** (compact sidebar/DnD).
- P0 iPad: **#2390** (core commands + view switching). Perf: **#2307**.
- EPICs: #2328 adaptive shell host, #2096 iOS client, #1926/#2253 universal app.

## Operating model (Daniel, this session)
1. **Cleanup → workers → work**, in that order. ✅ cleanup done.
2. **Model tiering** to conserve weekly Claude context: kimi (ollama/codex) for
   easy/mechanical → haiku → sonnet → opus (hard/structural only). If kimi can do
   it, do it there.
3. **Workers do NOT build/verify — the manager does**, batched: 3–5 (or 5–10)
   issues land, THEN one build/test; `verify_all` full at good checkpoints.
   Building is slow on this machine — be judicious, don't gate every issue.
4. Workers run in external worktrees `~/code/fichero-worktrees/`, claim issues
   (`/claim-task`), never `.claude/worktrees/`.

## Lanes (tmux, at handoff)
- `f_cli_2388` (claude): #2388 CLI pairing, live — its worktree kept.
- `f_ux_shell_review` (opus): reviewing #2390 iPad shell, read-only.
- `f_security_claude`/`f_security_codex`: TLS pinning, **no findings ≥ MEDIUM** — idle/releasable.
- `f_ux_capture/device/share/users`: their worktrees were merged + removed; re-dispatch fresh if needed.

## Next (manager)
1. Stand up ollama/kimi worker(s) for the contained perf fix **#2307** + mechanical
   adaptive-nav items (#2333 SplittablePane desktop-only is a clean guard).
2. Opus worker for the structural iPhone NavigationSplitView adaptive collapse
   (#2329/#2100/#2334) — the "swiping columns" keystone.
3. Batch-verify after ~5 issues, push.
4. Remote TLS: app connecting via `macbook-pro-m1.local:8765` fails cert pinning
   (cert is loopback-only) → change-stream retry storm in runtime logs. Real
   remote-pairing bug, tracked #2382/#2157/#2162.
