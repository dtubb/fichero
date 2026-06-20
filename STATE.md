# STATE — autonomous manager session (2026-06-20, Daniel out / iPhone demo for Ann tonight)

Branch `0.0.2`, in sync with origin (`373a6f6e`). All pushes build-green via Xcode MCP
(`BuildProject` tab `windowtab5`) + backend pytest. verify_all run = exit 0 (guardrail
FAILs are pre-existing baseline, none name this session's files).

## ✅ DEMO PATH — shipped + verified this session
- **iOS multiple libraries + sidebar-first swipe nav** (#2329/#2334/#2394): registry-backed
  `iOSLibraryPickerMenu` (top bar) + `LibraryManager.switchToRemoteLibrary`; phone launches on
  the **sidebar/library list** (`preferredCompactColumn = .sidebar`); drill in → doc list →
  reader → inspector. Build 0 errors.
- **Per-page transcription scope** (#2303/#2395/#2396): root cause was `_whole_pdf_parent`
  set whenever `per_page_texts` was truthy incl. the 1-element per-page case → mis-routed
  page text. 14-line fix in `vision_base.py` + 17 passing unit tests. ICANH transcripts now
  land on the right page.
- **Liquid Glass bar** (#2041): `.glassEffect()` on MiniToolbar body (compiles + ships).
  NOTE: `.buttonStyle(.glass)/.glassProminent` are NOT in this SDK (build error) — reverted
  split buttons to plain+accent; per-button glass deferred until the API/SDK is confirmed.
- Earlier: recovered Codex toolbar work, worktrees 23→1, **Mac deploy target → macOS 26**,
  Dynamic-Type toolbar glyphs.

## 🔄 Running now
- `f_lane_reader` (sonnet) — iPhone reader/inspector swipe polish (#2331/#2332/#2100),
  worktree ~/code/fichero-worktrees/ios-reader-polish. Additive only.

## ⚠️ THE ONE THING THAT NEEDS DANIEL — Tailscale connectivity to Ann's phone
The iOS UI is ready, but for Ann's phone to actually reach the Mac's libraries the transport
must work. Runtime logs show the app hitting `https://macbook-pro-m1.local:8765` and failing
cert pinning (`-9807`, cert is loopback-only) → change-stream drops. The intended model
(memory): engine binds 127.0.0.1 + **`tailscale serve`** → tailnet-private HTTPS to localhost,
where Tailscale terminates TLS with a valid `*.ts.net` cert (no pinning issue). For the demo:
run `tailscale serve` on the Mac and point the iPhone app at the `<machine>.<tailnet>.ts.net`
host. This is a security-perimeter + tailscale-config call → left for Daniel, NOT auto-changed.
Tracked #2394 / #2382 / #2157 / #2162.

## Bugs filed this session
#2391 spatial zoom/xy-share · #2392 Activity empty (handrolled URLSession) · #2393 URLSession
guardrail · #2394 iOS↔Mac libraries · #2395/#2396 per-page (DONE) · #2397 cross-library DnD ·
#2398 AR/immersive Spaces (walls/floor + single-item floor projection).

## Operating rules (Daniel)
Min OS 26 everywhere, no back-deploy. Universal app + native Liquid Glass, Mac shell flexible.
Workers don't build — manager builds (Xcode MCP) + verify_all/pytest gate, lots of tests,
verify-before-push, iterate-never-replace, external worktrees, codex RATE-LIMITED till Jun 25
(using claude sonnet/opus lanes).

## Next (manager loop)
Integrate reader-polish when it lands (Xcode build gate). Then: per-button Liquid Glass once
SDK API confirmed; the .local/tailnet TLS (needs Daniel); #2392 Activity-empty + #2393 guardrail.
