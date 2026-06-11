"""
Fichero Backend Entry Point

Starts the FastAPI backend server for Briefcase.
Defaults to dev hot-reload when running from a Briefcase dev bundle, and
defaults to production behavior otherwise.
"""

import logging
import os
import socket
import sys
import faulthandler
import tracemalloc
import warnings

from fichero.bind_host import resolve_bind_host

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


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


def main():
    """Start the Fichero API backend server."""

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

    bind_host = resolve_bind_host()

    logger.info("Starting Fichero Backend (Briefcase bundle)")
    logger.info("Server will listen on http://%s:8765", bind_host)
    logger.info(
        "Hot-reload: %s",
        "ENABLED (dev mode)" if reload_enabled else "DISABLED (production mode)",
    )

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
        reload=reload_enabled,
    )
    if reload_enabled:
        # Limit reload scope to backend source to avoid whole-home scan noise.
        uvicorn_kwargs["reload_dirs"] = [src_dir]

    # Preflight port check avoids noisy socket ResourceWarning when bind fails.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if sock.connect_ex((bind_host, 8765)) == 0:
            logger.error(
                "Port 8765 is already in use on %s. Stop the existing backend process and retry.",
                bind_host,
            )
            return

    # Start server.
    try:
        uvicorn.run(**uvicorn_kwargs)
    except KeyboardInterrupt:
        logger.info("Backend shutting down...")
    except Exception as e:
        logger.error(f"Backend failed to start: {e}")
        raise


if __name__ == "__main__":
    main()
