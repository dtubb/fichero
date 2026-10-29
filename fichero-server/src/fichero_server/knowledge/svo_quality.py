"""What makes an SVO row a statement rather than a fragment (#4666).

Daniel, 2026-09-04, on a Caciques Indios run: *"we're lazily doing `they` — if
we can't do it properly, e.g. with the right subject…"*, and, of a row reading
``Andres otorgamos que damos mostrando tenemos cargo``: *"these seem a bit
weak."*

Two distinct defects hide behind that. Both are checkable without a model, and
both are cheaper to reject at the boundary than to explain to a historian
later.

**A pronoun is not a subject.** ``they`` / ``ellos`` / ``nosotros`` name nobody.
A KG row whose subject is a pronoun asserts nothing that can be joined,
counted, or followed, and it pollutes entity lists with a row every document
matches. Stage-1 NER emits them when a page is hard to read; the write path
used to resolve one against a running antecedent and, failing that, create an
entity called "they".

**A clause dump is not a predicate.** ``otorgamos que damos mostrando tenemos``
is four verbs of a 17th-century notarial formula concatenated into one field.
The information is real, but it is not a predicate, and the row it composes is
not a sentence. A word cap turns the overflow back into object text — where a
run-on at least reads as one — instead of silently claiming it is the verb.

Pure functions: no DB, no I/O, no model. The callers decide what to do with a
verdict; this module only names it.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

# Pronouns and bare determiners that are never a legitimate KG subject, across
# the languages this corpus actually holds. Matched case- and accent-folded, so
# "Él" and "el" both land.
PRONOUN_SUBJECTS = frozenset(
    {
        # English
        "i", "you", "he", "she", "it", "we", "they",
        "me", "him", "her", "us", "them",
        "my", "your", "his", "hers", "its", "our", "their",
        "mine", "yours", "ours", "theirs",
        "this", "that", "these", "those", "who", "whom", "which", "someone",
        "anyone", "everyone", "no one", "nobody", "somebody", "one",
        # Spanish (accents folded before the lookup)
        "yo", "tu", "el", "ella", "usted", "nosotros", "nosotras",
        "vosotros", "vosotras", "ellos", "ellas", "ustedes",
        "me", "te", "se", "nos", "os", "le", "les", "lo", "la", "los", "las",
        "mi", "su", "sus", "nuestro", "nuestra", "nuestros", "nuestras",
        "este", "esta", "esto", "estos", "estas",
        "ese", "esa", "eso", "esos", "esas",
        "aquel", "aquella", "aquello", "aquellos", "aquellas",
        "quien", "quienes", "alguien", "nadie", "uno", "una",
        # Relative pronouns (kg-readable review, 2026-09-18): "que" is the
        # single most common Spanish relative marker ("Pedro, que compró la
        # mina, ...") and was missing entirely -- "quien"/"quienes" were
        # already here, but a relative-clause subject surviving as "que"
        # is exactly the #4671 defect this gate exists to catch. "cual"/
        # "cuales" ("el cual" etc.) and "cuyo" family ("whose") join it.
        "que", "cual", "cuales", "cuyo", "cuya", "cuyos", "cuyas",
        # Portuguese / French neighbours that show up in mixed corpora
        "eles", "elas", "nos", "voce", "voces",
        "il", "elle", "ils", "elles", "nous", "vous", "je",
    }
)

# A verb phrase longer than this is a clause, not a predicate. Four words holds
# every real periphrastic form we see ("had been granted", "se ha de dar")
# while rejecting the notarial run-ons.
MAX_VERB_WORDS = 4
# An object longer than this is a paragraph the model declined to segment.
MAX_OBJECT_WORDS = 25

# How much of a span must actually appear in the source before we will call it
# a reading of that source. Two thirds, which makes a one-token span
# all-or-nothing and lets a three-token span carry one inflected form.
MIN_GROUNDED_FRACTION = 2 / 3

# Function words carry no evidence, so they neither ground a span nor condemn
# it. Spanish first, since that is the corpus that exposed this.
_GROUNDING_STOPWORDS = frozenset(
    {
        "de", "del", "la", "el", "los", "las", "un", "una", "unos", "unas",
        "y", "e", "o", "u", "que", "en", "por", "para", "con", "sin", "al",
        "se", "su", "sus", "lo", "es", "son", "fue", "era", "ser", "como",
        "the", "a", "an", "of", "to", "in", "on", "for", "with", "and", "or",
        "is", "was", "as", "at", "by", "from", "that", "which",
    }
)


def fold(text: str) -> str:
    """Case- and accent-folded form used for every comparison here."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.casefold().split())


def _has_letter(text: str) -> bool:
    """Whether ``text`` contains at least one alphabetic character.

    A predicate of pure punctuation or digits is not a word; this is the
    cheapest way to say so, and it treats accented letters as letters.
    """
    return any(ch.isalpha() for ch in text or "")


# ---------------------------------------------------------------------------
# Names that are not entities, and dates that are not subjects
# ---------------------------------------------------------------------------
#
# A month, a bare "De Diciembre" or a role word ("Agente") is not somebody or
# somewhere, whatever type a model gave it; a date fused onto a name ("Juzgado
# de X julio veinticinco") is a name plus a date. All checkable without a model.

_MONTHS = frozenset(
    "enero febrero marzo abril mayo junio julio agosto septiembre setiembre octubre noviembre diciembre "
    "january february march april may june july august september october november december "
    "janeiro fevereiro marco maio junho julho setembro outubro novembro dezembro".split()
)
_UNITS = frozenset(
    "uno una un dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince diecis"
    "eis diecisiete dieciocho diecinueve veinte treinta y primero primer mil novecientos".split()
)
_DATE_FILLER = frozenset("de del el la los dia dias ano anos a".split())
#: Titles of people: alone they name nobody, and in front of a name they make a person, not an organisation.
_ROLE_WORDS = frozenset(
    "agente perito avaluador avaluadores juez alcalde secretario escribano notario testigo apoderado albacea "
    "curador tutor comisionado visitador recaudador administrador alguacil fiscal procurador sindico regidor "
    "corregidor".split()
)
#: Kinds of body: alone they name no particular one.
_GENERIC_BODY_WORDS = frozenset("agencia juzgado notaria oficina alcaldia tribunal despacho".split())
_ISO_DATE = re.compile(r"^\d{1,4}([-/.]\d{1,2}){0,2}$")


def _is_number(word: str) -> bool:
    return bool(_ISO_DATE.match(word)) or word in _UNITS or word.startswith("veinti") or word[:1].isdigit()


def is_date_only(text: str | None) -> bool:
    """Whether ``text`` is only a date: months, numbers, number words and "de" ("De Diciembre", "1918-06-06").

    A lone month ("Mayo", "Abril") or a lone number word ("Cinco") is a name as often as a date, so it counts
    only next to a digit ("7 de agosto", "1918") or as a "de <month>" fragment. "Primero de Mayo" stays a name."""
    words = fold(text or "").replace(".º", "").replace("º", "").split()
    if not words or not any(w in _MONTHS or _is_number(w) for w in words):
        return False
    if not all(w in _MONTHS or w in _DATE_FILLER or _is_number(w) for w in words):
        return False
    if any(w[:1].isdigit() for w in words):
        return True
    return len(words) > 1 and words[0] in ("de", "del") and any(w in _MONTHS for w in words)


#: Words that start a place or body name; one left alone after a trim is no complete name.
_GENERIC_PLACE_WORDS = frozenset("calle plaza puerto colonia villa barrio avenida pueblo ciudad rio hacienda cerro paseo camino".split())


def _is_date_tail(words: list[str]) -> bool:
    """``[d] [de] month [de] [year]`` with at least one number: "7 de agosto", "de agosto de 1910", "julio 25"."""
    i = 0
    if i < len(words) and _is_number(words[i]):
        i += 1
    if i < len(words) and words[i] in ("de", "del"):
        i += 1
    if i >= len(words) or words[i] not in _MONTHS:
        return False
    i += 1
    if i < len(words) and words[i] in ("de", "del"):
        i += 1
    rest = words[i:]
    return all(_is_number(w) for w in rest) and (bool(rest) or _is_number(words[0]))


def _complete_name(words: list[str]) -> bool:
    """Whether ``words`` (folded) stand as a name on their own: not ending on a number, a filler or a bare
    generic word ("Calle", "Puerto"), and not made only of those."""
    if not words or words[-1] in _DATE_FILLER or words[-1] in _GENERIC_PLACE_WORDS or _is_number(words[-1]):
        return False
    return any(w not in _GENERIC_PLACE_WORDS and w not in _GENERIC_BODY_WORDS and w not in _DATE_FILLER for w in words)


def usable_entity_name(name: str, entity_type: Any) -> str | None:
    """The name to save as an entity of ``entity_type``, or ``None`` when it names nothing.

    Refuses a date (a lone month only for a non-person: "Mayo" is a surname), a bare role or kind-of-body word,
    and an organisation that is a person's title and name. A date tail ("de agosto de 1910", "julio 25") is
    trimmed off only from a complete name: "Calle 7 de Agosto" and "Puerto Mayo 1910" stay whole. A person is
    never refused for a month in the name ("Julio Cesar", "Juan Mayo"); a stray month beats a lost person."""
    kind = getattr(entity_type, "value", entity_type)
    text = (name or "").strip()
    words = text.split()
    folded = fold(text).split()
    if not folded or is_date_only(text):
        return None
    if kind != "person" and len(folded) == 1 and folded[0] in _MONTHS:
        return None
    if all(w in _ROLE_WORDS or w in _GENERIC_BODY_WORDS or w in _DATE_FILLER or w in ("y", "e") for w in folded):
        return None
    if kind == "organization" and len(folded) > 1 and folded[0] in _ROLE_WORDS:
        return None
    if kind in {"location", "organization"} and len(folded) == len(words):
        for start in range(1, len(words)):
            if _is_date_tail(folded[start:]) and _complete_name(folded[:start]):
                return " ".join(words[:start])
    return text or None


_FUNCTION_WORDS = frozenset(
    "a al con de del e el en la las lo los me mi no o por que se si su u un una y ya".split()
)


class LineJoin:
    """A page's lines joined for reading (``text``) and the page text they came from (``original``).
    ``spans_in_joined`` moves spans measured on ``original`` (a tied line's) onto ``text``."""

    def __init__(self, text: str, original: str, start: list[int], end: list[int]) -> None:
        self.text, self.original, self._start, self._end = text, original, start, end

    def spans_in_joined(self, spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
        return [(self._start[a], self._end[b]) for a, b in spans]


def _is_mid_word_break(before: str, after: str) -> bool:
    """A hyphen at a line end is a word cut in two when both sides are lowercase letters and the pieces are not
    function words: "Ene-"+"ro" is one word, "señor-"+"que" is two (the hyphen is dropped, a space kept)."""
    head = re.search(r"([^\W\d_]+)-$", before)
    tail = re.match(r"[^\W\d_]+", after)
    if not head or not tail or not before[-2].islower() or not after[0].islower():
        return False
    piece, rest = head.group(1).casefold(), tail.group(0).casefold()
    return piece not in _FUNCTION_WORDS and rest not in _FUNCTION_WORDS and len(piece) + len(rest) <= 25


def join_page(text: str) -> LineJoin:
    """A page's lines as running text, so a statement is read across a line break and not cut at it. A hyphen
    break mid-word is rejoined ("Ene-\nro" → "Enero"), a blank line stays a paragraph break ("\n\n"), the
    rest joins with a space. Characters inside a line are copied as they are, so a span within one line keeps
    its offsets; ``LineJoin`` maps the line ends back to ``text``."""
    text = text or ""
    out: list[str] = []
    start = [0] * (len(text) + 1)  # where the text at i begins in the joined text
    end = [0] * (len(text) + 1)  # where the text before i ends in it
    pending = ""
    hyphen_at = -1
    pos = 0
    previous = ""
    for raw in text.split("\n"):
        line = raw.strip()
        lead = len(raw) - len(raw.lstrip())
        if not line:
            if out:
                pending = "\n\n"
            for j in range(pos, pos + len(raw) + 1):
                start[min(j, len(text))] = end[min(j, len(text))] = len(out)
            pos += len(raw) + 1
            continue
        if out:
            if pending:
                out.extend(pending)
            elif previous.endswith("-") and _is_mid_word_break(previous, line):
                out.pop()  # the hyphen
                end[hyphen_at + 1] = len(out)
            elif previous.endswith("-") and previous[-2:-1].islower() and line[0].islower():
                out.pop()  # a hyphen before a separate word ("señor- que"): two words, never one
                end[hyphen_at + 1] = len(out)
                out.append(" ")
            elif previous.endswith("-") and line[0].isupper():
                pass  # "Pérez-" / "Gómez": a compound name keeps its hyphen
            else:
                out.append(" ")
        pending = ""
        for j in range(pos, pos + lead + 1):
            start[j] = end[j] = len(out)
        for k, ch in enumerate(line):
            j = pos + lead + k
            start[j] = len(out)
            out.append(ch)
            end[j + 1] = len(out)
        hyphen_at = pos + lead + len(line) - 1
        for j in range(hyphen_at + 1, min(pos + len(raw) + 1, len(text) + 1)):
            start[j] = end[j] = len(out)
        previous = line
        pos += len(raw) + 1
    return LineJoin("".join(out), text, start, end)


def join_lines(text: str) -> str:
    """``join_page``'s running text alone."""
    return join_page(text).text


# ---------------------------------------------------------------------------
# Statement identity — "too much repetition" (beta feedback, 2026-09)
# ---------------------------------------------------------------------------
#
# Two rows are the same statement when they name the same subject and say the
# same thing about it, whatever incidental punctuation or article separates
# them. The parser is the worst offender: it emits one row per object child of
# a verb, so a verb with both an ``obj`` and an ``obl`` becomes two rows that
# differ only by a trailing phrase. Folding those back to one is what the
# tester meant by "better quality statements", and it is checkable without a
# model.
#
# Deliberately conservative on the subject: two statements about DIFFERENT
# people are never duplicates, so the subject is compared whole and must match
# exactly (folded). Only the predicate side is fuzzed.

#: A predicate this similar to another under the same subject is the same
#: statement written twice. Matches the display-tier threshold's intent
#: (``svo_cleanup``) while staying independent of it.
NEAR_DUPLICATE_RATIO = 0.90


def _normalized_words(text: str) -> list[str]:
    """Folded, punctuation-free tokens — the unit statement identity compares."""
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in fold(text))
    return cleaned.split()


#: Determiners, articles and legalese filler a near-duplicate may differ by
#: without being a different statement: "signed the deed" and "signed the said
#: deed" are one fact — "said"/"dicho" is notarial "the aforementioned".
#: Deliberately short: a content word wrongly listed here would merge
#: statements that differ, so nouns, verbs, names, prepositions and — above all
#: — numbers stay off the list. A different object head or a different
#: date/number therefore always survives as its own statement.
_FILLER_WORDS = frozenset(
    {
        "the", "a", "an", "said", "same", "aforesaid", "aforementioned",
        "el", "la", "los", "las", "un", "una", "unos", "unas",
        # Spanish prepositions + preposition/article contractions — function
        # words, not content, on a Spanish corpus (Daniel's Istmina archive):
        # "poder a Juan" / "poder al dicho Juan" are one statement. A different
        # NAME or NUMBER still survives because those are content tokens that
        # stay on the list's far side (guarded by test).
        "de", "del", "al",
        "dicho", "dicha", "dichos", "dichas",
        "mismo", "misma", "mismos", "mismas", "mesmo", "mesma",
    }
)


def _content_sequence(predicate: str) -> list[str]:
    """``predicate``'s tokens with filler removed, order kept.

    Order is kept on purpose: "Pedro met Ana" and "Ana met Pedro" have the same
    words and are not the same statement.
    """
    return [w for w in _normalized_words(predicate) if w not in _FILLER_WORDS]


def same_statement(pred_a: str, pred_b: str, *, ratio: float = NEAR_DUPLICATE_RATIO) -> bool:
    """Whether two predicate strings say the same thing (one shared standard).

    Used by the spaCy tier, the display cleanup (``svo_cleanup``) and the batch
    planner (``dedupe``) so "too much repetition" is judged one way everywhere.
    Conservative, in three widening steps:

    1. identical once folded and de-punctuated;
    2. identical CONTENT tokens in order — the same words bar determiners,
       articles and notarial "said"/"dicho"; this is what collapses "signed the
       deed" and "signed the said deed";
    3. at least ``ratio`` similar AND the same token set — word-order and
       inflection variants, the pre-existing rule these callers already trusted.

    Numbers are never filler, so "gave 3 pesos" / "gave 5 pesos" and "the deed"
    / "the deed in 1830" are different statements at every step.
    """
    a = _normalized_words(pred_a)
    b = _normalized_words(pred_b)
    if a == b:
        return True
    content_a = _content_sequence(pred_a)
    if content_a and content_a == _content_sequence(pred_b):
        return True
    return (
        SequenceMatcher(None, " ".join(a), " ".join(b)).ratio() >= ratio
        and set(a) == set(b)
    )


def statement_key(
    subject: str | None, verb: str | None, obj: str | None
) -> tuple[str, str]:
    """A ``(subject, predicate)`` identity for recognising the same triple twice.

    Folded and stripped of punctuation so surface noise does not hide a
    duplicate. A leading copy of the subject inside the object is dropped, so
    "Andres | otorgó Andres poder" and "Andres | otorgó poder" share a key.
    """
    subj_words = _normalized_words(subject or "")
    obj_words = _normalized_words(obj or "")
    if subj_words and obj_words[: len(subj_words)] == subj_words:
        obj_words = obj_words[len(subj_words) :]
    predicate = " ".join(_normalized_words(verb or "") + obj_words)
    return " ".join(subj_words), predicate


def near_duplicate(
    a: tuple[str, str], b: tuple[str, str], *, ratio: float = NEAR_DUPLICATE_RATIO
) -> bool:
    """Whether two :func:`statement_key` tuples name the same statement.

    Different subjects are never duplicates. Under one subject, a predicate
    that contains the other (the parser's obj/obl double-emit) or is textually
    at least ``ratio`` similar counts as the same statement.
    """
    subj_a, pred_a = a
    subj_b, pred_b = b
    if subj_a != subj_b:
        return False
    if not pred_a or not pred_b:
        return pred_a == pred_b
    # The parser's obj/obl double-emit leaves one predicate a prefix-extension
    # of the other ("otorgó poder" ⊂ "otorgó poder cumplido a Juan"); that is a
    # duplicate here even though the two say different amounts.
    if pred_a in pred_b or pred_b in pred_a:
        return True
    return same_statement(pred_a, pred_b, ratio=ratio)


def is_pronoun_subject(subject: str | None) -> bool:
    """Whether ``subject`` names nobody.

    True for a bare pronoun or determiner, in any of the corpus languages, with
    or without a leading article. False for anything with more substance —
    including "el cacique", which is a description and at least restricts.
    """
    folded = fold(subject or "")
    if not folded:
        return False
    folded = re.sub(r"^(the|el|la|los|las|un|una|a|an)\s+", "", folded)
    return folded in PRONOUN_SUBJECTS


def trim_predicate(verb: str, obj: str) -> tuple[str, str]:
    """Cap the verb at :data:`MAX_VERB_WORDS`, moving the overflow into ``obj``.

    Nothing is discarded: a run-on verb becomes a short verb plus a longer
    object, which is the honest reading of what the model produced. Returns the
    pair unchanged when the verb is already a predicate.
    """
    verb_words = (verb or "").split()
    if len(verb_words) <= MAX_VERB_WORDS:
        return (verb or "").strip(), (obj or "").strip()
    head = " ".join(verb_words[:MAX_VERB_WORDS])
    overflow = " ".join(verb_words[MAX_VERB_WORDS:])
    tail = f"{overflow} {obj}".strip() if obj else overflow
    return head.strip(), tail.strip()


def claim_rejection(
    subject: str | None,
    verb: str | None,
    obj: str | None,
    source_text: str | None = None,
) -> str | None:
    """Why this SVO triple must not be written, or ``None`` when it may be.

    The string is a reason a person can read in a log, not an error code.
    ``source_text`` is the page the claim was read off; when given, the verb
    and object must be found in it.
    """
    if is_pronoun_subject(subject):
        return f"pronoun subject {subject!r} — names no entity"
    if is_date_only(subject):
        return f"subject {subject!r} is a date — a date is when, not who"
    verb_text = (verb or "").strip()
    obj_text = (obj or "").strip()
    if not verb_text and not obj_text:
        return "empty predicate — no verb and no object"
    # A verb made only of punctuation or digits — a stray "]" or a page number
    # like "00533" welded into the verb field — is not a predicate. It slips the
    # grounding rule (a bracket has no content token to look for) and the
    # first-person rule (a number carries no ending), so it must be named here.
    if verb_text and not _has_letter(verb_text):
        return f"predicate {verb_text!r} is not a word — no letters, not a verb"
    # "Andres … Andres": an object that only restates the subject asserts
    # nothing that can be joined or read. Folded so "Mérida"/"merida" match.
    if obj_text and subject and fold(obj_text) == fold(subject):
        return f"object {obj_text!r} only restates the subject — not a statement"
    if len(obj_text.split()) > MAX_OBJECT_WORDS:
        return (
            f"object is {len(obj_text.split())} words — a clause dump, "
            f"not an object (cap {MAX_OBJECT_WORDS})"
        )
    if ungrounded_span(obj_text, source_text):
        return f"object {obj_text!r} is not on the page — a paraphrase, not a reading"
    if ungrounded_span(verb_text, source_text):
        return f"verb {verb_text!r} is not on the page — a paraphrase, not a reading"
    return None


def _content_tokens(span: str) -> list[str]:
    """The tokens of ``span`` that could carry evidence, folded for comparison."""
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in fold(span))
    return [
        token
        for token in cleaned.split()
        if len(token) > 2 and token not in _GROUNDING_STOPWORDS
    ]


def grounded_fraction(span: str, source_text: str | None) -> float:
    """How much of ``span`` is actually present in ``source_text``.

    ``1.0`` when there is nothing to check — no source text to compare
    against, or a span with no content tokens. Fail-open is deliberate: a
    check that cannot run must not condemn.
    """
    if not source_text or not span:
        return 1.0
    tokens = _content_tokens(span)
    if not tokens:
        return 1.0
    haystack = fold(source_text)
    return sum(1 for token in tokens if token in haystack) / len(tokens)


def ungrounded_span(span: str, source_text: str | None) -> bool:
    """Whether ``span`` reads as a paraphrase rather than as the source's words.

    Daniel, 2026-09-04: the SVO output "seemed to do weird bad Spanish". A
    model asked for facts about a 17th-century notarial page, in Spanish,
    writes modern Spanish it composed itself — grammatical, plausible, and not
    what the manuscript says. The words are the evidence; a claim whose verb
    and object cannot be found on the page is the model's reading of the page,
    not the page.

    This also does the work three other rules were reaching for: a span copied
    from the source cannot be a clause dump of invented text, and a span that
    IS on the page can be highlighted there when the historian clicks through.
    """
    return grounded_fraction(span, source_text) < MIN_GROUNDED_FRACTION


# ---------------------------------------------------------------------------
# First-person detection without a tagger (#4671)
# ---------------------------------------------------------------------------
#
# The grammar gate convicts two things: a predicate that is not a verb, and a
# first-person verb sitting under a bystander's name. The first needs a
# part-of-speech tagger. The second does not — Spanish marks person in the
# ending, and that is the half that caught 8 of the 16 bad rows in the
# Caciques library.
#
# Measured 2026-09-04 against Apple's on-device NaturalLanguage, the
# zero-download alternative: NLTagger exposes Language, Script, TokenType,
# NameType, LexicalClass and Lemma for Spanish — and NO MORPHOLOGY. It cannot
# answer "is this verb first person" at all, and it mis-tagged one of the
# not-a-verb cases ("oy" as a Verb). So Apple's tagger cannot replace spaCy
# for this gate; it can only do part of it.
#
# Which leaves the shipped app, where spaCy is not installed and the gate
# therefore convicts nothing. These endings are the half that can be had for
# nothing, in any build, so the shipped app is not left with no gate at all.
# Deliberately narrow: a suffix table is not morphology, and it says so by
# refusing anything it is not sure of.

#: Spanish first-person-plural endings. Regular across all three conjugations,
#: which is what makes the rule safe: "otorgamos", "dezimos", "tenemos".
_ES_FIRST_PLURAL_SUFFIXES = ("amos", "emos", "imos", "íamos", "aríamos", "eríamos")

#: The irregulars that carry no such ending, and the singular forms worth
#: catching. Short on purpose — a long list is a dictionary badly reimplemented.
_ES_FIRST_PERSON_IRREGULARS = frozenset(
    {"somos", "estamos", "vamos", "hemos", "damos", "soy", "estoy", "voy", "he"}
)

#: English is not inflected for person in a way a suffix can see ("we sign"
#: and "they sign" are identical), so this rule does not apply to it. A gate
#: that cannot see must abstain rather than guess.
_PERSON_LANGUAGES = frozenset({"es"})


def is_first_person_verb(word: str, language: str = "es") -> bool | None:
    """Whether ``word`` is a first-person verb form.

    ``True`` / ``False`` when the ending settles it; ``None`` when this rule
    has nothing to say — a language it does not cover, or a word too short to
    carry a distinguishing ending. ``None`` is not ``False``: the caller must
    be able to tell "not first person" from "I cannot tell".
    """
    if language not in _PERSON_LANGUAGES:
        return None
    folded = fold(word or "")
    if not folded:
        return None
    if folded in _ES_FIRST_PERSON_IRREGULARS:
        return True
    if len(folded) < 5:
        return None
    for suffix in _ES_FIRST_PLURAL_SUFFIXES:
        if folded.endswith(fold(suffix)):
            return True
    # A word long enough to have carried one of those endings and does not:
    # that is evidence, not silence.
    return False
