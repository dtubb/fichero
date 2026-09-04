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


def claim_rejection(subject: str | None, verb: str | None, obj: str | None) -> str | None:
    """Why this SVO triple must not be written, or ``None`` when it may be.

    The string is a reason a person can read in a log, not an error code.
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
    return None
