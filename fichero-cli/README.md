# fichero-cli

Thin command-line client for a running Fichero server. Every command is one or
two HTTP calls through `FicheroClient`; there is no backend logic here.

Run `fichero --help` (or `python -m fichero_cli --help`) against a running
server. See `fichero-server/README.md` for how to start one.
