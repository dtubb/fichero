# 15. Remote Engines


### Tailscale (the supported remote model)

Keep the engine bound to loopback; let `tailscale serve` publish a tailnet-private HTTPS proxy to it. Do not bind to `0.0.0.0`, a LAN address, or a Tailscale `100.x` address, and never use `tailscale funnel` — funnel is the public internet, and the engine is not a public web service.

Trust boundary: Tailscale answers “can this device reach the service over the tailnet.” App-level authorization stays Fichero’s: the shared-secret token is still required, and `FICHERO_MULTIUSER=1` still owns per-library and per-folder permissions.

On the engine machine, from the repo:

    fichero-server/scripts/start_tailscale_backend.sh --fast

The launcher obtains a Tailscale certificate, keeps the engine on loopback TLS, starts `tailscale serve` proxying to `127.0.0.1:8765`, and advertises the certificate pin to paired clients. `tailscale serve status` shows the generated tailnet URL; the engine itself still only sees a loopback service.

Create a one-time iPhone/iPad pairing link by naming the library explicitly:

    scripts/create_tailscale_pairing_link.sh "$HOME/Documents/My Library.fichero"

Paste the emitted `fichero://pair?...` link into **Connect → Manual link** before it expires. It contains a short-lived pairing code and certificate pin — do not publish it. Remote CLI or MCP clients need a paired device credential, not the Mac’s bootstrap token:

    export FICHERO_API_URL=https://<engine-name>.<tailnet-name>.ts.net
    export FICHERO_API_KEY=<remote-token>
    export FICHERO_LIBRARY_PATH=/path/on/engine/Library.fichero
    PYTHONPATH=fichero-server/src:fichero-cli/src .venv/bin/python -m fichero_cli --json health

Library paths resolve on the engine machine — a client-side path is invalid unless the same path exists on the engine host. Token handling: treat the `.api-key` file as a password (never commit, paste, or log it; rotate by stopping the engine, deleting the file, restarting). Validation from a tailnet device: `curl -s https://<engine>.<tailnet>.ts.net/api/health` succeeds; protected endpoints return `401` until the remote token is supplied; nothing is bound to a non-loopback address.

### ACENET (SSH loopback forwarding)

For an HPC host, the model is the same loopback-only engine reached through an SSH tunnel instead of a tailnet. On the remote host, set `FICHERO_REMOTE_BACKEND=1` and `FICHERO_REMOTE_BACKEND_BIND_HOST=127.0.0.1` and start the engine on port 8765; from the Mac, `ssh -N -L 8765:127.0.0.1:8765 <user>@<host>` (add `-J <login-host>` for a compute node behind a login node) and fetch the remote `.api-key` for `FICHERO_API_KEY`. Startup fails deliberately if remote mode is combined with a non-loopback bind, and the health payload reports `remote_backend` diagnostics (`connection_model: "ssh-loopback"`).

A caveat: this lane is less verified than the Tailscale path — it sees CLI/MCP automation traffic more than day-to-day app use, and the Mac app has no explicit remote-token setting yet (app testing against it means copying the remote token into the Mac token file for the session). Expect the usual failure modes: connection refused (tunnel closed), `401` (local token used instead of remote), and empty library data (client-side path sent to the remote engine).
