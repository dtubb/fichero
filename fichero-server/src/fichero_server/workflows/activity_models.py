"""The Activity window's Models tree (`activity.window.models-tree`, `activity.resources.everything-measured`, #6588).

One row per model this project used today or holds now, placed **this Mac › remote › cloud**, then by provider: from the job
rows (their `model`, and the calls each recorded in its `detail.usage`: provider, model and place, `llm/places.py`) and the
models the engine holds in memory (`execution/models_held.py`). Nothing guessed: a size nothing measures is None, a count
not recorded is not made up.
"""

from __future__ import annotations

import json
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


def _new(place: str, provider: str, name: str) -> dict[str, Any]:
    return {"id": f"{place}|{provider}|{name}", "name": name, "place": place, "provider": provider, "loaded": False,
            "active": False, "memory_bytes": None, "memory_estimated": False, "running": 0, "pages_today": 0,
            "calls_today": 0, "seconds_today": 0.0}


def _usage(detail: str | None) -> list[dict[str, Any]]:
    try:
        calls = (json.loads(detail) if detail else {}).get("usage") or []
    except (TypeError, ValueError, AttributeError):
        return []
    return [c for c in calls if isinstance(c, dict) and c.get("model")]


def models(db: "Database", *, held: list[dict[str, Any]] | None = None,
           now: datetime | None = None) -> list[dict[str, Any]]:
    """Every model used today or held now, with where it runs, whether it is loaded and active, its memory, and today's
    pages, calls and seconds. Sorted by place (this Mac, remote, cloud), then provider, then name."""
    from fichero_server.execution import jobs as job_queue
    from fichero_server.remote_read import job as read_job

    job_queue._ensure(db)
    now = ensure_utc(now or utc_now())
    since = (now - timedelta(hours=now.hour, minutes=now.minute, seconds=now.second)).replace(tzinfo=None)
    rows: dict[str, dict[str, Any]] = {}

    def row(place: str, provider: str, name: str) -> dict[str, Any]:
        key = f"{place}|{provider}|{name}"
        return rows.setdefault(key, _new(place, provider, name))

    hidden = " AND deleted_at IS NULL" if job_queue._has_deleted_at(db) else ""
    for kind, model, state, target, detail, started, finished in db.execute_fetchall(
        "SELECT kind, model, state, target, detail, started_at, finished_at FROM jobs "
        f"WHERE (state = 'running' OR finished_at >= ? OR started_at >= ?){hidden}",
        [since, since],
    ):
        seconds = ((ensure_utc(finished) if finished else now) - ensure_utc(started)).total_seconds() if started else 0.0
        calls = _usage(detail)
        if kind == read_job.KIND:
            # A read at scale runs off this Mac: Hugging Face's jobs are the cloud, any other target a cluster of the person's.
            on_cloud = target in (None, read_job.TARGET)
            entry = row(CLOUD if on_cloud else REMOTE, "Hugging Face" if on_cloud else (target or "Cluster"),
                        model or "Read at scale")
        elif calls:
            for call in calls:
                place = _CALL_PLACE.get(call.get("place") or "", None)
                provider = str(call.get("provider") or "")
                if place is None:
                    place = THIS_MAC if provider.lower() in _LOCAL_PROVIDERS else CLOUD
                one = row(place, _provider_word(provider), str(call["model"]))
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
    order = {place: index for index, place in enumerate(PLACES)}
    return sorted(rows.values(), key=lambda r: (order[r["place"]], r["provider"].lower(), r["name"].lower()))
