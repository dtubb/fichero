# fichero-cli

Thin command-line client for a running Fichero server. Every command is one
or two HTTP calls through `FicheroClient`; there is no backend logic here.

## Connecting

Zero setup against the running Fichero app: with the default base URL, when
nothing answers on `127.0.0.1:8765` and the app's engine socket exists, the
CLI dials that Unix socket directly — the engine trusts local socket
callers, and the credential is read from the app's key file automatically.

- `--base-url` / `FICHERO_API_URL` target a specific server (HTTPS).
- `FICHERO_UDS=<path>` forces a specific socket; `FICHERO_UDS=0` disables
  the socket probe.
- `-l / --library` (or `FICHERO_LIBRARY_PATH`) scopes commands to one
  `.fichero` library.

Run `fichero --help` for the command surface; `fichero workflow list` is a
good first probe.
