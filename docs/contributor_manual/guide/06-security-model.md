# 6. Security Model


### Local-first default

The engine binds to `127.0.0.1` by default. It refuses wildcard binds (`0.0.0.0` and `::`) and is not reachable from another machine without additional private transport. To keep other processes on the same Mac out, the engine generates a shared-secret token at startup and writes it (mode `0600`) to:

    ~/Library/Application Support/Fichero/.api-key

Every HTTP request must carry `Authorization: Bearer <token>`; requests without a valid token get `401`. The SwiftUI app reads the token from the same path and injects it via `APIClient`. The health endpoint is unauthenticated.

`FICHERO_BIND_HOST` is loopback-only by default. Binding to a non-loopback address requires the explicit escape hatch `FICHERO_ALLOW_NON_LOOPBACK_BIND=I_UNDERSTAND_SHARED_SECRET_RISK` and emits a runtime warning — owner-debugging only, never the supported remote-access path.

### FICHERO_MULTIUSER

The multi-user ACL layer is disabled by default; enable it with `FICHERO_MULTIUSER=1` in the engine environment. When enabled:

- Per-library and per-folder access control is enforced in `fichero-server/src/fichero_server/security/authz.py`.
- Enforcement happens at two points: `registry.invoke` (all mutations) and the read path (queries).
- The layer is **fail-closed**: unknown or missing permission is a denial.
- A user with library-level read cannot write to a folder without folder-level write.

The shipped sharing surface is the library-level authz routes in `api/routes/auth/authz.py`: `GET /api/authz/library` (a `LibraryAuthzSnapshot` — multiuser on/off, current role, manage rights, read/write answers for an optional target), `GET /api/authz/members` (role rows joined with account profiles), and `PUT /api/authz/members`, which routes role assignment through the audited `acl.set` action. The members list is owner-gated under multiuser; role membership is keyed by the normalized library path. On the Swift side this is consumed through the generated client plus hand-written wrappers (`UsersSettingsView`, `LibrarySharingBadge`, `ActionLibraryService`) — no second sharing protocol.

When disabled (the default), a single-user local trust model applies: the shared-secret token is the only gate.

### Auth actor

The actor recorded in every audit row comes exclusively from `request.state.user`, set by the authentication middleware after verifying the token. It is never taken from a body field, query parameter, or custom header — a client cannot forge attribution by adding an `actor` field. Contributor rule: never use a client-supplied identity field as the actor.

### Remote transport

For iPad or remote access, the engine stays bound to loopback and `tailscale serve` publishes a tailnet-private HTTPS proxy to it. Tailscale is transport: it answers “can this device reach the service,” never “can this user edit this library” — that remains the `FICHERO_MULTIUSER`/authz layer’s job, and the shared-secret token remains required behind Tailscale. Never use `tailscale funnel` (public internet) and never bind the engine to `0.0.0.0`. Setup details are in chapter 15.

Summary of layers:

| Layer | What it controls |
|----|----|
| `127.0.0.1` binding | Other machines cannot reach the API directly |
| Shared-secret token | Other apps on the same Mac cannot call the API |
| `tailscale serve` | Extends access to trusted tailnet devices |
| `FICHERO_MULTIUSER` / `security/authz.py` | Per-library/folder control between user accounts |

### Contributor checklist

- No mutation bypasses `registry.invoke`; no direct DuckDB writes in routes.
- No auth check trusts client-supplied identity; always `request.state.user`.
- New routes needing multi-user control call into `security/authz.py` on the read path; `registry.invoke` handles the write path.
- Never expose the engine on `0.0.0.0`, including for local development.
- Anything touching auth, file I/O, network, secrets, or keychain gets a security review before merge.

------------------------------------------------------------------------
