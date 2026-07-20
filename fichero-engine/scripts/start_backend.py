#!/usr/bin/env python3
"""Backend launcher for the bundled Fichero engine."""

from __future__ import annotations

import argparse
import logging
import os
import pathlib
import socket
import sys

# Shared with the engine entrypoint so the remote-access launch path uses the
# same bind-host policy as the rest of the backend.
from fichero.bind_host import resolve_lan_bind_host
from fichero.remote_access_tls import (
    material_manifest_json,
    prepare_remote_access_tls,
    uvicorn_ssl_kwargs_from_env,
)
from fichero.bind_host import resolve_bind_host

logger = logging.getLogger(__name__)

# The Swift app pins https://127.0.0.1:8765 fail-closed (#2376/#2370), so a
# plain-HTTP engine on that port is silently unreachable — the Activity SSE
# stream and every loopback call die with no error (#2538).
APP_LOOPBACK_PORT = 8765


def _warn_if_app_unreachable(scheme: str, port: int) -> None:
    """Loudly flag the HTTP-vs-pinned-HTTPS mismatch instead of a dead stream.

    Plain HTTP is a legitimate CLI-only dev choice, so we warn rather than
    raise — but we make the mismatch impossible to miss (Daniel's rule:
    log loudly, never fail silently).
    """
    if scheme == "http" and port == APP_LOOPBACK_PORT:
        logger.warning(
            "Engine is serving PLAIN HTTP on :%d but the Swift app pins "
            "https://127.0.0.1:%d fail-closed (#2538) — the Activity stream "
            "and all loopback calls from the app will silently fail. "
            "Launch via scripts/start_backend.sh (prepares loopback TLS), or "
            "set FICHERO_TLS_CERTFILE/FICHERO_TLS_KEYFILE, to serve HTTPS.",
            port,
            port,
        )


def _listener_hosts(bind_host: str) -> list[str]:
    lan_host = resolve_lan_bind_host()
    if lan_host is None or lan_host == bind_host:
        return [bind_host]
    return [bind_host, lan_host]


def _bind_listener_socket(host: str, port: int) -> socket.socket:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(socket.SOMAXCONN)
    sock.setblocking(False)
    return sock


def main(argv: list[str] | None = None) -> None:
    """Start the backend or prepare remote-access TLS material."""

    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--prepare-remote-access", action="store_true")
    parser.add_argument("--prepare-local-access", action="store_true")
    parser.add_argument("--public-base-url")
    parser.add_argument("--remote-access-dir")
    parser.add_argument("--reload", action="store_true")
    args, _remaining = parser.parse_known_args(argv)

    if args.prepare_local_access:
        subject_alt_hosts = []
        lan_host = (os.environ.get("FICHERO_LAN_HOST") or "").strip()
        if lan_host:
            subject_alt_hosts.append(lan_host)
        material = prepare_remote_access_tls(
            "https://127.0.0.1:8765",
            storage_root=args.remote_access_dir,
            allow_loopback=True,
            subject_alt_hosts=subject_alt_hosts,
        )
        sys.stdout.write(material_manifest_json(material))
        sys.stdout.write("\n")
        return

    if args.prepare_remote_access:
        if not args.public_base_url:
            raise SystemExit("--public-base-url is required for --prepare-remote-access")
        material = prepare_remote_access_tls(
            args.public_base_url,
            storage_root=args.remote_access_dir,
        )
        sys.stdout.write(material_manifest_json(material))
        sys.stdout.write("\n")
        return

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Detect if we're running from a bundle.
    bundle_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    is_bundled = bundle_dir.endswith(".app/Contents/Resources/python")

    if is_bundled:
        logger.info("Running from bundle: %s", bundle_dir)
        python_home = os.path.dirname(os.path.dirname(sys.executable))
        os.environ["PYTHONHOME"] = python_home
    else:
        logger.info("Running in development mode")

    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    import uvicorn

    # UDS transport (additive, env-driven): plaintext Unix-domain socket, no
    # port, no TLS, no network listener. TLS stays mandatory on the TCP path.
    uds_path = (os.environ.get("FICHERO_UDS_PATH") or "").strip()
    if uds_path:
        from fichero.api.uds_transport import app as uds_app

        # CRITICAL: unlink a stale socket from a prior crash before bind.
        pathlib.Path(uds_path).unlink(missing_ok=True)
        uds_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        uds_sock.bind(uds_path)
        uds_sock.listen(socket.SOMAXCONN)
        uds_sock.setblocking(False)
        logger.info("Starting Fichero backend on unix:%s (no TCP port, no TLS)", uds_path)
        server = uvicorn.Server(
            uvicorn.Config(app=uds_app, workers=1, log_level="info")
        )
        try:
            server.run(sockets=[uds_sock])
        finally:
            uds_sock.close()
            pathlib.Path(uds_path).unlink(missing_ok=True)
        return

    bind_host = resolve_bind_host()
    config: dict[str, object] = {
        "app": "fichero.api.main:app",
        "host": bind_host,
        "port": 8765,
        "workers": 1,
        "log_level": "info",
        "reload": args.reload,
    }
    config.update(uvicorn_ssl_kwargs_from_env())

    listener_hosts = _listener_hosts(bind_host)
    if len(listener_hosts) > 1 and "ssl_certfile" not in config:
        raise SystemExit("FICHERO_LAN_HOST requires TLS; set FICHERO_TLS_CERTFILE/FICHERO_TLS_KEYFILE.")
    if len(listener_hosts) > 1 and args.reload:
        raise SystemExit("FICHERO_LAN_HOST is not supported with --reload.")

    scheme = "https" if "ssl_certfile" in config else "http"
    logger.info("Starting Fichero backend on %s://%s:%d", scheme, bind_host, config["port"])
    if len(listener_hosts) > 1:
        logger.info("LAN TLS listener enabled on %s://%s:%d", scheme, listener_hosts[1], config["port"])
    logger.info("Hot-reload: %s", config["reload"])
    _warn_if_app_unreachable(scheme, int(config["port"]))
    if len(listener_hosts) == 1:
        uvicorn.run(**config)
        return

    uvicorn_config = uvicorn.Config(**config)
    server = uvicorn.Server(uvicorn_config)
    sockets = [_bind_listener_socket(host, int(config["port"])) for host in listener_hosts]
    try:
        server.run(sockets=sockets)
    finally:
        for sock in sockets:
            sock.close()


if __name__ == "__main__":
    main()
