## Multi-user login UX — SLICE 1 — 2026-07-03, f_fichero_claude_swiftui (#2021/#2022)

Made multi-user (`FICHERO_MULTIUSER=1`) usable: when the engine requires auth and
there's no valid session, the app now shows a native login (or first-run owner-setup)
screen instead of a library that 401/403s against its own backend. Typed FicheroClient
only (no raw URLSession); secrets in Keychain; passwords/tokens never logged; fails closed.
Build-gated: `xcodebuild build-for-testing` (isolated, scratch DD, CODE_SIGNING_ALLOWED=NO,
macOS) → `** TEST BUILD SUCCEEDED **`. NOT pushed.

### Backend contract wired (all via generated ops)
- `POST /api/auth/login {username,password,device_label}` → `{session_token,user}` (loginApiAuthLoginPost)
- `POST /api/auth/logout` (logoutApiAuthLogoutPost, best-effort revoke)
- `GET /api/auth/me` (meApiAuthMeGet) — 200 valid / 401 need-auth / 404 multiuser-off
- `POST /api/users` create-owner (createUserApiUsersPost, isOwner=true) — bootstrap-authed on first run
- `GET /api/users` (listUsersApiUsersGet) — first-run probe (works under loopback bootstrap token)

### Key design
The loopback bootstrap `.api-key` is owner-capable for admin endpoints but sets
`request.state.user = nil`, so it does NOT satisfy per-library authz — that's why the
library fails under multiuser. Fix: a real **session token**.
`AuthTokenMiddleware` now prefers a Keychain-stored session token when present; when none
exists (pre-login / first-owner bootstrap) it falls back to the bootstrap/device token, so
create-owner and the user-count probe still work. The gate is driven off the backend
`/api/auth/me` probe (not the Swift `multiuserEnabled` UserDefault), so the UI reflects the
engine's real state — no change needed to the EngineConfig stopgap.

### Files
- NEW `Models/SessionStore.swift` — `@Observable` auth store: `refresh()` (launch probe / session
  restore), `login`, `createOwner` (create + auto-login), `logout`; pure `nonisolated resolvePhase(...)`
  decision (unit-tested); `AuthError` with safe, category-only messages.
- NEW `Views/Auth/AuthGateView.swift` — login + first-run owner-setup forms (SecureField, semantic
  fonts, `.roundedBorder`, live validation, loading/error states; passwords held only in local @State).
- `AuthTokenMiddleware.swift` — session-token Keychain storage (persist/read/clear, host-scoped account
  `session-token|<host>`), preferred in `intercept`; added `/api/auth/login` to unauthenticated paths.
- `AppState.swift` — owns `sessionStore`; `checkBackendHealth()` calls `sessionStore.refresh()`.
- `ContentView.swift` — gate: shows `AuthGateView` when `!sessionStore.allowsLibraryAccess`.
- `FicheroApp.swift` — "Log Out <user>…" app-menu command (only when authenticated).

### Tests (fichero-tests, synchronized group — auto-included)
- `SessionStorePhaseTests.swift` — resolvePhase matrix (200→authed, 404→disabled, 401+0 accts→owner-setup,
  401+accts→login, nil/inconclusive→login fail-closed) + AuthError messages non-empty/distinct/leak-free.
- `AuthTokenMiddlewareStorageTests.swift` — session-token account host-scoping/normalization, no collision
  with the device-token account, `/api/auth/login` unauthenticated while `/me`+`/logout` are not.

### Stopped here / notes for follow-up
- Gate lives in `ContentView`; other window roots (`DocumentTabView`, iOS `FicheroApp_iOS`) still gate only
  on `isBackendRunning`. They flip once authed (shared session), but a dedicated iOS gate + secondary-window
  audit is worth a pass.
- Owner-setup requires password ≥ 8 chars (client-side); backend enforces only min_length 1.
- Did NOT run the suite (no-xcodebuild-test rule — would launch GUI); compile-gated only.

### SLICE 2 (later, not started)
In-app account management + role assignment (owner-only) over `POST/PATCH /api/users` + per-library authz,
and the per-tool access settings pane for agent-chat.
