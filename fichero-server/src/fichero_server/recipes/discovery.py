"""Finding models beyond the shipped cards (#5519; `source/models-chains-and-projects.md`, "Finding models
beyond the shipped cards" and step 1 of "One guided path to a good model").

The shipped cards are a seed, not the list. For a project's scripts and languages, discovery gathers
reader candidates from three more places, each turned into a `Card` the same rules rank:

* **Installed** (`installed_cards`): every MLX vision model complete in this engine's model store that no
  shipped card already describes: a catalogue model, one Fichero trained (`fichero-trained/*`), or one
  found in the store. Its card is made from its own metadata (`made_from: metadata`): its config says it
  reads images, its weights give its size, its README's front matter its licence and languages. Nothing
  else is guessed: its scripts are unstated (any), so it is never invisible to the rules for a script no
  shipped reader covers.
* **Kraken's model repository** (`repository_cards`): the HTRMoPo records of Zenodo's `ocr_models`
  community, read through `htrmopo.get_listing`, the call `kraken list` makes; only Kraken recognition
  models, the newest version of each, with the script, language, licence and CER their cards state. A
  published CER counts as accuracy only where the record names the project's languages (the rules'
  "published measurement on matching material"); elsewhere it is shown, not ranked on. Fetched only when
  asked (`refresh_repository`), kept in the model store's `discovery/` folder, read from there after.
* **Hugging Face** (`search_hugging_face`): image-to-text and image-text-to-text models by task and
  language tag, never by keyword, and only builds this Mac can run: an MLX build, or a safetensors model
  whose MLX conversion the Hub names (`base_model:`), offered as that conversion. A GGUF-only repository
  is never offered. Each result says why it is offered. What a search finds is kept beside the repository
  listing (`hugging-face.json`), so the rules choose from it for the languages it was found for, without
  the network; one the rules choose is offered as a download through this Mac's model store (`hub_spec`,
  #5593, `source.find.found-reader-downloads`).

The network is reached only when a caller asks (`online`), never at import time, and never when the engine
works offline (`llm.is_local_only`, the egress setting). Offline, discovery offers what is installed and
what was cached. Every candidate whose accuracy is not measured on the project says it is unmeasured
until a bake-off measures it.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fichero_server.recipes.assemble import Answers, Card

#: The jobs a found reader does: a vision model reads a line's picture (the bake-off's way) or a page.
READER_JOBS = frozenset({"read-a-line", "read-a-page"})
#: Where discovery keeps what it fetched, under the model store root.
CACHE_FOLDER = "discovery"
REPOSITORY_FILE = "kraken-repository.json"
#: The Hub readers the searches found, each with the languages it was found for (#5593).
HUB_FILE = "hugging-face.json"
#: A cached repository listing older than this is fetched again when a caller asks for the network.
REFRESH_AFTER = timedelta(days=1)
#: Hugging Face tasks a page or line reader is published under. MLX builds are asked for by the `mlx` tag:
#: the Hub ignores a `library` parameter, and asking that way returned GGUF repositories (2026-10-07).
HF_READER_TASKS = ("image-to-text", "image-text-to-text")  # OCR models first
#: How many Hub results per query, and how many non-MLX originals are looked up for an MLX conversion.
HF_LIMIT = 20
HF_CONVERSIONS_LOOKED_UP = 8

#: ISO 15924 codes that cover others (Han covers its simplified and traditional variants; Japanese is Han
#: plus the kana; Korean is Hangul plus Han), so a project's `Jpan` is covered by a card that states
#: `Hani`, `Hira` and `Kana`, and the reverse. A card is widened one step from what it states, never
#: further: a Japanese card covers Han as Japanese writes it, never Traditional or Simplified Chinese
#: (#5593: Classical Chinese was given the Kuzushiji reader, `source.recipe.no-cross-script-reader`).
_UNIONS: dict[str, frozenset[str]] = {
    "Hani": frozenset({"Hans", "Hant"}),
    "Jpan": frozenset({"Hani", "Hira", "Kana", "Hrkt"}),
    "Kore": frozenset({"Hang", "Hani"}),
    "Hrkt": frozenset({"Hira", "Kana"}),
}


def _store_root() -> Path:
    from fichero_server.db.paths import model_store_root

    return model_store_root() / CACHE_FOLDER


def covered_scripts(scripts: list[str] | frozenset[str]) -> frozenset[str]:
    """The scripts a card covers, its stated ones widened by the unions above (#5519: a Japanese project
    asked for `Jpan` and a card stated `Hani`, `Hira`, `Kana`)."""
    stated = set(scripts)
    out = set(stated)
    for whole, parts in _UNIONS.items():
        if whole in stated:  # one step down from what the card states, never chained (Jpan -> Hani -> Hant)
            out |= parts
    for _ in range(2):
        for whole, parts in _UNIONS.items():
            needed = {p for p in parts if p not in ("Hans", "Hant", "Hrkt")}
            if whole not in out and needed and needed <= out:
                out.add(whole)
    return frozenset(out)


def _language_tag(code: str) -> str | None:
    from fichero_server.recipes.names import _as_tag

    return _as_tag(str(code)) if code else None


def _tags(values: Any) -> frozenset[str] | None:
    """Language codes as the rules read them (BCP 47 tags), or None when none is stated."""
    values = [values] if isinstance(values, str) else list(values or [])
    tags = frozenset(t for t in (_language_tag(v) for v in values) if t)
    return tags or None


# --- installed ---------------------------------------------------------------------------------------


def _front_matter(readme: Path) -> dict[str, Any]:
    """A model README's YAML front matter (the Hub's card metadata), or {} when it has none."""
    import yaml

    try:
        text = readme.read_text(encoding="utf-8")
    except OSError:
        return {}
    match = re.match(r"^---\s*\n(.*?)\n---\s*(\n|$)", text, re.S)
    if not match:
        return {}
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def installed_cards(seed: tuple[Card, ...] | list[Card]) -> list[Card]:
    """A card for every complete MLX vision model in this engine's store that no shipped card pins."""
    from fichero_server.llm.mlx_model_store import MANAGED_MLX_MODELS, get_mlx_model_store

    store = get_mlx_model_store()
    pinned = {str(c.pin.get("hf")) for c in seed if "hf" in c.pin}
    names = [*MANAGED_MLX_MODELS, *store.trained_model_ids(), *store._scan_cached_repo_ids()]
    out: dict[str, Card] = {}
    for name in names:
        model_id = store.canonical_id(name)
        if model_id is None or model_id in out:
            continue
        spec = store.spec(model_id)
        if spec.repo_id in pinned or "vision" not in spec.capabilities or not store.is_complete(spec):
            continue
        trained = store.trained_card(model_id)
        meta = _front_matter(store.snapshot_path(spec) / "README.md")
        if trained is not None:
            licence, open_licence = "trained by you", True
            why = f"installed on this Mac: {spec.display_name}, a vision model you trained"
        else:
            licence = str(meta.get("license_name") or meta.get("license") or "")
            open_licence = _is_open(licence)
            why = (f"installed on this Mac: {spec.display_name}, a vision model in your model store; "
                   "its card is made from its own config")
        memory = max(spec.min_memory_bytes, spec.page_memory_bytes or 0)
        out[model_id] = Card(
            id=f"mlx:installed/{spec.repo_id}@{spec.revision}",
            pin={"hf": spec.repo_id, "revision": spec.revision},
            jobs=READER_JOBS, scripts=None, languages=_tags(meta.get("language")), material=frozenset(),
            open_licence=open_licence, size_gb=round(spec.download_size_bytes / 1e9, 3),
            memory_gb=round(memory / 1024**3, 2), trainable=True, licence=licence,
            note=spec.display_name, source="installed", offered_because=why, installed=True,
        )
    return sorted(out.values(), key=lambda c: c.id)


def mark_installed(cards) -> list[Card]:
    """These cards, each MLX model's card saying whether its model is complete in this Mac's store
    (`Card.installed`, #5583); every other card as it is. The rules rank a model already here first."""
    from dataclasses import replace

    from fichero_server.llm.mlx_model_store import get_mlx_model_store
    from fichero_server.recipes.cards import mlx_model_for

    store = get_mlx_model_store()
    out = []
    for card in cards:
        repo = mlx_model_for(card.pin) if card.local and card.installed is None else None
        model_id = store.canonical_id(repo) if repo else None
        out.append(replace(card, installed=store.is_complete(store.spec(model_id))) if model_id else card)
    return out


def _is_open(licence: str) -> bool:
    from fichero_server.recipes.cards import is_open_licence

    return is_open_licence(licence)


# --- Kraken's repository -----------------------------------------------------------------------------


def _harvest() -> dict[str, dict[str, Any]]:
    """Kraken's model repository as `kraken list` reads it: htrmopo's listing of Zenodo's `ocr_models`
    community, {doi: {"v0"|"v1": record}}. The one network boundary here; tests replace it with a
    recorded listing."""
    from fichero_server.llm.kraken_runtime import repository_listing

    return repository_listing()


def _row(record: Any) -> dict[str, Any] | None:
    """A repository record as discovery keeps it, or None when it is not a Kraken recognition model."""
    keywords = list(getattr(record, "keywords", None) or [])
    if getattr(record, "software_name", None) != "kraken" and "kraken_pytorch" not in keywords:
        return None
    if "recognition" not in (getattr(record, "model_type", None) or []):
        return None
    metrics = getattr(record, "metrics", None) or {}
    published = getattr(record, "publication_date", None)
    return {
        "doi": str(record.doi), "concept_doi": str(getattr(record, "concept_doi", "") or ""),
        "summary": str(getattr(record, "summary", "") or "").strip(),
        "licence": str(getattr(record, "license", "") or ""),
        "scripts": sorted(getattr(record, "script", None) or []),
        "languages": sorted(getattr(record, "language", None) or []),
        "keywords": sorted(keywords),
        "cer_percent": float(metrics["cer"]) if isinstance(metrics.get("cer"), (int, float)) else None,
        "size_bytes": sum(max(0, int(f.get("size") or 0)) for f in getattr(record, "distribution", None) or []),
        "published": published.isoformat() if hasattr(published, "isoformat") else str(published or ""),
    }


def repository_rows(listing: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """The listing's Kraken recognition models, the newest version of each (by its concept DOI)."""
    newest: dict[str, dict[str, Any]] = {}
    for versions in listing.values():
        record = versions.get("v1") or versions.get("v0")
        row = _row(record) if record is not None else None
        if row is None:
            continue
        key = row["concept_doi"] or row["doi"]
        if key not in newest or row["published"] > newest[key]["published"]:
            newest[key] = row
    return sorted(newest.values(), key=lambda r: r["doi"])


def cached_repository() -> dict[str, Any] | None:
    """The repository listing kept from the last fetch ({"fetched_at", "records"}), or None."""
    try:
        data = json.loads((_store_root() / REPOSITORY_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("records"), list) else None


def refresh_repository() -> dict[str, Any]:
    """Fetch Kraken's repository listing and keep it. Network: call only behind the egress check."""
    rows = repository_rows(_harvest())
    data = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "records": rows}
    folder = _store_root()
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / f".{REPOSITORY_FILE}.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(folder / REPOSITORY_FILE)
    return data


def _stale(data: dict[str, Any] | None) -> bool:
    if data is None:
        return True
    try:
        fetched = datetime.fromisoformat(str(data["fetched_at"]))
    except (KeyError, ValueError):
        return True
    return datetime.now(timezone.utc) - fetched > REFRESH_AFTER


def _row_scripts(row: dict[str, Any]) -> frozenset[str]:
    """A record's scripts, with Fraktur (`Latf`) where a Latin-script record says Fraktur in its summary
    or keywords: the repository's Fraktur readers are mostly filed as `Latn`."""
    scripts = set(row["scripts"])
    text = " ".join([row["summary"], *row["keywords"]]).lower()
    if "Latn" in scripts and "fraktur" in text:
        scripts.add("Latf")
    return covered_scripts(scripts)


def _row_material(row: dict[str, Any]) -> frozenset[str]:
    """The material a record's own words name ("printed", "manuscripts", "typewritten"), or none: the rules
    rank a reader whose card states the asked material first (`source.recipe.script-reader-first`, #5593)."""
    text = " ".join([row["summary"], *row["keywords"]]).lower()
    found = set()
    if re.search(r"\bprint|\bincunab|\bnewspaper", text):
        found.add("print")
    if re.search(r"handwrit|manuscript", text):
        found.add("handwriting")
    if re.search(r"typewrit|typescript", text):
        found.add("typescript")
    return frozenset(found)


def repository_cards(rows: list[dict[str, Any]], seed: tuple[Card, ...] | list[Card],
                     languages: frozenset[str] = frozenset()) -> list[Card]:
    """A card for each repository record no shipped card pins. Its published CER is its accuracy only
    when its record names every one of the project's `languages`; otherwise the CER is in its reason."""
    from fichero_server.llm.kraken_runtime import is_recognition_model_installed, reader_id_for_doi

    pinned = {str(c.pin.get("zenodo")) for c in seed if "zenodo" in c.pin}
    out = []
    for row in rows:
        if row["doi"] in pinned or row["concept_doi"] in pinned:
            continue
        langs = _tags(row["languages"])
        cer = row["cer_percent"] / 100 if row["cer_percent"] is not None else None
        matches = bool(languages) and langs is not None and languages <= langs
        why = f"in Kraken's model repository (Zenodo, {row['doi']})"
        if cer is not None and not matches:
            why += f"; its card reports CER {cer * 100:.1f}% on its own material, not your languages"
        if is_recognition_model_installed(reader_id_for_doi(row["doi"])):
            why += "; downloaded on this Mac"
        out.append(Card(
            id=f"kraken:zenodo/{row['doi']}@pinned", pin={"zenodo": row["doi"]}, jobs=frozenset({"read-a-line"}),
            scripts=_row_scripts(row) or None, languages=langs, material=_row_material(row),
            open_licence=_is_open(row["licence"]), size_gb=round(row["size_bytes"] / 1e9, 4),
            trainable=True, cer_published=cer if matches else None, licence=row["licence"],
            note=row["summary"] or row["doi"], source="kraken-repository", offered_because=why,
        ))
    return out


# --- Hugging Face --------------------------------------------------------------------------------------


def _hf_card(model: dict[str, Any], why: str) -> Card:
    repo = str(model.get("modelId") or model.get("id"))
    tags = [str(t) for t in model.get("tags") or []]
    licence = next((t.split(":", 1)[1] for t in tags if t.startswith("license:")), "")
    langs = _tags([t for t in tags if re.fullmatch(r"[a-z]{2,3}", t)])
    return Card(
        id=f"mlx:hf/{repo}@main", pin={"hf": repo, "revision": "main"}, jobs=READER_JOBS, scripts=None,
        languages=langs, material=frozenset(), open_licence=_is_open(licence), trainable=True,
        licence=licence, note=repo.rsplit("/", 1)[-1], source="hugging-face", offered_because=why,
    )


def _runs_on_mlx(model: dict[str, Any]) -> bool:
    tags = set(model.get("tags") or [])
    return model.get("library_name") == "mlx" or "mlx" in tags


def _gguf_only(model: dict[str, Any]) -> bool:
    tags = set(model.get("tags") or [])
    return ("gguf" in tags or model.get("library_name") == "gguf") and not _runs_on_mlx(model)


async def search_hugging_face(languages: frozenset[str]) -> list[Card]:
    """Reader candidates on the Hub for these languages, only builds this Mac can run, each saying why it
    is offered. Network: call only behind the egress check. Raises the Hub fetch's error."""
    from fichero_server.api.routes.ai.models import _fetch_hf_models

    filters = [[lang.split("-")[0]] for lang in sorted(languages)] or [[]]
    found: dict[str, Card] = {}
    originals: list[tuple[dict[str, Any], str]] = []
    for task in HF_READER_TASKS:
        for tags in filters:
            said = f"tagged {', '.join(tags)}" if tags else "any language"
            for m in await _fetch_hf_models(task=task, tags=["mlx", *tags], limit=HF_LIMIT):
                if _runs_on_mlx(m) and not _gguf_only(m):
                    repo = str(m.get("modelId") or m.get("id"))
                    found.setdefault(repo, _hf_card(m, f"an MLX build on Hugging Face ({task}, {said}): "
                                                       "runs on this Mac's MLX server"))
            for m in await _fetch_hf_models(task=task, tags=tags or None, limit=HF_LIMIT):
                if not _runs_on_mlx(m) and not _gguf_only(m) and "safetensors" in (m.get("tags") or []):
                    originals.append((m, f"{task}, {said}"))
    for original, said in originals[:HF_CONVERSIONS_LOOKED_UP]:
        repo = str(original.get("modelId") or original.get("id"))
        for m in await _fetch_hf_models(tags=["mlx", f"base_model:{repo}"], limit=5):
            if _runs_on_mlx(m) and not _gguf_only(m):
                conversion = str(m.get("modelId") or m.get("id"))
                card = _hf_card(m, f"the MLX conversion of {repo} (safetensors on Hugging Face, {said}), "
                                   "which runs on this Mac's MLX server")
                if card.languages is None:
                    card = _with_languages(card, _tags([t for t in original.get("tags") or []
                                                         if re.fullmatch(r"[a-z]{2,3}", str(t))]))
                found.setdefault(conversion, card)
                break
    return sorted(found.values(), key=lambda c: c.id)


def _with_languages(card: Card, languages: frozenset[str] | None) -> Card:
    from dataclasses import replace

    return replace(card, languages=languages)


def cached_hub() -> dict[str, dict[str, Any]]:
    """The Hub readers the searches found, {repo: row}, each row with the languages it was found for."""
    try:
        data = json.loads((_store_root() / HUB_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    found = data.get("found") if isinstance(data, dict) else None
    return found if isinstance(found, dict) else {}


def keep_hub(cards: list[Card], languages: frozenset[str]) -> None:
    """Keep what a Hub search for these languages found, beside what earlier searches found (#5593)."""
    if not cards or not languages:
        return
    found = cached_hub()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for card in cards:
        repo = str(card.pin["hf"])
        before = found.get(repo) or {}
        found[repo] = {"repo": repo, "languages": sorted(card.languages) if card.languages else None,
                       "licence": card.licence, "note": card.note, "offered_because": card.offered_because,
                       "size_gb": card.size_gb, "found_for": sorted({*before.get("found_for", []), *languages}),
                       "found_at": now}
    folder = _store_root()
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / f".{HUB_FILE}.tmp"
    tmp.write_text(json.dumps({"found": found}, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(folder / HUB_FILE)


def hub_cards(languages: frozenset[str] | None, skip_repos: set[str] = frozenset()) -> list[Card]:
    """The kept Hub readers found for any of these languages (every one kept, for None: a card looked up by its
    id), as cards the rules rank, except those whose repository another card already pins (a shipped card, or
    the installed copy once downloaded)."""
    out = []
    for repo, row in sorted(cached_hub().items()):
        if repo in skip_repos or (languages is not None and not languages & set(row.get("found_for") or ())):
            continue
        out.append(Card(
            id=f"mlx:hf/{repo}@main", pin={"hf": repo, "revision": "main"}, jobs=READER_JOBS, scripts=None,
            languages=_tags(row.get("languages")), material=frozenset(),
            open_licence=_is_open(str(row.get("licence") or "")), trainable=True,
            size_gb=float(row.get("size_gb") or 0), licence=str(row.get("licence") or ""),
            note=str(row.get("note") or repo.rsplit("/", 1)[-1]), source="hugging-face",
            offered_because=str(row.get("offered_because") or "found on Hugging Face"),
        ))
    return out


def hub_spec(repo_id: str) -> Any:
    """The model store's spec for a Hub reader a search found and kept, so this Mac's model store downloads it
    as it downloads a catalogue model (`model.download`, #5593); None for any other name. Its size and memory are
    not stated by the Hub's listing: zero here, said as unknown, until its files are in the store (then the store
    reads it as a found model, `found_spec`)."""
    from fichero_server.llm.mlx_model_store import ManagedModelSpec

    row = cached_hub().get(repo_id or "")
    if row is None:
        return None
    size = int(float(row.get("size_gb") or 0) * 1e9)
    return ManagedModelSpec(
        model_id=repo_id, repo_id=repo_id, revision="main", display_name=str(row.get("note") or repo_id),
        download_size_bytes=size, min_memory_bytes=size,
        memory_class="memory not stated until it is downloaded" if not size else
        f"needs at least {size / 1e9:.1f} GB unified memory (its weights)",
        capabilities=("text", "vision"),
        note=f"Found on Hugging Face by Fichero's model search: {row.get('offered_because') or ''}. "
             "Not measured here yet.",
    )


# --- what the rules see -------------------------------------------------------------------------------


def known_cards(a: Answers | None = None, *, include_not_built: bool = False) -> list[Card]:
    """Every card the rules choose from, without the network: the shipped seed, the installed models'
    cards, the cached repository's, and the Hub readers kept for the project's languages (#5593).
    `include_not_built` keeps seed cards whose runtime is not in this build (the bake-off names Tesseract)."""
    from fichero_server.recipes.cards import all_seed_cards, seed_cards

    seed = all_seed_cards() if include_not_built else seed_cards()
    cached = cached_repository()
    languages = a.languages if a is not None else frozenset()
    installed = installed_cards(seed)
    return [*mark_installed(seed), *installed,
            *(repository_cards(cached["records"], seed, languages) if cached else []),
            *mark_installed(hub_cards(a.languages if a is not None else None,
                                      _pinned_repos([*seed, *installed])))]


def _pinned_repos(cards: list[Card]) -> set[str]:
    return {str(c.pin["hf"]) for c in cards if "hf" in c.pin}


def egress_allowed() -> bool:
    """Whether discovery may reach the network: not when this engine works offline (local-only)."""
    from fichero_server.llm import is_local_only

    return not is_local_only()


async def discover(a: Answers, *, online: bool) -> tuple[list[Card], list[dict[str, Any]]]:
    """(every candidate card, what each source did). Reaches the network only when `online` and the
    egress check allows it; the repository listing is fetched again only when the cached one is a day
    old. Hugging Face cards come last and only from a search made now."""
    import asyncio

    from fichero_server.recipes.cards import all_seed_cards

    seed = all_seed_cards()
    sources: list[dict[str, Any]] = []
    shipped = mark_installed(c for c in seed if c.runs_here)
    sources.append({"source": "shipped", "state": "read", "count": len(shipped),
                    "detail": "the cards that ship with Fichero"})
    installed = installed_cards(seed)
    sources.append({"source": "installed", "state": "read", "count": len(installed),
                    "detail": "MLX vision models complete in this engine's model store"})
    allowed = online and egress_allowed()
    offline_why = ("this engine works offline (local-only), so nothing was fetched" if online
                   else "not searched: ask with online=true to search it")
    cached = cached_repository()
    state, detail = "cached", ""
    if allowed and _stale(cached):
        try:
            cached = await asyncio.to_thread(refresh_repository)
            state = "searched"
        except Exception as exc:  # the network or the repository failed: say so, keep the cache
            state, detail = "failed", f"the repository could not be read ({exc}); "
    if cached is None:
        repo_cards: list[Card] = []
        state = state if state == "failed" else ("offline" if online else "not-searched")
        detail += offline_why if state != "failed" else "nothing is cached"
    else:
        repo_cards = repository_cards(cached["records"], seed, a.languages)
        detail += f"Kraken's model repository on Zenodo, as fetched {cached['fetched_at']}"
    sources.append({"source": "kraken-repository", "state": state, "count": len(repo_cards), "detail": detail})
    hf_cards: list[Card] = []
    pinned = _pinned_repos([*seed, *installed])
    if allowed:
        try:
            searched = await search_hugging_face(a.languages)
            # Kept, so the rules choose from them for these languages without the network (#5593).
            keep_hub(searched, a.languages)
            hf_cards = mark_installed(c for c in searched if str(c.pin["hf"]) not in pinned)
            sources.append({"source": "hugging-face", "state": "searched", "count": len(hf_cards),
                            "detail": "image-to-text and image-text-to-text models by language tag; MLX "
                                      "builds only, never GGUF"})
        except Exception as exc:  # HTTPException from the one Hub fetch, or the network
            sources.append({"source": "hugging-face", "state": "failed", "count": 0,
                            "detail": f"the Hub could not be searched ({getattr(exc, 'detail', exc)})"})
    else:
        hf_cards = mark_installed(hub_cards(a.languages, pinned))
        if hf_cards:
            sources.append({"source": "hugging-face", "state": "cached", "count": len(hf_cards),
                            "detail": "the readers earlier searches found for these languages"})
        else:
            sources.append({"source": "hugging-face", "state": "offline" if online else "not-searched",
                            "count": 0, "detail": offline_why})
    return [*shipped, *installed, *repo_cards, *hf_cards], sources
