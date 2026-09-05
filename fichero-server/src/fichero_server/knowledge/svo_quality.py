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
    verb_text = (verb or "").strip()
    obj_text = (obj or "").strip()
    if not verb_text and not obj_text:
        return "empty predicate — no verb and no object"
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
