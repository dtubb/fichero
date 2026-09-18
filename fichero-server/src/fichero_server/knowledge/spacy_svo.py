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
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

#: spaCy model per language. Small models only: the medium/large ones carry
#: word vectors we do not use here and cost ~10× the disk for a parse quality
#: difference this corpus will not notice.
MODELS = {"es": "es_core_news_sm", "en": "en_core_web_sm"}

# ---------------------------------------------------------------------------
# Per-language dependency-label vocabulary (kg-readable review, 2026-09-18).
#
# The single UD-shaped set that used to live here claimed "both models use
# Universal Dependencies" -- FALSE, verified by RUNNING both real models on
# the review's sample sentences, not assumed from memory: en_core_web_sm
# speaks a ClearNLP-derived scheme (`dobj`/`pobj`/`nsubjpass`/`dative`/
# `agent`), never UD's `obj`/`obl`/`nsubj:pass`. Old `_OBJECT_DEPS` matched
# almost nothing in English -- "Juan Asprilla sold the mine to Pedro
# Mosquera" proposed an EMPTY object, and the English passive ("nsubjpass")
# was never even in `_SUBJECT_DEPS`, so it produced no triple at all.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _LangDeps:
    """One language's dependency-label vocabulary for the SPECIFIC small
    model this module loads -- not the UD label list in the abstract."""

    #: Active-clause grammatical subject.
    subject: frozenset[str]
    #: Passive-clause grammatical subject (the patient) -- a dep label
    #: DISTINCT from `subject` only where this parser bothers to mark it
    #: (English: `nsubjpass`). Empty where it doesn't (Spanish: plain
    #: `nsubj` either way; passive is detected structurally instead, see
    #: `_is_passive_clause`).
    passive_subject: frozenset[str]
    #: Direct-child object dependencies for an ACTIVE clause.
    object: frozenset[str]
    #: The dep label this parser gives an agent-introducing adposition
    #: ("by") as a DIRECT CHILD of the passive verb, when it has one.
    #: English has it ("agent"). Spanish's small model has no dedicated
    #: label -- verified: "vendida ... por Juan Asprilla" puts "Juan" at
    #: plain `obj`, same as any other object.
    agent_dep: str | None
    #: Prepositions (accent-folded) that introduce a passive agent, for a
    #: language with no dedicated `agent_dep` (Spanish "por"). Detected via
    #: a `case` grandchild of an object-dep child, not a top-level label.
    agent_prepositions: frozenset[str]
    #: Deps whose entire subtree is a relative clause -- never part of the
    #: antecedent's own span.
    relative_clause: frozenset[str]


_RELATIVE_CLAUSE_DEPS = frozenset({"relcl", "acl", "acl:relcl"})

_LANG_DEPS: dict[str, _LangDeps] = {
    # Verified 2026-09-18 against real en_core_web_sm output:
    #   "Juan Asprilla sold the mine to Pedro Mosquera." -> nsubj / dobj /
    #     prep(to) + pobj(Mosquera) -- the PP object is TWO levels below
    #     the verb, not a direct child, hence the separate prep-walk below.
    #   "The mine was sold by Juan Asprilla." -> nsubjpass(mine) /
    #     auxpass(was) / agent(by) -> pobj(Asprilla).
    #   "Juan Asprilla gave Pedro Mosquera two slaves." -> dative(Mosquera)
    #     / dobj(slaves).
    "en": _LangDeps(
        subject=frozenset({"nsubj"}),
        passive_subject=frozenset({"nsubjpass"}),
        object=frozenset({"dobj", "dative", "attr", "oprd", "ccomp", "xcomp"}),
        agent_dep="agent",
        agent_prepositions=frozenset(),
        relative_clause=_RELATIVE_CLAUSE_DEPS,
    ),
    # Verified 2026-09-18 against real es_core_news_sm output:
    #   "Juan Asprilla vendió la mina a Pedro Mosquera." -> nsubj(Juan) /
    #     obj(mina) AND obj(Pedro) -- both direct-a-marked objects land at
    #     plain `obj`, so this DOES propose two triples (mine, Pedro), same
    #     shape as the pre-existing "one row per object child" behavior
    #     `dedupe_proposals`/downstream aggregation already handle.
    #   "La mina fue vendida por Juan Asprilla." -> nsubj(mina, the
    #     PATIENT -- this small model never uses nsubjpass for Spanish) /
    #     aux(fue) / obj(Juan) with a `case` child "por" -- the agent, at
    #     plain `obj`, not a dedicated label.
    #   "Se le entregó la escritura." -> nsubj(escritura) / obj(le, a
    #     clitic) -- the clitic must never become the claim's object; see
    #     the pronoun-object filter in `propose_triples`, not here.
    "es": _LangDeps(
        subject=frozenset({"nsubj"}),
        passive_subject=frozenset(),
        object=frozenset({"obj", "obl", "iobj", "attr", "xcomp", "ccomp"}),
        agent_dep=None,
        agent_prepositions=frozenset({"por"}),
        relative_clause=_RELATIVE_CLAUSE_DEPS,
    ),
}

# "ser" forms, for detecting a Spanish `ser`-passive ("fue vendida") without
# lemma access (`_pipeline` loads with `exclude=["lemmatizer"]`; verified
# empirically that `token.lemma_` comes back EMPTY for content words without
# it -- only spaCy's small rule table for common AUX still resolves a few,
# not enough to rely on). A small, closed, accent-folded list is safe here
# specifically because "ser" is a closed, highly irregular paradigm -- unlike
# a content verb, the whole conjugation fits in one set. This is what tells
# a `ser`-passive apart from a `haber`-perfect ("había vendido"), which also
# puts a participle under an `aux` child in this parser's output.
_SPANISH_SER_FORMS = frozenset({
    "es", "son", "era", "eran", "fue", "fueron", "sido", "siendo",
    "sera", "seran", "sea", "sean", "fuera", "fueran", "seria", "serian",
})


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


# A spaCy ``Language`` object is NOT thread-safe -- calling ``nlp(text)``
# mutates shared per-pipe state and the shared Vocab/StringStore (the exact
# hazard `knowledge/spacy_ner.py`'s own `_spacy_lock` already documents and
# guards against for ITS pipeline cache). This module's `_pipeline(language)`
# is a SEPARATE cache holding a SEPARATE `Language` instance per language,
# with no lock of its own -- and it is called from `propose_triples` (via
# `importers/nlp_draft.py::run_nlp_draft`) on the derivatives module's
# bounded 2-worker executor, the same concurrent context `spacy_ner.py`'s
# lock exists for. Two worker threads calling `nlp(text)` on the SAME
# cached `Language` object at once corrupts its internal state -- observed
# 2026-09-18 as a background test hanging the whole pytest PROCESS at exit
# (a worker thread parked forever inside spaCy's C extension, at ~0% CPU,
# which then blocked interpreter shutdown from joining it). A SEPARATE lock
# from `spacy_ner._spacy_lock` on purpose: the two modules load INDEPENDENT
# `Language` objects for unrelated purposes, so serialising them against
# each other would only slow both down for no correctness reason -- each
# module's own cache needs its own lock around its own calls, not a shared
# global one (that would be solving a different, wider problem than the one
# actually observed).
_spacy_svo_lock = threading.Lock()


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


def _subject_span(token: Any, relative_deps: frozenset[str] = _RELATIVE_CLAUSE_DEPS) -> list[Any]:
    """The subject with its modifiers — "Andres xptoval Hernandez Varela",
    not "Andres" — WITHOUT any relative clause hanging off it.

    kg-readable review (2026-09-18): the old filter dropped only the
    relative clause's OWN head token (whose dep_ IS "relcl"/"acl") and left
    every word UNDER it in the span, since a clause's internal children
    ("la", "mina" inside "que compró la mina") carry their OWN dep labels
    (det/obj), not the clause head's. "Pedro, que compró la mina," survived
    as a subject nearly whole. Now the WHOLE subtree under a relative-clause
    child is excluded, not just its head.
    """
    excluded: set[int] = set()
    for child in token.children:
        if child.dep_ in relative_deps:
            excluded.update(t.i for t in child.subtree)
    return [tok for tok in token.subtree if tok.i not in excluded]


def _is_passive_clause(token: Any, lang_deps: _LangDeps, language: str) -> bool:
    """Whether ``token`` (a VERB/AUX clause head) is passive voice."""
    if lang_deps.passive_subject and any(
        c.dep_ in lang_deps.passive_subject for c in token.children
    ):
        return True
    if language == "es":
        from fichero_server.knowledge.svo_quality import fold

        has_ser_aux = any(
            c.dep_ in ("aux", "auxpass", "cop") and fold(c.text) in _SPANISH_SER_FORMS
            for c in token.children
        )
        is_participle = "Part" in (token.morph.get("VerbForm") or [])
        return has_ser_aux and is_participle
    return False


def _find_agent(token: Any, lang_deps: _LangDeps) -> list[Any] | None:
    """The STATED agent of a passive clause, or ``None`` when none is
    named — the review: "must NOT invent one where it is not". A patient-
    only passive ("The mine was sold.") returns ``None`` here and the
    caller drops the clause rather than guessing a subject."""
    if lang_deps.agent_dep:
        for child in token.children:
            if child.dep_ == lang_deps.agent_dep:
                pobj = next((g for g in child.children if g.dep_ == "pobj"), None)
                if pobj is not None:
                    return list(pobj.subtree)
        return None
    if lang_deps.agent_prepositions:
        from fichero_server.knowledge.svo_quality import fold

        for child in token.children:
            if child.dep_ not in ("obj", "obl"):
                continue
            marker = next((g for g in child.children if g.dep_ == "case"), None)
            if marker is not None and fold(marker.text) in lang_deps.agent_prepositions:
                return [t for t in child.subtree if t.i != marker.i]
    return None


def propose_triples(
    text: str, language: str = "es", *, max_triples: int = 60
) -> list[ProposedTriple]:
    """Every subject–verb–object the parser can find, as verbatim spans.

    No filtering happens here beyond dropping the structurally empty: judging
    a proposal is `svo_quality`'s job, and one module deciding both what is
    findable and what is acceptable would make the two impossible to measure
    apart.

    Passive voice (kg-readable review, 2026-09-18): yields the LOGICAL
    subject (subject=agent, object=patient) when the clause states its
    agent ("The mine was sold by Juan Asprilla" -> subject Juan Asprilla,
    object the mine); a passive with NO stated agent produces no triple at
    all, never a guessed one. Pro-drop / no-subject clauses are COUNTED
    (logged) and skipped, never silently dropped without a trace, and
    never bound to a PREVIOUS sentence's subject -- that binding, when it
    happens at all, is `_entity_writer`'s job downstream, restricted to
    the SAME sentence.
    """
    nlp = _pipeline(language)
    if nlp is None or not (text or "").strip():
        return []

    lang_deps = _LANG_DEPS.get(language, _LANG_DEPS["es"])
    # Serialise the actual parse call only (see `_spacy_svo_lock`'s
    # docstring) -- everything below reads the returned `Doc`, which is
    # this call's own, not shared with a concurrent caller.
    with _spacy_svo_lock:
        doc = nlp(text)
    out: list[ProposedTriple] = []
    skipped_no_subject = 0

    def _finish() -> list[ProposedTriple]:
        if skipped_no_subject:
            logger.info(
                "propose_triples: skipped %d clause(s) with no identifiable "
                "subject (pro-drop, or a passive with no stated agent) on "
                "this page (language=%r) -- kept OUT of the claim stream, "
                "never auto-bound to a prior subject (kg-readable review)",
                skipped_no_subject, language,
            )
        return out

    for token in doc:
        if token.pos_ not in ("VERB", "AUX"):
            continue

        # Auxiliaries belong to the verb phrase: "ha de dar", not "dar".
        verb_tokens = sorted(
            [token, *[c for c in token.children if c.dep_ in ("aux", "aux:pass", "cop")]],
            key=lambda t: t.i,
        )
        verb = _span_text(verb_tokens)

        is_passive = _is_passive_clause(token, lang_deps, language)
        if is_passive:
            agent_tokens = _find_agent(token, lang_deps)
            if agent_tokens is None:
                skipped_no_subject += 1
                continue
            patient = next(
                (
                    c for c in token.children
                    if c.dep_ in (lang_deps.subject | lang_deps.passive_subject)
                ),
                None,
            )
            subject_spans = [agent_tokens]
            objects_text = (
                [_span_text(_subject_span(patient, lang_deps.relative_clause))]
                if patient is not None and patient.pos_ != "PRON" else [""]
            )
        else:
            subjects = [c for c in token.children if c.dep_ in lang_deps.subject]
            if not subjects:
                skipped_no_subject += 1
                continue
            subject_spans = [_subject_span(s, lang_deps.relative_clause) for s in subjects]
            object_children = [c for c in token.children if c.dep_ in lang_deps.object]
            # English attaches a PP's true object TWO levels down (verb ->
            # prep -> pobj) -- "sold the mine TO Pedro Mosquera" -- unlike
            # Spanish, which attaches "a Pedro Mosquera" as a direct `obj`
            # child. Verified against the real parse, not assumed.
            # The PREPOSITION stays in the object text ("to Pedro Mosquera",
            # never a bare "Pedro Mosquera"): a triple's object slot has no
            # role, so a bare recipient reads as the thing sold -- "Juan
            # Asprilla sold Pedro Mosquera" is a false and, in this corpus,
            # a grave claim. Same shape Spanish ("a Pedro Mosquera") and the
            # English `dative` path already produce. A pronominal pobj ("to
            # him") names nobody and is skipped, like any pronoun object.
            for c in token.children:
                if c.dep_ == "prep" and any(
                    g.dep_ == "pobj" and g.pos_ != "PRON" for g in c.children
                ):
                    object_children.append(c)
            # A pronominal/clitic object names nobody -- the SAME principle
            # #4666 applies to a pronominal subject, now applied to the
            # other side of the triple ("la escritura | entregó | le" --
            # "le" is a clitic, not a referent). Filtered on the TOKEN's
            # own POS tag, not a lexical word list: a lexical check here
            # (`is_pronoun_subject` on the rendered text) collided with
            # real nouns that happen to share a pronoun's spelling --
            # English "mine" the excavation vs. "mine" the possessive
            # pronoun dropped "the mine" as an object on the review's own
            # sample sentence. spaCy's POS tag tells the two apart; a
            # lexical list cannot.
            object_children = [c for c in object_children if c.pos_ != "PRON"]
            objects_text = (
                [_span_text(list(o.subtree)) for o in object_children]
                if object_children else [""]
            )

        for subject_tokens in subject_spans:
            subject_text = _span_text(subject_tokens)
            if not subject_text:
                continue
            for object_text in objects_text:
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
                        meta={"passive": is_passive},
                    )
                )
                if len(out) >= max_triples:
                    return _finish()
    return _finish()


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


def dedupe_proposals(
    proposals: list[ProposedTriple],
) -> tuple[list[ProposedTriple], list[tuple[ProposedTriple, str]]]:
    """Fold exact and near-duplicate triples down to one, first-seen winning.

    This is where the parser's habit of emitting one row per object child of a
    verb — an ``obj`` AND an ``obl`` become two rows that differ only by a
    trailing phrase — is turned back into the single statement it always was.
    Identity is `svo_quality.statement_key`/`near_duplicate`, the SAME standard
    the LLM tier's cleanup answers to, so "too much repetition" is measured one
    way across both extractors. Returns ``(unique, [(dropped, reason)])``.
    """
    from fichero_server.knowledge.svo_quality import near_duplicate, statement_key

    unique: list[ProposedTriple] = []
    dropped: list[tuple[ProposedTriple, str]] = []
    keys: list[tuple[str, str]] = []
    for proposal in proposals:
        key = statement_key(proposal.subject, proposal.verb, proposal.object)
        if any(near_duplicate(key, seen) for seen in keys):
            dropped.append((proposal, "duplicate of an earlier statement"))
            continue
        keys.append(key)
        unique.append(proposal)
    return unique, dropped


def filter_proposals(
    proposals: list[ProposedTriple], text: str
) -> tuple[list[ProposedTriple], list[tuple[ProposedTriple, str]]]:
    """Apply the SHARED quality gates and say what each rejection was for.

    The same `svo_quality` rules the LLM tier answers to, so the accuracy
    table compares two extractors under one standard rather than two. After the
    per-row gates, identical and near-identical survivors are folded to one so
    the tier does not hand the writer the repetition beta testers flagged.
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
    kept, duplicates = dedupe_proposals(kept)
    rejected.extend(duplicates)
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
    with _spacy_svo_lock:
        parsed = nlp(text)
    for token in parsed:
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
