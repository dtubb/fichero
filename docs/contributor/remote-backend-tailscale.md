(AI generated. Not reviewed.)

# Tailscale private transport for Fichero

This is the supported model for using one Fichero engine from another device on
your tailnet: keep the engine bound to loopback, then let `tailscale serve`
publish a tailnet-private HTTPS proxy to that loopback service.

Do not bind the engine to `0.0.0.0`, a LAN address, or a Tailscale `100.x`
address for normal remote access. Do not use `tailscale funnel`. Funnel exposes
the service on the public internet, and the Fichero engine is not a public web
service.

## Trust boundary

Tailscale is transport security. It answers "can this device reach the service
over the tailnet?" It does not answer "can this Fichero user read or edit this
library, folder, claim, or document?"

App-level authorization still belongs to Fichero:

- The shared-secret API token is still required for protected endpoints.
- Multi-user authorization, when enabled with `FICHERO_MULTIUSER=1`, still owns
  per-library and per-folder permissions.
- Tailscale ACLs can reduce which devices can reach the engine, but they are not
  a substitute for object-level app authorization.

## Start the engine

On the Mac or lab machine that owns the library, start the engine on loopback:

```bash
PYTHONPATH=fichero-server/src:fichero-cli/src .venv/bin/python -m fichero_cli engine start --port 8765
```

The default bind host is `127.0.0.1`. If you set it explicitly, keep it
loopback-only:

```bash
export FICHERO_BIND_HOST=127.0.0.1
PYTHONPATH=fichero-server/src:fichero-cli/src .venv/bin/python -m fichero_cli engine start --port 8765
```

Current bind behavior is:

- unset `FICHERO_BIND_HOST`: binds `127.0.0.1`
- `127.0.0.1`, `localhost`, or `::1`: allowed
- `0.0.0.0` or `::`: refused
- any other non-loopback host: refused unless
  `FICHERO_ALLOW_NON_LOOPBACK_BIND=I_UNDERSTAND_SHARED_SECRET_RISK` is set

That escape hatch is for owner-debugging only. It emits a runtime warning
because the shared-secret bootstrap token is not an internet-facing auth
boundary. It is not the supported remote-access path.

## Publish to the tailnet

Install and sign in to Tailscale on the engine machine and on each client
device. Then run this from the Fichero repository on the engine machine:

```bash
fichero-server/scripts/start_tailscale_backend.sh --fast
```

The launcher obtains a Tailscale certificate, keeps the engine on loopback TLS,
starts `tailscale serve` as `https+insecure://127.0.0.1:8765`, and advertises the
Tailscale certificate pin to paired clients. Use `tailscale serve status` to
inspect the generated tailnet URL. The engine itself still only sees a loopback
service.

Create a one-time iPhone/iPad manual pairing link by passing the library path on
the Mac explicitly:

```bash
scripts/create_tailscale_pairing_link.sh \
  "$HOME/Library/CloudStorage/Box-Box/Fichero Libraries/INCANH Ann New.fichero"
```

Paste the emitted `fichero://pair?...` link into **Connect → Manual link** before
it expires. The link contains a short-lived pairing code and certificate pin; do
not publish it. It is deliberately scoped to the supplied library rather than
guessing from the registry.

Do not run:

```bash
tailscale funnel 8765
```

Do not change the engine start command to:

```bash
--host 0.0.0.0
```

Both patterns create the wrong security boundary for Fichero.

## Token handling

The engine writes its API token on the engine host:

```bash
"$HOME/Library/Application Support/Fichero/.api-key"
```

The token authorizes API access once a request has reached the engine. Treat it
like a password:

- Do not paste it into shared shell history, tickets, chat, or documentation.
- Do not commit it to a repository.
- Copy it only to devices that should be able to call the engine.
- Rotate it by stopping the engine, deleting the token file on the engine host,
  and restarting the engine.

The health endpoint is unauthenticated, but library operations require:

```http
Authorization: Bearer <token>
```

CLI or MCP clients pointed at the Tailscale URL need a paired device credential,
not the Mac's bootstrap token. The iPhone/iPad app receives that credential by
redeeming the one-time pairing link above.

```bash
export FICHERO_API_URL=https://<engine-name>.<tailnet-name>.ts.net
export FICHERO_API_KEY=<remote-token>
export FICHERO_LIBRARY_PATH=/path/on/engine/Library.fichero
PYTHONPATH=fichero-server/src:fichero-cli/src .venv/bin/python -m fichero_cli --json health
```

The library path is resolved on the engine machine. A path from the client
device is not valid unless the same path also exists on the engine host.

## Validation

From a device on the tailnet:

```bash
curl -s https://<engine-name>.<tailnet-name>.ts.net/api/health
```

Expected properties:

- no public DNS or public internet exposure is required
- no engine process is bound to `0.0.0.0`, `::`, a LAN address, or a Tailscale
  address
- protected endpoints return `401` until the remote token is supplied
- user and object authorization still comes from Fichero, not Tailscale
