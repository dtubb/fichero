"""The Activity window's Models tree (`activity.window.models-tree`, `activity.resources.everything-measured`, #6588).

One row per model this project used today, holds now, or has installed on this Mac, placed **this Mac › remote › cloud**,
then by provider: from the job rows (their `model`, and the calls each recorded in its `detail.usage`: provider, model and
place, `llm/places.py`), the models the engine holds in memory (`execution/models_held.py`) and the local catalogue's
installed models (`installed_local_model_entries`, not loaded until held). Beside them every place work can run, used or
not (`places`): this Mac, another Mac by its address, each cluster set up, each cloud provider set up (owner 2026-11-16).
Nothing guessed: a size nothing measures is None, a count not recorded is not made up.
"""

from __future__ import annotations

import functools
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
#: The place Hugging Face's paid Jobs (training, reading at scale) run on; its account is the Hugging Face token's state.
HF_JOBS = "Hugging Face Jobs"
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
_installed_cache: tuple[float, list[tuple]] | None = None
_installed_lock = threading.Lock()


def installed_on_this_mac() -> list[tuple]:
    """(provider shown, model id, catalogue entry) of every model installed on this Mac, from the one local catalogue Settings lists;
    a runtime whose probe fails lists none (the catalogue says so in the log)."""
    global _installed_cache
    with _installed_lock:
        if _installed_cache is not None and time.monotonic() - _installed_cache[0] < _INSTALLED_TTL_SECONDS:
            return _installed_cache[1]
    from fichero_server.api.routes.ai.local_inference import installed_local_model_entries

    found = [(word, e.model_id, e) for runtime, word in _INSTALLED_RUNTIMES.items()
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
             load: float | None = None, gpu: str | None = None) -> dict[str, Any]:
    """This Mac, measured (`activity.resources.everything-measured`, decision 42): memory used of its total (the kernel's
    share free of the physical memory), the processor's load (the last minute's load average over its cores), and each
    lane's jobs running now (this project's) of its width, and its GPU's name. What nothing measures is None, never 0."""
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
    if gpu is None:
        gpu = _gpu_name()
    return {"memory_used_bytes": used, "memory_total_bytes": total, "gpu": gpu or None,
            "processor_percent": round(100 * load / cores, 1) if load is not None and cores else None,
            "lanes": [{"lane": lane, "busy": busy.get(lane, 0), "width": width}
                      for lane, width in job_queue.LANES.items()]}


#: How long a server's answer is kept: the window asks every ten seconds, and a Mac that is asleep costs a timeout each time.
_REACH_TTL_SECONDS = 45.0
_reach_cache: dict[str, tuple[float, bool]] = {}
_reach_lock = threading.Lock()


def reachable(url: str) -> bool:
    """Whether a server answers at `url` (any HTTP answer; a refused or timed-out connection is not reachable); the answer
    is kept for `_REACH_TTL_SECONDS`."""
    import httpx

    with _reach_lock:
        kept = _reach_cache.get(url)
    if kept is not None and time.monotonic() - kept[0] < _REACH_TTL_SECONDS:
        return kept[1]
    try:
        httpx.get(url, timeout=2.0)
        answer = True
    except httpx.HTTPError:
        answer = False
    with _reach_lock:
        _reach_cache[url] = (time.monotonic(), answer)
    return answer


def places(probe: Any = reachable) -> list[dict[str, Any]]:
    """Every place work can run, set up or not used: this Mac, another Mac (a provider row whose Server URL is off this
    Mac, by its host), each cluster set up (by its name) and each cloud provider set up. (place, provider) pairs in the
    tree's order; the provider is the node under the place, as a model's provider is. Each carries its `account`
    (`models.row.account-from-a-probe`): another Mac's from `probe(its address)` ("ready" / "not-reachable"), a cloud provider's
    from the key a call uses, app-supplied keys included ("ready" / "needs-key"); None where nothing probes (a cluster). Each carries its `egress`, worked out from where it is
    (`models.place.egress-from-the-address`): this-mac, own-machine (an address off this Mac), provider (a cloud provider), institution (a cluster)."""
    found: list[tuple[str, str, str | None, str]] = [(THIS_MAC, "This Mac", "ready", "this-mac")]
    kinds: dict[tuple[str, str], str] = {}  # a cloud place -> its provider id, the key its calls in flight are counted by
    to_probe: dict[int, str] = {}  # index in `found` -> address, probed together after the loop
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
                    to_probe[len(found)] = row.api_base
                    found.append((REMOTE, _host(row.api_base) or _provider_word(kind), None, "own-machine"))
            else:
                from fichero_server.llm import get_api_key

                found.append((CLOUD, _provider_word(kind), "ready" if get_api_key(kind) else "needs-key", "provider"))
                kinds[(CLOUD, _provider_word(kind))] = kind
        found.extend((REMOTE, name, None, "institution") for name in _cluster_names(app_db).values())
        from fichero_server.llm import get_api_key as _token

        found.append((CLOUD, HF_JOBS, "ready" if _token("huggingface") else "needs-key", "provider"))
        if to_probe:  # all at once: a poll waits one timeout, not one per Mac
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=len(to_probe)) as pool:
                answers = dict(zip(to_probe, pool.map(probe, to_probe.values())))
            for index, answer in answers.items():
                place, provider, _, egress = found[index]
                found[index] = (place, provider, "ready" if answer else "not-reachable", egress)
    except Exception:  # noqa: BLE001 -- the tree still shows what ran; the places set up are an addition
        import logging

        logging.getLogger(__name__).warning("Activity models: could not read the places set up", exc_info=True)
    order = {place: index for index, place in enumerate(PLACES)}
    unique = {(p, v): (a, e) for p, v, a, e in found}
    from fichero_server.workflows import circuit_breaker

    return [{"place": p, "provider": v, "account": unique[(p, v)][0], "egress": unique[(p, v)][1],
             "calls_in_flight": circuit_breaker.calls_in_flight(kinds[(p, v)]) if (p, v) in kinds else None,
             "calls_cap": circuit_breaker.provider_cap(kinds[(p, v)]) if (p, v) in kinds else None, "credit": None}
            for p, v in sorted(unique, key=lambda pv: (order[pv[0]], pv[1].lower()))]


#: The failure kinds that say a provider cannot be used now, the words of `models.row.credit-and-limits`.
_CREDIT_KINDS = ("no-credit", "key-refused", "rate-limited")


def add_credit(listed: list[dict[str, Any]], found: list[dict[str, Any]]) -> None:
    """Each cloud place's `credit`: the newest failure today of a kind in `_CREDIT_KINDS` on one of its models (its words,
    kind and fix button), else None. The engine keeps no provider-wide dead mark between runs, so there are no seconds left."""
    for place in listed:
        failures = [m["last_failed"] for m in found if (m["place"], m["provider"]) == (place["place"], place["provider"])
                    and m["last_failed"] and m["last_failed"]["kind"] in _CREDIT_KINDS]
        place["credit"] = max(failures, key=lambda f: f["at"] or "") if failures else None


def _fits_here(rows: list[dict[str, Any]], facts: dict[str, Any], physical_memory: int | None) -> None:
    """Each sized installed model's `fits_here` ("yes" / "tight" / "no"), what it needs and the engine's words, from the one
    memory rule (`local_inference.fit_estimate`) against this Mac's memory; a model that does not fit names the loaded,
    idle models whose unloading frees memory (`models.row.fits-here`). A model nothing sizes, or a Mac whose memory cannot be
    read, stays None."""
    from fichero_server.llm import local_inference

    if physical_memory is None:
        from fichero_server.llm import kraken_runtime

        try:
            physical_memory = kraken_runtime._physical_memory_bytes()
        except Exception:  # noqa: BLE001 -- unmeasured reads "—"
            physical_memory = None
    if not physical_memory:
        return
    idle = [r["name"] for r in rows if r["loaded"] and not r["active"] and r["memory_bytes"]]
    for one in rows:
        entry = facts.get(one["id"])
        if entry is None or not entry.download_size_bytes:
            continue
        estimate = local_inference.fit_estimate(entry, physical_memory=physical_memory)
        one["fits_here"], one["needs_bytes"], one["fits_note"] = _FITS_WORD[estimate.word], estimate.need_bytes, estimate.reason
        if estimate.word != local_inference.FITS:
            one["unload_to_fit"] = [name for name in idle if name != one["name"]]


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


def call_key(call: dict[str, Any], hosts: dict[str, str]) -> tuple[str, str, str]:
    """(place, provider, model) of one recorded call, as the tree places it; another Mac by its address (`hosts`, from
    `provider_hosts`, read once per request)."""
    provider = str(call.get("provider") or "")
    place = _CALL_PLACE.get(call.get("place") or "", None)
    if place is None:
        place = THIS_MAC if provider.lower() in _LOCAL_PROVIDERS else CLOUD
    word = (hosts.get(provider.strip().lower()) if place == REMOTE else None) or _provider_word(provider)
    return place, word, str(call["model"])


def model_id(place: str, provider: str, name: str) -> str:
    """A model's id in the tree, the key its graph series is read by (`activity.window.graph-on-every-view`)."""
    return f"{place}|{provider}|{name}"


def _new(place: str, provider: str, name: str) -> dict[str, Any]:
    return {"id": model_id(place, provider, name), "name": name, "place": place, "provider": provider, "loaded": False,
            "active": False, "memory_bytes": None, "memory_estimated": False, "running": 0, "pages_today": 0,
            "calls_today": 0, "seconds_today": 0.0, "size_bytes": None, "licence": None, "fits_here": None,
            "needs_bytes": None, "fits_note": None, "unload_to_fit": [], "account": None, "using_now": [],
            "last_failed": None}


#: `FitEstimate.word` -> the column's word (`models.row.fits-here`).
_FITS_WORD = {"fits": "yes", "tight": "tight", "won't fit": "no"}


def _failure_of(reason: str | None, finished: datetime | None) -> dict[str, Any]:
    """A failed job's row words and the button of its fix (`models.row.using-now-and-last-failed`): the kind and button
    come from the same classifier the Activity row uses; a reason that keeps its own words has neither."""
    from fichero_server.execution import jobs as job_queue

    failure = job_queue.failed_failure(reason)
    return {"words": failure.words, "kind": None if failure.kind == "unexpected" else failure.kind,
            "button": failure.actions[0].kind if failure.actions else None,
            "at": ensure_utc(finished).isoformat() if finished else None}


@functools.cache
def _gpu_name() -> str | None:
    """This Mac's GPU as its chip names it ("Apple M1 GPU"); None off Apple silicon or when the chip cannot be read. Read once: the chip does not change while the engine runs."""
    import subprocess
    import sys

    if sys.platform != "darwin":
        return None
    try:
        brand = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True,
                               timeout=2, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return f"{brand} GPU" if brand.startswith("Apple") else None


def _usage(detail: str | None) -> list[dict[str, Any]]:
    try:
        calls = (json.loads(detail) if detail else {}).get("usage") or []
    except (TypeError, ValueError, AttributeError):
        return []
    return [c for c in calls if isinstance(c, dict) and c.get("model")]


def provider_hosts() -> dict[str, str]:
    """Provider type -> the host of its first provider row that has a Server URL. One read of the provider list; a request
    makes it once and hands it to every `call_key`."""
    from fichero_server.llm.places import _norm

    try:
        from fichero_server.db.app import get_app_db

        rows = get_app_db().list_providers()
    except Exception:  # noqa: BLE001 -- no app database (a bare test): every provider reads under its own word
        return {}
    hosts: dict[str, str] = {}
    for row in rows:
        kind = _norm(getattr(getattr(row, "provider_type", None), "value", None))
        host = _host(getattr(row, "api_base", None))
        if kind and host:
            hosts.setdefault(kind, host)
    return hosts


def models(db: "Database", *, held: list[dict[str, Any]] | None = None,
           installed: list[tuple] | None = None, now: datetime | None = None,
           physical_memory: int | None = None, accounts: dict[tuple[str, str], str | None] | None = None
           ) -> list[dict[str, Any]]:
    """Every model used today, held now or installed on this Mac, with where it runs, whether it is loaded and active, its
    memory, and today's pages, calls and seconds; an installed model's size on disk, licence and whether it fits this Mac
    (`physical_memory`, read when not given), a cloud or remote model's `accounts[(place, provider)]`, the kinds of job
    running on each (`using_now`) and its newest failure today (`last_failed`). `installed`: (provider, id[, catalogue
    entry]). Sorted by place (this Mac, remote, cloud), then provider, then name."""
    from fichero_server.execution import jobs as job_queue
    from fichero_server.remote_read import job as read_job

    job_queue._ensure(db)
    now = ensure_utc(now or utc_now())
    since = (now - timedelta(hours=now.hour, minutes=now.minute, seconds=now.second)).replace(tzinfo=None)
    rows: dict[str, dict[str, Any]] = {}
    clusters: dict[str, str] | None = None
    hosts = provider_hosts()

    def row(place: str, provider: str, name: str) -> dict[str, Any]:
        return rows.setdefault(model_id(place, provider, name), _new(place, provider, name))

    for kind, model, state, target, detail, started, finished, reason in job_queue.usage_rows_since(db, since):
        seconds = ((ensure_utc(finished) if finished else now) - ensure_utc(started)).total_seconds() if started else 0.0
        calls = _usage(detail)
        touched: list[dict[str, Any]] = []
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
                one = row(*call_key(call, hosts))  # another Mac by its address, as the places list names it
                one["calls_today"] += 1
                if state == "running":
                    one["active"] = True
                touched.append(one)
            entry = None
        elif model:
            entry = row(*place_and_provider(model))
        else:
            continue
        if entry is not None:
            touched.append(entry)
            if state == "running":
                entry["active"] = True
                entry["running"] += 1
            elif state == "done":
                entry["pages_today"] += 1
            entry["seconds_today"] += max(0.0, seconds)
        for one in touched:
            if state == "running" and kind not in one["using_now"]:
                one["using_now"].append(kind)
            elif state == "failed":
                at = ensure_utc(finished) if finished else None
                if one["last_failed"] is None or (at and at.isoformat() > (one["last_failed"]["at"] or "")):
                    one["last_failed"] = _failure_of(reason, at)

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
    facts: dict[str, Any] = {}
    for provider, installed_id, *entry in installed if installed is not None else installed_on_this_mac():
        one = row(THIS_MAC, provider, installed_id)
        if entry:
            facts[one["id"]] = entry[0]
            one["size_bytes"] = entry[0].disk_usage_bytes or None
            one["licence"] = entry[0].license_label
    _fits_here(list(rows.values()), facts, physical_memory)
    for one in rows.values():
        if one["place"] != THIS_MAC:
            one["account"] = (accounts or {}).get((one["place"], one["provider"]))
    order = {place: index for index, place in enumerate(PLACES)}
    return sorted(rows.values(), key=lambda r: (order[r["place"]], r["provider"].lower(), r["name"].lower()))


#: How long a library's trained rows are kept: reading them walks every trained card and build on this Mac, and the
#: window asks every ten seconds; they change only when a training run finishes.
#: ponytail: key by the cards' modification times so a finished training shows at once.
_TRAINED_TTL_SECONDS = 60.0
_trained_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def trained_rows(db: "Database") -> list[dict[str, Any]]:
    """Kept for `_TRAINED_TTL_SECONDS` per library. The models Fichero trained in this project as rows under This Mac › Trained here (`models.trained.are-rows`), each
    with its newest held-out scores, where it can run, and the ground truth it was trained on
    (`models.ground-truth.counts`): the card's own counts, None where the card has none. `not_for_release` is the
    card's rule inverted: a card that does not say it may be published is not released."""
    from fichero_server.training.model_nodes import model_nodes

    key = str(db.path)
    kept = _trained_cache.get(key)
    if kept is not None and time.monotonic() - kept[0] < _TRAINED_TTL_SECONDS:
        return kept[1]
    out = []
    for node in model_nodes(db):
        truth = node.get("training_set")
        out.append({
            "id": node["id"], "name": node["name"], "kind": node["kind"], "place": THIS_MAC, "section": "Trained here",
            "trained_at": node.get("trained_at"), "trained_where": node.get("trained_where"), "scores": node.get("scores"),
            "size_bytes": node.get("size_bytes"), "runs_on": node.get("runs_on") or [], "lives": node.get("lives"),
            "ground_truth": ({k: truth.get(k) for k in ("pages", "lines", "lines_checked_by_a_person", "held_out_pages")}
                             if truth else None),
            "not_for_release": not node.get("may_publish"),
        })
    _trained_cache[key] = (time.monotonic(), out)
    return out
