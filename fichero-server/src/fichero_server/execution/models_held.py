"""Which models this engine holds in memory, and how much each takes (#6129, `Diagnostics`): the Activity popover lists them so a
Mac that says 'memory is tight' shows what the engine itself could hand back. Reads only what is already loaded: nothing is
imported or started to answer."""
from __future__ import annotations

import subprocess
import sys
import time
from typing import Any

_RSS: dict[int, tuple[float, int | None]] = {}
_RSS_SECONDS = 5.0
_RSS_FORGET_SECONDS = 60.0


def process_bytes(pid: int | None) -> int | None:
    """The resident size of another process, from `ps` (cached for a few seconds: the popover asks every moment); None unknown."""
    if not pid:
        return None
    now = time.monotonic()
    seen = _RSS.get(pid)
    if seen is not None and now - seen[0] < _RSS_SECONDS:
        return seen[1]
    try:
        out = subprocess.run(["/bin/ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, timeout=2).stdout.strip()
        size: int | None = int(out) * 1024 if out else None
    except (OSError, ValueError, subprocess.SubprocessError):
        size = None
    for gone in [p for p, (when, _size) in _RSS.items() if now - when > _RSS_FORGET_SECONDS]:
        del _RSS[gone]  # a child that ended is not remembered for ever
    _RSS[pid] = (now, size)
    return size


def models_held() -> list[dict[str, Any]]:
    """Each model held: {name, kind, memory_bytes}. `memory_bytes` is None where the model lives inside the engine's own memory
    (Kraken's readers), and the child's resident size where it has a process of its own (the search embedder)."""
    held: list[dict[str, Any]] = []
    embeddings = sys.modules.get("fichero_server.db.embeddings")
    if embeddings is not None:
        for name, embedder in list(embeddings._EMBEDDER_CACHE.items()):
            pid = getattr(getattr(embedder, "_process", None), "pid", None)
            held.append({"name": name, "kind": "search embedder", "memory_bytes": process_bytes(pid)})
    kraken = sys.modules.get("fichero_server.llm.kraken_runtime")
    if kraken is not None:
        for kind, (key, _model) in list(kraken._RESIDENT.items()):
            held.append({"name": f"Kraken {kind}: {key}", "kind": "Kraken", "memory_bytes": None})
    return held
