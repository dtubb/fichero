(AI generated. Not reviewed.)

# Security Model

## Local-First Default

The engine binds to `127.0.0.1` by default. It refuses wildcard binds (`0.0.0.0` and `::`) and is not reachable from another machine over plain TCP without additional private transport.

To prevent other processes on the same Mac from calling the API, the engine generates a shared-secret token at startup and writes it to:

```
~/Library/Application Support/Fichero/.api-key
```

The file is created with mode `0600` (owner read/write only). Every HTTP request must carry this token:

```
Authorization: Bearer <token>
```

Requests without a valid token are rejected with `401`. The SwiftUI app reads the token from the same path at startup and injects it into every request via `APIClient`.

## FICHERO_MULTIUSER

The multi-user ACL layer is disabled by default. To enable it:

```bash
FICHERO_MULTIUSER=1 PYTHONPATH=fichero-server/src .venv/bin/uvicorn fichero_server.api.main:app --port 8765
```

When enabled:

- Per-library and per-folder access control is enforced in `fichero-server/src/fichero_server/security/authz.py`.
- Enforcement happens at two points: `registry.invoke` (for all mutations) and the read path (for queries).
- The authz layer is fail-closed: an unknown or missing permission is treated as a denial, not a pass-through.
- Permissions are stored per library and per folder. A user with library-level read cannot write to a folder unless they also hold folder-level write.

### Library sharing and members API

The current shipped sharing surface is built around the library-level authz
routes in `fichero-server/src/fichero_server/api/routes/authz.py`.

Current endpoints on `main`:

- `GET /api/authz/library` returns a `LibraryAuthzSnapshot` for the active
  library: whether multi-user mode is on, the current user's role, whether the
  current user can manage roles, and read/write answers for an optional target
  id.
- `GET /api/authz/members` returns `LibraryMembersResponse`, which joins
  library role rows with account profiles so the UI receives
  `user_id` + `username` + `display_name` + `is_owner_account` + `role`.
- `PUT /api/authz/members` accepts `SetLibraryRoleRequest` (`user`, `role`) and
  routes the role assignment through the audited `acl.set` action, then returns
  the refreshed member list.

Important built behavior:

- the members list is owner-gated when `FICHERO_MULTIUSER=1`
- role lookups normalize the library path before joining against
  `library_roles`, so role membership is keyed by the normalized library path
- the mutation path is audited because `PUT /api/authz/members` uses
  `registry.invoke(...)`, not a direct app-db write from the route

On the SwiftUI side, this shipped surface is already consumed by:

- `Views/Settings/Sharing/UsersSettingsView.swift`
- `Views/Sidebar/Sharing/LibrarySharingBadge.swift`
- `Services/ActionLibraryService.swift`

Those client paths use the generated OpenAPI surface plus hand-written service
wrappers; they do not special-case a second sharing protocol.

When disabled (the default), a single-user local trust model applies. The shared-secret token provides the only gate.

## Auth Actor

The actor recorded in every audit row comes exclusively from `request.state.user`. It is never taken from a body field, a query parameter, or a custom header supplied by the client.

This matters because route handlers pass `request.state.user` directly to `ActionContext`:

```python
ctx = ActionContext(actor=request.state.user, origin_window=request.headers.get("X-Window-Id"))
await registry.invoke("entity.merge", params, ctx)
```

The value in `request.state.user` is set by the authentication middleware after verifying the token. A client cannot forge it by adding an `actor` field to the request body. All audit attribution is therefore trustworthy by construction.

Contributor rule: never use a client-supplied identity field as the actor. Always derive it from `request.state`.

## Tailscale Transport for Remote Access

For iPad or remote access, the setup is:

1. The engine continues to bind to `127.0.0.1:8765`, with no change there.
2. `tailscale serve` creates a tailnet-private HTTPS URL that proxies to localhost.

```bash
tailscale serve https / http://127.0.0.1:8765
```

This exposes the API only to devices on your Tailscale tailnet. It is not publicly reachable, and the engine process still listens only on loopback.

Do not use `tailscale funnel`. Funnel exposes the service to the public internet.

Tailscale is transport. It provides network-level access control (tailnet vs. internet). User-vs-user authorization is a separate concern, handled by the `FICHERO_MULTIUSER` / `fichero-server/src/fichero_server/security/authz.py` layer. The two concerns are independent.

`FICHERO_BIND_HOST` is loopback-only by default. Binding the engine directly to
a non-loopback address requires the explicit escape hatch
`FICHERO_ALLOW_NON_LOOPBACK_BIND=I_UNDERSTAND_SHARED_SECRET_RISK` and emits a
runtime warning. That mode is for owner-debugging only; it is not the supported
remote-access path.

The shared-secret token remains required behind Tailscale. Treat the token as a
password: do not commit it, paste it into shared logs, or use it as a substitute
for user/object authorization. For setup details, see
[Tailscale private transport for Fichero](./remote-backend-tailscale.md).

Summary of what each layer does:

| Layer | What it controls |
|---|---|
| `127.0.0.1` binding | Prevents other machines reaching the API directly |
| Shared-secret token | Prevents other apps on the same Mac from calling the API |
| `tailscale serve` | Extends local access to trusted tailnet devices |
| `FICHERO_MULTIUSER` / `fichero-server/src/fichero_server/security/authz.py` | Per-library/folder access control between user accounts |

## Audit Chain

Every mutation through the action registry writes an `action_audit` row that records the actor, the before/after snapshots, and the timestamp. See [action-registry.md](./action-registry.md) for the full schema.

An HMAC-keyed tamper-evidence chain across `action_audit` rows is in progress (#2127). Once shipped, each row will include a chain sequence number and an HMAC over the previous row's hash, making undetected deletion or reordering of audit records infeasible.

## Contributor Checklist

- No mutation should bypass `registry.invoke`. Route handlers must not write to DuckDB directly.
- No auth check should trust client-supplied identity. Always use `request.state.user`.
- New routes that need multi-user access control must call into `fichero-server/src/fichero_server/security/authz.py` at the read path. `registry.invoke` handles the write path automatically.
- Do not expose the engine on `0.0.0.0` for any reason, including local development. `127.0.0.1` plus `tailscale serve` covers every legitimate remote-access need.
