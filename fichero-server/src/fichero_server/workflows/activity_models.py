"""The Activity window's Models tree (`activity.window.models-tree`, `activity.resources.everything-measured`, #6588).

One row per model this project used today, holds now, or has installed on this Mac, placed **this Mac › remote › cloud**,
then by provider: from the job rows (their `model`, and the calls each recorded in its `detail.usage`: provider, model and
place, `llm/places.py`), the models the engine holds in memory (`execution/models_held.py`) and the local catalogue's
installed models (`installed_local_model_entries`, not loaded until held). Beside them every place work can run, used or
not (`places`): this Mac, another Mac by its address, each cluster set up, each cloud provider set up (owner 2026-11-16).
Nothing guessed: a size nothing measures is None, a count not recorded is not made up.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from fichero_server.core.timeutil import ensure_utc, utc_now

if TYPE_CHECKING:
    from fichero_server.db import Database

#: The three places of the tree, in its order.
THIS_MAC, REMOTE, CLOUD = "this-mac", "remote", "cloud"
PLACES = (THIS_MAC, REMOTE, CLOUD)
#: A call's recorded place (`llm/places.py`) -> the tree's.
_CALL_PLACE = {"this_mac": THIS_MAC, "own_machine": REMOTE, "provider": CLOUD}
#: Providers that serve models on this Mac unless a call says otherwise.
_LOCAL_PROVIDERS = frozenset({"ollama", "lmstudio", "omlx", "mlx", "apple", "local"})
#: The engine's own tools on this Mac, by the model name their jobs carry -> the provider shown.
_ON_THIS_MAC = {"apple-vision": "Apple", "apple-intelligence": "Apple", "pdf-text-layer": "Text layer", "spacy": "spaCy",
                "histdate": "Dates", "turbo": "Whisper", "embedder": "Embeddings", "local-model": "Local model"}
#: How a provider id reads.
_PROVIDER_NAMES = {"anthropic": "Anthropic", "openai": "OpenAI", "openrouter": "OpenRouter", "gemini": "Gemini",
                   "google": "Google", "huggingface": "Hugging Face", "huggingface-jobs": "Hugging Face",
                   "ollama": "Ollama", "lmstudio": "LM Studio", "omlx": "MLX", "mlx": "MLX", "mistral": "Mistral"}


def _provider_word(provider: str) -> str:
    return _PROVIDER_NAMES.get(provider.lower(), provider)


#: The local catalogue's runtimes whose installed models the tree lists on this Mac -> the provider shown.
_INSTALLED_RUNTIMES = {"kraken": "Kraken", "omlx": "MLX", "spacy": "spaCy", "whisper": "Whisper"}
#: How long the installed list is kept: probing Kraken takes a second or more, and the sidebar asks every ten.
_INSTALLED_TTL_SECONDS = 60.0
_installed_cache: tuple[float, list[tuple[str, str]]] | None = None
_installed_lock = threading.Lock()


def installed_on_this_mac() -> list[tuple[str, str]]:
    """(provider shown, model id) of every model installed on this Mac, from the one local catalogue Settings lists;
    a runtime whose probe fails lists none (the catalogue says so in the log)."""
    global _installed_cache
    with _installed_lock:
        if _installed_cache is not None and time.monotonic() - _installed_cache[0] < _INSTALLED_TTL_SECONDS:
            return _installed_cache[1]
    from fichero_server.api.routes.ai.local_inference import installed_local_model_entries

    found = [(word, e.model_id) for runtime, word in _INSTALLED_RUNTIMES.items()
             for e in installed_local_model_entries(runtime)]
    with _installed_lock:
        _installed_cache = (time.monotonic(), found)
    return found


def _host(url: str | None) -> str | None:
    from urllib.parse import urlparse

    return urlparse(url).hostname if url else None


def _cluster_names(app_db: Any = None) -> dict[str, str]:
    """Each cluster set up, its id -> the name a person gave it; {} when none or unreadable."""
    try:
        from fichero_server.api.routes.ai.hpc import _load_clusters
        from fichero_server.db.app import get_app_db

        return {cid: str((raw or {}).get("name") or cid) for cid, raw in _load_clusters(app_db or get_app_db()).items()}
    except Exception:  # noqa: BLE001 -- a cluster then reads by its id
        return {}


def this_mac(db: "Database", *, memory: tuple[int | None, int | None] | None = None,
             load: float | None = None) -> dict[str, Any]:
    """This Mac, measured (`activity.resources.everything-measured`, decision 42): memory used of its total (the kernel's
    share free of the physical memory), the processor's load (the last minute's load average over its cores), and each
    lane's jobs running now (this project's) of its width. What nothing measures is None, never 0."""
    import os

    from fichero_server.execution import jobs as job_queue

    if memory is None:
        from fichero_server.llm import kraken_runtime

        try:
            memory = (kraken_runtime._physical_memory_bytes(), kraken_runtime._memory_free_percent())
        except Exception:  # noqa: BLE001 -- unmeasured reads "—"
            memory = (None, None)
    total, free_percent = memory
    used = int(total * (100 - free_percent) / 100) if total and free_percent is not None else None
    if load is None:
        try:
            load = os.getloadavg()[0]
        except OSError:
            load = None
    from fichero_server.core.cores import cores_available
    from fichero_server.db import activity_queries
    cores = cores_available()[0]
    busy: dict[str, int] = {}
    job_queue._ensure(db)
    for kind in activity_queries.running_job_kinds(db):
        registered = job_queue.KINDS.get(kind)
        if registered is not None:
            busy[registered.lane] = busy.get(registered.lane, 0) + 1
    return {"memory_used_bytes": used, "memory_total_bytes": total,
            "processor_percent": round(100 * load / cores, 1) if load is not None and cores else None,
            "lanes": [{"lane": lane, "busy": busy.get(lane, 0), "width": width}
                      for lane, width in job_queue.LANES.items()]}


def places() -> list[dict[str, str]]:
    """Every place work can run, set up or not used: this Mac, another Mac (a provider row whose Server URL is off this
    Mac, by its host), each cluster set up (by its name) and each cloud provider set up. (place, provider) pairs in the
    tree's order; the provider is the node under the place, as a model's provider is."""
    found: list[tuple[str, str]] = [(THIS_MAC, "This Mac")]
    try:
        from fichero_server.db.app import get_app_db
        from fichero_server.llm import places as call_places
        from fichero_server.llm.providers import get_provider_info

        app_db = get_app_db()
        for row in app_db.list_providers():
            if not row.enabled:
                continue
            kind = getattr(row.provider_type, "value", str(row.provider_type))
            info = get_provider_info(kind)
            if info is None or info.is_builtin:
                continue
            if info.is_local:
                if row.api_base and not call_places.address_is_on_this_mac(row.api_base):
                    found.append((REMOTE, _host(row.api_base) or _provider_word(kind)))
            else:
                found.append((CLOUD, _provider_word(kind)))
        found.extend((REMOTE, name) for name in _cluster_names(app_db).values())
    except Exception:  # noqa: BLE001 -- the tree still shows what ran; the places set up are an addition
        import logging

        logging.getLogger(__name__).warning("Activity models: could not read the places set up", exc_info=True)
    order = {place: index for index, place in enumerate(PLACES)}
    unique = list(dict.fromkeys(found))
    return [{"place": p, "provider": v} for p, v in sorted(unique, key=lambda pv: (order[pv[0]], pv[1].lower()))]


def place_and_provider(model: str) -> tuple[str, str, str]:
    """(place, provider, short name) for a job's model string: `kraken:<reader>` is Kraken on this Mac, `<provider>:<model>`
    a provider's model (this Mac for a local server), an engine tool by its name; anything else this Mac under its own
    name."""
    if model.startswith("kraken:"):
        return THIS_MAC, "Kraken", model.split(":", 1)[1] or "Kraken"
    if model.lower().startswith("whisper"):
        return THIS_MAC, "Whisper", model
    if model in _ON_THIS_MAC:
        return THIS_MAC, _ON_THIS_MAC[model], model
    if ":" in model:
        provider, name = model.split(":", 1)
        place = THIS_MAC if provider.lower() in _LOCAL_PROVIDERS else CLOUD
        return place, _provider_word(provider), name
    return THIS_MAC, "This Mac", model


def call_key(call: dict[str, Any]) -> tuple[str, str, str]:
    """(place, provider, model) of one recorded call, as the tree places it; another Mac by its address."""
    provider = str(call.get("provider") or "")
    place = _CALL_PLACE.get(call.get("place") or "", None)
    if place is None:
        place = THIS_MAC if provider.lower() in _LOCAL_PROVIDERS else CLOUD
    word = (_host(_row_url(provider)) if place == REMOTE else None) or _provider_word(provider)
    return place, word, str(call["model"])


def model_id(place: str, provider: str, name: str) -> str:
    """A model's id in the tree, the key its graph series is read by (`activity.window.graph-on-every-view`)."""
    return f"{place}|{provider}|{name}"


def _new(place: str, provider: str, name: str) -> dict[str, Any]:
    return {"id": model_id(place, provider, name), "name": name, "place": place, "provider": provider, "loaded": False,
            "active": False, "memory_bytes": None, "memory_estimated": False, "running": 0, "pages_today": 0,
            "calls_today": 0, "seconds_today": 0.0}


def _usage(detail: str | None) -> list[dict[str, Any]]:
    try:
        calls = (json.loads(detail) if detail else {}).get("usage") or []
    except (TypeError, ValueError, AttributeError):
        return []
    return [c for c in calls if isinstance(c, dict) and c.get("model")]


def _row_url(provider: str) -> str | None:
    from fichero_server.llm.places import row_server_url

    try:
        return row_server_url(provider)
    except Exception:  # noqa: BLE001 -- no row: the provider's own word
        return None


def models(db: "Database", *, held: list[dict[str, Any]] | None = None,
           installed: list[tuple[str, str]] | None = None, now: datetime | None = None) -> list[dict[str, Any]]:
    """Every model used today, held now or installed on this Mac, with where it runs, whether it is loaded and active, its
    memory, and today's pages, calls and seconds. Sorted by place (this Mac, remote, cloud), then provider, then name."""
    from fichero_server.execution import jobs as job_queue
    from fichero_server.remote_read import job as read_job

    job_queue._ensure(db)
    now = ensure_utc(now or utc_now())
    since = (now - timedelta(hours=now.hour, minutes=now.minute, seconds=now.second)).replace(tzinfo=None)
    rows: dict[str, dict[str, Any]] = {}
    clusters: dict[str, str] | None = None

    def row(place: str, provider: str, name: str) -> dict[str, Any]:
        return rows.setdefault(model_id(place, provider, name), _new(place, provider, name))

    for kind, model, state, target, detail, started, finished in job_queue.usage_rows_since(db, since):
        seconds = ((ensure_utc(finished) if finished else now) - ensure_utc(started)).total_seconds() if started else 0.0
        calls = _usage(detail)
        if kind == read_job.KIND:
            # A read at scale runs off this Mac: Hugging Face's jobs are the cloud, any other target a cluster of the person's.
            on_cloud = target in (None, read_job.TARGET)
            if not on_cloud and clusters is None:
                clusters = _cluster_names()
            entry = row(CLOUD if on_cloud else REMOTE,
                        "Hugging Face" if on_cloud else ((clusters or {}).get(target or "") or target or "Cluster"),
                        model or "Read at scale")
        elif calls:
            for call in calls:
                one = row(*call_key(call))  # another Mac by its address, as the places list names it
                one["calls_today"] += 1
                if state == "running":
                    one["active"] = True
            entry = None
        elif model:
            entry = row(*place_and_provider(model))
        else:
            continue
        if entry is not None:
            if state == "running":
                entry["active"] = True
                entry["running"] += 1
            elif state == "done":
                entry["pages_today"] += 1
            entry["seconds_today"] += max(0.0, seconds)

    # What the engine holds in memory now: loaded, with its resident size where it has a process of its own.
    if held is None:
        from fichero_server.execution.models_held import models_held

        held = models_held()
    for one in held:
        kind = str(one.get("kind") or "")
        name = str(one.get("name") or "")
        if kind == "Kraken":
            short = name.split(": ", 1)[1] if ": " in name else name
            entry = row(THIS_MAC, "Kraken", short)
        else:
            entry = row(THIS_MAC, "Embeddings" if "embed" in kind.lower() else kind or "This Mac", name)
        entry["loaded"] = True
        if one.get("memory_bytes") is not None:
            entry["memory_bytes"] = int(one["memory_bytes"])
        elif kind == "Kraken":
            # Kraken's readers live in the engine's own memory: the size its load is given, said as an estimate.
            from fichero_server.llm import kraken_runtime

            try:
                size = kraken_runtime._kraken_memory_need_bytes()
            except Exception:  # noqa: BLE001 -- an unsized model reads "—", never a guess
                size = None
            if size:
                entry["memory_bytes"], entry["memory_estimated"] = int(size), True
    # Installed on this Mac and not held: listed, not loaded (hollow), so a person sees what is here to load.
    for provider, installed_id in installed if installed is not None else installed_on_this_mac():
        row(THIS_MAC, provider, installed_id)
    order = {place: index for index, place in enumerate(PLACES)}
    return sorted(rows.values(), key=lambda r: (order[r["place"]], r["provider"].lower(), r["name"].lower()))
