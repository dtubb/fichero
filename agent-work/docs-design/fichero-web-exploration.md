# fichero-web — feasibility exploration (#2563)

Status: **exploration / proposal only. No commitment, no product code.** This
document maps what the codebase already provides toward a browser front-end for
Fichero, sketches viable approaches, names the hard problems, and recommends a
smallest first step. Every claim is grounded in code cited inline.

The question: *could a `fichero-web` — a website front-end — be built alongside
the SwiftUI app, talking to the same engine?*

Short answer: **yes, and the engine is already most of the way there for a
read-only viewer** — it already serves browser-renderable HTML and a complete
HTTP API. The gap is not "build a backend"; it's "decide how a browser
authenticates and reaches a loopback-first engine, and how much interaction the
web surface needs."

---

## (a) What already exists toward this

### 1. The engine already serves browser HTML — the `/view/...` routes

`fichero-engine/src/fichero/api/routes/views.py` mounts two HTML routes (router
registered in `_CORE_ROUTE_SPECS`, `fichero-engine/src/fichero/api/main.py`, as
`(views.router, "", ["views"])` — so they ship in the default release tier):

- `GET /view/document/{doc_id}` → `document_view()` — builds a JSON payload
  (document transcript + document-scoped entities + claims) and renders it into
  a Jinja2 template.
- `GET /view/kg/global` → `global_kg_view()` — same template, fed the whole
  library's entities + claims (no document scoping).

Both render the **same single template**:
`fichero-engine/src/fichero/api/templates/document_view.html` — a ~51 KB
self-contained HTML+JS bundle. The Python route injects `document_json`,
`entities_json`, `claims_json` as `<script>`-embedded JSON; all the rendering
(KG graph, reader, inspector) happens client-side in that one file. There is no
other `.html`/`.js`/`.css` asset under `api/` — it is a single monolithic page.

This template is **already loaded in a browser engine today**: the SwiftUI app's
`fichero/fichero/Views/Library/DocumentKGWebPane.swift` loads
`\(baseURL)/view/document/{id}` and `\(baseURL)/view/kg/global` into a
`WKWebView`, attaching the `X-Fichero-Library-Path` header (see
`DocumentKGPaneRouteTests.swift`, `InspectorLayoutTests.swift`). So the KG +
reader surface the user sees in the app is **already a web page** — WebKit is
just the host. A real browser pointed at the same URL (with the library header
and TLS/auth satisfied) would render the same thing.

> Most important consequence: a **read-only web reader already exists in
> embryo.** It is one un-navigable page per document/KG — no library list, no
> links between documents, no chrome, no editing — but the renderer, the data
> assembly, and the HTTP plumbing are done.

There is also a latent static-export path: `fichero-engine/src/fichero/export_service.py`
has `_render_document_markdown()`, `_render_index(root, links)`, and
`_render_kg_placeholder()` — i.e. the engine can already emit a linked index +
per-document HTML/markdown offline. That is the seed of approach (C) below and
aligns with the standing IIIF + 11ty static-site vision (MEMORY:
*iiif-interchange-static-site-vision*).

### 2. The API is a clean, complete OpenAPI surface

`_CORE_ROUTE_SPECS` registers ~80 routers, essentially all under `/api/*`:
documents, folders, entities, claims, claim-links, search, chat, workflows,
workflow-execution, annotations, notes, projects, artifacts, storage, KG
(graph/render/sparql/predictions/curation/…), hermeneutics, mind-palace, IIIF,
the action registry (`/api/actions/invoke`), auth/users/pairing, and more.

This surface is **already consumed by a browser-shaped client**: the SwiftUI app
talks to it exclusively through the generated OpenAPI client
(`fichero/fichero-api-client/Sources/FicheroAPIClient/FicheroClient.swift`) with
`LibraryPathMiddleware` injecting `X-Fichero-Library-Path` on every call
(`LibraryPathMiddleware.swift`). The CLI mirrors the same surface via
`fichero-engine/src/fichero/cli/openapi_surface_generated.py`. The app is
**functionally already an API client** — virtually all behaviour is HTTP calls
to `/api/*`, not local logic. A web SPA would generate a TypeScript client from
the very same `openapi.json` the Swift client is generated from.

CORS is already permissive for browsers in dev: `_get_cors_origins()` returns
`http://localhost:*`, `http://127.0.0.1:*`, the `https://` equivalents, and
`app://localhost`; production requires explicit `FICHERO_CORS_ORIGINS`.

### 3. Auth / transport model as it stands

- **TLS + SPKI pinning** (#2538, #2376/#2370): the engine serves HTTPS on
  loopback; the SwiftUI app pins the server's public-key (SPKI) **fail-closed**.
  A plain-HTTP engine is unreachable from the app.
- **Bearer token**: `attach_auth_middleware(app, token)`
  (`fichero-engine/src/fichero/api/auth.py`) enforces
  `Authorization: Bearer <token>`; the token is generated/persisted in
  Application Support (`initialize_token()`). Unauthenticated paths are limited:
  `_UNAUTHENTICATED_PATHS = {/api/health, /api/auth/login, …}` and prefixes
  `/docs/`, `/redoc/`. Direct loopback clients are trusted
  (`_is_loopback_request`, `_LOOPBACK_HOSTS = {127.0.0.1, ::1}`); multi-user
  session auth is feature-flagged (`_use_multiuser_auth`, `FICHERO_MULTIUSER`).
- **Per-library selection**: every data request carries
  `X-Fichero-Library-Path`; the path is validated server-side
  (`_is_allowed_library_path`, `_configured_library_allowed_roots`) and gated by
  per-library/folder ACL (`assert_library_read_authorized`,
  `assert_library_write_authorized`).
- **Accounts + pairing exist**: `auth_accounts` (login → session token),
  `pairing` (QR device pairing over Bonjour+TLS), and a bootstrap-secret HMAC
  server-proof handshake (`_with_server_proof`). Remote reach is via
  `tailscale serve` (tailnet-private HTTPS to localhost), never Funnel — see
  MEMORY *loopback-tailscale-serve-transport* and *device-connection-auth-design*.

---

## (b) Viable approaches

### Approach A — Extend the server-rendered `/view` routes into a full app (SSR)

Grow `views.py` + `document_view.html` (plus a new `/view/library` index using
`export_service._render_index`) into a navigable, server-rendered site: a
library list, document/KG pages that link to each other, and write actions that
`fetch()` the existing `/api/actions/invoke` and resource endpoints.

- **Pros**: reuses the renderer, the data-assembly code, and the single-origin
  story (page and API on the same host → no CORS, cookies "just work"). Smallest
  delta from what ships today. No build toolchain.
- **Cons**: `document_view.html` is a read-only monolith; turning it into a full
  app means re-implementing the SwiftUI app's interaction model in hand-written
  JS inside one template — exactly the kind of parallel re-implementation the
  *iterate, never replace* rule warns against if it drifts from the app.

### Approach B — Separate SPA against the OpenAPI

A standalone web app (React/Svelte/SolidJS/etc.) consuming a TypeScript client
generated from the same `openapi.json`, with a login flow against
`/api/auth/login` and `X-Fichero-Library-Path` sent per request.

- **Pros**: full functionality, clean separation, the API is already designed
  for exactly this consumer, generated client keeps it in lockstep with the
  backend contract.
- **Cons**: a whole second front-end to build and maintain in parallel with
  SwiftUI; duplicates view logic, stores, and the observable-data-layer model
  (MEMORY *observable-data-layer*) in a different stack. Largest cost. Inherits
  every hard problem in (c).

### Approach C — Thin static published site (read-only)

Use the existing export path (`export_service._render_index` /
`_render_document_markdown`) to pre-render a static, navigable archive site
(HTML, IIIF manifests, annotations) hosted on GitHub Pages / Netlify / 11ty.

- **Pros**: no live engine, no auth/transport problem at all, publishable to the
  open web safely, directly matches the standing IIIF + static-site vision.
- **Cons**: read-only snapshot; no editing, no live KG queries, no chat. It's a
  *publishing* feature, not an *application* — a different product goal.

---

## (c) The hard problems (browser vs pinned-loopback app)

1. **Certificate pinning doesn't transfer to browsers.** The app pins the
   loopback SPKI fail-closed; a browser pointed at `https://127.0.0.1:8765`
   sees a self-signed cert and throws a TLS interstitial. There is no
   browser-side equivalent of `RemoteCertificatePinning`. The clean answer is
   **not** to pin in-browser but to front the engine with `tailscale serve`,
   which terminates a *valid* HTTPS cert for the tailnet hostname — the already-
   sanctioned remote transport. (Never Funnel / never public.)

2. **A browser has no Keychain/Application-Support token.** The app reads the
   Bearer token from disk; a browser can't. A web client needs a real login flow
   (`/api/auth/login` → session token in an httpOnly cookie or localStorage),
   then sends it on every call. Loopback-trust (`_is_loopback_request`) papers
   over this only for a same-machine browser; any remote/tailnet browser must
   authenticate for real. Note top-level navigations (not `fetch`) can't carry an
   `Authorization` header — SSR (approach A) needs cookie auth, not Bearer.

3. **Per-library selection + ACL.** Every request needs
   `X-Fichero-Library-Path`, validated against allowed roots. A web user needs a
   library picker, and the server must expose only permitted libraries
   (`_configured_library_allowed_roots`, ACL via `FICHERO_MULTIUSER`). For a
   remote engine the library lives on the server, not the user's Mac.

4. **Who hosts the engine?** The engine is loopback-first by design. A web
   front-end only makes sense in two shapes: (i) **same-machine** localhost
   browser — but then the native app already exists and is better; or (ii) a
   **hosted/tailnet engine** reached over `tailscale serve` — which pulls in
   multi-user accounts (#2021/#2022), real auth, and ACL as first-class, not
   feature-flagged. The interesting `fichero-web` is shape (ii), and it is
   gated on the multi-user account work, not on rendering.

---

## (d) Recommended smallest first step

**Add one navigable read-only shell route and confirm it loads in a real browser
over `tailscale serve` — reusing everything that exists, adding zero new auth or
build infrastructure.**

Concretely (when/if Daniel wants to pursue it):

1. Add `GET /view/library` to `views.py` that renders a navigable index
   (library + document list + a link to `/view/kg/global`), reusing
   `export_service._render_index` and the existing template/renderer. Wire the
   existing `/view/document/{id}` links so the read-only reader is *browsable*,
   not one-page-at-a-time.
2. Serve it over `tailscale serve` (valid cert, tailnet-private) and load it in
   Safari/Chrome with the loopback-trust path satisfied.

That converts the already-served, already-rendering HTML into a real (read-only)
**web reader** with essentially no new code and no new attack surface — and it
directly tests the two things that actually matter (browser transport without
in-browser pinning, and whether the existing renderer is enough). Decide on
approach A vs B *after* seeing that, not before.

## (e) What this would explicitly NOT do (scope guard)

- **Not** a second full editing front-end. The first step is read-only; editing
  is a later, separate decision (and would lean on `/api/actions/invoke`, not
  bespoke JS).
- **Not** public-internet hosting. No Tailscale Funnel, no exposed engine. Reach
  is loopback or tailnet-private only.
- **Not** a replacement for the SwiftUI app. The native app stays the primary
  surface; `fichero-web` is an *additional* reach, per *iterate, never replace*.
- **Not** in-browser certificate pinning or any workaround for the app's
  pinning model — the browser uses a valid cert via `tailscale serve` instead.
- **Not** a commitment to a JS framework or build pipeline. Approach A keeps us
  framework-free until there's a proven need for a SPA.
- **Not** a multi-user auth project. If shape (ii) (hosted engine) is the goal,
  that is gated on the existing accounts/ACL epics (#2021/#2022), tracked
  separately — this exploration only flags the dependency.
