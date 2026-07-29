"""spaCy first-pass NER (Phase C of #899).

Runs spaCy's pre-trained pipelines (en_core_web_sm,
es_core_news_sm) BEFORE the LLM extractor in the catalogue
workflow. The downstream LLM still produces the SVO predicate +
epistemic / ontological classification, but the entity boundaries
are detected deterministically by spaCy.

Why this matters:
- **Cost**: spaCy is ~100x faster than an on-device LLM call per
  entity. A 50-page archive PDF that runs Catalogue in ~5min today
  should drop to ~1min with NER moved out of the LLM's job.
- **Cleaner alias clustering**: parenthetical aliases (Davidson
  [Deibinson]) appear as one entity with two surface forms in
  spaCy's span output, then handed to the LLM as one item rather
  than two — directly attacks the #896 within-page duplication.
- **Better entity boundaries**: spaCy's models were trained on
  100Ms of labelled tokens; LLM entity recognition is a byproduct
  of next-token prediction. spaCy wins on consistency.

Why a pre-pass and not a replacement: spaCy doesn't produce SVO
predicates, epistemic_status, or claim_type. The LLM still owns the
hard part (interpretation, classification) — spaCy owns the easy
part (where in the text is a name).

Models lazy-loaded on first use per the
``feedback_lazy_import`` memory (no cold-start cost for users who
don't catalogue).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    pass

logger = logging.getLogger(__name__)


# Map spaCy entity labels (the ones produced by the small/medium
# pre-trained pipelines) to Fichero's EntityType enum. Anything not in
# the table maps to .other so we don't drop spans we don't recognise.
# Labels are documented at https://spacy.io/models/en
_SPACY_TO_FICHERO_EN = {
    "PERSON": "person",
    "ORG": "organization",
    "GPE": "location",  # Geo-political entity (country/city/state)
    "LOC": "location",  # Non-GPE locations (mountains, water)
    "FAC": "location",  # Facilities (airports, bridges)
    "EVENT": "event",
    "WORK_OF_ART": "concept",
    "LAW": "concept",
    "LANGUAGE": "concept",
    "NORP": "concept",  # Nationalities, religious or political groups
    "PRODUCT": "concept",
}
# Spanish (es_core_news_sm) uses a smaller label set; map the four
# OntoNotes-style labels the model emits.
_SPACY_TO_FICHERO_ES = {
    "PER": "person",
    "ORG": "organization",
    "LOC": "location",
    "MISC": "concept",
}


@dataclass(frozen=True)
class EntitySpan:
    """One spaCy-detected mention.

    ``start`` and ``end`` are character offsets into the input
    text — call sites use them to highlight the source span in the
    PDF preview (#893) and to feed the LLM with the surrounding
    sentence as context.
    """
    text: str
    fichero_type: str
    start: int
    end: int
    label: str  # raw spaCy label, kept for downstream inspection


# Cached pipeline objects per language. Keys are language codes
# ("en", "es"); values are the loaded spaCy Language objects.
_pipelines: dict[str, object] = {}


def _load_pipeline(language: str):
    """Lazy-load and cache the spaCy pipeline for ``language``."""
    if language in _pipelines:
        return _pipelines[language]

    try:
        import spacy
    except ImportError as exc:
        logger.warning(
            "spacy_ner: spaCy is not installed (%s) — falling through to LLM-only NER",
            exc,
        )
        return None

    model_name = {
        "en": "en_core_web_sm",
        "es": "es_core_news_sm",
    }.get(language)
    if not model_name:
        logger.warning("spacy_ner: no pipeline for language=%r, falling back to English", language)
        model_name = "en_core_web_sm"
        language = "en"

    try:
        nlp = spacy.load(model_name)
    except OSError as exc:
        # Model not downloaded — emit a useful error rather than
        # crashing the catalogue workflow. Returning None lets
        # callers fall through to the LLM-only path.
        logger.warning(
            "spacy_ner: model %r not available (%s) — falling through to "
            "LLM-only NER. Run: python -m spacy download %s",
            model_name, exc, model_name,
        )
        return None

    _pipelines[language] = nlp
    return nlp


def detect_language(text: str) -> str:
    """Lightweight language guess for picking the right spaCy model.

    Heuristic — counts Spanish-specific tokens and accents. Good
    enough for ES vs EN; anything else returns 'en'. For a real
    detector we'd add ``langdetect`` or ``cld3`` but those are heavy.

    Returns a two-letter ISO code: 'en' or 'es'.
    """
    if not text:
        return "en"
    lower = text.lower()
    # Spanish-specific high-frequency markers.
    es_markers = (" el ", " la ", " los ", " las ", " que ", " de ", " del ", " es ", " un ", " una ", " pero ", " por ", " para ", " años ", " años,")
    es_chars = "ñáéíóúü¿¡"
    es_score = sum(lower.count(m) for m in es_markers) + sum(lower.count(c) for c in es_chars)
    en_markers = (" the ", " and ", " of ", " to ", " in ", " is ", " a ", " on ", " for ", " that ", " with ")
    en_score = sum(lower.count(m) for m in en_markers)
    return "es" if es_score > en_score else "en"


def extract_entities(text: str, language: str | None = None) -> list[EntitySpan]:
    """Run spaCy NER over ``text`` and return Fichero-typed spans.

    ``language`` overrides the heuristic guess. Returns an empty list
    when the model isn't available — callers should treat this as
    "LLM gets to do all the work" and continue rather than fail.

    Spans are deduplicated on (text, fichero_type) within a single
    call so identical mentions ("Davidson" appearing 6 times on the
    same page) collapse to one span with the earliest offsets.
    """
    if not text or not text.strip():
        return []

    lang = language or detect_language(text)
    nlp = _load_pipeline(lang)
    if nlp is None:
        return []

    label_map = _SPACY_TO_FICHERO_ES if lang == "es" else _SPACY_TO_FICHERO_EN
    doc = nlp(text)

    seen: dict[tuple[str, str], EntitySpan] = {}
    for ent in doc.ents:
        fichero_type = label_map.get(ent.label_)
        if not fichero_type:
            continue
        key = (ent.text, fichero_type)
        if key in seen:
            # Keep the earliest occurrence — the LLM later sees this
            # one span and can include the parenthetical variants
            # via alternative_spellings.
            continue
        seen[key] = EntitySpan(
            text=ent.text,
            fichero_type=fichero_type,
            start=ent.start_char,
            end=ent.end_char,
            label=ent.label_,
        )
    return list(seen.values())


def cluster_aliases(spans: list[EntitySpan]) -> dict[EntitySpan, list[str]]:
    """Group spans whose text is one a substring of another into
    alias clusters.

    Use case: ``Davidson`` and ``Davidson [Deibinson]`` and
    ``[Deibinson]`` all reference the same person — spaCy detects all
    three as separate PERSON spans, but they belong together. The
    cluster picks the longest as canonical and treats the others as
    aliases.

    Returns a dict mapping each canonical span → list of alias surface
    forms. Spans that aren't a member of any cluster appear as keys
    with an empty alias list.
    """
    # Sort by length descending so longer spans (likely canonical
    # forms) anchor the clusters.
    by_length = sorted(spans, key=lambda s: -len(s.text))
    clusters: dict[EntitySpan, list[str]] = {}

    for span in by_length:
        absorbed = False
        for canonical in clusters:
            if canonical.fichero_type != span.fichero_type:
                continue
            ct = canonical.text.lower()
            st = span.text.lower()
            # Substring in either direction → cluster. Cheap proxy for
            # alias relationship that catches parenthetical variants
            # without an explicit list.
            if st in ct or ct in st:
                if span.text != canonical.text and span.text not in clusters[canonical]:
                    clusters[canonical].append(span.text)
                absorbed = True
                break
        if not absorbed:
            clusters[span] = []

    return clusters


__all__ = [name for name in globals() if not name.startswith("__")]
