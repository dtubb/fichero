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
