"""Deterministic SVO proposals from a dependency parse (#4671).

Daniel: "are there good NLP tools for SVO?" and, after the first numbers:
"let's get spaCy going; its entities aren't good, but maybe it's a start, and
a free way to do SVO that we can then improve."

WHAT THIS IS FOR. An LLM writes fluent Spanish it composed itself — the
failure the grounding contract (#4666) exists to catch. A dependency parser
cannot: every span it returns is a slice of the text, with the offsets it was
taken from. So spaCy is not a better extractor than the model, it is a
DIFFERENT one, strong exactly where the model is weak:

    spaCy       grounded by construction, subjects often pronouns
    LLM         subjects always named, spans often invented

Hence the tiers. spaCy proposes verbatim candidates; the shared quality gates
(`svo_quality`) throw out the pronoun subjects and the empty predicates; an
optional model pass refines what survives. Each tier is usable alone, and the
cheapest one is free.

WHAT IT IS NOT. spaCy's Spanish models are trained on modern prose, and this
corpus is 16th–17th-century notarial Spanish. Measured on a real Caciques
page: NER called a stamp a person and a personal name a place, and four of
five triples had a pronoun subject. The parser is a proposer, never an
authority — which is precisely why nothing here writes to the database.

Optional dependency: spaCy is an extra (`pip install -e ".[kg]"`), not part of
the embedded engine. Every entry point degrades to an empty list with a
logged reason rather than raising, so a library without it loses this tier
and nothing else.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

#: spaCy model per language. Small models only: the medium/large ones carry
#: word vectors we do not use here and cost ~10× the disk for a parse quality
#: difference this corpus will not notice.
MODELS = {"es": "es_core_news_sm", "en": "en_core_web_sm"}

#: Dependency labels that name a clause's subject and its object side, in the
#: Universal Dependencies scheme both models use.
_SUBJECT_DEPS = frozenset({"nsubj", "nsubj:pass"})
_OBJECT_DEPS = ("obj", "obl", "iobj", "attr", "xcomp", "ccomp")


@dataclass
class ProposedTriple:
    """One candidate statement, and where every part of it was read."""

    subject: str
    verb: str
    object: str
    #: Character offsets of the SENTENCE the triple came from, so a proposal
    #: can be shown, checked, and highlighted without re-finding it.
    sentence: str
    char_start: int
    char_end: int
    #: What produced it — "spacy:dep" or "spacy:pattern:<name>". Carried
    #: through so a stored row can say which tier proposed it rather than
    #: presenting a parse and a model as the same kind of thing.
    source: str = "spacy:dep"
    meta: dict[str, Any] = field(default_factory=dict)

    def as_item(self) -> dict[str, Any]:
        """The shape `_write_kg_rows` consumes, minus anything it must infer."""
        return {
            "name": self.subject,
            "verb": self.verb,
            "object": self.object,
            "source_text": self.sentence,
            "extraction_source": self.source,
        }


@lru_cache(maxsize=4)
def _pipeline(language: str):
    """Load a spaCy model once per process, or return None with a reason."""
    model = MODELS.get(language, MODELS["es"])
    try:
        import spacy

        return spacy.load(model, exclude=["lemmatizer"])
    except Exception as exc:  # noqa: BLE001 — an absent extra is not a fault
        logger.info(
            "spaCy tier unavailable (%s): %s. Install with "
            'pip install -e ".[kg]" && python -m spacy download %s',
            model, exc, model,
        )
        return None


def _span_text(tokens: list[Any]) -> str:
    """A contiguous slice of the ORIGINAL text covering ``tokens``.

    Rebuilt from offsets rather than joined from token strings: joining
    invents the whitespace, and a span that is not a substring of the page
    cannot be highlighted on it.
    """
    if not tokens:
        return ""
    doc = tokens[0].doc
    start = min(tok.idx for tok in tokens)
    end = max(tok.idx + len(tok.text) for tok in tokens)
    return doc.text[start:end].strip()


def _subject_span(token: Any) -> list[Any]:
    """The subject with its modifiers — "Andres xptoval Hernandez Varela",
    not "Andres" — but without the relative clauses hanging off it."""
    return [
        tok
        for tok in token.subtree
        if tok.dep_ not in ("relcl", "acl", "acl:relcl")
    ]


def propose_triples(
    text: str, language: str = "es", *, max_triples: int = 60
) -> list[ProposedTriple]:
    """Every subject–verb–object the parser can find, as verbatim spans.

    No filtering happens here beyond dropping the structurally empty: judging
    a proposal is `svo_quality`'s job, and one module deciding both what is
    findable and what is acceptable would make the two impossible to measure
    apart.
    """
    nlp = _pipeline(language)
    if nlp is None or not (text or "").strip():
        return []

    doc = nlp(text)
    out: list[ProposedTriple] = []
    for token in doc:
        if token.pos_ not in ("VERB", "AUX"):
            continue
        subjects = [c for c in token.children if c.dep_ in _SUBJECT_DEPS]
        if not subjects:
            continue
        objects = [c for c in token.children if c.dep_ in _OBJECT_DEPS]
        # Auxiliaries belong to the verb phrase: "ha de dar", not "dar".
        verb_tokens = sorted(
            [token, *[c for c in token.children if c.dep_ in ("aux", "aux:pass", "cop")]],
            key=lambda t: t.i,
        )
        verb = _span_text(verb_tokens)
        for subject in subjects:
            subject_text = _span_text(_subject_span(subject))
            for obj in objects or [None]:
                object_text = _span_text(list(obj.subtree)) if obj is not None else ""
                if not subject_text or not (verb or object_text):
                    continue
                sent = token.sent
                out.append(
                    ProposedTriple(
                        subject=subject_text,
                        verb=verb,
                        object=object_text,
                        sentence=sent.text.strip(),
                        char_start=sent.start_char,
                        char_end=sent.end_char,
                        meta={"dep": obj.dep_ if obj is not None else "none"},
                    )
                )
                if len(out) >= max_triples:
                    return out
    return out


# ---------------------------------------------------------------------------
# The formulaic tier (#4671)
# ---------------------------------------------------------------------------
#
# An escribano's page is not free prose. A large share of it is a fixed form
# repeated across thousands of documents — "Sepan quantos esta carta vieren",
# "otorgamos que damos poder cumplido a X", "ante mí, Y, escrivano público".
# For that share a pattern is not a heuristic; it is a reading of a known
# genre, and it is right or wrong in a way anyone can check.
#
# This is where the notarial run-ons came from that the LLM turned into
# "Andres otorgamos que damos mostrando tenemos cargo": the formula defeated
# a general extractor precisely BECAUSE it is stereotyped. Patterns are
# deliberately few and narrow — a pattern that fires on the wrong page is
# worse than no pattern, because it is confident.

_NAME = r"[A-ZÁÉÍÓÚÑ][\w'’.]*(?:\s+(?:de|del|la|las|los|y)?\s*[A-ZÁÉÍÓÚÑ][\w'’.]*){0,4}"

FORMULAIC_PATTERNS: list[tuple[str, str, str, str]] = [
    # (name, regex, verb, which group is the object)
    (
        "otorga_poder",
        rf"otorga(?:mos|n|ba)?\s+(?:que\s+)?(?:damos?\s+)?(?:todo\s+)?"
        rf"(?:nuestro\s+|su\s+)?poder\s+cumplido\s+a\s+(?P<object>{_NAME})",
        "otorga poder cumplido a",
        "object",
    ),
    (
        "ante_escrivano",
        rf"ante\s+(?:mi|mí)\s*,?\s*(?P<object>{_NAME})\s*,?\s*escriv?ano",
        "otorgado ante",
        "object",
    ),
    (
        "testigos",
        rf"testigos?\s+(?:que\s+fueron\s+presentes\s*:?\s*)(?P<object>{_NAME})",
        "tuvo por testigo a",
        "object",
    ),
]


def propose_formulaic(
    text: str, subject_hint: str = "", *, max_triples: int = 20
) -> list[ProposedTriple]:
    """Triples from the notarial formulas this corpus repeats.

    ``subject_hint`` is the entity the page is about; a formula names its
    object ("...a Juan Bazán") and leaves the grantor to the surrounding text,
    so without a hint the subject is left empty for the caller to fill rather
    than guessed here.
    """
    out: list[ProposedTriple] = []
    for name, pattern, verb, group in FORMULAIC_PATTERNS:
        for match in re.finditer(pattern, text or "", re.IGNORECASE):
            obj = (match.group(group) or "").strip()
            if not obj:
                continue
            out.append(
                ProposedTriple(
                    subject=subject_hint,
                    verb=verb,
                    object=obj,
                    sentence=text[match.start() : match.end()],
                    char_start=match.start(),
                    char_end=match.end(),
                    source=f"spacy:pattern:{name}",
                )
            )
            if len(out) >= max_triples:
                return out
    return out


def filter_proposals(
    proposals: list[ProposedTriple], text: str
) -> tuple[list[ProposedTriple], list[tuple[ProposedTriple, str]]]:
    """Apply the SHARED quality gates and say what each rejection was for.

    The same `svo_quality` rules the LLM tier answers to, so the accuracy
    table compares two extractors under one standard rather than two.
    Returns ``(kept, [(rejected, reason)])``.
    """
    from fichero_server.knowledge.svo_quality import claim_rejection, trim_predicate

    kept: list[ProposedTriple] = []
    rejected: list[tuple[ProposedTriple, str]] = []
    for proposal in proposals:
        verb, obj = trim_predicate(proposal.verb, proposal.object)
        reason = claim_rejection(proposal.subject, verb, obj, text)
        if reason:
            rejected.append((proposal, reason))
            continue
        kept.append(
            ProposedTriple(
                subject=proposal.subject,
                verb=verb,
                object=obj,
                sentence=proposal.sentence,
                char_start=proposal.char_start,
                char_end=proposal.char_end,
                source=proposal.source,
                meta=proposal.meta,
            )
        )
    return kept, rejected


# ---------------------------------------------------------------------------
# The validator (#4671) — where spaCy actually earns its place
# ---------------------------------------------------------------------------
#
# Measured on the 17 SVO rows a real Apple-Intelligence run left in the
# Caciques Indios library (2026-09-04). As an EXTRACTOR spaCy was worse than
# the model: four of five triples it proposed had a pronoun subject. As a
# VALIDATOR of the model's rows it was right about every single one:
#
#     9 rows whose "verb" is not a verb — "cañistin" (PROPN), "estantes"
#       (ADJ), "a" (ADP), "oy" (NOUN). An SVO row whose predicate is a proper
#       noun is not a statement; it is three fragments in a row's shape.
#     8 rows carrying a FIRST-PERSON PLURAL verb under a named third-party
#       subject — "Andres otorgamos", "Corte estamos", "Puerto estamos". The
#       page is a petition written in the first person ("nosotros ... somos a
#       tomar la confesión"), and the extractor stamped whichever name was
#       nearby onto every "we" verb. This is precisely what Daniel meant by
#       "one name stamped onto unrelated predicates", and Spanish morphology
#       settles it deterministically, in 21 ms, for free.
#
# The tagging is done ON THE PAGE, not on the extracted fragment: a word out
# of context is a guess, and "estantes" alone tells you nothing. Everything
# fails open — no spaCy, no model for the language, or a verb that does not
# appear on the page at all, and the claim passes untouched. A validator that
# cannot see must not condemn.

#: Coarse tags a predicate's head word may legitimately carry.
_VERBAL_POS = frozenset({"VERB", "AUX"})


@lru_cache(maxsize=8)
def _page_morphology(text: str, language: str) -> dict[str, tuple[str, str]]:
    """``{lowercased word: (pos, person)}`` for one page, tagged in context.

    Cached because a page is validated once per claim and there can be dozens.
    First occurrence wins: a word used twice in one notarial page is the same
    word, and the alternative — tagging per claim — would cost the parse we
    are trying to make cheap.
    """
    nlp = _pipeline(language)
    if nlp is None or not (text or "").strip():
        return {}
    out: dict[str, tuple[str, str]] = {}
    for token in nlp(text):
        key = token.text.casefold()
        if key in out:
            continue
        person = token.morph.get("Person")
        out[key] = (token.pos_, person[0] if person else "")
    return out


def model_language(page_text: str) -> str | None:
    """Which spaCy model may judge this page, or ``None`` for none of them.

    THE PAGE'S OWN LANGUAGE DECIDES, not the caller's default. Caught the
    first time this gate ran across the whole suite: an ENGLISH fixture page
    judged by the Spanish model, which tags "took" as a proper noun and
    rejected a perfectly good claim. A validator running the wrong grammar is
    not a stricter validator, it is a broken one — and it fails in the
    direction that silently discards real statements.

    Detection is the stdlib helper the write path already uses. A language we
    have no model for returns ``None`` and the gate abstains: there are far
    more languages in an archive than there are models on this machine.
    """
    if not (page_text or "").strip():
        return None
    try:
        from fichero_server.llm.lang_detect import detect_language
    except Exception:  # noqa: BLE001
        return None
    name = (detect_language(page_text[:2000], default="") or "").strip().casefold()
    return {"spanish": "es", "english": "en"}.get(name)


def predicate_problem(
    subject: str,
    verb: str,
    page_text: str,
    *,
    language: str | None = None,
    speaker: str = "",
) -> str | None:
    """Why this predicate cannot belong to this subject, or ``None``.

    ``speaker`` is the person the document's first person refers to — a
    diary's diarist, a petition's petitioner. When the subject IS the speaker,
    a first-person verb is correct and is left alone; that is the whole reason
    the extractor carries a document context at all.

    ``language`` defaults to the page's own, detected. Pass one only when the
    caller knows better than the detector.
    """
    head = (verb or "").strip().split()
    if not head:
        return None
    language = language or model_language(page_text)
    if language is None:
        return None
    morphology = _page_morphology(page_text or "", language)
    if not morphology:
        # NO TAGGER — the shipped engine's normal state, since spaCy is an
        # optional extra. Half the gate can still run: Spanish marks person in
        # the ending, and that half convicted 8 of the 16 bad rows. Measured
        # 2026-09-04, Apple's NLTagger cannot do even this — it exposes no
        # morphology for Spanish at all — so the endings are what a build
        # without spaCy has. The other half (is the predicate a verb?) needs a
        # tagger and stays silent.
        return _person_problem_without_tagger(subject, head[0], language, speaker)
    pos, person = morphology.get(head[0].casefold(), ("", ""))
    if not pos:
        # The word is not on the page. `svo_quality`'s grounding rule owns
        # that verdict; this one has nothing to say.
        return None
    if pos not in _VERBAL_POS:
        return f"predicate {head[0]!r} is a {pos}, not a verb — this is not a statement"
    if person == "1" and (subject or "").strip():
        from fichero_server.knowledge.svo_quality import fold

        if speaker and fold(speaker) == fold(subject):
            return None
        return (
            f"first-person verb {head[0]!r} under the third-party subject "
            f"{subject!r} — the page says 'we', and this row says {subject}"
        )
    return None


def _person_problem_without_tagger(
    subject: str, head: str, language: str, speaker: str
) -> str | None:
    """The first-person half of the gate, with no model installed."""
    from fichero_server.knowledge.svo_quality import fold, is_first_person_verb

    if not (subject or "").strip():
        return None
    if is_first_person_verb(head, language) is not True:
        return None
    if speaker and fold(speaker) == fold(subject):
        return None
    return (
        f"first-person verb {head!r} under the third-party subject "
        f"{subject!r} — the page says 'we', and this row says {subject}"
    )
