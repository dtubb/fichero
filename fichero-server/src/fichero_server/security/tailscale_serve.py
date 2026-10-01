"""Share over Tailscale: the engine puts its own loopback listener on the tailnet (#2603).

The ruled transport is loopback + ``tailscale serve`` (never a raw public bind, never funnel).
With a ``.ts.net`` sharing address the engine binds 127.0.0.1 only (#5311), so nothing reaches
it until ``tailscale serve --tcp <port> tcp://127.0.0.1:<port>`` forwards the tailnet port to
it. A raw TCP forward, not an HTTPS proxy: the engine's own TLS -- and the device's SPKI pin --
hold end to end. The engine sets that forward up at start and removes it at stop, but only the
one it made: a forward the person configured themselves is never overwritten or removed.
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
    """What the tailnet ``port`` forwards to: "127.0.0.1:8765", "https" for an HTTPS
    terminator, or None when nothing is configured on it."""
    entry = (status.get("TCP") or {}).get(str(port))
    if not entry:
        return None
    return entry.get("TCPForward") or ("https" if entry.get("HTTPS") else "other")


def ensure_tcp_forward(port: int, cli: str) -> bool:
    """Forward the tailnet ``port`` to this engine's loopback listener.

    Returns True when this call created the forward (so the caller removes it at stop), False
    when it was already in place. Raises RuntimeError -- never overwrites -- when the port
    already serves something else, or when the forward did not take.
    """
    want = f"127.0.0.1:{port}"
    current = forward_target(serve_status(cli), port)
    if current == want:
        return False
    if current is not None:
        raise RuntimeError(
            f"tailnet port {port} already serves {current!r}; not replacing a forward "
            "Fichero did not make"
        )
    _run([cli, "serve", "--bg", "--tcp", str(port), f"tcp://{want}"])
    if forward_target(serve_status(cli), port) != want:
        raise RuntimeError(f"tailscale serve did not forward tailnet port {port} to {want}")
    return True


def remove_tcp_forward(port: int, cli: str) -> None:
    _run([cli, "serve", f"--tcp={port}", "off"])


def start_for_engine(env: Mapping[str, str] | None = None, *, log) -> tuple[str, int] | None:
    """At engine start: forward the tailnet port when sharing over Tailscale with a TLS listener.

    Returns ``(cli, port)`` when this engine created the forward -- hand it to
    ``stop_for_engine`` -- else None. Never raises: a failure is a WARNING naming the cause
    (and the remote-backend status reports the forward missing), not a failed launch.
    """
    source = env if env is not None else os.environ
    if not tailnet_url(source) or (source.get("FICHERO_TCP_TLS_ALSO") or "").strip() != "1":
        return None
    port = int(source.get("FICHERO_TCP_PORT", "8765"))
    cli = tailscale_cli()
    if cli is None:
        log.warning("Sharing over Tailscale, but Tailscale is not installed: nothing forwards port %d", port)
        return None
    try:
        created = ensure_tcp_forward(port, cli)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        log.warning("Sharing over Tailscale: could not forward tailnet port %d: %r", port, exc)
        return None
    log.info("Sharing over Tailscale: tailnet port %d -> 127.0.0.1:%d (%s)", port, port,
             "created" if created else "already in place")
    return (cli, port) if created else None


def stop_for_engine(made: tuple[str, int] | None, *, log) -> None:
    """At engine stop: remove the forward this engine created, and only that one."""
    if made is None:
        return
    cli, port = made
    try:
        remove_tcp_forward(port, cli)
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("Sharing over Tailscale: could not remove the forward on port %d: %r", port, exc)
