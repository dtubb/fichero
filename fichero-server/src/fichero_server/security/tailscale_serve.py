"""Share over Tailscale: the engine puts its own loopback listener on the tailnet (#2603).

The ruled transport is loopback + ``tailscale serve`` (never a raw public bind, never funnel).
With a ``.ts.net`` sharing address the engine binds 127.0.0.1 only (#5311), and
``tailscale serve --https=<port> https+insecure://127.0.0.1:<port>`` publishes it: Tailscale
terminates TLS with the tailnet host's public certificate, which is what the app expects of a
``.ts.net`` host (it holds no pin for one, #5041), and proxies to the engine on loopback. A raw
TCP forward (#5311's first form) handed devices the engine's self-signed certificate, so no app
could pair, and made every tailnet peer look like loopback to the engine (#5320); behind the
HTTPS proxy, Tailscale's forwarding headers mark them as remote. The engine sets the forward up
at start and removes it at stop, but only the one it made: a forward the person configured
themselves is never overwritten or removed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Mapping
from urllib.parse import urlparse

TAILNET_URL_ENV = "FICHERO_TAILNET_URL"
PUBLIC_BASE_URL_ENV = "FICHERO_PUBLIC_BASE_URL"
# The Mac app's own binary is the CLI; `/usr/local/bin/tailscale` exists only after the
# person chose "Install CLI" from Tailscale's menu, so it cannot be relied on.
APP_BUNDLE_CLI = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"


def tailscale_cli() -> str | None:
    """The tailscale CLI to run, or None when Tailscale is not installed."""
    found = shutil.which("tailscale")
    if found:
        return found
    return APP_BUNDLE_CLI if os.path.exists(APP_BUNDLE_CLI) else None


def tailnet_url(env: Mapping[str, str] | None = None) -> str:
    """The tailnet address this engine is shared at, or "" when it is not shared over Tailscale.

    ``FICHERO_TAILNET_URL`` when set; otherwise the sharing address itself when it is a
    ``.ts.net`` name -- the app sets only the sharing address, so without this a pairing code
    never carried the tailnet URL.
    """
    source = env if env is not None else os.environ
    explicit = (source.get(TAILNET_URL_ENV) or "").strip()
    if explicit:
        return explicit
    public = (source.get(PUBLIC_BASE_URL_ENV) or "").strip()
    host = (urlparse(public).hostname or "").lower() if public else ""
    return public if host.endswith(".ts.net") else ""


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, check=True, text=True, timeout=20)


def serve_status(cli: str) -> dict:
    return json.loads(_run([cli, "serve", "status", "--json"]).stdout or "{}")


def forward_target(status: dict, port: int) -> str | None:
    """What the tailnet ``port`` serves: an HTTPS proxy's target ("https+insecure://127.0.0.1:8765"),
    "tcp://<target>" for a raw TCP forward, "https" or "other" when unreadable, None when free."""
    entry = (status.get("TCP") or {}).get(str(port))
    if not entry:
        return None
    if entry.get("TCPForward"):
        return f"tcp://{entry['TCPForward']}"
    if not entry.get("HTTPS"):
        return "other"
    for host_port, web in (status.get("Web") or {}).items():
        if host_port.endswith(f":{port}"):
            proxy = ((web.get("Handlers") or {}).get("/") or {}).get("Proxy")
            if proxy:
                return proxy
    return "https"


def wanted_target(port: int) -> str:
    """The engine's own loopback TLS listener, proxied without re-verifying its self-signed
    certificate: the hop never leaves this Mac."""
    return f"https+insecure://127.0.0.1:{port}"


def ensure_forward(port: int, cli: str) -> bool:
    """Publish this engine's loopback listener on the tailnet ``port`` over Tailscale's HTTPS.

    Returns True when this call created the forward (so the caller removes it at stop), False
    when it was already in place. Raises RuntimeError -- never overwrites -- when the port
    already serves something else, or when the forward did not take. The one exception is the
    raw TCP forward to this same listener that earlier engines made (#5320): it is replaced.
    """
    want = wanted_target(port)
    current = forward_target(serve_status(cli), port)
    if current == want:
        return False
    if current == f"tcp://127.0.0.1:{port}":
        _run([cli, "serve", f"--tcp={port}", "off"])
    elif current is not None:
        raise RuntimeError(
            f"tailnet port {port} already serves {current!r}; not replacing a forward "
            "Fichero did not make"
        )
    _run([cli, "serve", "--bg", f"--https={port}", want])
    if forward_target(serve_status(cli), port) != want:
        raise RuntimeError(f"tailscale serve did not publish tailnet port {port} as {want}")
    return True


def remove_forward(port: int, cli: str) -> None:
    _run([cli, "serve", f"--https={port}", "off"])


def start_for_engine(env: Mapping[str, str] | None = None, *, log) -> tuple[str, int] | None:
    """At engine start: forward the tailnet port when sharing over Tailscale with a TLS listener.

    Returns ``(cli, port)`` when this engine created the forward -- hand it to
    ``stop_for_engine`` -- else None. Never raises: a failure is a WARNING naming the cause
    (and the remote-backend status reports the forward missing), not a failed launch.
    """
    source = env if env is not None else os.environ
    # Any engine with a TLS listener: the app's (FICHERO_TCP_TLS_ALSO sets the certificate too)
    # and start_fichero_server.sh's, which never set that flag and so never forwarded (#5320).
    if not tailnet_url(source) or not (source.get("FICHERO_TLS_CERTFILE") or "").strip():
        return None
    port = int(source.get("FICHERO_TCP_PORT", "8765"))
    cli = tailscale_cli()
    if cli is None:
        log.warning("Sharing over Tailscale, but Tailscale is not installed: nothing forwards port %d", port)
        return None
    try:
        created = ensure_forward(port, cli)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        log.warning("Sharing over Tailscale: could not forward tailnet port %d: %r", port, exc)
        return None
    log.info("Sharing over Tailscale: https on tailnet port %d -> 127.0.0.1:%d (%s)", port, port,
             "created" if created else "already in place")
    return (cli, port) if created else None


def stop_for_engine(made: tuple[str, int] | None, *, log) -> None:
    """At engine stop: remove the forward this engine created, and only that one."""
    if made is None:
        return
    cli, port = made
    try:
        remove_forward(port, cli)
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("Sharing over Tailscale: could not remove the forward on port %d: %r", port, exc)
