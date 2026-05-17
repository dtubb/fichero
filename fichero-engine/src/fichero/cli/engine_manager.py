"""Engine lifecycle management commands: start, stop, restart, status.

Provides CLI commands to manage the Fichero engine as a background process,
including PID tracking, port readiness probes, and graceful shutdown.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import typer

# PID file location: ~/.fichero/engine.pid
PID_FILE = Path.home() / ".fichero" / "engine.pid"


def _read_pid() -> Optional[int]:
    """Read PID from file, return None if missing/corrupted."""
    try:
        return int(PID_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


def _write_pid(pid: int) -> None:
    """Write PID to file."""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(pid))


def _remove_pid() -> None:
    """Remove PID file."""
    PID_FILE.unlink(missing_ok=True)


def _is_process_alive(pid: int) -> bool:
    """Check if process with given PID is alive (cross-platform).

    Uses os.kill with signal 0 (POSIX) or Windows equivalents.
    """
    try:
        # signal.SIGKILL doesn't exist on Windows; use signal.SIGTERM as proxy
        # signal 0 tests for process existence without sending a signal
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _wait_for_port(
    port: int, timeout_s: int = 5, retries: int = 10
) -> bool:
    """Poll port until responsive or timeout.

    Returns True if port becomes responsive within timeout, False otherwise.
    """
    for attempt in range(retries):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect(("localhost", port))
            s.close()
            return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            if attempt < retries - 1:
                time.sleep(timeout_s / retries)
    return False


def _get_uptime(pid: int) -> Optional[str]:
    """Return human-readable uptime for process.

    Reads /proc or uses lsof as fallback on macOS. Returns None if
    process is not found or creation time cannot be determined.
    """
    import subprocess

    try:
        # Try macOS approach first (lsof)
        result = subprocess.run(
            ["lsof", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            # lsof output has start time in last column of first line
            # For simplicity, estimate: assume recent start if process exists
            # and is responsive
            try:
                result = subprocess.run(
                    ["ps", "-p", str(pid), "-o", "etime="],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    elapsed = result.stdout.strip()
                    return elapsed if elapsed else None
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return None


def status() -> None:
    """Show engine status (running or stopped with uptime if available)."""
    pid = _read_pid()
    if pid and _is_process_alive(pid):
        uptime = _get_uptime(pid)
        uptime_str = f" (uptime {uptime})" if uptime else ""
        typer.echo(f"Engine running (PID {pid}{uptime_str})")
    else:
        if pid:
            _remove_pid()
        typer.echo("Engine stopped")


def start(port: int = 8765, workers: int = 4) -> None:
    """Start engine in background.

    Launches a detached uvicorn process and polls the port until responsive.
    If engine is already running, prints its PID and returns.
    """
    pid = _read_pid()
    if pid and _is_process_alive(pid):
        typer.echo(f"Engine already running (PID {pid})")
        return

    # Clear stale PID file if process is gone
    if pid:
        _remove_pid()

    try:
        # Daemonize uvicorn: detach from parent process group on POSIX
        # and suppress stdout/stderr
        kwargs: dict = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }

        # On POSIX, use start_new_session to detach; on Windows, use
        # CREATE_NEW_PROCESS_GROUP (not available in Python directly,
        # so we omit it and accept that Windows may have different behavior)
        if sys.platform != "win32":
            kwargs["start_new_session"] = True

        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "fichero.api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--workers",
                str(workers),
            ],
            **kwargs,  # type: ignore[arg-type]
        )

        _write_pid(proc.pid)

        # Poll port until responsive
        if _wait_for_port(port, timeout_s=5, retries=10):
            typer.echo(f"Engine started (PID {proc.pid})")
        else:
            typer.echo(
                f"Engine started but port {port} not responding yet; "
                "check status with `fichero engine status`",
                err=True,
            )
    except Exception as exc:
        typer.secho(f"Failed to start engine: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


def stop() -> None:
    """Stop engine gracefully.

    Attempts graceful shutdown via HTTP first, then SIGTERM, finally SIGKILL.
    """
    pid = _read_pid()
    if not pid:
        typer.echo("Engine not running")
        return

    # Try graceful shutdown via HTTP first
    try:
        import requests

        requests.post("http://localhost:8765/api/shutdown", timeout=5)
        time.sleep(1)
    except Exception:
        pass

    # If still alive, SIGTERM then SIGKILL
    if _is_process_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(3)
        except (OSError, ProcessLookupError):
            pass

    if _is_process_alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass

    _remove_pid()
    typer.echo("Engine stopped")


def restart(port: int = 8765, workers: int = 4) -> None:
    """Stop and start engine.

    Useful for reloading configuration or recovering from a hung state.
    """
    stop()
    time.sleep(1)
    start(port=port, workers=workers)
