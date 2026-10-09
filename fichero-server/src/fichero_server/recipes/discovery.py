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

A Hub result is a reader only when its listing says so (`reads_text`, #5594): published as image-to-text,
or a vision-language model whose tags or name say OCR use; a chat build (uncensored, abliterated, heretic)
is never listed, only counted as left out. A size the listing does not state stays zero on the card and is
said as not stated.

The network is reached only when a caller asks (`online`), never at import time, never when the engine
works offline (`llm.is_local_only`, the egress setting), and never inside a request: the online search is
the open project's `find-models` job on the network lane (#5594, `search`), and `discover` reads only what
is installed and what the searches kept. Every candidate whose accuracy is not measured on the project
says it is unmeasured until a bake-off measures it.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

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


def candidate_installed(card: Card) -> bool | None:
    """Whether a candidate's model is already on this Mac (#5612): an MLX model in this Mac's store (`installed`, set
    by `mark_installed`), a spaCy pipeline, a Kraken model bundled with Fichero; None where a person downloads
    nothing first (a Kraken reader the run fetches, a cloud model)."""
    if card.installed is not None:
        return card.installed
    if set(card.pin) <= {"spacy", "version"} and "spacy" in card.pin:
        from fichero_server.llm.local_models import spacy_pipeline_available

        return bool(spacy_pipeline_available(str(card.pin["spacy"])))
    if card.pin.get("kraken_version") == "bundled" or "builtin" in card.pin:
        return True
    return None


def candidate_download(card: Card) -> dict[str, Any] | None:
    """The action that downloads a candidate's model, as the Start plan's `downloads` name it (`model.download` with
    its runtime and id, #5612), or None when there is nothing to download first: it is here already, the run fetches
    it (a Kraken reader), or it runs elsewhere."""
    from fichero_server.recipes.cards import mlx_model_for

    if not card.local or candidate_installed(card) is not False:
        return None
    repo = mlx_model_for(card.pin)
    if repo:
        from fichero_server.llm.mlx_model_store import get_mlx_model_store

        runtime, model = "mlx", get_mlx_model_store().canonical_id(repo)
    elif "spacy" in card.pin:
        runtime, model = "spacy", str(card.pin["spacy"])
    else:
        return None
    return {"runtime": runtime, "model": model, "action": "model.download",
            "params": {"runtime": runtime, "model": model}}


def candidate_place(card: Card) -> str:
    """Where a candidate runs, in the places the AI settings use (`llm.places`, #5612): this Mac, a machine of the
    person's own (a cluster, or a model server off this Mac), or the provider that runs it."""
    from types import SimpleNamespace

    from fichero_server.llm.places import OWN_MACHINE, PROVIDER, THIS_MAC, place_of

    if card.runs_on == "this-mac":
        return THIS_MAC
    if card.runs_on == "cluster":
        return OWN_MACHINE
    if card.runs_on.startswith("cloud:"):
        return place_of(SimpleNamespace(provider=card.runs_on.split(":", 1)[1], api_base=None))
    return PROVIDER


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
        "description": str(getattr(record, "description", "") or "").strip(),
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


def repository_record(doi: str) -> dict[str, Any] | None:
    """The kept repository record for a DOI (its own or its concept DOI), or None: no listing kept, or the
    record is not in it. Never the network (#5617)."""
    for row in (cached_repository() or {}).get("records", []):
        if doi in (row.get("doi"), row.get("concept_doi")):
            return row
    return None


#: A period a record's words name: "19th century", "16th-17th centuries", or a span of years.
_PERIOD = re.compile(r"\b\d{1,2}(?:st|nd|rd|th)(?:\s*(?:-|–|to|and)\s*\d{1,2}(?:st|nd|rd|th))?[\s-]centur(?:y|ies)\b"
                     r"|\b1\d{3}\s*(?:-|–|to)\s*1\d{3}\b", re.IGNORECASE)


def _and(words: list[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def record_words(row: dict[str, Any]) -> str:
    """What a repository record states, in words (#5617, `source.find.repository-reader-named`): its languages
    and scripts by name, then the material and period its own words name. Empty when it states none."""
    from fichero_server.recipes.names import language_name, script_name

    langs = [language_name(t) for t in sorted(_tags(row.get("languages")) or [])]
    scripts = [script_name(s) for s in sorted(row.get("scripts") or [])]
    text = " ".join([row.get("summary", ""), row.get("description", ""), *row.get("keywords", [])])
    parts = [_and(langs)] if langs else []
    if scripts:
        parts.append(_and(scripts) + (" script" if len(scripts) == 1 else " scripts"))
    parts += sorted(_row_material({"summary": text, "keywords": []}))
    parts += list(dict.fromkeys(m.group(0) for m in _PERIOD.finditer(text)))
    return ", ".join(parts)


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
        if stated := record_words(row):
            why += f"; its record states {stated}"
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


#: Words (tags, or parts of the repository's name) that mark a chat build, never a reader, whatever task it
#: is published under (#5594: 'uncensored', 'abliterated' and 'Heretic' builds were offered for Fraktur).
CHAT_BUILD_WORDS = frozenset({"uncensored", "abliterated", "decensored", "heretic", "unrestricted"})
#: Words that say a vision-language model reads text: its OCR use (#5594, `source.find.hub-readers-only`).
OCR_WORDS = frozenset({"ocr", "htr", "text-recognition", "textline_recognition", "text recognition", "handwriting",
                       "handwritten", "handwriting-recognition", "document-understanding", "document-ocr"})
#: Script words a reader's tags or name may state, as ISO 15924 codes.
_SCRIPT_WORDS = {"fraktur": "Latf", "kuzushiji": "Jpan"}


def _words(model: dict[str, Any]) -> frozenset[str]:
    """A listing's tags and the parts of its repository's name, lower-cased."""
    name = str(model.get("modelId") or model.get("id") or "").rsplit("/", 1)[-1].lower()
    return frozenset({str(t).lower() for t in model.get("tags") or []} | set(re.split(r"[^a-z0-9]+", name)))


def reads_text(model: dict[str, Any]) -> str | None:
    """What a Hub listing reads, in words, when it is a reader; None for anything else (#5594,
    `source.find.hub-readers-only`). Decided from its listing alone (`pipeline_tag`, `tags`, its name):
    published as image-to-text (not a captioner), or a vision-language model (image-text-to-text) whose
    tags or name say OCR use. A chat build is never a reader, whatever its task."""
    words = _words(model)
    if words & CHAT_BUILD_WORDS:
        return None
    ocr = bool(words & OCR_WORDS)
    if model.get("pipeline_tag") == "image-to-text" and (ocr or "image-captioning" not in words):
        return "an OCR model (image-to-text)" if ocr else "reads text from images (image-to-text)"
    if model.get("pipeline_tag") == "image-text-to-text" and ocr:
        return "a vision-language model made for OCR"
    return None


def _hub_material(words: frozenset[str]) -> frozenset[str]:
    found = set()
    if words & {"htr", "handwriting", "handwritten", "handwriting-recognition", "manuscript", "manuscripts"}:
        found.add("handwriting")
    if words & {"print", "printed", "newspaper", "newspapers"}:
        found.add("print")
    return frozenset(found)


def _hub_tags(model: dict[str, Any]) -> frozenset[str] | None:
    return _tags([t for t in model.get("tags") or [] if re.fullmatch(r"[a-z]{2,3}", str(t))])


def _hf_card(model: dict[str, Any], what: str, how: str, wanted: frozenset[str],
             languages: frozenset[str] | None = None) -> Card:
    """A Hub reader's card. Its reason says why it fits (#5594, `source.find.reason-names-fit`): what it
    reads, the script and material its listing states, the project's languages it lists by name, and how
    it runs here. Its size and memory are not in the listing: zero here, said as not stated."""
    from fichero_server.recipes.names import language_name, script_name

    repo = str(model.get("modelId") or model.get("id"))
    tags = [str(t) for t in model.get("tags") or []]
    words = _words(model)
    licence = next((t.split(":", 1)[1] for t in tags if t.startswith("license:")), "")
    langs = _hub_tags(model) or languages
    scripts = frozenset(code for word, code in _SCRIPT_WORDS.items() if word in words)
    material = _hub_material(words)
    why = [what]
    if scripts:
        why.append("made for " + " and ".join(script_name(c) for c in sorted(scripts)))
    if material:
        why.append("for " + " and ".join(sorted(material)))
    listed = sorted(wanted & langs) if langs else []
    if listed:
        why.append("lists " + ", ".join(language_name(t) for t in listed))
    elif wanted:
        why.append("does not list your languages")
    why.append(how)
    return Card(
        id=f"mlx:hf/{repo}@main", pin={"hf": repo, "revision": "main"}, jobs=READER_JOBS,
        scripts=covered_scripts(scripts) if scripts else None, languages=langs, material=material,
        open_licence=_is_open(licence), trainable=True, licence=licence, note=repo.rsplit("/", 1)[-1],
        source="hugging-face", offered_because="; ".join(why),
    )


def _runs_on_mlx(model: dict[str, Any]) -> bool:
    tags = set(model.get("tags") or [])
    return model.get("library_name") == "mlx" or "mlx" in tags


def _gguf_only(model: dict[str, Any]) -> bool:
    tags = set(model.get("tags") or [])
    return ("gguf" in tags or model.get("library_name") == "gguf") and not _runs_on_mlx(model)


async def search_hugging_face(languages: frozenset[str],
                              progress: Callable[[str], None] = lambda _: None) -> tuple[list[Card], int]:
    """(reader candidates on the Hub for these languages, how many builds this Mac runs were left out as
    not readers). Only builds this Mac can run, only readers by their listing (`reads_text`), each saying
    why it fits. `progress` is told each query in words. Network: call only behind the egress check.
    Raises the Hub fetch's error."""
    from fichero_server.api.routes.ai.models import _fetch_hf_models

    filters = [[lang.split("-")[0]] for lang in sorted(languages)] or [[]]
    found: dict[str, Card] = {}
    left_out: set[str] = set()
    originals: list[tuple[dict[str, Any], str]] = []
    queries, asked = len(HF_READER_TASKS) * len(filters) * 2, 0
    for task in HF_READER_TASKS:
        for tags in filters:
            for mlx in (True, False):
                asked += 1
                progress(f"Searching Hugging Face ({task}, query {asked} of {queries})")
                listing = await _fetch_hf_models(task=task, tags=["mlx", *tags] if mlx else (tags or None),
                                                 limit=HF_LIMIT)
                for m in listing:
                    what = reads_text(m)
                    if mlx and _runs_on_mlx(m) and not _gguf_only(m):
                        repo = str(m.get("modelId") or m.get("id"))
                        if what is None:
                            left_out.add(repo)
                        else:
                            found.setdefault(repo, _hf_card(
                                m, what, "an MLX build on Hugging Face that runs on this Mac", languages))
                    elif (not mlx and what is not None and not _runs_on_mlx(m) and not _gguf_only(m)
                          and "safetensors" in (m.get("tags") or [])):
                        originals.append((m, what))
    for original, what in originals[:HF_CONVERSIONS_LOOKED_UP]:
        repo = str(original.get("modelId") or original.get("id"))
        progress(f"Looking up the MLX conversion of {repo}")
        for m in await _fetch_hf_models(tags=["mlx", f"base_model:{repo}"], limit=5):
            if _runs_on_mlx(m) and not _gguf_only(m):
                conversion = str(m.get("modelId") or m.get("id"))
                if _words(m) & CHAT_BUILD_WORDS:
                    left_out.add(conversion)
                    continue
                found.setdefault(conversion, _hf_card(
                    m, what, f"the MLX conversion of {repo} (safetensors on Hugging Face), which runs on this Mac",
                    languages, _hub_tags(original)))
                break
    return sorted(found.values(), key=lambda c: c.id), len(left_out - set(found))


def _hub_file() -> dict[str, Any]:
    try:
        data = json.loads((_store_root() / HUB_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def cached_hub() -> dict[str, dict[str, Any]]:
    """The Hub readers the searches found, {repo: row}, each row with the languages it was found for."""
    found = _hub_file().get("found")
    return found if isinstance(found, dict) else {}


def _languages_key(languages: frozenset[str]) -> str:
    return ",".join(sorted(languages)) or "any"


def hub_left_out(languages: frozenset[str]) -> int | None:
    """How many builds the last Hub search for these languages left out as not readers (#5594); None when
    no search for them was kept."""
    count = (_hub_file().get("left_out") or {}).get(_languages_key(languages))
    return int(count) if isinstance(count, int) else None


def keep_hub(cards: list[Card], languages: frozenset[str], left_out: int = 0) -> None:
    """Keep what a Hub search for these languages found, beside what earlier searches found (#5593), and how
    many it left out (#5594). A reader an earlier search found for these languages that this one did not find
    is no longer kept for them (a chat build kept before the reader rule is gone after the next search)."""
    if not languages:
        return
    data = _hub_file()
    found = cached_hub()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    found_now = {str(card.pin["hf"]) for card in cards}
    for repo, row in list(found.items()):
        if repo not in found_now:
            row["found_for"] = sorted(set(row.get("found_for") or ()) - languages)
            if not row["found_for"]:
                del found[repo]
    for card in cards:
        repo = str(card.pin["hf"])
        before = found.get(repo) or {}
        found[repo] = {"repo": repo, "languages": sorted(card.languages) if card.languages else None,
                       "scripts": sorted(card.scripts) if card.scripts else None,
                       "material": sorted(card.material), "licence": card.licence, "note": card.note,
                       "offered_because": card.offered_because, "size_gb": card.size_gb,
                       "found_for": sorted({*before.get("found_for", []), *languages}), "found_at": now}
    left = dict(data.get("left_out") or {})
    left[_languages_key(languages)] = left_out
    folder = _store_root()
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / f".{HUB_FILE}.tmp"
    tmp.write_text(json.dumps({"found": found, "left_out": left}, ensure_ascii=False, indent=1), encoding="utf-8")
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
            id=f"mlx:hf/{repo}@main", pin={"hf": repo, "revision": "main"}, jobs=READER_JOBS,
            scripts=frozenset(row["scripts"]) if row.get("scripts") else None,
            languages=_tags(row.get("languages")), material=frozenset(row.get("material") or ()),
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


#: Why the online search did not run when no project is open: its job is one of a project's (#5594).
NO_PROJECT = "the online search runs as an Activity job of an open project: open a project to search"


def discover(a: Answers, *, online: bool, search: dict[str, Any] | None = None,
             not_searched: str | None = None) -> tuple[list[Card], list[dict[str, Any]]]:
    """(every candidate card, what each source did), never reaching the network: the shipped cards, the
    installed models, and the repository listing and Hub readers the online search kept (#5594: the search
    itself is a job, `find-models`). `search` is that job's row when `online` asked for one: while it runs the
    two online sources say they are being searched, and once it is done they say what it found. `not_searched`
    says why no search was made when one was asked for (no project open)."""
    from fichero_server.recipes.cards import all_seed_cards

    seed = all_seed_cards()
    sources: list[dict[str, Any]] = []
    shipped = mark_installed(c for c in seed if c.runs_here)
    sources.append({"source": "shipped", "state": "read", "count": len(shipped),
                    "detail": "the cards that ship with Fichero"})
    installed = installed_cards(seed)
    sources.append({"source": "installed", "state": "read", "count": len(installed),
                    "detail": "MLX vision models complete in this engine's model store"})
    if online and not egress_allowed():
        why, quiet = "this engine works offline (local-only), so nothing was fetched", "offline"
    elif online:
        why, quiet = not_searched or "being searched", "not-searched"
    else:
        why, quiet = "not searched: ask with online=true to search it", "not-searched"
    cached = cached_repository()
    if cached is None:
        repo_cards: list[Card] = []
        repo_source = {"source": "kraken-repository", "state": quiet, "count": 0, "detail": why}
    else:
        repo_cards = repository_cards(cached["records"], seed, a.languages)
        repo_source = {"source": "kraken-repository", "state": "cached", "count": len(repo_cards),
                       "detail": f"Kraken's model repository on Zenodo, as fetched {cached['fetched_at']}"}
    hf_cards = mark_installed(hub_cards(a.languages, _pinned_repos([*seed, *installed])))
    left_out = hub_left_out(a.languages) or 0
    if hf_cards or hub_left_out(a.languages) is not None:
        hub_source = {"source": "hugging-face", "state": "cached", "count": len(hf_cards), "left_out": left_out,
                      "detail": "the readers earlier searches found for these languages" + _left_out_words(left_out)}
    else:
        hub_source = {"source": "hugging-face", "state": quiet, "count": 0, "detail": why}
    if search is not None:
        _say_search(search, repo_source, hub_source)
    sources += [repo_source, hub_source]
    return [*shipped, *installed, *repo_cards, *hf_cards], sources


def _left_out_words(left_out: int) -> str:
    if not left_out:
        return ""
    return f"; {left_out} build{'s' if left_out != 1 else ''} left out: chat models, not readers"


def _say_search(search: dict[str, Any], *rows: dict[str, Any]) -> None:
    """The online sources as the search job leaves them: being searched, what it found, or why it failed."""
    state = search.get("state")
    if state in ("waiting", "running", "paused"):
        doing = search.get("reason") or "waiting for the network lane"
        for row in rows:
            row["state"] = "searching"
            row["detail"] = (f"being searched now (Activity job {search['id']}: {doing}); "
                             f"{'showing what was kept before' if row['count'] else 'nothing kept yet'}")
        return
    if state == "failed":
        for row in rows:
            row["state"], row["detail"] = "failed", f"the search failed ({search.get('reason') or 'no reason'})"
        return
    try:
        done = json.loads(search.get("detail") or "{}").get("sources") or {}
    except ValueError:
        done = {}
    for row in rows:
        said = done.get(row["source"])
        if said:
            row["state"], row["detail"] = said["state"], said["detail"]


# --- the online search, as an Activity job (#5594) ------------------------------------------------------

#: The job kind: a person waits on it, on the network lane (`source.find.online-search-is-a-job`).
SEARCH_KIND = "find-models"


def register_job_kinds() -> None:
    from fichero_server.core.background_compute import set_utility_qos
    from fichero_server.execution import jobs

    if SEARCH_KIND not in jobs.KINDS or jobs.KINDS[SEARCH_KIND].run is None:
        jobs.register_kind(SEARCH_KIND, _run_search, model=None, lane="network", qos=set_utility_qos,
                           name="Find reading models online")


def _subject(languages: frozenset[str]) -> str:
    return f"languages:{_languages_key(languages)}"


def _languages_of(subject: str) -> frozenset[str]:
    key = subject.partition(":")[2]
    return frozenset() if key in ("", "any") else frozenset(key.split(","))


def search(db: Any, languages: frozenset[str]) -> dict[str, Any]:
    """The search job for these languages (its row: id, state, reason, detail, finished_at): the one waiting
    or running, or one done within a day; otherwise a new one, queued on the network lane with a person
    waiting on it. Never reaches the network itself."""
    from fichero_server.core.timeutil import ensure_utc
    from fichero_server.execution import jobs

    register_job_kinds()
    subject = _subject(languages)
    latest = jobs.job_id_for(db, SEARCH_KIND, subject)
    row = jobs.find_jobs(db, kinds=[SEARCH_KIND], job_id=latest)[0] if latest else None
    if row is not None:
        if row["state"] in ("waiting", "running", "paused"):
            return row
        finished = row["finished_at"]
        if (row["state"] == "done" and finished is not None
                and datetime.now(timezone.utc) - ensure_utc(finished) < REFRESH_AFTER):
            return row
    job_id = jobs.enqueue(db, SEARCH_KIND, subject, started_by="owner", watched=True)
    return jobs.find_jobs(db, kinds=[SEARCH_KIND], job_id=job_id)[0]


def _run_search(db: Any, subject: str) -> dict[str, Any]:
    """The job's work: search, keep what was found, and keep what each source did on the job's row."""
    from fichero_server.execution import jobs

    job_id = jobs.current_job_id() or jobs.job_id_for(db, SEARCH_KIND, subject)

    def say(words: str) -> None:
        jobs.save_detail(db, job_id, json.dumps({"doing": words}, ensure_ascii=False), reason=words)

    result = search_online(_languages_of(subject), progress=say)
    jobs.save_detail(db, job_id, json.dumps(result, ensure_ascii=False))
    failed = [s["detail"] for s in result["sources"].values() if s["state"] == "failed"]
    if len(failed) == len(result["sources"]):
        raise RuntimeError("; ".join(failed))
    return result


def search_online(languages: frozenset[str], progress: Callable[[str], None] = lambda _: None) -> dict[str, Any]:
    """Fetch Kraken's repository listing when the kept one is a day old, and search Hugging Face for these
    languages, keeping both in the model store's `discovery/` folder; return what each source did. Network:
    run only as the `find-models` job. Refused when this engine works offline."""
    import asyncio

    if not egress_allowed():
        raise RuntimeError("this engine works offline (local-only), so nothing was searched")
    sources: dict[str, dict[str, Any]] = {}
    cached = cached_repository()
    if _stale(cached):
        progress("Reading Kraken's model repository on Zenodo")
        try:
            cached = refresh_repository()
            sources["kraken-repository"] = {"state": "searched", "detail": (
                f"Kraken's model repository on Zenodo, fetched {cached['fetched_at']}")}
        except Exception as exc:  # the network or the repository failed: say so, keep the cache
            sources["kraken-repository"] = {"state": "failed",
                                            "detail": f"the repository could not be read ({exc})"}
    else:
        sources["kraken-repository"] = {"state": "cached", "detail": (
            f"Kraken's model repository on Zenodo, as fetched {cached['fetched_at']} (fetched again after a day)")}
    try:
        found, left_out = asyncio.run(search_hugging_face(languages, progress))
        keep_hub(found, languages, left_out)
        sources["hugging-face"] = {"state": "searched", "count": len(found), "left_out": left_out, "detail": (
            f"{len(found)} reader{'s' if len(found) != 1 else ''} found: image-to-text models and vision-language "
            "models made for OCR, by language tag; MLX builds only, never GGUF" + _left_out_words(left_out))}
    except Exception as exc:  # HTTPException from the one Hub fetch, or the network
        sources["hugging-face"] = {"state": "failed",
                                   "detail": f"the Hub could not be searched ({getattr(exc, 'detail', exc)})"}
    return {"languages": sorted(languages), "searched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sources": sources}
