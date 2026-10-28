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
the open project's `find-models` job on the search lane (#5594, `search`), and `discover` reads only what
is installed and what the searches kept. Every candidate whose accuracy is not measured on the project
says it is unmeasured until a bake-off measures it.
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from fichero_server.recipes.assemble import Answers, Card
from fichero_server.llm.local_model_facts import GIB, gib

logger = logging.getLogger(__name__)

#: The jobs a found reader does: a vision model reads a line's picture (the bake-off's way) or a page.
READER_JOBS = frozenset({"read-a-line", "read-a-page"})
#: A job whose model is one reader SAMPLED several times: its finder is the readers' (vision models only), never a
#: text-model search (`source.disagree.one-reader-says-which-to-add`, #5812).
SAMPLED_READER_JOBS = frozenset({"find-where-readers-disagree"})
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


def _trained_terms(card: dict[str, Any]) -> tuple[str, bool, frozenset[str] | None]:
    """(licence, open, languages) of a model Fichero trained, from its own card (#5683,
    `source.model.trained-card-keeps-its-release`). Open to use (it is the person's own; `open_licence` is whether
    the rules may choose it without a licence to accept), but its licence says "not for release" unless its card
    says `not_for_release: false`, the one release test; its languages as the card names them, never its base's
    README's (None: not said)."""
    from fichero_server.training.project_models import _may_publish

    licence = "trained by you" if _may_publish(card) else "trained by you; not for release"
    return licence, True, _tags(card.get("languages"))


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
        languages = _tags(meta.get("language"))
        if trained is not None:
            licence, open_licence, languages = _trained_terms(trained)
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
            jobs=READER_JOBS, scripts=None, languages=languages, material=frozenset(),
            open_licence=open_licence, size_gb=round(gib(spec.download_size_bytes), 3),
            memory_gb=round(gib(memory), 2), trainable=True, licence=licence,
            note=spec.display_name, source="installed", offered_because=why, installed=True,
        )
    return sorted(out.values(), key=lambda c: c.id)


#: The jobs that send a model the text alone and that no shipped card covers: a text model already here does them
#: (`source.recipe.local-text-models-are-cards`, #5619).
TEXT_MODEL_JOBS = frozenset({"find-statements", "split-into-entries",
                             # Find names too (#5660 item 4): spaCy's shipped pipelines are its default; a text model
                             # here, Apple Intelligence or a cloud model is the person's to choose instead.
                             "find-names-tag-words",
                             # A folder's archival description (`catalogue.folder-description-fields`, #6087).
                             "describe-for-the-catalogue",
                             # Translate and Correct write text too: a text model here, Apple Intelligence or a cloud model is a
                             # candidate for both (owner 2026-10-24: every step can choose models), where the menu offered one Qwen.
                             "translate-transliterate-normalise", "correct",
                             # The two other jobs a text model does with the text alone (the Check and Extract to a table steps).
                             "extract-to-a-table", "check"})

#: The languages Apple Intelligence's on-device model writes (its published list), for the rewriting jobs, which refuse a model
#: that does not list the language (it would rewrite it into one it knows).
APPLE_INTELLIGENCE_LANGUAGES = frozenset({"en", "fr", "de", "it", "pt", "es", "zh", "ja", "ko"})


def text_model_languages(repo_id: str) -> tuple[frozenset[str] | None, bool]:
    """(the languages a local text model lists, whether it is multilingual) from its repository's name, for the rewriting jobs
    (Correct, Translate): Qwen3's family is multilingual, Llama 3.2 lists eight languages, any other says nothing and so is
    refused for them, never trusted with a language it may not know. ponytail: by name until a card carries it."""
    name = repo_id.casefold()
    if "qwen" in name:
        return None, True
    if "llama-3.2" in name or "llama-3.1" in name:
        return frozenset({"en", "de", "fr", "it", "pt", "hi", "es", "th"}), False
    return None, False
#: Model servers the person runs, whose enabled models are cards for those jobs (the engine's own MLX server is
#: its model store's, read above).
_TEXT_SERVERS = frozenset({"ollama", "lmstudio"})


def installed_spacy_cards(languages: frozenset[str], seed: tuple[Card, ...] | list[Card] = ()) -> list[Card]:
    """A Find names card for every spaCy pipeline installed on this Mac for the project's languages that no shipped
    card pins (#5688: a Names try compared the shipped small one alone, beside an installed medium one)."""
    from fichero_server.llm.local_models import SPACY_MODELS, spacy_pipeline_available

    pinned = {str(c.pin.get("spacy")) for c in seed if "spacy" in c.pin}
    asked = {t.split("-")[0] for t in languages}
    out = []
    for name, info in SPACY_MODELS.items():
        lang = str(info.get("language") or "")
        if name in pinned or (asked and lang not in asked) or not spacy_pipeline_available(name):
            continue
        # disk_mb is decimal MB at its source (local_models.py), so it goes through bytes to GiB.
        out.append(Card(
            id=f"spacy:pkg/{name}@installed", pin={"spacy": name, "version": "installed"},
            jobs=frozenset({"find-names-tag-words"}), scripts=None, languages=frozenset({lang}) if lang else None,
            material=frozenset(), open_licence=True, licence=str(info.get("licence") or ""),
            size_gb=round(float(info.get("disk_mb") or 0) * 1_000_000 / GIB, 3), note=f"spaCy {name}", source="installed",
            installed=True, offered_because=f"installed on this Mac: the spaCy pipeline {name}",
        ))
    return out


def _is_embedder(model: Any) -> bool:
    caps = {str(c).lower() for c in (getattr(model, "capabilities", None) or [])}
    return bool(caps & {"embedding", "embeddings", "embed"}) or "embed" in str(model.model_id).lower()


def local_text_cards(seed: tuple[Card, ...] | list[Card] = ()) -> list[Card]:
    """A card for every text model already on this Mac or on a machine of the person's own, for
    `TEXT_MODEL_JOBS` (`source.recipe.local-text-models-are-cards`, #5619): each MLX model complete in this Mac's
    store that reads text (its licence from its seed card, else its own README), and each enabled model of the
    person's Ollama and LM Studio rows (no embedder). Where it runs is by its address (`llm.places`): a server on
    this Mac runs on this Mac, free; one on another machine of the person's own is free, but its pages leave this
    Mac (`cloud:<type>`), so the rules choose it only where the project lets pages leave."""
    from fichero_server.llm.local_inference import local_memory_gb
    from fichero_server.llm.mlx_model_store import MANAGED_MLX_MODELS, get_mlx_model_store

    out: dict[str, Card] = {}
    store = get_mlx_model_store()
    licence_of = {str(c.pin.get("hf")): c.licence for c in seed if "hf" in c.pin}
    for name in [*MANAGED_MLX_MODELS, *store.trained_model_ids(), *store._scan_cached_repo_ids()]:
        model_id = store.canonical_id(name)
        if model_id is None or f"mlx:{model_id}" in out:
            continue
        spec = store.spec(model_id)
        if tuple(spec.capabilities) != ("text",) or not store.is_complete(spec):
            continue  # a model with a vision path reads pages: a reader, never a text job's (#5668)
        if (trained := store.trained_card(model_id)) is not None:
            licence, open_licence, _languages = _trained_terms(trained)
        else:
            licence = licence_of.get(spec.repo_id) or str(
                (meta := _front_matter(store.snapshot_path(spec) / "README.md")).get("license_name")
                or meta.get("license") or "")
            open_licence = _is_open(licence)
        out[f"mlx:{model_id}"] = Card(
            id=f"mlx:text/{spec.repo_id}@{spec.revision}", pin={"hf": spec.repo_id, "revision": spec.revision},
            jobs=TEXT_MODEL_JOBS, scripts=None, languages=text_model_languages(spec.repo_id)[0],
            multilingual=text_model_languages(spec.repo_id)[1], material=frozenset(),
            open_licence=open_licence, licence=licence,
            size_gb=round(gib(spec.download_size_bytes), 3),
            memory_gb=local_memory_gb(spec),  # the load gate's number (#5537)
            note=spec.display_name, source="installed", installed=True,
            offered_because=f"installed on this Mac: {spec.display_name}, in your model store; it reads text",
        )
    out.update({f"row:{c.id}": c for c in _server_text_cards()})
    return sorted(out.values(), key=lambda c: c.id)


#: Apple Intelligence as a card: the on-device Foundation Models through this build's fm-bridge (`llm.providers`,
#: provider `apple`, the text model `apple-intelligence` the factory defaults name).
APPLE_INTELLIGENCE_PIN = {"cloud": "apple", "model": "apple-intelligence"}
#: The cloud model a person adds for text work when none is configured (#5660 item 4: "a cloud model (Claude)").
CLAUDE_PROVIDER = "anthropic"


def other_text_cards() -> list[Card]:
    """The text models a person may choose for a text job beyond spaCy and the models already here (#5660 item 4):
    offered by the finder and kept by use-candidate, never chosen by the rules by themselves (a step with no text
    model here still says so, `source.recipe.local-text-models-are-cards`),
    each said plainly where it cannot run yet rather than offered as if it could: Apple Intelligence (this Mac's
    Foundation Models; not available where this build or this Mac lacks it), the catalogue's MLX text models still
    to download, and the cloud models of the person's provider rows (Claude, when none is configured, as a card that
    says to add it in Settings › AI)."""
    from fichero_server.llm.local_inference import local_memory_gb
    from fichero_server.llm.local_model_choice import apple_intelligence_in_this_build
    from fichero_server.llm.mlx_model_store import MANAGED_MLX_MODELS, get_mlx_model_store

    try:
        apple_here = bool(apple_intelligence_in_this_build())
    except Exception as exc:  # noqa: BLE001 -- unreadable: said as not available, never offered as if it ran
        logger.info("Apple Intelligence could not be checked: %s", exc)
        apple_here = False
    out = [Card(
        id="apple:intelligence/foundation-models@os", pin=dict(APPLE_INTELLIGENCE_PIN), jobs=TEXT_MODEL_JOBS,
        scripts=None, languages=APPLE_INTELLIGENCE_LANGUAGES, material=frozenset(), open_licence=True, licence="system",
        note="Apple Intelligence, on this Mac", source="installed", runs_here=apple_here, offered_only=True,
        cannot_run_because="" if apple_here else "Apple Intelligence is not available in this build or on this Mac",
        offered_because="Apple's on-device model (Foundation Models): free, and the pages stay on this Mac",
    )]
    store = get_mlx_model_store()
    for name, spec in MANAGED_MLX_MODELS.items():
        if tuple(spec.capabilities) != ("text",) or store.is_complete(spec):
            continue  # a reader (vision path), or one already here (`local_text_cards`')
        out.append(Card(
            id=f"mlx:text/{spec.repo_id}@{spec.revision}", pin={"hf": spec.repo_id, "revision": spec.revision},
            jobs=TEXT_MODEL_JOBS, scripts=None, languages=text_model_languages(spec.repo_id)[0],
            multilingual=text_model_languages(spec.repo_id)[1], material=frozenset(), open_licence=True,
            licence="", size_gb=round(gib(spec.download_size_bytes), 3),
            memory_gb=local_memory_gb(spec), note=spec.display_name, source="shipped", offered_only=True,
            installed=False, offered_because=f"{spec.display_name}, an MLX model to download to this Mac; it reads text",
        ))
    out += _cloud_text_cards()
    out += _parser_statement_cards()
    return out


def _parser_statement_cards() -> list[Card]:
    """The parser's tier for Find statements (#5637, `source.job.find-statements.parser-tier`): each bundled spaCy
    pipeline, its dependency parse's subject-verb-object triples as proposals, free on this Mac. Offered, the person's
    to choose; never chosen by the rules over a text model they have."""
    from dataclasses import replace

    from fichero_server.recipes.cards import seed_cards

    return [replace(c, id=c.id.replace("spacy:pkg/", "spacy:svo/", 1), jobs=frozenset({"find-statements"}),
                    offered_only=True, note=f"{c.note.split(';')[0]}: its parse's subject-verb-object statements",
                    offered_because="free and on this Mac: the parser's statements, proposals for you to accept or "
                                    "reject (no language model)")
            for c in seed_cards() if c.id.startswith("spacy:pkg/")]


FRONTIER_PROVIDERS_FILE = Path(__file__).parent / "seed" / "frontier-cloud-providers.txt"


@lru_cache(maxsize=1)
def frontier_providers() -> frozenset[str]:
    """The cloud provider types whose models count as multilingual (a default the owner can change)."""
    lines = FRONTIER_PROVIDERS_FILE.read_text(encoding="utf-8").splitlines()
    return frozenset(line.strip() for line in lines if line.strip() and not line.startswith("#"))


def _retired(model_id: str) -> dict[str, Any]:
    """A cloud card's fields when its provider no longer serves the model (#6096): it cannot run, and says why, so the menu
    shows it, use-candidate refuses it and no rule picks it. Empty for a model still served."""
    from fichero_server.llm.model_types import retired_because

    why = retired_because(model_id or "")
    return {"runs_here": False, "cannot_run_because": f"retired: {why}"} if why else {}


def _cloud_text_cards() -> list[Card]:
    """The enabled models of the person's cloud provider rows, as cards for `TEXT_MODEL_JOBS`: they run through the
    provider settings already there, and the rules take one only where the project lets pages leave this Mac. With no
    Claude row, a Claude card that says to add it first (never one that pretends to run)."""
    from fichero_server.db.app import get_app_db
    from fichero_server.llm import LLMConfig
    from fichero_server.llm.places import PROVIDER, place_of

    out = []
    try:
        app_db = get_app_db()
        rows = app_db.list_providers()
    except Exception as exc:  # noqa: BLE001 -- no app database (a bare tool run): no rows, said in the log
        logger.info("cloud text cards: the provider rows could not be read: %s", exc)
        rows = []
    seen_types = set()
    for row in rows:
        ptype = row.provider_type.value
        if not row.enabled or place_of(LLMConfig(provider=ptype, model="", api_base=row.api_base)) != PROVIDER:
            continue
        seen_types.add(ptype)
        for model in app_db.list_models(row.id):
            if not model.enabled or _is_embedder(model):
                continue
            frontier = ptype in frontier_providers()
            gone = _retired(model.model_id)
            out.append(Card(
                id=f"{ptype}:{model.model_id}@{row.id}", pin={"cloud": ptype, "model": model.model_id},
                jobs=TEXT_MODEL_JOBS if frontier else TEXT_MODEL_JOBS - {"correct"}, multilingual=frontier,  # Correct: the frontier list only
                scripts=None, languages=None, material=frozenset(),
                runs_on=f"cloud:{ptype}", open_licence=True, licence="",
                note=f"{model.name or model.model_id} ({row.name})", source="installed", offered_only=True,
                offered_because=f"a cloud model from your {row.name} settings: its pages leave this Mac",
                **gone,
            ))
    if CLAUDE_PROVIDER not in seen_types:
        out.append(Card(
            id="anthropic:claude@settings", pin={"cloud": CLAUDE_PROVIDER, "model": "claude"}, jobs=TEXT_MODEL_JOBS,
            scripts=None, languages=None, material=frozenset(), runs_on=f"cloud:{CLAUDE_PROVIDER}",
            open_licence=True, licence="", note="Claude (Anthropic), in the cloud", source="installed", offered_only=True,
            runs_here=False, cannot_run_because="add Claude (Anthropic) in Settings › AI first",
            offered_because="a cloud model through your provider settings: its pages leave this Mac",
        ))
    return out


def _server_text_cards() -> list[Card]:
    """The enabled models of the person's Ollama and LM Studio rows, as cards for `TEXT_MODEL_JOBS`."""
    from fichero_server.db.app import get_app_db
    from fichero_server.llm import LLMConfig
    from fichero_server.llm.places import OWN_MACHINE, THIS_MAC, place_of

    try:
        app_db = get_app_db()
        rows = app_db.list_providers()
    except Exception as exc:  # noqa: BLE001 -- no app database (a bare tool run): no rows, said in the log
        logger.info("local_text_cards: the provider rows could not be read: %s", exc)
        return []
    out = []
    for row in rows:
        ptype = row.provider_type.value
        if not row.enabled or ptype not in _TEXT_SERVERS:
            continue
        place = place_of(LLMConfig(provider=ptype, model="", api_base=row.api_base))
        if place not in (THIS_MAC, OWN_MACHINE):
            continue
        here = place == THIS_MAC
        where = "on this Mac" if here else "on a machine of yours (its pages leave this Mac)"
        for model in app_db.list_models(row.id):
            if not model.enabled or _is_embedder(model):
                continue
            out.append(Card(
                id=f"{ptype}:{model.model_id}@{row.id}", pin={"cloud": ptype, "model": model.model_id},
                jobs=TEXT_MODEL_JOBS, scripts=None, languages=None, material=frozenset(),
                runs_on="this-mac" if here else f"cloud:{ptype}", open_licence=True,
                licence="", note=f"{model.name or model.model_id} on {row.name}", source="installed",
                installed=here,  # on this Mac it is installed here, so the rules take it over the parser (#5637)
                offered_because=f"a model you run with {row.name}, {where}, free",
            ))
    return out


#: The frontier families offered for a key with no saved model, newest of each, in the order they are expected to read
#: best (owner 2026-10-24: mini and nano are fine, ranked below their full model). (words it has, words it must not have)
FRONTIER_FAMILIES = (
    (("gemini", "pro"), ()), (("claude", "opus"), ()), (("claude", "sonnet"), ()), (("gpt-5",), ("-mini", "-nano")),
    (("gemini", "flash"), ("lite",)), (("claude", "haiku"), ()), (("gpt-5", "-mini"), ()), (("gemini", "flash", "lite"), ()),
    (("gpt-5", "-nano"), ()),
)
#: Never a reader: not a model for reading a page.
_NOT_A_READER = ("codex", "image", "tts", "audio", "live", "embed")


def _family(model_id: str) -> int | None:
    """The index of the frontier family a model id belongs to (`FRONTIER_FAMILIES`), or None."""
    m = model_id.casefold()
    for i, (has, hasnt) in enumerate(FRONTIER_FAMILIES):
        if all(w in m for w in has) and not any(w in m for w in hasnt) and not any(w in m for w in _NOT_A_READER):
            return i
    return None


def frontier_rank(card: Card) -> int:
    """Where a cloud reader ranks before any measurement: its frontier family's place, else after them all. ponytail: a
    fixed expected order; a CER measured on the Test Corpus per language is the upgrade (owner 2026-10-24)."""
    family = _family(str(card.pin.get("model", "")))
    return len(FRONTIER_FAMILIES) if family is None else family


def frontier_catalog_models(provider: str) -> list[str]:
    """The newest vision model of each frontier family the price list has for `provider`, best expected first.
    ponytail: newest = the largest version numbers in the id; a date is no version."""
    from fichero_server.llm.model_types import list_models_for_provider

    try:
        from fichero_server.llm.model_types import retired_because

        listed = [m["model_id"] for m in list_models_for_provider(provider)
                  if m.get("supports_vision") and not retired_because(m["model_id"])]  # #6096
    except Exception:  # noqa: BLE001 -- no price list: no offers, never a failed listing
        return []
    out = []
    for i in range(len(FRONTIER_FAMILIES)):
        fits = [m for m in listed if _family(m) == i]
        if fits:
            out.append(max(fits, key=_version))
    return out


def _version(model_id: str) -> tuple[int, ...]:
    """A model id's version numbers (claude-sonnet-4-6 -> (4, 6)); a date is no version."""
    import re

    return tuple(int(n) for n in re.findall(r"\d+", model_id.rsplit("/", 1)[-1]) if len(n) < 4)


def _saved_as_new(model_id: str, saved: list[Any]) -> bool:
    """Is a model of `model_id`'s family saved that is at least as new? An older one covers nothing: the current model
    is offered beside it (#6266: a saved claude-3-5-sonnet hid claude-sonnet-4-6)."""
    family = _family(model_id)
    return any(m.enabled and _family(m.model_id) == family and _version(m.model_id) >= _version(model_id) for m in saved)


def remote_reader_cards() -> list[Card]:
    """A reader card for each vision model at the person's remote endpoints (their cloud provider rows in Settings ›
    AI: OpenRouter, Anthropic, Gemini, …); with no Anthropic row, a Claude card that says to add it first (#5660 item
    7). Offered, never the rules' (the bake-off measures them, ruled 2026-10-11). Never the network: the rows as
    kept."""
    from fichero_server.db.app import get_app_db
    from fichero_server.llm import LLMConfig
    from fichero_server.llm.places import PROVIDER, place_of
    from fichero_server.llm.providers import get_provider_info

    out: list[Card] = []
    try:
        app_db = get_app_db()
        rows = app_db.list_providers()
    except Exception:  # noqa: BLE001 -- no app database (a bare tool run): no rows
        rows = []
    for row in rows:
        ptype = row.provider_type.value
        if not row.enabled or place_of(LLMConfig(provider=ptype, model="", api_base=row.api_base)) != PROVIDER:
            continue
        info = get_provider_info(ptype)
        provider_vision = bool(info and info.supports_vision)
        saved = [m for m in app_db.list_models(row.id) if (m.model_id or "").strip()]
        # A key with no model saved under it (owner 2026-10-23: providers were listed, not models), or with models of
        # some families only (owner 2026-10-25, #6120: Gemini via OpenRouter saved, Claude never offered): its newest
        # frontier vision models from the vendored price list, one per family not already saved.
        # A retired model saved long ago covers nothing: its family's current model is offered (#6259).
        from fichero_server.llm.model_types import retired_because

        covered = {_family(m.model_id) for m in saved if m.enabled and not retired_because(m.model_id)}
        for model_id in frontier_catalog_models(ptype):
            if (_family(model_id) in covered and _saved_as_new(model_id, saved)) or any(m.model_id == model_id for m in saved):
                continue
            out.append(Card(id=f"{ptype}:{model_id}@{row.id}", pin={"cloud": ptype, "model": model_id},
                            jobs=READER_JOBS, scripts=None, languages=None, material=frozenset(),
                            runs_on=f"cloud:{ptype}", note=f"{row.name}: {model_id}", short_name=model_id, source="remote",
                            offered_only=True, from_catalogue=True,
                            offered_because=f"a vision model {row.name} serves"))
        for model in saved:
            # The tri-state rule (`llm._configured_vision_model_suggestions`): a model saved with no capabilities, as a
            # Gemini model added with a key is, inherits its provider's vision support.
            caps = [str(c).strip().lower() for c in (model.capabilities or [])]
            if not model.enabled or not ("vision" in caps or (not caps and provider_vision) or ptype == "anthropic"):
                continue
            out.append(Card(id=f"{ptype}:{model.model_id}@{row.id}", pin={"cloud": ptype, "model": model.model_id},
                            jobs=READER_JOBS, scripts=None, languages=None, material=frozenset(),
                            runs_on=f"cloud:{ptype}", note=f"{row.name}: {(model.name or '').strip() or model.model_id}",
                            short_name=(model.name or '').strip() or model.model_id, source="remote", offered_only=True,
                            offered_because=f"a vision model at your remote endpoint {row.name}", **_retired(model.model_id)))
    if not any(c.pin["cloud"] == "anthropic" or "claude" in str(c.pin["model"]).casefold() for c in out):
        out.append(Card(id="anthropic:claude@settings", pin={"cloud": "anthropic", "model": "claude"},
                        jobs=READER_JOBS, scripts=None, languages=None, material=frozenset(),
                        runs_on="cloud:anthropic", note="Claude (Anthropic), in the cloud", source="remote",
                        offered_only=True, runs_here=False,
                        cannot_run_because="not available yet: add Claude (Anthropic) in Settings › AI"))
    return out


#: Why Transkribus is never searched (#5809), in the finder's one short line: Fichero has no way to list its models.
#: What Fichero does read from Transkribus is the pages exported from it (PAGE XML), imported like any other.
TRANSKRIBUS_NOT_SEARCHED = "Transkribus: Fichero can't list its models"


def shipped_words(shipped: list[Card]) -> str:
    """The models that ship with Fichero for this step in one short line: how many, how many are on this Mac and how
    many still need a download (a model needing no download counts as on this Mac), not a bare count (#5809)."""
    n = len(shipped)
    if not n:
        return "Nothing available for this step"
    to_download = sum(1 for c in shipped if candidate_installed(c) is False)
    lead = f"{n} available" if n == 1 else f"{n} available"
    if not to_download:
        return f"{lead}, all on this Mac"
    return f"{lead}: {n - to_download} here, {to_download} to download"


def installed_words(n: int, *, text: bool) -> str:
    """The models you have installed beyond those that ship with Fichero, in one short line (#5809)."""
    where = "here or on a server" if text else "on this Mac"
    return f"None of your own {where}" if not n else f"{n} of your own {where}"


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
    if "make-a-vector" in card.jobs and card.pin.get("hf"):
        from fichero_server.llm import local_models

        here = local_models.embedding_model_installed(str(card.pin["hf"]))
        if here is not None:
            return here
    if card.pin.get("trocr"):
        from fichero_server.llm.trocr_runtime import is_installed

        return is_installed(str(card.pin["trocr"]))
    if card.pin.get("zenodo") or card.pin.get("kraken_hf"):
        # A Kraken reader: downloaded (Settings, Set Up, or a run that fetched it) or not yet (#5660 item 3).
        from fichero_server.llm.kraken_runtime import is_recognition_model_installed
        from fichero_server.recipes.cards import kraken_reader_for

        return bool(is_recognition_model_installed(kraken_reader_for(card.pin)))
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
    elif card.pin.get("zenodo") or card.pin.get("kraken_hf") or card.pin.get("trocr"):
        from fichero_server.recipes.cards import kraken_reader_for

        runtime, model = "kraken", str(kraken_reader_for(card.pin))
    else:
        return None
    return {"runtime": runtime, "model": model, "action": "model.download",
            "params": {"runtime": runtime, "model": model}}


def size_words(size_gb: float | None) -> str:
    """A size a person reads: "16 MB", "2.3 GB", or "size not stated" (never 0.0 GB, #5594)."""
    if not size_gb:
        return "size not stated"
    return f"{size_gb * 1000:.0f} MB" if size_gb < 1 else f"{size_gb:.1f} GB"


SHORT_NAME_MAX = 40


def short_name(card: Card) -> str:
    """The name a model row shows (`source.find.model-row-words`): the card's own `short_name`, else the first clause
    of its note, clipped at a word; the whole note is the hover text."""
    if card.short_name:
        return card.short_name
    first = re.split(r";| \u2014 |, ", card.note.strip().rstrip("."), maxsplit=1)[0].strip()
    if len(first) <= SHORT_NAME_MAX:
        return first or card.id
    return first[:SHORT_NAME_MAX].rsplit(" ", 1)[0].strip() or first[:SHORT_NAME_MAX]


def _partial_words(card: Card) -> str:
    """What an unfinished download of a Kraken reader says, in words: how much is here and that it resumes."""
    if not card.pin.get("zenodo"):
        return ""
    from fichero_server.llm.kraken_runtime import recognition_partial_bytes
    from fichero_server.recipes.cards import kraken_reader_for

    try:
        have = recognition_partial_bytes(kraken_reader_for(card.pin))
    except Exception:  # noqa: BLE001 -- the words are a courtesy; the availability stands without them
        return ""
    return f"{size_words(have / 1e9)} fetched, it resumes" if have else ""


def candidate_availability(card: Card) -> tuple[str, str]:
    """(where it stands, in one short phrase) for the finder (#5660 item 3): it ships with Fichero, it is on this
    Mac, it can be downloaded (and how big), it runs elsewhere, or Fichero cannot run it yet."""
    if not card.runs_here:
        return "not_here", f"Fichero cannot run it yet ({card.cannot_run_because or 'not in this build'})"
    if card.runs_on == REMOTE_RUNS_ON:
        return "elsewhere", f"Runs on remote compute ({REMOTE_WHERE})"
    if not card.local:
        where = card.runs_on.split(":", 1)[-1] if card.runs_on.startswith("cloud:") else "a machine of yours"
        return "elsewhere", f"Runs at {where}"
    pin = card.pin
    if "builtin" in pin or pin.get("kraken_version") == "bundled" or pin.get("version") == "bundled":
        return "ships", "Available"
    if candidate_installed(card):
        return "installed", "Downloaded" + (f" ({size_words(card.size_gb)})" if card.size_gb else "")
    if candidate_download(card) is not None:
        partial = _partial_words(card)
        return "download", f"Download ({size_words(card.size_gb)})" + (f", {partial}" if partial else "")
    return "download", f"Downloads when first used ({size_words(card.size_gb)})"


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
            open_licence=_is_open(row["licence"]), size_gb=round(gib(row["size_bytes"]), 4),
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
#: What a person reading old hands searches Hugging Face for, beside the language-tagged task listings (#5660
#: item 3: the tag listings found general VLMs, never the HTR models made for manuscripts). Each is a free-text
#: search of model names, asked of the image-to-text listing; the first three of the vision-language one too.
HTR_SEARCH_TERMS = ("htr", "manuscript", "handwrit", "trocr", "medieval", "paleograph", "palaeograph")
#: The Hub tags HTR models are published under (ruled 2026-10-11, #5660: search wide every time). A name search for
#: "htr" missed `wjbmattingly/comma-qwen-3.5-0.8b-full-33k`; its tags (htr, catmus, palaeography, …) find it and its
#: family. Each is asked alone and with each of the project's language tags; "ocr" only with a language (alone it
#: lists every OCR model there is).
HTR_TAGS = ("htr", "handwritten-text-recognition", "catmus", "palaeography", "paleography", "manuscripts")
#: How many of each tag listing are read, most downloaded first.
HF_TAG_LIMIT = 50
#: The project's languages as Hugging Face model names spell them ("trocr-spanish-…", "…-latin-htr").
_LANGUAGE_WORDS = {"es": "spanish", "la": "latin", "fr": "french", "it": "italian", "de": "german", "pt": "portuguese",
                   "ca": "catalan", "nl": "dutch", "en": "english"}
#: Script words a reader's tags or name may state, as ISO 15924 codes: these two, then any one-word script name
#: ISO 15924 lists (`script_words`).
_SCRIPT_WORDS = {"fraktur": "Latf", "kuzushiji": "Jpan"}
#: Not read from a listing: "latin" in a model's name is the language, "gothic" the blackletter hand of Latin script
#: (not Wulfila's Gothic alphabet, Goth), and the codes for no script in particular.
_NOT_SCRIPT_WORDS = frozenset({"Latn", "Goth", "Zyyy", "Zinh", "Zzzz", "Zsym", "Zmth", "Zxxx", "Zsye"})


#: Tags models are published under that differ from the project's language tag: Ottoman Turkish is `ota` in the registry and
#: `ott` on the Hub, Church Slavonic `cu` and `chu`, Syriac and Aramaic each other's, classical Chinese `lzh` and `zh`
#: (the search audit, 2026-10-20, #5970: nobody tags models `ota`).
_TAG_ALIASES = {"ota": ("ott",), "cu": ("chu",), "chu": ("cu",), "arc": ("syc", "syr"), "syc": ("arc", "syr"), "syr": ("syc", "arc"),
                "lzh": ("zh",), "grc": ("el",), "fro": ("fr",), "pro": ("oc",), "ang": ("en",)}
#: A script's name as models are named for it when its ISO 15924 name is not one word the listings use.
_SCRIPT_SEARCH_WORDS = {"Hant": "chinese", "Hans": "chinese", "Hani": "chinese", "Jpan": "japanese", "Hang": "korean",
                        "Cans": "syllabics", "Syrc": "syriac", "Deva": "devanagari"}
#: Words in a language's name that say nothing about it.
_NAME_NOISE = frozenset({"language", "languages", "old", "middle", "modern", "classical", "ancient", "early", "late", "standard",
                         "north", "south", "east", "west", "central", "official", "regional", "dialect", "spoken", "written",
                         "literary", "colloquial"})
#: Names models of a language or script go by that its ISO name does not say: Church Slavic is "Church Slavonic" on the Hub,
#: Han text is "hanzi" and old Chinese books "guji" (the search audit, #5970). Added to the words searched.
_LANGUAGE_EXTRA_WORDS = {"cu": ("slavonic",), "chu": ("slavonic",), "lzh": ("hanzi", "guji", "chinese"), "zh": ("hanzi",),
                         "arc": ("aramaic", "syriac"), "syc": ("syriac", "aramaic"), "syr": ("syriac", "aramaic")}
_SCRIPT_EXTRA_WORDS = {"Hant": ("hanzi", "guji"), "Hans": ("hanzi",), "Hani": ("hanzi",)}
#: What marks a reader made for old hands and manuscripts, beside the words of OCR_WORDS (the specialist signal of the rank).
SPECIALIST_WORDS = frozenset({"htr", "handwriting", "handwritten", "handwriting-recognition", "manuscript", "manuscripts",
                              "catmus", "palaeography", "paleography", "medieval", "historical", "incunabula", "kurrent"})
#: Parts of an OCR pipeline published under the same task as the readers (a detector, an orientation or layout model): never a
#: reader, so never a candidate (`source.onboard.model-search-ranks-specialists`).
COMPONENT_WORDS = frozenset({"det", "detector", "detection", "orientation", "ori", "layout", "cls", "unwarping", "uvdoc", "lcnet"})


def language_tags(languages: frozenset[str]) -> list[str]:
    """The Hub tags to ask for: each project language's primary tag and the tags models of that language are published under."""
    out: list[str] = []
    for tag in sorted(languages):
        primary = tag.split("-")[0].lower()
        for t in (primary, *_TAG_ALIASES.get(primary, ())):
            if t not in out:
                out.append(t)
    return out


def search_words(languages: frozenset[str]) -> list[str]:
    """The names to search model names for, for every project language and the script it is written in: the language's own
    name and its words ("Ottoman Turkish" -> ottoman, turkish), the nine Latin-script words that were there before, and the
    script's name (arabic, hebrew, syriac). Not the words of a language's name that say nothing (old, modern)."""
    from fichero_server.recipes.names import language_name, script_name, usual_script

    words: list[str] = []

    def add(word: str | None) -> None:
        if word and len(word) >= 4 and word not in words and word not in _NAME_NOISE:
            words.append(word)

    for tag in sorted(languages):
        primary = tag.split("-")[0].lower()
        add(_LANGUAGE_WORDS.get(primary))
        for word in _LANGUAGE_EXTRA_WORDS.get(primary, ()):
            add(word)
        name = language_name(tag)
        if name != tag:
            for word in re.findall(r"[a-z]+", name.lower().split("(")[0]):
                add(word)
        code = usual_script(tag)
        if code and code not in _NOT_SCRIPT_WORDS:
            add(_SCRIPT_SEARCH_WORDS.get(code))
            for word in _SCRIPT_EXTRA_WORDS.get(code, ()):
                add(word)
            sname = script_name(code).lower()
            if re.fullmatch(r"[a-z]{4,}", sname):
                add(sname)
    return words


def is_component(model: dict[str, Any]) -> bool:
    """A detector, orientation or layout part of an OCR pipeline: it carries the readers' task on the Hub and reads nothing."""
    return bool(_words(model) & COMPONENT_WORDS) and not (_words(model) & SPECIALIST_WORDS)


def specialist_score(model: dict[str, Any], languages: frozenset[str]) -> int:
    """How much a listing says it was made for old hands and for these languages and their scripts: a point for each
    handwriting or manuscript word, two when a language's name or tag, or its script's name, is in the tags or the name.
    Downloads are not in it."""
    words = _words(model)
    score = len(words & SPECIALIST_WORDS)
    if words & (set(search_words(languages)) | set(language_tags(languages))):
        score += 2
    return score


def parse_card_text(text: str) -> dict[str, Any]:
    """What a model's README states (front matter first, then its words): licence, languages, datasets and a CER as a fraction,
    or None for a CER it does not state. Nothing is guessed: a number is read only from a `model-index` metric named CER or
    character error rate, or a sentence 'CER ... n %'."""
    out: dict[str, Any] = {"licence": None, "languages": [], "datasets": [], "cer": None}
    front = ""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        front, text = (text[3:end], text[end + 4:]) if end > 0 else ("", text)
    meta: dict[str, Any] = {}
    if front:
        try:
            import yaml

            loaded = yaml.safe_load(front)
            meta = loaded if isinstance(loaded, dict) else {}
        except Exception:  # noqa: BLE001 -- a card with broken front matter states nothing
            meta = {}
    lic = meta.get("license")
    out["licence"] = str(lic) if isinstance(lic, (str, int, float)) else None
    langs = meta.get("language")
    out["languages"] = [str(x) for x in (langs if isinstance(langs, list) else [langs] if langs else [])]
    data = meta.get("datasets")
    out["datasets"] = [str(x) for x in (data if isinstance(data, list) else [data] if data else [])]

    def fraction(value: Any) -> float | None:
        try:
            number = float(str(value).strip().rstrip("%"))
        except ValueError:
            return None
        return number / 100 if number > 1 else number

    for entry in meta.get("model-index") or []:
        for result in (entry or {}).get("results") or []:
            for metric in result.get("metrics") or []:
                label = f"{metric.get('type', '')} {metric.get('name', '')}".lower()
                if re.search(r"\bcer\b|character error", label) and (v := fraction(metric.get("value"))) is not None:
                    out["cer"] = v
                    return out
    found = re.search(r"\bCER\b[^0-9\n]{0,24}([0-9]+(?:\.[0-9]+)?)\s*%", text)
    if found:
        out["cer"] = float(found.group(1)) / 100
    return out


def card_words(read: dict[str, Any] | None) -> str:
    """What a read card adds to a candidate's reason: its stated CER on its own material, else that it states none."""
    if read is None:
        return "its card could not be read: unmeasured"
    if read["cer"] is None:
        return "its card states no measurement: unmeasured"
    return f"CER {read['cer'] * 100:.1f}% on its own material"


#: How many of the best-ranked candidates have their card read (one fetch each, together).
CARDS_READ = 5
#: How much of a card is read: the front matter and the first pages state the licence and the numbers; a card is never
#: downloaded whole (some hold megabytes of tables).
CARD_BYTES = 64_000


async def _fetch_card_text(repo: str) -> str | None:
    """A Hub repository's README, or None when it cannot be fetched. Network: only behind the search's egress check."""
    import httpx  # lazy: off the engine boot path

    try:
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", f"https://huggingface.co/{repo}/raw/main/README.md", timeout=20.0,
                                     follow_redirects=True) as response:
                if response.status_code != 200:
                    return None
                body = b""
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) >= CARD_BYTES:
                        break
                return body[:CARD_BYTES].decode("utf-8", errors="replace")
    except httpx.HTTPError:
        return None


def nothing_found_words(languages: frozenset[str]) -> str:
    """What Set Up says when no source has a reader for the project's language and script, and what a person can do."""
    from fichero_server.recipes.names import language_name, usual_script, script_name

    names = ", ".join(language_name(t) for t in sorted(languages)) or "your language"
    codes = {usual_script(t) for t in languages} - {None}
    script = " in " + " and ".join(sorted(script_name(c) for c in codes)) if codes else ""
    return (f"No model that reads {names}{script} was found. You can train one from about a hundred lines you correct, "
            "or use a cloud reader if this project lets pages leave this Mac.")


@lru_cache(maxsize=1)
def script_words() -> dict[str, str]:
    """Word -> ISO 15924 code for every script whose English name is one word ("cyrillic" -> Cyrl) (#5594 residue)."""
    from fichero_server.recipes.names import _scripts

    words = {row["name"].lower(): row["code"] for row, _text in _scripts()
             if row["code"] not in _NOT_SCRIPT_WORDS and re.fullmatch(r"[a-z]{4,}", row["name"].lower())}
    return {**words, **_SCRIPT_WORDS}


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
    if words & CHAT_BUILD_WORDS or is_component(model):
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
    scripts = frozenset(code for word, code in script_words().items() if word in words)
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


def _kraken_on_hub(model: dict[str, Any]) -> bool:
    """A Kraken reader hosted on Hugging Face (`library_name: kraken`, or the tag): Fichero ships Kraken, so it runs here."""
    return "kraken" in (model.get("tags") or []) or model.get("library_name") == "kraken"


def _kraken_hub_card(model: dict[str, Any], what: str, wanted: frozenset[str]) -> Card | None:
    """A Hub Kraken reader's card: downloads from the repository and runs on this Mac with the Kraken Fichero ships
    (`source.onboard.model-search-kraken-on-hub`). None when its name could not be made into a reader id."""
    from dataclasses import replace

    from fichero_server.llm.kraken_runtime import reader_id_for_hub

    repo = str(model.get("modelId") or model.get("id"))
    try:
        reader_id_for_hub(repo)
    except ValueError:
        return None
    card = _hf_card(model, what, "a Kraken reader on Hugging Face: downloads and runs on this Mac with the Kraken Fichero ships",
                    wanted)
    sha = str(model.get("sha") or "")  # the commit the listing was read at, kept in the pin when the Hub gave one
    return replace(card, id=f"kraken:hf/{repo}@main", pin={"kraken_hf": repo, **({"revision": sha} if sha else {})})


def _trocr_on_hub(model: dict[str, Any]) -> bool:
    """A TrOCR-family model on the Hub (a VisionEncoderDecoder with safetensors): the bundled torch and transformers run it."""
    words = _words(model)
    return (bool(words & {"trocr", "vision-encoder-decoder"}) and "safetensors" in (model.get("tags") or [])
            and not _gguf_only(model))


def _trocr_hub_card(model: dict[str, Any], what: str, wanted: frozenset[str]) -> Card:
    """A Hub TrOCR model's card: it reads the lines Kraken found, here, and downloads when first used
    (`source.onboard.model-search-trocr-runs-here`, #5981)."""
    from dataclasses import replace

    repo = str(model.get("modelId") or model.get("id"))
    card = _hf_card(model, what, "a TrOCR model: it reads the lines Kraken finds, on this Mac with the torch and transformers "
                    "Fichero ships; its safetensors download before the run asks (a pickled repository is refused)", wanted)
    return replace(card, id=f"trocr:hf/{repo}@main", pin={"trocr": repo}, jobs=frozenset({"read-a-line"}))


#: Why a PyLaia reader cannot run here or in a Job yet (`source.onboard.model-search-pylaia-is-remote-only`).
PYLAIA_WHY = ("PyLaia 1.1.2 pins torch 1.13 and Python below 3.11, and Fichero ships torch 2 on a newer Python, so it "
              "cannot be bundled; a Job would need an environment of its own")


def _is_pylaia(model: dict[str, Any]) -> bool:
    return model.get("library_name") == "pylaia" or "pylaia" in _words(model)


def _not_runnable_card(model: dict[str, Any], what: str, wanted: frozenset[str]) -> Card:
    """A reader on the Hub this build cannot run (a TrOCR or other transformers model with no MLX build, or a GGUF
    build): listed so a person sees what exists for their material, never chosen by the rules (`runs_here` False,
    #5660 item 3), saying how it could run: transformers only, or GGUF."""
    from dataclasses import replace

    words = _words(model)
    if _is_pylaia(model):
        kind, how = "a PyLaia model", f"a PyLaia model: cannot run yet ({PYLAIA_WHY})"
    elif _gguf_only(model):
        kind, how = "a GGUF build", "a GGUF build: cannot run yet (this build runs MLX builds)"
    else:
        kind = "a TrOCR model" if "trocr" in words or "vision-encoder-decoder" in words else "a transformers model"
        how = f"{kind}, transformers only: cannot run yet (no MLX build Fichero can run)"
    card = _hf_card(model, what, how, wanted)
    return replace(card, id=card.id.replace("mlx:hf/", "hf:hf/"), runs_here=False,
                   cannot_run_because=PYLAIA_WHY if _is_pylaia(model) else f"{kind}, and this build runs MLX builds only")


#: Where a model too big for this Mac runs: the Hugging Face Jobs the engine already sends reading to
#: (`remote_read/`, `compute/remote-compute.md`).
REMOTE_RUNS_ON = "cloud:huggingface-jobs"
REMOTE_WHERE = "Hugging Face Jobs"


def remote_compute(*, price: bool = True) -> dict[str, Any]:
    """The person's remote compute, as the finder offers it (#5717): whether Hugging Face Jobs is set up (a token in
    Settings), the hardware a read would use and its listed price an hour. `price` asks the service for it (the
    network: only behind a search the person asked for); without it, or when the service cannot be reached, the
    price is None and said unknown, never invented. Not set up: `available` False and `why` says what to add."""
    from fichero_server.training import hf_jobs

    out = {"available": False, "where": REMOTE_WHERE, "flavor": hf_jobs.DEFAULT_FLAVOR, "price_per_hour_usd": None,
           "why": ""}
    try:
        target = hf_jobs.HfJobsTarget()
    except (hf_jobs.NoHuggingFaceToken, RuntimeError) as exc:
        return {**out, "why": str(exc)}
    out["available"] = True
    if price:
        try:
            out["price_per_hour_usd"] = target.price_per_hour(out["flavor"])
        except Exception as exc:  # noqa: BLE001 -- unreachable or unlisted: the price is unknown, the model still offered
            out["why"] = f"the price could not be read: {exc}"
    return out


def _remote_vlm(model: dict[str, Any]) -> bool:
    """A vision-language model in standard Hugging Face form (safetensors, transformers) that no MLX build covers:
    the kind the remote reader runs (`remote_read.job.VLM_DEPENDENCIES`)."""
    return (model.get("pipeline_tag") == "image-text-to-text" and "safetensors" in (model.get("tags") or [])
            and not _runs_on_mlx(model) and not _gguf_only(model) and not _is_adapter(model))


def _remote_card(model: dict[str, Any], what: str, remote: dict[str, Any], wanted: frozenset[str]) -> Card:
    """A reader that needs a bigger machine than this Mac, offered for the person's remote compute: where it would
    run, the hardware's price an hour and its size (two bytes a weight, from the listing's count), the pages leaving
    this Mac said. Never the rules' choice. With no remote compute set up it says why it is unavailable."""
    from dataclasses import replace

    weights = int(((model.get("safetensors") or {}).get("total")) or 0)
    price = remote["price_per_hour_usd"]
    how = (f"runs on remote compute ({remote['where']}, {remote['flavor']}, "
           + (f"about ${price:.2f} an hour" if price is not None else "price not listed")
           + "); the pages leave this Mac"
           + (f"; about {gib(weights * 2):.0f} GB of weights" if weights else "; size not stated"))
    card = _hf_card(model, what, how, wanted)
    return replace(card, id=card.id.replace("mlx:hf/", "remote:hf/"), runs_on=REMOTE_RUNS_ON, trainable=False,
                   offered_only=True, size_gb=round(gib(weights * 2), 1) if weights else 0.0,
                   runs_here=bool(remote["available"]),
                   cannot_run_because="" if remote["available"] else remote["why"])


def _is_adapter(model: dict[str, Any]) -> bool:
    """A PEFT/LoRA adapter (`library_name: peft`, or the tag): weights that are only a difference to a base model."""
    return model.get("library_name") == "peft" or "peft" in (model.get("tags") or [])


def _adapter_base(model: dict[str, Any]) -> str | None:
    """The base model an adapter's listing names (`base_model:adapter:<repo>`, else `base_model:<repo>`), or None."""
    tags = [str(t) for t in model.get("tags") or [] if str(t).startswith("base_model:")]
    named = [t.split(":", 2)[2] for t in tags if t.startswith("base_model:adapter:")] or [
        t.split(":", 1)[1] for t in tags if t.count(":") == 1]
    return next(iter(named), None) if _is_adapter(model) else None


def _adapter_card(model: dict[str, Any], what: str, remote: dict[str, Any], wanted: frozenset[str]) -> Card:
    """An adapter's card (`source.onboard.model-search-adapters-name-their-base`, #5977): "adapter: needs <base>", offered for
    remote compute only, which loads the base and puts the adapter on it. One with no base named, or with no safetensors
    (its adapter file would be unpickled), is listed as unable to run, in words."""
    from dataclasses import replace

    base = _adapter_base(model)
    if base is None or "safetensors" not in (model.get("tags") or []):
        why = ("an adapter that does not name its base model" if base is None
               else f"an adapter with no safetensors file (a pickled adapter is never loaded); it needs {base}")
        card = _hf_card(model, what, f"adapter: {why}", wanted)
        return replace(card, id=card.id.replace("mlx:hf/", "hf:hf/"), runs_here=False, cannot_run_because=why)
    price = remote["price_per_hour_usd"]
    how = (f"adapter: needs {base}, loaded under it on remote compute ({remote['where']}, {remote['flavor']}, "
           + (f"about ${price:.2f} an hour" if price is not None else "price not listed") + "); the pages leave this Mac")
    card = _hf_card(model, what, how, wanted)
    return replace(card, id=card.id.replace("mlx:hf/", "remote:hf/"), pin={**card.pin, "base_model": base},
                   runs_on=REMOTE_RUNS_ON, trainable=False, offered_only=True, runs_here=bool(remote["available"]),
                   cannot_run_because="" if remote["available"] else remote["why"])


def _catalogue_repo(repo: str) -> bool:
    """Whether Fichero's MLX catalogue fetches and runs this repository as it is (#5665: a checkpoint mlx-vlm
    loads directly)."""
    from fichero_server.llm.mlx_model_store import get_mlx_model_store

    try:
        return get_mlx_model_store().canonical_id(repo) is not None
    except Exception:  # noqa: BLE001 -- no model store (a bare tool run): not known
        return False


def _runs_on_mlx(model: dict[str, Any]) -> bool:
    tags = set(model.get("tags") or [])
    return model.get("library_name") == "mlx" or "mlx" in tags


def _gguf_only(model: dict[str, Any]) -> bool:
    tags = set(model.get("tags") or [])
    return ("gguf" in tags or model.get("library_name") == "gguf") and not _runs_on_mlx(model)


async def search_hugging_face(languages: frozenset[str],
                              progress: Callable[[str], None] = lambda _: None,
                              hand_tags: tuple[str, ...] | list[str] = ()) -> tuple[list[Card], int]:
    """(reader candidates on the Hub for these languages, how many builds this Mac runs were left out as
    not readers). Only builds this Mac can run, only readers by their listing (`reads_text`), each saying
    why it fits. `progress` is told each query in words. Network: call only behind the egress check.
    Raises the Hub fetch's error."""
    from fichero_server.api.routes.ai.models import _fetch_hf_models

    filters = [[tag] for tag in language_tags(languages)] or [[]]
    models: dict[str, dict[str, Any]] = {}  # every listing seen, by repository: the rank reads their tags and names
    found: dict[str, Card] = {}
    left_out: set[str] = set()
    originals: list[tuple[dict[str, Any], str]] = []
    vlms: dict[str, tuple[dict[str, Any], str]] = {}  # reader VLMs no MLX build covers: offered for remote compute
    adapters: dict[str, tuple[dict[str, Any], str]] = {}  # PEFT adapters: each needs its base (#5977)
    queries, asked = len(HF_READER_TASKS) * len(filters) * 2, 0
    for task in HF_READER_TASKS:
        for tags in filters:
            for mlx in (True, False):
                asked += 1
                progress(f"Searching Hugging Face ({asked} of {queries})")
                listing = await _fetch_hf_models(task=task, tags=["mlx", *tags] if mlx else (tags or None),
                                                 limit=HF_LIMIT)
                for m in listing:
                    models.setdefault(str(m.get("modelId") or m.get("id")), m)
                    what = reads_text(m)
                    if not mlx and what is not None and _kraken_on_hub(m):
                        if (card := _kraken_hub_card(m, what, languages)) is not None:
                            found.setdefault(str(m.get("modelId") or m.get("id")), card)
                    elif mlx and _runs_on_mlx(m) and not _gguf_only(m):
                        repo = str(m.get("modelId") or m.get("id"))
                        if what is None:
                            left_out.add(repo)
                        else:
                            found.setdefault(repo, _hf_card(
                                m, what, "an MLX build on Hugging Face that runs on this Mac", languages))
                    elif not mlx and what is not None and _is_adapter(m):
                        adapters[str(m.get("modelId") or m.get("id"))] = (m, what)
                    elif (not mlx and what is not None and not _runs_on_mlx(m) and not _gguf_only(m)
                          and "safetensors" in (m.get("tags") or [])):
                        originals.append((m, what))
                        if _remote_vlm(m):
                            vlms[str(m.get("modelId") or m.get("id"))] = (m, what)
    downloads: dict[str, int] = {}
    not_runnable: dict[str, Card] = {}

    def consider(m: dict[str, Any], what: str | None) -> None:
        """One listing found by a name or a tag: an MLX build, a repository the catalogue runs, a safetensors
        original whose MLX conversion is looked up, or listed as one that cannot run yet (transformers, GGUF)."""
        repo = str(m.get("modelId") or m.get("id"))
        models.setdefault(repo, m)
        downloads[repo] = max(downloads.get(repo, 0), int(m.get("downloads") or 0))
        if what is None or repo in found:
            return
        if _kraken_on_hub(m):
            if (card := _kraken_hub_card(m, what, languages)) is not None:
                found.setdefault(repo, card)
            return
        if _trocr_on_hub(m) and not _runs_on_mlx(m):
            try:
                from fichero_server.llm.trocr_runtime import reader_id_for_trocr

                reader_id_for_trocr(repo)
                found.setdefault(repo, _trocr_hub_card(m, what, languages))
            except ValueError:
                not_runnable.setdefault(repo, _not_runnable_card(m, what, languages))
            return
        if _is_adapter(m):
            adapters[repo] = (m, what)
            return
        if _remote_vlm(m) and not _catalogue_repo(repo):
            vlms[repo] = (m, what)
        if _runs_on_mlx(m) and not _gguf_only(m):
            found.setdefault(repo, _hf_card(m, what, "an MLX build on Hugging Face that runs on this Mac", languages))
        elif _catalogue_repo(repo):
            found.setdefault(repo, _hf_card(m, what, "in Fichero's MLX catalogue: downloads and runs on this Mac",
                                            languages))
        elif (not _gguf_only(m) and "safetensors" in (m.get("tags") or [])
              and len(originals) < HF_CONVERSIONS_LOOKED_UP and repo not in {str(o.get("modelId") or o.get("id"))
                                                                             for o, _ in originals}):
            originals.append((m, what))
            not_runnable.setdefault(repo, _not_runnable_card(m, what, languages))
        else:
            not_runnable.setdefault(repo, _not_runnable_card(m, what, languages))

    def htr(m: dict[str, Any]) -> str | None:
        if is_component(m) or _words(m) & CHAT_BUILD_WORDS:  # a detector or orientation part, a chat build: never a reader
            return None
        return reads_text(m) or ("an HTR model" + (" (image-to-text)" if m.get("pipeline_tag") == "image-to-text"
                                                   else "") if _words(m) & (OCR_WORDS | {"catmus", "palaeography",
                                                                                         "paleography"}) else None)

    # The HTR models made for manuscripts (TrOCR fine-tunes, VLMs trained on old hands): by the tags they are
    # published under, alone and with each project language (ruled 2026-10-11), then by name (#5660 item 3).
    langs = language_tags(languages)
    # The hand answered in Your Material joins them (#5668, `source.onboard.material.feeds-the-reader-search`):
    # a Kurrent hand asks for `kurrent`, alone and with each language.
    hands = [t for t in dict.fromkeys(hand_tags) if t not in HTR_TAGS]
    tag_asks = ([[tag] for tag in (*HTR_TAGS, *hands)]
                + [[lang, tag] for lang in langs for tag in (*HTR_TAGS, "ocr", *hands)])
    asks = len(tag_asks) * len(HF_READER_TASKS)
    for n, (tags, task) in enumerate(((t, k) for t in tag_asks for k in HF_READER_TASKS), 1):
        progress(f"Searching Hugging Face by tag ({n} of {asks})")
        for m in await _fetch_hf_models(task=task, tags=tags, limit=HF_TAG_LIMIT):
            if m.get("pipeline_tag") in (None, *HF_READER_TASKS):
                consider(m, htr(m))
    terms = list(HTR_SEARCH_TERMS) + search_words(languages)  # the language's and the script's names, not only the nine
    asks = [(term, "image-to-text") for term in terms] + [(term, "image-text-to-text") for term in terms[:3]]
    for n, (term, task) in enumerate(asks, 1):
        progress(f"Searching Hugging Face for HTR models ({n} of {len(asks)})")
        for m in await _fetch_hf_models(task=task, search=term, limit=HF_LIMIT):
            consider(m, htr(m))
    for original, what in originals[:HF_CONVERSIONS_LOOKED_UP]:
        repo = str(original.get("modelId") or original.get("id"))
        progress(f"Looking up the MLX conversion of {repo}")
        for m in await _fetch_hf_models(tags=["mlx", f"base_model:{repo}"], limit=5):
            if _runs_on_mlx(m) and not _gguf_only(m):
                conversion = str(m.get("modelId") or m.get("id"))
                if _words(m) & CHAT_BUILD_WORDS:
                    left_out.add(conversion)
                    continue
                downloads[conversion] = downloads.get(repo, 0)
                found.setdefault(conversion, _hf_card(
                    m, what, f"the MLX conversion of {repo} (safetensors on Hugging Face), which runs on this Mac",
                    languages, _hub_tags(original)))
                break
    converted = {str(c.offered_because).split("the MLX conversion of ", 1)[-1].split(" ", 1)[0] for c in found.values()}
    if any(repo not in converted and repo not in found for repo in vlms):
        remote = remote_compute()  # one look at the account and its price for the whole search
        for repo, (m, what) in vlms.items():
            if repo in converted or repo in found:
                continue
            not_runnable.pop(repo, None)
            downloads[repo] = max(downloads.get(repo, 0), int(m.get("downloads") or 0))
            found[f"remote:{repo}"] = _remote_card(m, what, remote, languages)
    if adapters:
        remote = remote_compute()
        for repo, (m, what) in adapters.items():
            downloads[repo] = max(downloads.get(repo, 0), int(m.get("downloads") or 0))
            found[f"adapter:{repo}"] = _adapter_card(m, what, remote, languages)
    for repo, card in not_runnable.items():
        if repo not in converted and repo not in found:
            found.setdefault(f"not-runnable:{repo}", card)

    wanted_tags = set(language_tags(languages))

    def rank(card: Card) -> tuple:
        # A reader that lists the project's languages first (ruled 2026-10-11); then the one made for old hands and for these
        # languages and scripts over a general OCR model (`source.onboard.model-search-ranks-specialists`, #5970); downloads
        # only last, since a general reader has thousands of times a specialist's.
        repo = str(card.pin.get("hf") or card.pin.get("kraken_hf"))
        matches = bool(languages and card.languages and wanted_tags & set(card.languages))
        return (not matches, -min(specialist_score(models.get(repo, {}), languages), 6), -downloads.get(repo, 0), card.id)

    ranked = sorted(found.values(), key=rank)
    # The best few have their card read: licence, and a CER the card itself states, else "unmeasured"
    # (`source.onboard.model-search-reads-the-card`). One fetch each; a card that cannot be fetched says so.
    from dataclasses import replace

    import asyncio

    top = ranked[:CARDS_READ]
    progress(f"Reading the cards of {len(top)} models")
    texts = await asyncio.gather(*(_fetch_card_text(str(card.pin.get("hf"))) for card in top))
    for n, (card, text) in enumerate(zip(top, texts)):
        read = parse_card_text(text) if text else None
        ranked[n] = replace(card, offered_because="; ".join([card.offered_because, card_words(read)]),
                            cer_published=(read or {}).get("cer") if card.cer_published is None else card.cer_published,
                            licence=card.licence or ((read or {}).get("licence") or ""))
    return ranked, len(left_out - set(found))


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
    found_now = {_hub_key(card) for card in cards}
    for repo, row in list(found.items()):
        if repo not in found_now:
            row["found_for"] = sorted(set(row.get("found_for") or ()) - languages)
            if not row["found_for"]:
                del found[repo]
    for card in cards:
        key, repo = _hub_key(card), _hub_repo(card)
        before = found.get(key) or {}
        # A TrOCR card pins `trocr` and a Kraken repository card `kraken_hf`: their row keeps the id, pin and jobs so the offline
        # cache gives the same card back (`hub_cards`), not a plain `hf` reader.
        own = {} if "hf" in card.pin else {"id": card.id, "pin": dict(card.pin), "jobs": sorted(card.jobs)}
        found[key] = {**own, "repo": repo, "languages": sorted(card.languages) if card.languages else None,
                       "scripts": sorted(card.scripts) if card.scripts else None,
                       "material": sorted(card.material), "licence": card.licence, "note": card.note,
                       "offered_because": card.offered_because, "size_gb": card.size_gb,
                       "runs_here": card.runs_here, "cannot_run_because": card.cannot_run_because,
                       "runs_on": card.runs_on, "found_for": sorted({*before.get("found_for", []), *languages}), "found_at": now}
    left = dict(data.get("left_out") or {})
    left[_languages_key(languages)] = left_out
    folder = _store_root()
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / f".{HUB_FILE}.tmp"
    tmp.write_text(json.dumps({"found": found, "left_out": left}, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(folder / HUB_FILE)


def _hub_key(card: Card) -> str:
    """Where a kept Hub reader is filed: its repository, or `not-runnable:<repo>` for one this build cannot run, so
    the MLX conversion of a model and the model itself are both kept."""
    repo = _hub_repo(card)
    if "hf" not in card.pin:
        return f"{'trocr' if 'trocr' in card.pin else 'kraken'}:{repo}"
    if card.runs_on == REMOTE_RUNS_ON:
        return f"remote:{repo}"
    return repo if card.runs_here else f"not-runnable:{repo}"


def _hub_repo(card: Card) -> str:
    """The Hugging Face repository a card names, whichever runtime pin it carries (`hf`, `trocr`, `kraken_hf`)."""
    return str(card.pin.get("hf") or card.pin.get("trocr") or card.pin.get("kraken_hf"))


def hub_cards(languages: frozenset[str] | None, skip_repos: set[str] = frozenset(), *,
              runnable_only: bool = True) -> list[Card]:
    """The kept Hub readers found for any of these languages (every one kept, for None: a card looked up by its
    id), as cards the rules rank, except those whose repository another card already pins (a shipped card, or
    the installed copy once downloaded). A model that runs on remote compute (#5717) is offered to the person only:
    never in the rules' view (`runnable_only`), and it has no download."""
    out = []
    for key, row in sorted(cached_hub().items()):
        repo = str(row.get("repo") or key)
        runs_here = bool(row.get("runs_here", True))
        runs_on = str(row.get("runs_on") or "this-mac")
        remote = runs_on != "this-mac"
        if repo in skip_repos or (languages is not None and not languages & set(row.get("found_for") or ())):
            continue
        if runnable_only and (not runs_here or remote):
            continue
        own = row.get("pin") if isinstance(row.get("pin"), dict) and "hf" not in row["pin"] else None
        out.append(Card(
            id=str(row["id"]) if own and row.get("id") else f"{'remote' if remote else 'mlx' if runs_here else 'hf'}:hf/{repo}@main",
            pin=dict(own) if own else {"hf": repo, "revision": "main"}, runs_on=runs_on, offered_only=remote,
            jobs=frozenset(row["jobs"]) if own and row.get("jobs") else READER_JOBS, runs_here=runs_here, cannot_run_because=str(row.get("cannot_run_because") or ""),
            scripts=frozenset(row["scripts"]) if row.get("scripts") else None,
            languages=_tags(row.get("languages")), material=frozenset(row.get("material") or ()),
            open_licence=_is_open(str(row.get("licence") or "")), trainable=not remote,
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
    text_only = False
    if row is None:
        row, text_only = _step_hub_row(repo_id or ""), True  # an MLX text build a step's search found (#5668)
        if row is None:
            return None
    size = int(float(row.get("size_gb") or 0) * GIB)
    return ManagedModelSpec(
        model_id=repo_id, repo_id=repo_id, revision="main", display_name=str(row.get("note") or repo_id),
        download_size_bytes=size, min_memory_bytes=size,
        memory_class="memory not stated until it is downloaded" if not size else
        f"needs at least {gib(size):.1f} GB unified memory (its weights)",
        capabilities=("text",) if text_only else ("text", "vision"),
        note=f"Found on Hugging Face by Fichero's model search: {row.get('offered_because') or row.get('job')}. "
             "Not measured here yet.",
    )


# --- a step's own search (#5668 walkthrough section 4: "the online search must be per step") ------------------

#: Each non-reading job's Hugging Face search: (pipeline tag, Hub tags) asks, each asked alone and with each project
#: language. A text model (an MLX text-generation build) does any text job; the others name what the step finds.
_TEXT_ASK = ("text-generation", ("mlx",))
STEP_SEARCHES: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "find-names-tag-words": (("token-classification", ("ner",)), _TEXT_ASK),
    "find-statements": (_TEXT_ASK, ("text2text-generation", ("relation-extraction",)),
                        ("token-classification", ("relation-extraction",))),
    "split-into-entries": (_TEXT_ASK,),
    "extract-to-a-table": (_TEXT_ASK,),
    "find-regions": (("object-detection", ("doclaynet",)), ("object-detection", ("document-layout",)),
                     ("object-detection", ("layout-detection",))),
}
#: What each job's search found, {job: {languages: {"found_at", "rows"}}}, beside the reader search's file.
STEP_HUB_FILE = "hugging-face-steps.json"
#: Why a model a step's search found cannot run here, by its pipeline tag (an MLX text build runs).
_CANNOT_RUN_FOR = {
    "token-classification": "a transformers tagger: Fichero finds names with spaCy pipelines, not this yet",
    "text2text-generation": "a transformers model: Fichero runs MLX builds only",
    "object-detection": "a layout model Fichero cannot run yet: it runs the layout models it lists",
}


def _step_hub_file() -> dict[str, Any]:
    try:
        data = json.loads((_store_root() / STEP_HUB_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _step_row(m: dict[str, Any], job: str, task: str) -> dict[str, Any]:
    repo = str(m.get("modelId") or m.get("id"))
    tags = [str(t) for t in m.get("tags") or []]
    runs = task == "text-generation" and _runs_on_mlx(m) and not _gguf_only(m)
    return {"repo": repo, "job": job, "pipeline_tag": m.get("pipeline_tag") or task, "runs_here": runs,
            "licence": next((t.split(":", 1)[1] for t in tags if t.startswith("license:")), ""),
            "languages": sorted(_hub_tags(m) or ()) or None, "downloads": int(m.get("downloads") or 0),
            "cannot_run_because": "" if runs else (
                "a GGUF build: this build runs MLX builds only" if _gguf_only(m)
                else _CANNOT_RUN_FOR.get(m.get("pipeline_tag") or task, "Fichero cannot run it yet"))}


async def search_hugging_face_for_step(job: str, languages: frozenset[str],
                                       progress: Callable[[str], None] = lambda _: None) -> list[dict[str, Any]]:
    """What Hugging Face lists for this step's job (`STEP_SEARCHES`), runnable first, then most downloaded, one row
    a repository. Network: call only behind the egress check. Raises the Hub fetch's error."""
    from fichero_server.api.routes.ai.models import _fetch_hf_models

    langs = language_tags(languages)
    asks = [(task, list(tags)) for task, tags in STEP_SEARCHES[job]]
    asks += [(task, [*tags, lang]) for task, tags in STEP_SEARCHES[job] for lang in langs]
    rows: dict[str, dict[str, Any]] = {}
    for n, (task, tags) in enumerate(asks, 1):
        progress(f"Searching Hugging Face ({n} of {len(asks)})")
        for m in await _fetch_hf_models(task=task, tags=tags, limit=HF_LIMIT):
            if m.get("pipeline_tag") not in (None, task):
                continue
            # A GGUF-only repository is listed, not runnable and saying why: nothing is dropped silently
            # (`ai.where.never-dropped-silently`, #5519).
            row = _step_row(m, job, task)
            rows.setdefault(row["repo"], row)
    return sorted(rows.values(), key=lambda r: (not r["runs_here"], -r["downloads"], r["repo"]))


def keep_step_hub(job: str, languages: frozenset[str], rows: list[dict[str, Any]]) -> None:
    """Keep what this job's search found for these languages, in place of the last such search's finds."""
    data = _step_hub_file()
    data.setdefault(job, {})[_languages_key(languages)] = {
        "found_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "rows": rows}
    folder = _store_root()
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / f".{STEP_HUB_FILE}.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(folder / STEP_HUB_FILE)


def step_hub_cards(job: str, languages: frozenset[str]) -> list[Card] | None:
    """The cards this job's kept search found for these languages; None when none was kept."""
    kept = (_step_hub_file().get(job) or {}).get(_languages_key(languages))
    if kept is None:
        return None
    out = []
    for row in kept.get("rows") or []:
        repo, runs = str(row["repo"]), bool(row.get("runs_here"))
        out.append(Card(
            id=f"{'mlx' if runs else 'hf'}:hf/{repo}@main", pin={"hf": repo, "revision": "main"},
            jobs=frozenset({job}), runs_here=runs, cannot_run_because=str(row.get("cannot_run_because") or ""),
            scripts=None, languages=_tags(row.get("languages")), material=frozenset(),
            open_licence=_is_open(str(row.get("licence") or "")), licence=str(row.get("licence") or ""),
            note=repo.rsplit("/", 1)[-1], source="hugging-face", offered_only=True,
            offered_because=(f"found on Hugging Face for this step ({row.get('pipeline_tag')})"
                             + (": an MLX build that runs on this Mac" if runs else "")),
        ))
    return out


def _step_hub_row(repo_id: str) -> dict[str, Any] | None:
    """A runnable text build some step's search found and kept, by its repository."""
    for by_languages in _step_hub_file().values():
        for kept in (by_languages or {}).values():
            for row in kept.get("rows") or []:
                if row.get("repo") == repo_id and row.get("runs_here"):
                    return row
    return None


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
    from dataclasses import replace

    # The parser's free triples are a candidate the rules may take where no text model is installed (#5637).
    here = [*mark_installed(seed), *installed, *local_text_cards(seed)]
    taken = {c.id for c in here}
    parser = [replace(c, offered_only=False) for c in _parser_statement_cards() if c.id not in taken]
    return [*(_describes_folders(c) for c in (*here, *parser)),
            *(repository_cards(cached["records"], seed, languages) if cached else []),
            *mark_installed(hub_cards(a.languages if a is not None else None,
                                      _pinned_repos([*seed, *installed])))]


def _describes_folders(card: Card) -> Card:
    """A GENERATIVE text model (one that writes text: it carries both `split-into-entries` and `find-statements`, as the parser's
    subject-verb-object cards and spaCy's taggers do not, and it reads no pictures) writes a folder's archival description too
    (`catalogue.folder-description-fields`, #6087): `describe-for-the-catalogue` had no card, so the step could never run."""
    from dataclasses import replace

    if {"split-into-entries", "find-statements"} <= card.jobs and not card.jobs & {"read-a-line", "read-a-page"}:
        return replace(card, jobs=card.jobs | {"describe-for-the-catalogue"})
    return card


def _pinned_repos(cards: list[Card]) -> set[str]:
    return {str(c.pin["hf"]) for c in cards if "hf" in c.pin}


def egress_allowed() -> bool:
    """Whether discovery may reach the network: not when this engine works offline (local-only)."""
    from fichero_server.llm import is_local_only

    return not is_local_only()


#: Why the online search did not run when no project is open: its job is one of a project's (#5594).
NO_PROJECT = "Open a project to search online"


def discover(a: Answers, *, online: bool, search: dict[str, Any] | None = None,
             not_searched: str | None = None, job: str = "read-a-line") -> tuple[list[Card], list[dict[str, Any]]]:
    """(every candidate card, what each source did), never reaching the network: the shipped cards, the
    installed models, and the repository listing and Hub readers the online search kept (#5594: the search
    itself is a job, `find-models`). `search` is that job's row when `online` asked for one: while it runs the
    two online sources say they are being searched, and once it is done they say what it found. `not_searched`
    says why no search was made when one was asked for (no project open)."""
    if job in SAMPLED_READER_JOBS:
        # The readers' own finder, kept to the models a step can sample (a vision model), as the plan tests it.
        from fichero_server.recipes.start import _override

        cards, sources = discover(a, online=online, search=search, not_searched=not_searched, job="read-a-line")
        return [c for c in cards if _override(c.pin) is not None], sources
    from fichero_server.recipes.cards import all_seed_cards

    seed = all_seed_cards()
    sources: list[dict[str, Any]] = []
    shipped = mark_installed(c for c in seed if c.runs_here)
    sources.append({"source": "shipped", "state": "read", "count": len(shipped),
                    "detail": shipped_words(shipped)})
    if job in TEXT_MODEL_JOBS:
        # A job a text model does: the text models here and on the person's own servers (#5619).
        installed = [*local_text_cards(seed), *other_text_cards()]
        if job == "find-names-tag-words":  # the spaCy pipelines installed here, beside the shipped one (#5688)
            installed += installed_spacy_cards(a.languages, seed)
        sources.append({"source": "installed", "state": "read", "count": len(installed),
                        "detail": installed_words(len(installed), text=True)})
    else:
        installed = installed_cards(seed)
        sources.append({"source": "installed", "state": "read", "count": len(installed),
                        "detail": installed_words(len(installed), text=False)})
    if online and not egress_allowed():
        why, quiet = "Offline: not searched", "offline"
    elif online:
        failed = SEARCH_FAILURES.get(_languages_key(a.languages))
        why, quiet = not_searched or (f"The automatic search could not be queued: {failed}" if failed else "Searching…"), "not-searched"
    else:
        why, quiet = "Not searched", "not-searched"
    if job not in READER_JOBS:
        return _discover_for_step(job, a, shipped, installed, sources, search, why, quiet)
    cached = cached_repository()
    if cached is None:
        repo_cards: list[Card] = []
        repo_source = {"source": "kraken-repository", "state": quiet, "count": 0, "detail": why}
    else:
        repo_cards = repository_cards(cached["records"], seed, a.languages)
        repo_source = {"source": "kraken-repository", "state": "cached", "count": len(repo_cards),
                       "detail": f"{len(repo_cards)} found on Zenodo"}
    hf_cards = mark_installed(hub_cards(a.languages, _pinned_repos([*seed, *installed]), runnable_only=False))
    left_out = hub_left_out(a.languages) or 0
    if hf_cards or hub_left_out(a.languages) is not None:
        hub_source = {"source": "hugging-face", "state": "cached", "count": len(hf_cards), "left_out": left_out,
                      "detail": f"{len(hf_cards)} found on Hugging Face" + _left_out_words(left_out)}
    else:
        hub_source = {"source": "hugging-face", "state": quiet, "count": 0, "detail": why}
    if search is not None:
        _say_search(search, repo_source, hub_source)
    sources += [repo_source, hub_source]
    remote: list[Card] = []
    if job in READER_JOBS:
        # The person's remote endpoints are searched every time, beside Kraken's repository and the Hub (ruled
        # 2026-10-11): not a fallback.
        remote = remote_reader_cards()
        here = [c for c in remote if c.runs_here]
        sources.append({"source": "remote-endpoints", "state": "read", "count": len(here),
                        "detail": (f"{len(here)} at your remote endpoints" if here
                                   else "No remote endpoint with a vision model is set up")})
        # The remote compute models too big for this Mac would run on, and the sources not searched, said (#5717).
        compute = remote_compute(price=False)
        sources.append({"source": "remote-compute", "state": "read", "count": sum(c.runs_on == REMOTE_RUNS_ON
                                                                                for c in hf_cards),
                        "detail": (f"Remote compute: {compute['where']}" if compute["available"]
                                   else "Remote compute: not set up (needs a token)")})
        sources += [{"source": "transkribus", "state": "not-searched", "count": 0,
                     "detail": TRANSKRIBUS_NOT_SEARCHED}, _htr_united_source(a)]
    everything = [*shipped, *installed, *repo_cards, *hf_cards, *remote, *_print_baselines(seed, job, a)]
    if cached is not None and hub_source["state"] == "cached":
        # Both online sources have been searched: if no card reads this project's script and language, say so in words and
        # what a person can do, never a bare "0 found" (`source.onboard.model-search-nothing-found-says-what-next`, #5970).
        from fichero_server.recipes.assemble import _refusal

        if not any(job in c.jobs and _refusal(job, c, a, a.material) is None for c in everything):
            sources.append({"source": "nothing-found", "state": "read", "count": 0,
                            "detail": nothing_found_words(a.languages)})
    return everything, sources


#: A local vision model up to this size is a small one; a larger one is a general model (`source.recipe.reader-tiers`).
SMALL_VLM_GB = 8.0

TIER_WORDS = {"cloud": "Your cloud models", "specialist": "Specialist line reader", "small-vlm": "Small vision model, on this Mac",
              "general": "General model"}


def is_cloud(card: Card) -> bool:
    """A cloud model, from any provider the person added (owner 2026-10-23: their cloud models lead the list); a Hugging
    Face model run on remote compute is not one of theirs."""
    return str(card.runs_on).startswith("cloud:") and "hf" not in card.pin


def reader_tier(card: Card, job: str) -> str | None:
    """Which tier a reader is in, for the reading job only (`source.recipe.reader-tiers`): `specialist` (a line
    recogniser made for a script: Kraken's, PP-OCR, Tesseract), `small-vlm` (a vision-language model that runs on
    this Mac and is small), `general` (a large or cloud or built-in page reader). None for any other job."""
    if job != "read-a-line":
        return None
    pin = card.pin
    if any(k in pin for k in ("kraken", "zenodo", "tesseract")):
        return "specialist"
    if "hf" in pin and card.runs_on in ("this-mac", ""):
        if not card.size_gb:
            return None  # its size is not stated: no tier is invented for it
        return "small-vlm" if card.size_gb <= SMALL_VLM_GB else "general"
    if is_cloud(card):
        return "cloud"  # the person's cloud models: likely the best readers, shown first (owner 2026-10-23)
    return "general"  # another cloud or remote model, Apple Vision (built in, one reader for every script)


def _print_baselines(seed: list[Card], job: str, a: Answers) -> list[Card]:
    """Tesseract's data, named for a project that reads print or typescript and for no other: a card Fichero cannot run
    yet, listed so a person sees the fast local baseline exists (`source.recipe.reader-tiers`). Never for handwriting."""
    from dataclasses import replace

    from fichero_server.recipes.bakeoff import TESSERACT_MATERIALS, _tesseract_has_the_language

    if not any(m in TESSERACT_MATERIALS for m in a.materials):
        return []
    # Only a project whose language and script the data covers (Spanish data is no reader for German in Fraktur).
    return [replace(c, offered_because="the fast local baseline for print and typescript",
                    cannot_run_because="Tesseract is not in this build yet")
            for c in seed if not c.runs_here and "tesseract" in c.pin and job in c.jobs
            and any(m in TESSERACT_MATERIALS for m in c.material) and _tesseract_has_the_language(c, a)
            and (c.scripts is None or bool(a.scripts & set(c.scripts)))]


def _htr_united_source(a: Answers) -> dict[str, Any]:
    """HTR-United's ground-truth datasets for the project's languages, from the kept catalogue (#5571); never the
    network. Said not searched when none is kept."""
    from fichero_server.recipes import htr_united

    kept = htr_united.cached()
    if kept is None:
        return {"source": "htr-united", "state": "not-searched", "count": 0, "detail": "HTR-United: not searched"}
    found = htr_united.matching(kept["records"], languages=a.languages, scripts=a.scripts)
    return {"source": "htr-united", "state": "cached", "count": len(found),
            "detail": f"HTR-United: {len(found)} datasets for these"}


#: Said in place of the online sources for a step with no search of its own (#5668).
NO_STEP_SEARCH = "No online search for this step"


def _discover_for_step(job: str, a: Answers, shipped: list[Card], installed: list[Card],
                       sources: list[dict[str, Any]], search: dict[str, Any] | None, why: str,
                       quiet: str) -> tuple[list[Card], list[dict[str, Any]]]:
    """A step that is not a reader's: the shipped and installed cards, and what this job's own Hugging Face
    search kept (`STEP_SEARCHES`); Kraken's repository holds readers and line finders, so it is not asked."""
    if job not in STEP_SEARCHES:
        sources.append({"source": "hugging-face", "state": "not-searched", "count": 0, "detail": NO_STEP_SEARCH})
        return [*shipped, *installed], sources
    found = step_hub_cards(job, a.languages)
    if found is not None:
        hub_source = {"source": "hugging-face", "state": "cached", "count": len(found),
                      "detail": f"{len(found)} found on Hugging Face"}
    else:
        hub_source = {"source": "hugging-face", "state": quiet, "count": 0, "detail": why}
    if search is not None:
        _say_search(search, hub_source)
    sources.append(hub_source)
    return [*shipped, *installed, *(found or [])], sources


def _left_out_words(left_out: int) -> str:
    if not left_out:
        return ""
    return f" ({left_out} chat model{'s' if left_out != 1 else ''} left out)"


#: Each online source by the name a person knows it by, in the finder's one-line status (#5660 item 3).
SOURCE_NAMES = {"kraken-repository": "Zenodo", "hugging-face": "Hugging Face"}


def _say_search(search: dict[str, Any], *rows: dict[str, Any]) -> None:
    """The online sources as the search job leaves them, each in one short sentence (#5660 item 3: never an
    Activity job id or the engine's own words): "Searching Hugging Face…", "3 found on Zenodo", or that it
    could not be reached."""
    state = search.get("state")
    if state in ("waiting", "running", "paused"):
        for row in rows:
            row["state"] = "searching"
            row["detail"] = f"Searching {SOURCE_NAMES[row['source']]}…"
        return
    if state == "failed":
        for row in rows:
            row["state"], row["detail"] = "failed", f"Could not reach {SOURCE_NAMES[row['source']]}"
        return
    try:
        done = json.loads(search.get("detail") or "{}").get("sources") or {}
    except ValueError:
        done = {}
    for row in rows:
        said = done.get(row["source"])
        if said:
            row["state"] = said["state"]
            row["detail"] = (f"Could not reach {SOURCE_NAMES[row['source']]}" if said["state"] == "failed"
                             else f"{row['count']} found on {SOURCE_NAMES[row['source']]}"
                             + _left_out_words(int(row.get("left_out") or 0)))


# --- the online search, as an Activity job (#5594) ------------------------------------------------------

#: The job kind: a person waits on it, on the search lane (`source.find.online-search-is-a-job`).
SEARCH_KIND = "find-models"
#: Why the automatic search could not be queued, by languages key: the candidate list says it beside the search.
SEARCH_FAILURES: dict[str, str] = {}


def register_job_kinds() -> None:
    from fichero_server.core.background_compute import set_utility_qos
    from fichero_server.execution import jobs

    if SEARCH_KIND not in jobs.KINDS or jobs.KINDS[SEARCH_KIND].run is None:
        jobs.register_kind(SEARCH_KIND, _run_search, model=None, lane="search", qos=set_utility_qos,
                           name="Find reading models online")


def _subject(languages: frozenset[str], job: str | None = None) -> str:
    """The search's subject: the reader search's by languages; a step's own (`STEP_SEARCHES`) by job too."""
    return (f"job:{job};" if job else "") + f"languages:{_languages_key(languages)}"


def _job_of(subject: str) -> str | None:
    return subject.partition(";")[0][len("job:"):] if subject.startswith("job:") else None


def _languages_of(subject: str) -> frozenset[str]:
    key = subject.rpartition("languages:")[2]
    return frozenset() if key in ("", "any") else frozenset(key.split(","))


def search(db: Any, languages: frozenset[str], job: str | None = None, *, by_itself: bool = False) -> dict[str, Any]:
    """The search job for these languages, and for a step's own job when given one with a search of its own
    (`STEP_SEARCHES`, #5668), else the reader search (its row: id, state, reason, detail, finished_at): the one
    waiting or running, or one done within a day; otherwise a new one, queued on the search lane with a person
    waiting on it (`by_itself`: started by Set Up's save, not by a person: 'automatic' and not watched, so Activity says
    so and it goes in its turn). Never reaches the network itself."""
    from fichero_server.core.timeutil import ensure_utc
    from fichero_server.execution import jobs

    register_job_kinds()
    subject = _subject(languages, job if job in STEP_SEARCHES else None)
    latest = jobs.job_id_for(db, SEARCH_KIND, subject)
    row = jobs.find_jobs(db, kinds=[SEARCH_KIND], job_id=latest)[0] if latest else None
    if row is not None:
        if row["state"] in ("waiting", "running", "paused"):
            return row
        finished = row["finished_at"]
        if (row["state"] == "done" and finished is not None
                and datetime.now(timezone.utc) - ensure_utc(finished) < REFRESH_AFTER):
            return row
    job_id = jobs.enqueue(db, SEARCH_KIND, subject, started_by="automatic" if by_itself else "owner",
                          watched=not by_itself)
    return jobs.find_jobs(db, kinds=[SEARCH_KIND], job_id=job_id)[0]


def _project_hand_tags(db: Any) -> list[str]:
    """The Hugging Face tags of the hand the open project's Your Material answered (#5668); none without one."""
    from pathlib import Path

    from fichero_server.recipes.hands import tags_for
    from fichero_server.recipes.project import read_project_setup

    try:
        answers = read_project_setup(Path(db.path).parent)["answers"] or {}
    except Exception:  # noqa: BLE001 -- a search without the project's answers asks without a hand
        return []
    return tags_for(answers.get("hands"))


def _run_search(db: Any, subject: str) -> dict[str, Any]:
    """The job's work: search, keep what was found, and keep what each source did on the job's row."""
    from fichero_server.execution import jobs

    job_id = jobs.current_job_id() or jobs.job_id_for(db, SEARCH_KIND, subject)

    def say(words: str) -> None:
        jobs.save_detail(db, job_id, json.dumps({"doing": words}, ensure_ascii=False), reason=words)

    step = _job_of(subject)
    if step:
        result = search_online_for_step(step, _languages_of(subject), progress=say)
    else:
        result = search_online(_languages_of(subject), progress=say, hand_tags=_project_hand_tags(db))
    jobs.save_detail(db, job_id, json.dumps(result, ensure_ascii=False))
    failed = [s["detail"] for s in result["sources"].values() if s["state"] == "failed"]
    if len(failed) == len(result["sources"]):
        raise RuntimeError("; ".join(failed))
    return result


def search_online(languages: frozenset[str], progress: Callable[[str], None] = lambda _: None,
                  hand_tags: tuple[str, ...] | list[str] = ()) -> dict[str, Any]:
    """Fetch Kraken's repository listing when the kept one is a day old, and search Hugging Face for these
    languages, keeping both in the model store's `discovery/` folder; return what each source did. Network:
    run only as the `find-models` job. Refused when this engine works offline."""
    import asyncio

    if not egress_allowed():
        raise RuntimeError("this engine works offline (local-only), so nothing was searched")
    sources: dict[str, dict[str, Any]] = {}
    cached = cached_repository()
    if _stale(cached):
        progress("Searching Zenodo…")
        try:
            cached = refresh_repository()
            sources["kraken-repository"] = {"state": "searched",
                                            "detail": f"{len(cached['records'])} found on Zenodo"}
        except Exception as exc:  # the network or the repository failed: say so, keep the cache
            logger.warning("Kraken's repository could not be read: %s", exc)
            sources["kraken-repository"] = {"state": "failed", "detail": "Could not reach Zenodo"}
    else:
        sources["kraken-repository"] = {"state": "cached", "detail": f"{len(cached['records'])} found on Zenodo"}
    from fichero_server.recipes import htr_united

    if _stale(htr_united.cached()):
        progress("Searching HTR-United…")
        try:
            kept = htr_united.refresh()
            sources["htr-united"] = {"state": "searched", "detail": f"{len(kept['records'])} datasets on GitHub"}
        except (OSError, ValueError) as exc:  # the network or the catalogue failed: say so, keep the cache
            logger.warning("HTR-United's catalogue could not be read: %s", exc)
            sources["htr-united"] = {"state": "failed", "detail": "Could not reach HTR-United"}
    else:
        sources["htr-united"] = {"state": "cached", "detail": "HTR-United: kept from before"}
    try:
        found, left_out = asyncio.run(search_hugging_face(languages, progress, hand_tags))
        keep_hub(found, languages, left_out)
        sources["hugging-face"] = {"state": "searched", "count": len(found), "left_out": left_out,
                                   "detail": f"{len(found)} found on Hugging Face"}
    except Exception as exc:  # HTTPException from the one Hub fetch, or the network
        logger.warning("the Hugging Face search failed: %s", getattr(exc, "detail", exc))
        sources["hugging-face"] = {"state": "failed", "detail": "Could not reach Hugging Face"}
    return {"languages": sorted(languages), "searched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sources": sources}


def search_online_for_step(job: str, languages: frozenset[str],
                           progress: Callable[[str], None] = lambda _: None) -> dict[str, Any]:
    """Search Hugging Face for this step's job (`STEP_SEARCHES`) and keep what it found for the job and these
    languages; return what the source did. Network: run only as the `find-models` job. Refused offline."""
    import asyncio

    if not egress_allowed():
        raise RuntimeError("this engine works offline (local-only), so nothing was searched")
    try:
        rows = asyncio.run(search_hugging_face_for_step(job, languages, progress))
        keep_step_hub(job, languages, rows)
        source = {"state": "searched", "count": len(rows), "detail": f"{len(rows)} found on Hugging Face"}
    except Exception as exc:  # HTTPException from the one Hub fetch, or the network
        logger.warning("the Hugging Face search for %s failed: %s", job, getattr(exc, "detail", exc))
        source = {"state": "failed", "detail": "Could not reach Hugging Face"}
    return {"job": job, "languages": sorted(languages),
            "searched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sources": {"hugging-face": source}}


def model_key(card: Card) -> str:
    """What makes two cards one model: its Hugging Face repo or Zenodo record (case-folded), else the card's own id.
    Revisions and the source that found it do not make another model (#5808)."""
    for name in ("hf", "zenodo"):
        if card.pin.get(name):
            return f"{name}:{str(card.pin[name]).strip().casefold()}"
    return f"id:{card.id}"


def dedupe_cards(cards: list[Card], own_ids: frozenset[str] = frozenset(),
                 own_pin: dict | None = None) -> list[Card]:
    """No model twice: the first card for a model is kept, so the order the sources are listed in (shipped, installed,
    then what a search found) says which source keeps it. Except the step's own card -- its id in `own_ids`, or the pin
    it runs (`own_pin`, a revision included) -- which keeps its model's place whatever came first (#5808, review 296):
    otherwise a shipped twin at another revision drops the project's own."""
    def is_own(card: Card) -> bool:
        return card.id in own_ids or (own_pin is not None and dict(card.pin) == own_pin)

    winners = {model_key(c): c for c in reversed(cards) if is_own(c)}
    seen: set[str] = set()
    out = []
    for card in cards:
        key = model_key(card)
        if key not in seen:
            seen.add(key)
            out.append(winners.get(key, card))
    return out


def model_link(card: Card) -> str | None:
    """The page of a card's model: Hugging Face for a repo, doi.org for a Zenodo record; None where it has none to
    link (a cloud model, Apple's recognition), never a guess."""
    if card.pin.get("hf"):
        return f"https://huggingface.co/{card.pin['hf']}"
    if card.pin.get("zenodo"):
        record = str(card.pin["zenodo"]).strip()
        return record if record.startswith("http") else f"https://doi.org/{record}" if record.startswith("10.") \
            else f"https://zenodo.org/records/{record}"
    return None


def does_the_step(card: Card, job: str) -> bool:
    """Whether a card does a step's job: the ONE rule behind both what a step's menu lists (`step_candidates`) and what
    `use-candidate` accepts (`recipes/start.py::use_candidate`), so a listed model is never one the press refuses (#5808).
    A reader of whole pages that runs somewhere else (a cloud vision model, a model on the person's other computer) also
    reads the line step's lines: it is sent Kraken's line pictures (`cloud-reads-kraken-lines`). One on this Mac (a local
    vision model) does not do the line step; Apple's recognition does, its card says so (`read-a-line`, #6071)."""
    if job in card.jobs:
        return True
    return job == "read-a-line" and "read-a-page" in card.jobs and (card.runs_on or "this-mac") != "this-mac"


def step_candidates(cards: list[Card], job: str, own_ids: frozenset[str] = frozenset(),
                    own_pin: dict | None = None) -> list[Card]:
    """The one list of a step's candidates (#5808, `source.find.one-candidate-source`), for Find a Reader, the stage
    page and Compare alike: the cards that do the job (`does_the_step`), every model once. For the line step that
    includes the page readers that run elsewhere (offered, the person's to choose), not the ones on this Mac, except the
    step's own card."""
    from dataclasses import replace

    if job == "read-a-line":
        # the step's own card stays listed even when it is a page reader on this Mac (a recipe saved with one keeps working)
        cards = [c if job in c.jobs or not (does_the_step(c, job) or c.id in own_ids)
                 else replace(c, jobs=c.jobs | {job}, offered_only=True) for c in cards]
    return dedupe_cards([c for c in cards if job in c.jobs], own_ids, own_pin)
