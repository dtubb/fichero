"""
Fichero Backend Entry Point

Starts the FastAPI backend server for Briefcase.
Defaults to dev hot-reload when running from a Briefcase dev bundle, and
defaults to production behavior otherwise.
"""

from __future__ import annotations

import argparse
import logging
import os
import pathlib
import socket
import sys
import faulthandler
import tracemalloc
import warnings

from fichero.security.bind_host import resolve_bind_host
from fichero.security.bind_host import resolve_lan_bind_host
from fichero.security.security_scoped_access import activate_library_bookmarks
from fichero.security.remote_access_tls import (
    material_manifest_json,
    prepare_remote_access_tls,
    uvicorn_ssl_kwargs_from_env,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


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


def _bind_uds_socket(uds_path: str) -> socket.socket:
    """Bind a Unix-domain stream socket, unlinking any stale path first.

    A stale socket file left behind by a crashed engine makes ``bind()`` fail
    with ``EADDRINUSE`` and blocks respawn, so unlink immediately before bind.
    """
    # CRITICAL: remove a stale socket left by a prior crash before binding.
    pathlib.Path(uds_path).unlink(missing_ok=True)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(uds_path)
    sock.listen(socket.SOMAXCONN)
    sock.setblocking(False)
    return sock


def _env_flag(name: str, default: bool = False) -> bool:
    """Parse a boolean env var with common truthy values."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _is_briefcase_dev_bundle() -> bool:
    """
    Detect Briefcase dev runtime path.

    Briefcase dev installs into a path like:
    .../.briefcase/<app>/dev.cpython-312-darwin/...
    """
    candidates = [
        os.path.abspath(__file__),
        os.path.abspath(sys.executable),
        os.path.abspath(os.environ.get("VIRTUAL_ENV", "")),
        os.path.abspath(os.getcwd()),
    ]
    return any(".briefcase" in p and "dev.cpython" in p for p in candidates if p)


def main(argv: list[str] | None = None):
    """Start the Fichero API backend server."""

    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--prepare-local-access", action="store_true")
    parser.add_argument("--prepare-remote-access", action="store_true")
    parser.add_argument("--public-base-url")
    parser.add_argument("--remote-access-dir")
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

    # Disable tokenizers parallelism (avoids fork warnings)
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    # Keep fatal thread dumps off by default; enable only when explicitly debugging crashes.
    fault_enabled = _env_flag("FICHERO_BACKEND_FAULTHANDLER", default=False)
    if fault_enabled:
        if not faulthandler.is_enabled():
            faulthandler.enable(all_threads=True)
        logger.info("Faulthandler: ENABLED")
    else:
        # If the parent process enabled it globally (e.g., PYTHONFAULTHANDLER=1), disable for clean logs.
        if faulthandler.is_enabled():
            faulthandler.disable()
            logger.info("Faulthandler: DISABLED")
    # Keep asyncio debug noise off by default; opt in with FICHERO_ASYNCIO_DEBUG=1.
    if _env_flag("FICHERO_ASYNCIO_DEBUG", default=False):
        os.environ["PYTHONASYNCIODEBUG"] = "1"
        logger.info("Asyncio debug: ENABLED")
    else:
        # Important: remove the var entirely; setting "0" still enables debug in some runtimes.
        os.environ.pop("PYTHONASYNCIODEBUG", None)
        # Suppress asyncio "Executing <Task ... took ...>" warning spam in normal runs.
        logging.getLogger("asyncio").setLevel(logging.ERROR)

    # Import uvicorn
    import uvicorn

    reload_enabled = _env_flag(
        "FICHERO_BACKEND_RELOAD",
        default=_is_briefcase_dev_bundle(),
    )
    # Workflow bug testing is much more stable without reloader subprocess churn.
    if _env_flag("FICHERO_BACKEND_STABLE_MODE", default=False):
        reload_enabled = False
    src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    # Enable traceback allocation context for ResourceWarning in dev mode.
    trace_enabled = _env_flag(
        "FICHERO_BACKEND_TRACEMALLOC",
        default=False,
    )
    if trace_enabled and not tracemalloc.is_tracing():
        tracemalloc.start(25)
        warnings.simplefilter("default", ResourceWarning)
        logger.info("Tracemalloc: ENABLED (ResourceWarning traces active)")

    # Sandboxed (Mac App Store) engine: the app hands us security-scoped bookmarks
    # for the user's libraries, because a dynamic Powerbox grant does NOT inherit
    # into a child process (#3747). Resolve them BEFORE anything opens a DuckDB
    # file — a plain open() on ~/Documents would be denied. A no-op when the env
    # var is unset, i.e. every non-sandboxed (DMG) run.
    activate_library_bookmarks()

    # UDS transport (additive, env-driven): when FICHERO_UDS_PATH is set, bind a
    # plaintext Unix-domain socket instead of TCP — no port, no TLS, no network
    # listener. TLS stays MANDATORY on the TCP path (below); the TCP-port
    # preflight is skipped here because there is no port. Auth trusts UDS via the
    # transport marker stamped by the wrapped app (fichero.api.uds_transport).
    uds_path = (os.environ.get("FICHERO_UDS_PATH") or "").strip()
    if uds_path:
        from fichero.api.uds_transport import app as uds_app

        uds_kwargs = dict(
            app=uds_app,
            workers=1,
            log_level="info",
            loop="asyncio",
            ws="websockets-sansio",
        )
        logger.info("Starting Fichero Backend (UDS transport)")
        logger.info("Server will listen on unix:%s (no TCP port, no TLS)", uds_path)
        uds_sock = _bind_uds_socket(uds_path)
        server = uvicorn.Server(uvicorn.Config(**uds_kwargs))
        try:
            server.run(sockets=[uds_sock])
        except KeyboardInterrupt:
            logger.info("Backend shutting down...")
        except Exception as e:
            logger.error(f"Backend failed to start: {e}")
            raise
        finally:
            uds_sock.close()
            pathlib.Path(uds_path).unlink(missing_ok=True)
        return

    bind_host = resolve_bind_host()
    listener_hosts = _listener_hosts(bind_host)

    uvicorn_kwargs = dict(
        app="fichero.api.main:app",
        host=bind_host,
        port=8765,
        workers=1,
        log_level="info",
        # Python 3.14 + uvloop can crash in asyncgen finalization paths.
        # Keep runtime stable by using the stdlib asyncio loop.
        # Force stdlib asyncio loop for stability with streaming + C extensions.
        loop="asyncio",
        ws="websockets-sansio",
        reload=reload_enabled,
    )
    if reload_enabled:
        # Limit reload scope to backend source to avoid whole-home scan noise.
        uvicorn_kwargs["reload_dirs"] = [src_dir]
    uvicorn_kwargs.update(uvicorn_ssl_kwargs_from_env())
    if len(listener_hosts) > 1 and "ssl_certfile" not in uvicorn_kwargs:
        raise SystemExit(
            "FICHERO_LAN_HOST requires TLS; set FICHERO_TLS_CERTFILE/FICHERO_TLS_KEYFILE."
        )
    if len(listener_hosts) > 1 and reload_enabled:
        raise SystemExit("FICHERO_LAN_HOST is not supported with reload enabled.")

    scheme = "https" if "ssl_certfile" in uvicorn_kwargs else "http"
    logger.info("Starting Fichero Backend (Briefcase bundle)")
    logger.info("Server will listen on %s://%s:8765", scheme, bind_host)
    if len(listener_hosts) > 1:
        logger.info("LAN TLS listener enabled on %s://%s:8765", scheme, listener_hosts[1])
    logger.info(
        "Hot-reload: %s",
        "ENABLED (dev mode)" if reload_enabled else "DISABLED (production mode)",
    )

    # Preflight port check avoids noisy socket ResourceWarning when bind fails.
    socket_family = socket.AF_INET6 if ":" in bind_host else socket.AF_INET
    with socket.socket(socket_family, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if sock.connect_ex((bind_host, 8765)) == 0:
            logger.error(
                "Port 8765 is already in use on %s. Stop the existing backend process and retry.",
                bind_host,
            )
            return

    if len(listener_hosts) == 1:
        try:
            uvicorn.run(**uvicorn_kwargs)
        except KeyboardInterrupt:
            logger.info("Backend shutting down...")
        except Exception as e:
            logger.error(f"Backend failed to start: {e}")
            raise
        return

    sockets = [_bind_listener_socket(host, 8765) for host in listener_hosts]
    server = uvicorn.Server(uvicorn.Config(**uvicorn_kwargs))
    try:
        server.run(sockets=sockets)
    except KeyboardInterrupt:
        logger.info("Backend shutting down...")
    except Exception as e:
        logger.error(f"Backend failed to start: {e}")
        raise
    finally:
        for sock in sockets:
            sock.close()


if __name__ == "__main__":
    main()
