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
import re
import unicodedata
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


# A period used as a WORD SEPARATOR — sitting directly between two letters
# with no space on either side. Paleographic PDFs export their text layer this
# way ("Antonio.de.guzman.vezino" for "Antonio de guzman vezino"), and NER
# carries the surface form through verbatim, so entity display names come out
# dotted. A period after an initial ("Laura C. Hall" — a space follows) or
# between digits ("3.5") is NOT a separator and is left alone. ``\w`` minus
# digit and underscore is "a letter" (Unicode-aware for str patterns).
_SEPARATOR_DOT = re.compile(r"(?<=[^\W\d_])\.(?=[^\W\d_])")


def readable_surface_form(text: str) -> str:
    """An entity display name with separator-dots turned back into spaces.

    Turns ``Antonio.de.guzman.vezino.dela.cibdad.de.uitoria`` into
    ``Antonio de guzman vezino dela cibdad de uitoria`` — the dots that stood
    in for spaces become spaces; a space that was lost outright ("de la"→"dela")
    cannot be recovered here and is left as it is. Whitespace is then collapsed.

    This normalises the DISPLAY string only. Callers keep character offsets
    pointing at the original span, so a highlight still lands on the page.
    """
    if not text:
        return text
    return " ".join(_SEPARATOR_DOT.sub(" ", text).split())


# Residence, role and kinship nouns that, following a personal name, begin a
# trailing DESCRIPTOR rather than continuing the name: "Antonio de Guzman
# vecino de la ciudad de Vitoria" — the person is "Antonio de Guzman", the rest
# is an appositive. spaCy (given the dotted, spaceless page text) swallows the
# whole run-on into one PERSON span; cutting at the first of these restores the
# name and lets its mentions cluster as one entity.
#
# Deliberately EXCLUDES leading titles that PRECEDE a name (don, doña, fray,
# capitán, licenciado): those are not trailing descriptors, and cutting at them
# would behead the name. Kept short and role-specific — a personal name that
# genuinely contains one of these is vanishingly rare in this corpus.
_PERSON_DESCRIPTOR_STOPWORDS = frozenset(
    {
        "vecino", "vezino", "vecina", "vezina", "vzo", "vza", "vz",
        "morador", "moradora", "natural", "naturales", "residente",
        "estante", "estantes", "difunto", "difunta", "difuntos",
        "hijo", "hija", "hijos", "hijas", "mujer", "muger", "esposa",
        "esposo", "viuda", "viudo", "padre", "madre", "hermano", "hermana",
        "escribano", "escrivano", "alcalde", "gobernador", "governador",
        "cacique", "principal", "indio", "india", "indios", "indias",
        "regidor", "alguacil", "corregidor", "encomendero", "criado", "criada",
    }
)


def _fold_word(word: str) -> str:
    """Accent-, case- and edge-punctuation-folded single word, for lookup."""
    decomposed = unicodedata.normalize("NFKD", word)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.casefold().strip(".,;:()[]\"'")


def trim_person_name(name: str) -> str:
    """Cut a PERSON name at the first trailing descriptor, or return it whole.

    "Antonio de Guzman vezino de la cibdad de uitoria" → "Antonio de Guzman".
    The cut only fires from the SECOND word on, so a span is never emptied and
    a name that opens with a title ("el capitan Galarza vz de Tunja") keeps the
    title and loses only the trailing "vz de Tunja". Names with no descriptor
    token ("Antonio de Guzman", "Juan de la Cruz") are returned unchanged.
    """
    words = name.split()
    for i in range(1, len(words)):
        if _fold_word(words[i]) in _PERSON_DESCRIPTOR_STOPWORDS:
            return " ".join(words[:i]).strip(" ,;:")
    return name


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


# Model preference PER LANGUAGE, best first. `md` before `sm` for the two
# bundled languages: the medium pipeline is the same tagger the SVO gate reads
# plus word vectors, so when a user has added it (from the model catalog) the
# gate uses it, and otherwise falls straight back to the small model that ships
# in the app. The order is a preference, not a requirement — a language with
# only the small model installed loads the small model with no fuss.
_MODEL_PREFERENCE: dict[str, tuple[str, ...]] = {
    "en": ("en_core_web_md", "en_core_web_sm"),
    "es": ("es_core_news_md", "es_core_news_sm"),
    "fr": ("fr_core_news_sm",),
    "de": ("de_core_news_sm",),
    "pt": ("pt_core_news_sm",),
}


# Cached pipeline objects per language. Keys are language codes
# ("en", "es"); values are the loaded spaCy Language objects.
_pipelines: dict[str, object] = {}


def _installed_models(spacy_module) -> set[str]:
    """Which pipeline packages this interpreter can load, empty on any doubt."""
    try:
        return set(spacy_module.util.get_installed_models())
    except Exception:  # noqa: BLE001 — never let a probe break NER
        return set()


def _load_pipeline(language: str):
    """Lazy-load and cache the best installed spaCy pipeline for ``language``.

    Tries the language's models in preference order (medium before small where
    both exist) and loads the first one actually installed. Returns None when
    spaCy is absent or no model for the language is installed, so callers fall
    through to the LLM-only path rather than crashing the workflow.
    """
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

    candidates = _MODEL_PREFERENCE.get(language)
    if not candidates:
        logger.warning(
            "spacy_ner: no pipeline for language=%r, falling back to English", language
        )
        language = "en"
        candidates = _MODEL_PREFERENCE["en"]

    installed = _installed_models(spacy)
    for model_name in candidates:
        if model_name not in installed:
            continue
        try:
            nlp = spacy.load(model_name)
        except OSError as exc:
            # Reported installed but did not load — try the next candidate
            # rather than giving up on the language entirely.
            logger.warning(
                "spacy_ner: model %r reported installed but failed to load (%s)",
                model_name, exc,
            )
            continue
        _pipelines[language] = nlp
        return nlp

    # Nothing installed for this language — say what would fix it, then let the
    # caller fall through to LLM-only NER.
    logger.warning(
        "spacy_ner: no installed model for language=%r (looked for %s) — "
        "falling through to LLM-only NER. Run: python -m spacy download %s",
        language, ", ".join(candidates), candidates[-1],
    )
    return None


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
        # Display surface form: dotted paleographic text ("Antonio.de.guzman")
        # reads naturally. Offsets stay on the original span so a highlight
        # still lands; the cleaned form also drives dedup, so a dotted and a
        # spaced mention of the same name collapse.
        name = readable_surface_form(ent.text)
        if fichero_type == "person":
            # Stop the name at a trailing residence/role descriptor so the same
            # person's mentions collapse to one entity instead of fragmenting.
            name = trim_person_name(name)
        key = (name, fichero_type)
        if key in seen:
            # Keep the earliest occurrence — the LLM later sees this
            # one span and can include the parenthetical variants
            # via alternative_spellings.
            continue
        seen[key] = EntitySpan(
            text=name,
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
    tokens_of: dict[str, frozenset[str]] = {}

    for span in by_length:
        st = tokens_of.setdefault(span.text, _name_tokens(span.text))
        absorbed = False
        for canonical in clusters:
            if canonical.fichero_type != span.fichero_type:
                continue
            ct = tokens_of.setdefault(canonical.text, _name_tokens(canonical.text))
            # WHOLE-TOKEN subset, not character substring. Raw substring merged
            # distinct people who merely share letters — "Ana"⊂"Susana",
            # "Juan"⊂"Juana", "Luis"⊂"Luisa", "Mari"⊂"María" — a disaster on a
            # Spanish corpus. Requiring the shorter name's tokens to ALL be
            # whole tokens of the longer keeps the real cases ("Davidson" and
            # "[Deibinson]" under "Davidson [Deibinson]") and drops the false
            # ones. Empty token sets never match.
            if st and ct and (st <= ct or ct <= st):
                if span.text != canonical.text and span.text not in clusters[canonical]:
                    clusters[canonical].append(span.text)
                absorbed = True
                break
        if not absorbed:
            clusters[span] = []

    return clusters


def _name_tokens(text: str) -> frozenset[str]:
    """Accent/case/punct-folded whole-word tokens of a name, for subset tests.

    ``_fold_word`` strips surrounding brackets and accents, so "[Deibinson]"
    and "Deibinson" fold to the same token and "María" to "maria". Empty tokens
    (a word that was pure punctuation) are dropped.
    """
    return frozenset(t for t in (_fold_word(w) for w in text.split()) if t)


__all__ = [name for name in globals() if not name.startswith("__")]
