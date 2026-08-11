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
import signal
import socket
import sys
import faulthandler
import tracemalloc
import warnings

from fichero_server.security.bind_host import resolve_bind_host
from fichero_server.security.bind_host import resolve_lan_bind_host
from fichero_server.security.security_scoped_access import activate_library_bookmarks
from fichero_server.security.remote_access_tls import (
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


def _ignore_sigpipe() -> None:
    """Ignore SIGPIPE so a write to a hung-up client raises, not signals-kill.

    When the host app closes the Unix-domain (or TCP) socket after a request —
    e.g. it cancels a readiness probe, or tears down a connection right after a
    401 — uvicorn may still be mid-write to that peer. With SIGPIPE at its
    default disposition (SIG_DFL, which terminates the process), that write
    delivers SIGPIPE and the engine dies. The Swift terminationHandler then
    reads ``terminationStatus == 13`` and reports it as "code 13", and the
    crash-restart path trips the "start already in flight" guard (#3108) —
    the whole stuck-on-launch cascade starts from one dropped write.

    Setting SIG_IGN makes the kernel return ``EPIPE`` from the write instead,
    which Python surfaces as ``BrokenPipeError`` — caught and logged by uvicorn
    as a normal client-disconnect, leaving the engine alive. CPython usually
    installs this at interpreter start, but we set it explicitly and defensively
    here: the disposition can be inherited/reset across the Briefcase launch
    wrapper, and this path is the one that actually serves sockets. We force the
    stdlib asyncio loop (never uvloop) below, so nothing re-installs SIG_DFL
    after this.
    """
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_IGN)


def _env_flag(name: str, default: bool = False) -> bool:
    """Parse a boolean env var with common truthy values."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _reload_enabled() -> bool:
    """#4381: reload is OPT-IN (FICHERO_BACKEND_RELOAD=1), never inferred.

    It used to default ON for any Briefcase dev bundle — and the dev engine's
    source dir was the very tree the manager merges lane branches into, so
    every merge tripped uvicorn's watcher and restarted the engine mid-session.
    That surfaced to the user as sign-in failures and dropped SSE streams, and
    masked #4379's real defect for an evening. Reload exists for
    editing-the-engine-while-it-runs; a live-testing session is not that, so
    the launch profile must ASK for it rather than inherit a developer default.
    FICHERO_BACKEND_STABLE_MODE=1 still forces it off, overriding everything.
    """
    if _env_flag("FICHERO_BACKEND_STABLE_MODE", default=False):
        return False
    return _env_flag("FICHERO_BACKEND_RELOAD", default=False)



class _QuietSteadyStateAccessLog(logging.Filter):
    NOISY_PREFIXES = (
        "/api/health",
        "/api/registry",
        "/api/activity/stream",
        "/api/ingest/status/",
        "/api/storage/thumbnail/",
        "/api/storage/display/",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        # uvicorn access records: args = (client, method, path, http, status)
        try:
            path, status = record.args[2], record.args[4]
        except (TypeError, IndexError):
            return True
        if not isinstance(status, int) or not 200 <= status < 300:
            return True
        return not any(str(path).startswith(p) for p in self.NOISY_PREFIXES)


def main(argv: list[str] | None = None):
    """Start the Fichero API backend server."""

    # Survive a client that hangs up mid-write (readiness probe cancel, a
    # connection closed right after a 401) instead of dying with SIGPIPE. Set
    # before anything binds a socket. See _ignore_sigpipe for the full cascade.
    _ignore_sigpipe()

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

    # Faulthandler ON by default (2026-08-09): a native fault in fitz /
    # pdfium / ONNX / the ObjC bridge previously left NOTHING in engine.log —
    # a whole day of 'the backend crashed' with no traceback. A C-level stack
    # on SIGSEGV is worth infinitely more than clean logs; opt OUT with
    # FICHERO_BACKEND_FAULTHANDLER=0 when clean logs truly matter.
    fault_enabled = _env_flag("FICHERO_BACKEND_FAULTHANDLER", default=True)
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

    # ------------------------------------------------------------------
    # Access-log hygiene (Daniel, 2026-08-10: "it pollutes our log every
    # 2 seconds"). The heartbeat traffic — health probes, registry polls,
    # SSE (re)subscribes, ingest-status polls, thumbnail/display fetches —
    # is content-free at 2xx: the interesting event is a FAILURE or an
    # endpoint outside this steady-state set. Filter those lines out of
    # uvicorn's access logger; every non-2xx and every other route still
    # logs. This is display hygiene only — app-level loggers are untouched.
    # ------------------------------------------------------------------
    logging.getLogger("uvicorn.access").addFilter(_QuietSteadyStateAccessLog())


    reload_enabled = _reload_enabled()
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
    # transport marker stamped by the wrapped app (fichero_server.api.uds_transport).
    uds_path = (os.environ.get("FICHERO_UDS_PATH") or "").strip()
    if uds_path:
        from fichero_server.api.uds_transport import app as uds_app

        uds_kwargs = dict(
            app=uds_app,
            workers=1,
            log_level="info",
            loop="asyncio",
            ws="websockets-sansio",
            # The app's SSE clients (activity/change streams) hold their
            # connections open across shutdown, and uvicorn's default is to
            # wait for them INDEFINITELY — so every quit blew through the
            # supervising app's 2s SIGTERM window and ended in SIGKILL
            # (#4291, live all day 2026-08-08). One second is enough for any
            # genuine in-flight response; lingering streams are force-closed.
            timeout_graceful_shutdown=1,
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
        app="fichero_server.api.tcp_transport:app",
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
        # Same 1s drain bound as the UDS transport above (#4291).
        timeout_graceful_shutdown=1,
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
