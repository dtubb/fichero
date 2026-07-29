(AI generated. Not reviewed.)

# Running the Fichero backend remotely on ACENET

This is the supported connection model for using ACENET as the compute host while
the Mac app stays the UI: run the backend on ACENET bound to remote loopback,
then SSH-forward the remote `127.0.0.1:8765` to the Mac's `127.0.0.1:8765`.

Keep the backend private. Do not bind it to `0.0.0.0`; the API is designed for a
loopback client and also rejects non-loopback requests in middleware.

This page covers SSH loopback forwarding for ACENET. For a lab machine reached
over a tailnet, use the same loopback-only engine model with
[`tailscale serve`](./remote-backend-tailscale.md). Do not use `tailscale funnel`
or bind the engine directly to a Tailscale, LAN, or public address.

## Start the engine on ACENET

On the ACENET host:

```bash
cd ~/code/fichero
export FICHERO_REMOTE_BACKEND=1
export FICHERO_REMOTE_BACKEND_BIND_HOST=127.0.0.1
PYTHONPATH=fichero-server/src /path/to/.venv/bin/python -m fichero_cli engine start --port 8765
```

If you want foreground logs instead of the detached engine manager:

```bash
cd ~/code/fichero
export FICHERO_REMOTE_BACKEND=1
export FICHERO_REMOTE_BACKEND_BIND_HOST=127.0.0.1
PYTHONPATH=fichero-server/src /path/to/.venv/bin/uvicorn fichero_server.api.main:app \
  --host 127.0.0.1 \
  --port 8765
```

The engine writes its bearer token on the remote host at:

```bash
"$HOME/Library/Application Support/Fichero/.api-key"
```

## Open the SSH tunnel from the Mac

If you can SSH directly to the host running the backend:

```bash
ssh -N -L 8765:127.0.0.1:8765 <user>@<acenet-host>
```

If the backend runs on a compute node reached through a login node, use
ProxyJump:

```bash
ssh -N -J <user>@<login-host> -L 8765:127.0.0.1:8765 <user>@<compute-node>
```

Leave this SSH process running. The Mac app is hardcoded today to
`http://127.0.0.1:8765`, so the app-compatible tunnel must normally use local
port `8765`. If local port `8765` is occupied, use another local port for CLI
or MCP work:

```bash
ssh -N -L 18765:127.0.0.1:8765 <user>@<acenet-host>
export FICHERO_API_URL=http://127.0.0.1:18765
```

## Auth token

The health endpoint is unauthenticated, but library operations require
`Authorization: Bearer <token>`. The Python CLI and MCP server discover the
local token file by default; when using a remote backend they need the remote
token instead:

```bash
export FICHERO_API_KEY="$(ssh <user>@<acenet-host> \
  'cat "$HOME/Library/Application Support/Fichero/.api-key"')"
```

The Swift app reads the same token path on the Mac. For app testing against a
remote backend, copy the remote token into the Mac token file for the session,
or run only unauthenticated health checks until the Swift side grows an explicit
remote-backend token setting. Preserve the previous local token if you still
need a local engine:

```bash
mkdir -p "$HOME/Library/Application Support/Fichero"
cp "$HOME/Library/Application Support/Fichero/.api-key" \
  "$HOME/Library/Application Support/Fichero/.api-key.local-backup" 2>/dev/null || true
ssh <user>@<acenet-host> \
  'cat "$HOME/Library/Application Support/Fichero/.api-key"' \
  > "$HOME/Library/Application Support/Fichero/.api-key"
chmod 600 "$HOME/Library/Application Support/Fichero/.api-key"
```

## Library paths

The backend resolves all library and source paths on the machine where the
backend runs. A Mac path such as `/Users/daniel/Documents/Book.fichero` is not a
valid ACENET path unless that path also exists there.

For CLI and MCP calls, set the remote `.fichero` package path explicitly:

```bash
export FICHERO_API_URL=http://127.0.0.1:18765
export FICHERO_API_KEY=<remote-token>
export FICHERO_LIBRARY_PATH=/remote/project/Library.fichero
PYTHONPATH=fichero-server/src /path/to/python -m fichero_cli --json health
```

For the Mac app, open a library whose path can be resolved by the remote backend
or expect library-specific calls to fail with a missing or invalid
`X-Fichero-Library-Path` context. In practice, remote-heavy workflows should use
a library package stored on ACENET and CLI/MCP automation until the Swift UI has
an explicit remote-library path control.

## Validation

From the Mac, with the tunnel running:

```bash
curl -s http://127.0.0.1:8765/api/health
```

The health payload includes `remote_backend` diagnostics. In remote mode,
expect:

```json
{
  "remote_backend": {
    "enabled": true,
    "connection_model": "ssh-loopback",
    "token_configured": true,
    "library_path_configured": true
  }
}
```

If `FICHERO_REMOTE_BACKEND=1` is set with
`FICHERO_REMOTE_BACKEND_BIND_HOST=0.0.0.0` or another non-loopback host, startup
fails. Remote mode is intentionally SSH-loopback only.

For the general engine bind host, `FICHERO_BIND_HOST` defaults to `127.0.0.1`.
Wildcard binds (`0.0.0.0` and `::`) are refused. Other non-loopback values are
allowed only with
`FICHERO_ALLOW_NON_LOOPBACK_BIND=I_UNDERSTAND_SHARED_SECRET_RISK`, which is an
owner-debugging escape hatch and not the supported remote-backend model. The
shared-secret token is not an internet-facing auth boundary.

For CLI validation against an alternate local tunnel port:

```bash
export FICHERO_API_URL=http://127.0.0.1:18765
export FICHERO_API_KEY=<remote-token>
PYTHONPATH=fichero-server/src /path/to/python -m fichero_cli --json health
```

Expected failure modes:

- `connection refused`: the engine is not running, the tunnel is closed, or the
  local port is wrong.
- `401 missing or invalid Authorization header`: the Mac/CLI is using the local
  token instead of the remote token.
- `403 loopback only`: the backend was exposed over the network instead of
  reached through SSH loopback forwarding.
- missing or empty library data: `X-Fichero-Library-Path` points at a Mac path
  or a non-existent remote `.fichero` package.
