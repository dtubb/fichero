"""Language policy: one resolver every AI surface consults (#2092).

Before this module the picture was: a global setting (``default_primary_language``)
that only three of roughly nine relevant tools consulted, transcription hardcoded
to ``en-US`` regardless of the setting, and SVO/entity extraction passing the
literal string ``"auto"`` into the prompt. On a Spanish-language colonial archive
that does not degrade gracefully — it produces fluent, plausible, wrong output,
which is the failure mode this project exists to avoid.

Three modes, exactly as #2092 asks, encoded in the SETTING THAT ALREADY EXISTS so
there is no second source of truth and no app-db migration:

===========================  ==============================================
``default_primary_language``  meaning
===========================  ==============================================
``""`` / unset                UNSET — legacy behaviour, detect from the text
``"Spanish"``                 ONE — force it everywhere
``"Spanish, English"``        MANY — the corpus is mixed; pick per document
                              from this set, and refuse to guess outside it
``"document"``                DOCUMENT — carry the document's own language
===========================  ==============================================

Existing installations hold either ``""`` or a single language name, and both
keep their exact prior meaning, so nothing changes under a user who has not
opted in.

UNKNOWN IS A VALUE, NOT A NULL
------------------------------
:class:`LanguageResolution` can come back with ``status == UNKNOWN`` and
``language is None``. That is a real answer meaning "we determined that we do
not know", and callers must render it rather than substitute English. It is
kept distinct from ``NEVER_DETERMINED`` (nothing has ever looked), because those
call for opposite responses from a user: one is "run detection", the other is
"this document needs a human". Silently resolving either to English or to the
global default is the specific bug this module exists to prevent
(cf. #4467's empty-resolution refusal, and the prefer-raise-over-silent-
substitution rule).
"""

from __future__ import annotations

import re

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Literal

# Resolution statuses. RESOLVED carries a concrete language; UNKNOWN means the
# policy ran and produced no trustworthy answer.
RESOLVED = "resolved"
UNKNOWN = "unknown"

# ``language_meta["status"]`` values recorded on a Document. Mirrors the
# three-way honesty of ``date_meta`` (dated / undated_explicit / none_found):
# a language that is recorded, a document that was examined and could not be
# told, and the absence of ``language_meta`` entirely meaning nothing has run.
STATUS_KNOWN = "known"
STATUS_UNKNOWN = "unknown"
NEVER_DETERMINED = "never_determined"

# ``language_meta["source"]`` values. ``user`` is load-bearing: it marks a human
# correction, which is a persistent curation rule and must survive re-extraction
# (same rule as ``date_meta["source"] == "user"`` in tools/date_extract.py).
SOURCE_USER = "user"
SOURCE_DETECTED = "detected"
SOURCE_METADATA = "metadata"

#: Computed from the resolved script rather than stated anywhere
#: (`source.dir.per-segment`, and the encoding read of `three-facts`). It belongs
#: on the SOURCE axis and was briefly, wrongly, a fifth `level`: a derivation is
#: not a rung, it is a way of determining, and a `level` field that sometimes
#: holds a non-rung cannot be reasoned about — the same conflation refused when
#: `source` was proposed as the home for the rung. A derived answer's `level` is
#: `None`, which is the accurate reading of the rule that `None` means NOT
#: STATED: no rung stated it, because nobody did.
SOURCE_DERIVED_FROM_SCRIPT = "derived-from-script"

# ``language_meta["level"]`` values — WHICH LEVEL of the cascade supplied the
# value (source-model slice 9, #4938, `source.lang.says-where-from`).
#
# A SECOND AXIS from ``source`` above, deliberately, and they must not be
# merged: ``source`` says HOW a value was determined (a person typed it, a
# detector guessed it, a file's metadata carried it) and ``level`` says WHERE it
# came from in the cascade. "A person set it on the project" and "a person set it
# on this reading" are the same source and different levels, and
# `source.lang.says-where-from` is about the second — a shown value has to say
# which level it came from, so that overriding it at a lower level is an
# informed act rather than a guess.
LEVEL_PROJECT = "project"
LEVEL_DOCUMENT = "document"
LEVEL_SEGMENT = "segment"
LEVEL_READING = "reading"

Mode = Literal["unset", "one", "many", "document"]

# The sentinel a user types into the primary-language setting to mean
# "each document in its own language".
_DOCUMENT_MODE_TOKENS = {"document", "document language", "language of document",
                         "language of the document", "per-document", "per document"}


@dataclass(frozen=True)
class LanguagePolicy:
    """A parsed language policy. ``languages`` is empty for unset/document."""

    mode: Mode = "unset"
    languages: tuple[str, ...] = ()

    @property
    def is_unset(self) -> bool:
        return self.mode == "unset"

    def permits(self, language: str | None) -> bool:
        """True when ``language`` is allowed by this policy.

        Unset and document modes permit anything — they impose no set. A
        ``many`` policy permits only its listed languages, which is what makes
        "detected French in a Spanish/English corpus" resolve to UNKNOWN
        instead of silently passing French through.
        """
        if not language:
            return False
        if self.mode in ("unset", "document"):
            return True
        return _norm(language) in {_norm(item) for item in self.languages}


@dataclass(frozen=True)
class LanguageResolution:
    """The outcome of resolving a language for one document.

    ``basis`` is a short human-readable phrase naming what decided it, so the
    answer can be shown to a user rather than silently applied.

    ONE TYPE FOR EVERY LANGUAGE-LIKE FACT (source-model slice 9, #4938): this
    also carries a resolved SCRIPT, DIRECTION and ENCODING. The four fields
    answer the same four questions for each of them — what the value is, whether
    it is known, how it was determined, and which rung it came from — so three
    dataclasses with identical fields would be three copies of one idea and three
    sets of readers to keep in step.

    The cost is that ``language`` holds a script at a `resolve_script` call site,
    which reads oddly and is said here rather than softened with a second name
    for the same type (an alias was tried and dropped: it renamed the type and
    not the field, so the awkwardness survived at the exact call site it was
    meant to help, while two names for one type made either one ungreppable on
    its own). If the field name is what grates, renaming it is a deliberate
    change to a type load-bearing at four levels, not a slice-9 edit.
    """

    language: str | None
    status: str
    source: str
    basis: str
    #: WHICH RUNG of the cascade the answer came from — the same
    #: `LEVEL_PROJECT`/`LEVEL_DOCUMENT`/`LEVEL_SEGMENT`/`LEVEL_READING`
    #: vocabulary `language_meta["level"]` uses, never a second spelling
    #: (source-model slice 9, #4938, `source.lang.says-where-from`).
    #:
    #: It is the rung the answer CAME FROM, not the rung that asked: a caller
    #: resolving for a segment that states nothing gets `LEVEL_DOCUMENT` back,
    #: because that is where the value was found. That is the whole purpose of
    #: the field — a caller already knows what it asked about.
    #:
    #: `None` means NOT STATED, never "unknown". `STATUS_UNKNOWN` already
    #: carries unknown and the two must not begin to overlap: a resolution can
    #: be unknown and still say which rung established that.
    level: str | None = None

    @property
    def is_known(self) -> bool:
        return self.status == RESOLVED and bool(self.language)


class UnknownDocumentLanguage(RuntimeError):
    """Raised by :func:`require_language` when no language could be resolved.

    For callers that must not guess. Prompt-building callers instead read
    ``resolution.is_known`` and omit the language claim from the prompt, which
    tells the model to work in the language of the source rather than asserting
    a language nobody established.
    """


def _norm(value: str) -> str:
    return value.strip().casefold()


def parse_policy(raw: str | None) -> LanguagePolicy:
    """Parse the ``default_primary_language`` setting into a typed policy.

    Accepts the two historical shapes (empty, one language name) unchanged, plus
    a comma-separated list and the ``document`` sentinel.
    """
    text = (raw or "").strip()
    if not text:
        return LanguagePolicy(mode="unset")
    if _norm(text) in _DOCUMENT_MODE_TOKENS:
        return LanguagePolicy(mode="document")

    names = tuple(part.strip() for part in text.split(",") if part.strip())
    if not names:
        return LanguagePolicy(mode="unset")
    if len(names) == 1:
        return LanguagePolicy(mode="one", languages=names)
    return LanguagePolicy(mode="many", languages=names)


def configured_policy() -> LanguagePolicy:
    """The library's current policy, read from the app database.

    Imported lazily for the same reason ``lang_detect.configured_primary_language``
    is: ``fichero_server.db.app`` pulls in the app database and this module is
    imported from tool modules that must stay cheap.
    """
    from fichero_server.llm.lang_detect import configured_primary_language

    return parse_policy(configured_primary_language())


# ---------------------------------------------------------------------------
# Reading and writing a document's own language
# ---------------------------------------------------------------------------


def _doc_get(document: Any, key: str) -> Any:
    """Read ``key`` off a Document model or the plain dict form tools pass around."""
    if document is None:
        return None
    if isinstance(document, dict):
        return document.get(key)
    return getattr(document, key, None)


def read_document_language(document: Any) -> LanguageResolution:
    """What the document itself says its language is.

    Three distinguishable outcomes, never collapsed:

    - a recorded language (``status`` RESOLVED, source ``user`` or ``detected``)
    - examined and undeterminable (``status`` UNKNOWN, basis names the run)
    - never examined (``status`` UNKNOWN, source ``never_determined``)
    """
    meta = _doc_get(document, "language_meta") or {}
    language = _doc_get(document, "language")
    source = meta.get("source") or SOURCE_DETECTED

    if language:
        return LanguageResolution(
            language=language,
            status=RESOLVED,
            source=source,
            basis=f"document language recorded by {source}",
        )
    if meta.get("status") == STATUS_UNKNOWN:
        return LanguageResolution(
            language=None,
            status=UNKNOWN,
            source=source,
            basis="document was examined and its language could not be determined",
        )
    return LanguageResolution(
        language=None,
        status=UNKNOWN,
        source=NEVER_DETERMINED,
        basis="document language has never been determined",
    )


def is_user_set(document: Any) -> bool:
    """True when a human asserted this document's language.

    A user assertion is a persistent curation rule stored on the row it governs
    — the same mechanism ``date_extract`` uses for ``date_meta["source"]``, not
    a second one. Re-running detection must not overwrite it.
    """
    meta = _doc_get(document, "language_meta") or {}
    return meta.get("source") == SOURCE_USER


def build_language_meta(
    *,
    status: str,
    source: str,
    confidence: float | None = None,
    basis: str | None = None,
    level: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble a ``language_meta`` payload.

    ``level`` is a NAMED parameter rather than a key passed through ``extra``
    (slice 9, #4938). It could have ridden in ``extra`` and nothing would have
    broken — but a magic key is one nobody can find, no caller is obliged to
    set, and no reader knows to look for. `source.lang.says-where-from` is a
    behaviour, so the thing that carries it is a parameter.
    """
    meta: dict[str, Any] = {"status": status, "source": source}
    if confidence is not None:
        meta["confidence"] = float(confidence)
    if basis:
        meta["basis"] = basis
    if level:
        meta["level"] = level
    if extra:
        meta.update(extra)
    return meta


@dataclass
class DetectionOutcome:
    """Result of offering a detected language to a document."""

    applied: bool
    reason: str
    conflict: dict[str, Any] | None = field(default=None)


def apply_detected_language(
    document: Any,
    language: str | None,
    *,
    confidence: float | None = None,
    basis: str = "automatic detection",
) -> DetectionOutcome:
    """Record a detected language on ``document``, never clobbering a user's.

    Returns without writing when the language was set by a user. When the two
    disagree the disagreement is REPORTED rather than resolved — a conflict the
    user cannot see is a fact they cannot correct.

    ``language=None`` records "examined, undeterminable" rather than leaving the
    document looking un-examined.
    """
    if is_user_set(document):
        existing = _doc_get(document, "language")
        conflict = None
        if language and existing and _norm(language) != _norm(existing):
            conflict = {"user_language": existing, "detected_language": language}
        return DetectionOutcome(
            applied=False,
            reason="language was set by a user and is preserved",
            conflict=conflict,
        )

    if language:
        meta = build_language_meta(
            status=STATUS_KNOWN,
            source=SOURCE_DETECTED,
            confidence=confidence,
            basis=basis,
        )
    else:
        meta = build_language_meta(
            status=STATUS_UNKNOWN,
            source=SOURCE_DETECTED,
            confidence=confidence,
            basis=basis,
        )

    if isinstance(document, dict):
        document["language"] = language
        document["language_meta"] = meta
    else:
        document.language = language
        document.language_meta = meta
    return DetectionOutcome(applied=True, reason="recorded from detection")


def set_user_language(document: Any, language: str | None) -> None:
    """Record a human's assertion about this document's language.

    ``language=None`` is itself an assertion — "I looked and I cannot tell" —
    and is preserved against re-extraction exactly like a named language is.
    """
    meta = build_language_meta(
        status=STATUS_KNOWN if language else STATUS_UNKNOWN,
        source=SOURCE_USER,
        basis="asserted by a user",
    )
    if isinstance(document, dict):
        document["language"] = language
        document["language_meta"] = meta
    else:
        document.language = language
        document.language_meta = meta


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


#: The ISO 15924 codes that let a script be recorded honestly rather than
#: guessed (`source.lang.registries`). Without these a reader is forced to
#: either invent a script or leave the fact blank, and blank already means
#: "never determined".
SCRIPT_UNWRITTEN = "Zxxx"     # a spoken source, a recording: no script at all
SCRIPT_UNDETERMINED = "Zyyy"  # written, and which script is not established

#: ISO 15924 reserves `Qaaa` to `Qabx` for private use, and
#: `source.lang.project-declared` rests on it: a project can declare a script no
#: registry has without minting a code that will one day collide with a real one.
SCRIPT_PRIVATE_USE_PREFIX = "Q"


def script_is_private_use(code: str | None) -> bool:
    """Whether a code LOOKS like a private-use script code: four letters, first `Q`.

    Says what it does rather than what the range is. ISO 15924's private-use
    range stops at `Qabx`, so `Qzzz` is not assignable — and this returns True
    for it anyway, deliberately: treating an unassignable Q-code as a project's
    own is harmless, while treating it as registered would let a project mint a
    code that collides the day the registry grows. The range is not checked
    because a predicate whose comment and behaviour disagree is worse than no
    predicate: the comment is what the next reader trusts.
    """
    return bool(code) and len(code) == 4 and code[0] == SCRIPT_PRIVATE_USE_PREFIX


def _stated_fact(
    holder: Any, *, value_field: str, meta_field: str, level: str, noun: str
) -> LanguageResolution | None:
    """What one record says about one fact, or None if it says nothing.

    ONE reader for language and script, parameterised by field name, because the
    three states are the same three for every fact: stated, examined-and-
    undetermined, never examined. `None` here means the third — it FALLS THROUGH
    to the next rung, while an examined-and-undetermined answer stops the walk
    (`source.lang.unknown-is-not-unexamined` as control flow).
    """
    value = _doc_get(holder, value_field)
    meta = _doc_get(holder, meta_field) or {}
    if value:
        return LanguageResolution(
            language=value,
            status=RESOLVED,
            source=meta.get("source") or SOURCE_METADATA,
            basis=f"recorded on this {noun}",
            level=level,
        )
    if meta.get("status") == STATUS_UNKNOWN:
        return LanguageResolution(
            language=None,
            status=UNKNOWN,
            source=meta.get("source") or SOURCE_DETECTED,
            basis=f"this {noun} was examined and its {value_field} could not be determined",
            level=level,
        )
    return None


#: Unicode character names whose first word is not their script's ISO 15924 English name.
_SCRIPT_NAME_ALIASES = {"cjk": "Hani", "canadian": "Cans"}


@lru_cache(maxsize=1)
def _script_codes_by_first_word() -> dict[str, str]:
    """`{first word of a script's English name, lowercased: ISO 15924 code}`, from the ISO 15924
    list the PAGE schema already ships (`pagexml._schema_vocabularies`), never a hand copy. Where
    several codes share a first word (`Syrc - Syriac`, `Syre - Syriac (Estrangelo variant)`), the
    plain one -- the name that IS the word -- wins."""
    from fichero_server.formats.pagexml import _schema_vocabularies

    table: dict[str, str] = {}
    for code, value in sorted(_schema_vocabularies()[1].items()):
        name = value.split(" - ", 1)[-1].strip()
        word = re.split(r"[\s,(]", name, maxsplit=1)[0].lower()
        if word and (word not in table or name.lower() == word):
            table[word] = code
    return {**table, **_SCRIPT_NAME_ALIASES}


def script_of_text(text: str | None) -> str | None:
    """The ISO 15924 code most of the text's LETTERS are written in, or None (#5176).

    A Unicode letter's name starts with its script ("SYRIAC LETTER ALAPH", "LATIN SMALL LETTER
    A", "CJK UNIFIED IDEOGRAPH-4E00"), which is the stdlib's only view of the Script property.
    Evidence about the text, not a statement about the source: the rung that uses it says so."""
    import unicodedata

    counts: dict[str, int] = {}
    table = _script_codes_by_first_word()
    for ch in text or "":
        if not ch.isalpha():
            continue
        code = table.get(unicodedata.name(ch, "").split(" ", 1)[0].lower())
        if code:
            counts[code] = counts.get(code, 0) + 1
    return max(counts, key=lambda code: counts[code]) if counts else None


def resolve_script(
    *,
    requested: str | None = None,
    reading: Any = None,
    segment: Any = None,
    document: Any = None,
    project: Any = None,
    text: str | None = None,
) -> LanguageResolution:
    """Which script a thing is written in, and which rung said so (#4938).

    With nothing stated at any rung and `text` given, the text's own LETTERS answer (#5176):
    `source=detected`, basis "from the letters of its text". A Syriac line said "not
    determined" while its reading was Syriac.

    A SIMPLER cascade than language's, deliberately, and not a copy of it:
    there is no script policy to consult and no script detector to run, so the
    walk is reading → segment → document and then honestly unknown. Inventing a
    project-wide script setting to make the two symmetrical would be adding a
    feature nobody asked for so that two functions could look alike.

    `source.lang.reading-overrides`: a reading's own script wins for that
    reading — a transliterated reading of a Latin-script line is Arabic script,
    and the line is not.

    Returns `Zyyy` (undetermined) for nothing found? **No.** It returns an
    UNKNOWN resolution with `level=None`, because `Zyyy` is a positive claim
    that somebody looked and could not tell, and "nobody has looked" is a
    different state. Writing `Zyyy` here would collapse exactly the distinction
    `unknown-is-not-unexamined` protects.
    """
    if requested and _norm(requested) not in {"", "auto"}:
        return LanguageResolution(
            language=requested.strip(),
            status=RESOLVED,
            source="requested",
            basis="pinned on the workflow node",
            level=None,
        )

    for holder, level, noun in (
        (reading, LEVEL_READING, "reading"),
        (segment, LEVEL_SEGMENT, "segment"),
        (document, LEVEL_DOCUMENT, "document"),
        # The PROJECT rung. A plain holder like the three above -- a
        # `ProjectFacts` record read once by the caller -- so adding a level cost
        # this walk one line and no new way of reading a fact. There is still no
        # project SCRIPT POLICY: the project states a script or it does not.
        (project, LEVEL_PROJECT, "project"),
    ):
        if holder is None:
            continue
        stated = _stated_fact(
            holder, value_field="script", meta_field="script_meta", level=level, noun=noun
        )
        if stated is not None:
            return stated

    from_letters = script_of_text(text)
    if from_letters:
        return LanguageResolution(
            language=from_letters,
            status=RESOLVED,
            source=SOURCE_DETECTED,
            basis=f"from the letters of its text: most are {from_letters}",
            level=None,
        )
    return LanguageResolution(
        language=None,
        status=UNKNOWN,
        source=NEVER_DETERMINED,
        basis="no script has been recorded at any level",
        level=None,
    )


def _segment_stated_language(segment: Any) -> LanguageResolution | None:
    """What a segment says about its own language, or None if it says nothing.

    `None` is the answer for a segment that has never been examined, and it is
    deliberately different from a segment recorded as unknown: the first falls
    through to the document, the second is an answer. That is
    `source.lang.unknown-is-not-unexamined` expressed as control flow.
    """
    language = _doc_get(segment, "language")
    meta = _doc_get(segment, "language_meta") or {}
    if language:
        return LanguageResolution(
            language=language,
            status=RESOLVED,
            source=meta.get("source") or SOURCE_METADATA,
            basis="recorded on this segment",
            level=LEVEL_SEGMENT,
        )
    if meta.get("status") == STATUS_UNKNOWN:
        # Examined and undetermined AT THIS LEVEL. It does not fall through:
        # somebody looked at this region and could not tell, and the document's
        # broader answer would overwrite that finding with a guess.
        return LanguageResolution(
            language=None,
            status=UNKNOWN,
            source=meta.get("source") or SOURCE_DETECTED,
            basis="this segment was examined and its language could not be determined",
            level=LEVEL_SEGMENT,
        )
    return None


def resolve_language(
    *,
    requested: str | None = None,
    document: Any = None,
    segment: Any = None,
    text: str = "",
    policy: LanguagePolicy | None = None,
    detect: bool = True,
    script: str | None = None,
) -> LanguageResolution:
    """Resolve the language to use for one document, or one segment of one.

    `script` (#5176): the script the text's letters are in, when the caller knows it. Where the
    legacy path would fall back to English, a text whose script is known is answered "not
    determined" and names the script instead -- a Syriac line is never a confident English.
    A language is never GUESSED from a script: Syriac script is Syriac, Aramaic, Arabic
    (Garshuni) or Malayalam (Suriyani Malayalam).

    Precedence, highest first:

    1. ``requested`` — an explicit language pinned on the workflow node. The
       user typed it into this run; nothing outranks that. ``""``/``auto`` mean
       "no request".
    2. **The segment's own language**, when a segment is given (source-model
       slice 9, #4938). Below a pinned request and above everything about the
       document, because `source.lang.many-per-page` means a page can hold
       several languages at once: a Latin marginal note beside a Spanish entry
       is a fact about the REGION, and the document's answer is the wrong one
       for it. A segment that states nothing falls through — stating nothing is
       not stating unknown.
    3. A **user-set** document language. A human correction outranks the global
       default, which is the whole point of an override; the global setting is a
       default, not an instruction to overwrite people's work.
    3. The policy:

       - ``one``    → that language.
       - ``many``   → the document's own language if it is in the set; else
         detection if that lands in the set; else UNKNOWN. It deliberately does
         NOT fall back to the first listed language — picking Spanish for a
         French document because Spanish was listed first is precisely the
         confident-nonsense failure.
       - ``document`` → the document's recorded language, else detection, else
         UNKNOWN. Never the global default: the user asked for the document's
         language, so substituting a global one would be answering a different
         question.
       - ``unset``  → legacy behaviour, detection with an English fallback,
         preserved so existing libraries do not shift under this change.
    """
    policy = policy if policy is not None else configured_policy()

    if requested and _norm(requested) not in {"", "auto"}:
        return LanguageResolution(
            language=requested.strip(),
            status=RESOLVED,
            source="requested",
            basis="pinned on the workflow node",
            # The caller's own rung: a language pinned on this run is not
            # inherited from anywhere, so it is not one of the four.
            level=None,
        )

    # The SEGMENT rung. Read before the document's, and it returns only when the
    # segment actually states a language: `Segment.language` is `None` until
    # something determines one, and `None` means never determined, so falling
    # through is correct rather than a missed case.
    if segment is not None:
        segment_language = _segment_stated_language(segment)
        if segment_language is not None:
            return segment_language

    doc_language = read_document_language(document) if document is not None else None

    if doc_language is not None and doc_language.is_known and doc_language.source == SOURCE_USER:
        return LanguageResolution(
            language=doc_language.language,
            status=RESOLVED,
            source=SOURCE_USER,
            basis="set on this document by a user",
            level=LEVEL_DOCUMENT,
        )

    if policy.mode == "one":
        return LanguageResolution(
            language=policy.languages[0],
            status=RESOLVED,
            source="policy",
            basis="the library's language policy",
            level=LEVEL_PROJECT,
        )

    # A language recorded ON the document outranks detecting one from its text
    # or falling back — in every mode, not just `document`. It is a stored fact
    # about this document; re-deriving it and possibly disagreeing would be
    # strictly worse information. This cannot shift an existing library: the
    # migration backfills `language` NULL, so nothing has a recorded language
    # until something determines one.
    if doc_language is not None and doc_language.is_known:
        if policy.permits(doc_language.language):
            return LanguageResolution(
                language=doc_language.language,
                status=RESOLVED,
                source=doc_language.source,
                basis="recorded on this document",
                level=LEVEL_DOCUMENT,
            )
        return LanguageResolution(
            language=None,
            status=UNKNOWN,
            source="policy",
            basis=(
                f"the document's language ({doc_language.language}) is not one of "
                f"the languages this library processes ({', '.join(policy.languages)})"
            ),
            # The PROJECT's policy refused the document's own answer, so the
            # project is the rung that decided — an unknown still says where
            # the decision was made.
            level=LEVEL_PROJECT,
        )

    if policy.mode == "unset":
        # Legacy path, unchanged: detect, fall back to English. Preserved so
        # libraries that never set a policy behave exactly as before. This is
        # the ONE place an unjustified English is still produced, and it is
        # reachable only when no policy is set and the document has no recorded
        # language — i.e. every library, before anyone opts in.
        from fichero_server.llm.lang_detect import detect_language

        if detect and text:
            return LanguageResolution(
                language=detect_language(text, default="English"),
                status=RESOLVED,
                source=SOURCE_DETECTED,
                basis="detected from the text (no language policy is set)",
            )
        if script:
            return LanguageResolution(
                language=None,
                status=UNKNOWN,
                source=NEVER_DETERMINED,
                basis=f"not determined: nothing states a language and none was detected; its letters are {script}",
            )
        return LanguageResolution(
            language="English",
            status=RESOLVED,
            source="fallback",
            basis="no language policy is set and there is no text to detect from",
        )

    if detect and text:
        from fichero_server.llm.lang_detect import detect_language

        # No `default=` fallback here on purpose. Under an explicit policy an
        # undetectable document must read as unknown, not as English.
        detected = detect_language(text, default="")
        if detected and policy.permits(detected):
            return LanguageResolution(
                language=detected,
                status=RESOLVED,
                source=SOURCE_DETECTED,
                basis="detected from this document's text",
            )
        if detected:
            return LanguageResolution(
                language=None,
                status=UNKNOWN,
                source="policy",
                basis=(
                    f"detected {detected}, which is not one of the languages this "
                    f"library processes ({', '.join(policy.languages)})"
                ),
            )

    return LanguageResolution(
        language=None,
        status=UNKNOWN,
        source=NEVER_DETERMINED if doc_language is None else doc_language.source,
        basis="this document's language is not known",
    )


# What a prompt says when the language is not known. Asserting a language
# nobody established is how a transcription pass produces fluent, plausible,
# wrong output; telling the model to follow the source is both honest and, on
# an unlabelled colonial-Spanish page, more likely to be right than "English".
UNKNOWN_LANGUAGE_INSTRUCTION = "the same language as the source document"


def prompt_language(resolution: LanguageResolution) -> str:
    """The phrase to interpolate into a prompt for this resolution."""
    return resolution.language if resolution.is_known else UNKNOWN_LANGUAGE_INSTRUCTION


def require_language(resolution: LanguageResolution) -> str:
    """Return the language or raise. For callers that must not guess."""
    if not resolution.is_known:
        raise UnknownDocumentLanguage(resolution.basis)
    return resolution.language  # type: ignore[return-value]


def describe(resolution: LanguageResolution) -> dict[str, Any]:
    """A result-payload fragment so a run reports what language it used.

    Every wired tool emits this, so "unknown" is visible in the run result
    instead of being invisible behind output that silently came out in English.
    """
    return {
        "language": resolution.language,
        "language_status": resolution.status,
        "language_source": resolution.source,
        "language_basis": resolution.basis,
    }


# ---------------------------------------------------------------------------
# Direction (`source.dir.per-segment`, `source.dir.logical-order-stored`; #4938)
# ---------------------------------------------------------------------------

#: The four straight directions, plus the two a manuscript actually needs: a
#: boustrophedon inscription that turns at the end of every line, and a line
#: that follows a curved or slanted baseline rather than any axis.
DIRECTION_LTR = "ltr"
DIRECTION_RTL = "rtl"
DIRECTION_TTB = "ttb"
DIRECTION_BTT = "btt"
DIRECTION_ALTERNATING = "alternating"
DIRECTION_FOLLOWS_BASELINE = "follows-baseline"
DIRECTIONS: tuple[str, ...] = (
    DIRECTION_LTR,
    DIRECTION_RTL,
    DIRECTION_TTB,
    DIRECTION_BTT,
    DIRECTION_ALTERNATING,
    DIRECTION_FOLLOWS_BASELINE,
)

#: Scripts written right to left. Short and deliberately so: this is a DEFAULT
#: for a value nobody set, not a claim to know every script's direction. A
#: script absent from here derives `ltr`, which is what an unlabelled page gets
#: today, and any level can override it.
_RTL_SCRIPTS = frozenset(
    {"Arab", "Hebr", "Syrc", "Thaa", "Nkoo", "Samr", "Mand", "Armi", "Phnx", "Adlm"}
)

#: Scripts that MAY be written vertically. They resolve `ltr` all the same,
#: because "may be vertical" is not a direction and a page of modern horizontal
#: Japanese is the common case. Kept as a named set because the honest answer
#: for these is "ask the source", and a caller that wants to prompt for one
#: needs to know which they are.
_MAYBE_VERTICAL_SCRIPTS = frozenset({"Hani", "Hans", "Hant", "Hira", "Kana", "Jpan", "Hang", "Kore", "Mong", "Phag"})


def script_may_be_vertical(script: str | None) -> bool:
    """Whether this script is one whose direction genuinely needs asking about."""
    return bool(script) and script in _MAYBE_VERTICAL_SCRIPTS


#: Unicode name prefixes of the letters of the scripts in `_MAYBE_VERTICAL_SCRIPTS`.
_MAYBE_VERTICAL_LETTER_NAMES = (
    "CJK UNIFIED IDEOGRAPH", "CJK COMPATIBILITY IDEOGRAPH", "HIRAGANA", "KATAKANA",
    "HANGUL", "MONGOLIAN", "PHAGS-PA",
)


def text_may_be_vertical(text: str | None) -> bool:
    """Whether most of the text's letters belong to a script that may be written vertically.

    For a reading with no script recorded: the letters are the only evidence of the script."""
    import unicodedata

    letters = [ch for ch in (text or "") if ch.isalpha()]
    if not letters:
        return False
    vertical = sum(
        1 for ch in letters if unicodedata.name(ch, "").startswith(_MAYBE_VERTICAL_LETTER_NAMES)
    )
    return vertical * 2 > len(letters)


#: A line is a COLUMN when it is at least this many times taller than wide, in pixels.
COLUMN_RATIO = 2.0


def lines_are_columns(boxes: list[tuple[float, float]]) -> bool | None:
    """Whether a page's lines, as `(width, height)` in pixels, are columns (#5147).

    None when there is too little to say (fewer than two lines with a shape of their own). True
    when more than half are at least `COLUMN_RATIO` times taller than wide: a vertical page's
    lines are narrow columns, and a horizontal page's lines are wide rows, so the vote is rarely
    close. A line with no shape of its own (placed only by its page's zone) is not a vote."""
    measured = [(w, h) for w, h in boxes if w > 0 and h > 0]
    if len(measured) < 2:
        return None
    columns = sum(1 for w, h in measured if h >= COLUMN_RATIO * w)
    return columns * 2 > len(measured)


def direction_is_known(direction: str | None) -> bool:
    """Whether a value is one of the six directions."""
    return direction in DIRECTIONS


class BadDirection(ValueError):
    """Raised when a direction outside the six is recorded."""

    def __init__(self, direction: str) -> None:
        self.direction = direction
        super().__init__(
            f"unknown direction {direction!r}; allowed: " + ", ".join(DIRECTIONS)
        )


def assert_known_direction(direction: str | None) -> None:
    """Refuse a direction outside the list. `None` is allowed: it means nothing
    has been set at this level, which is what the cascade walks past.

    NO WRITER CALLS THIS YET, and that is stated rather than hidden: nothing in
    the engine sets a segment's language, script or direction today — the action
    that will (`source_setting.set`) is the next chunk of this slice. It is
    called on a `requested` direction by `resolve_direction`, which is the one
    place a caller-supplied value arrives, so it is not dead code; it is a guard
    waiting for the writer it was designed with.
    """
    if direction is None:
        return
    if not direction_is_known(direction):
        raise BadDirection(direction)


def first_strong_direction(text: str | None) -> str | None:
    """`rtl` or `ltr` from the first strongly directional character (UBA rule P2), or None."""
    import unicodedata

    for ch in text or "":
        kind = unicodedata.bidirectional(ch)
        if kind in ("R", "AL"):
            return DIRECTION_RTL
        if kind == "L":
            return DIRECTION_LTR
    return None


def stated_direction_source(get_document: Any, document: Any) -> Any:
    """The nearest ancestor of `document` whose direction was stated or examined, or None.

    `get_document(id)` loads a parent (the caller's own db read). Walks `parent_id` up from the
    page's parent; a cycle or a missing parent ends the walk.
    """
    seen: set[str] = set()
    parent_id = _doc_get(document, "parent_id") if document is not None else None
    while parent_id and parent_id not in seen:
        seen.add(parent_id)
        parent = get_document(parent_id)
        if parent is None:
            return None
        if _stated_fact(parent, value_field="direction", meta_field="direction_meta",
                        level=LEVEL_DOCUMENT, noun="source") is not None:
            return parent
        parent_id = _doc_get(parent, "parent_id")
    return None


def resolve_direction(
    *,
    requested: str | None = None,
    reading: Any = None,
    segment: Any = None,
    document: Any = None,
    source: Any = None,
    project: Any = None,
    script: str | None = None,
    text: str | None = None,
    lines_are_vertical: bool | None = None,
) -> LanguageResolution:
    """Which direction a thing is written in, and which rung said so (#4938).

    `source` is the nearest document ABOVE the page that states a direction
    (`stated_direction_source`): a direction set on a file or folder reaches its pages'
    lines, after the page's own and before the project's (#5172). It answers at the
    document level -- the same vocabulary, not a new rung name.

    `lines_are_vertical` is the page's own geometry (`lines_are_columns`): with nothing stated
    and a script that may be vertical, columns mean `ttb` (#5147).

    With no script recorded either, `text` -- the reading itself -- decides, by the Unicode
    Bidirectional Algorithm's own paragraph rule (P2: the first strongly directional character).
    An unmarked Syriac or Hebrew line is right-to-left by its letters (#5137); without this it
    was `ltr` because nothing had SAID otherwise.

    The SAME walk as `resolve_script`, through the same `_stated_fact` reader,
    and then one thing neither of the other two facts has: a **derivation**. A
    page with nothing set anywhere still has to be laid out, and `Arab` gives
    `rtl` far more often than it does not — so the last step works the answer
    out from the resolved script and reports `level=derived-from-script`.

    Why that is not the same mistake as writing `Zyyy` for an unexamined script:
    a derived direction is a DISPLAY decision that must be made either way (the
    text is drawn somewhere), while a script is a CLAIM about the source that
    nobody has to make. Naming the level is what keeps the two apart — a reader
    is told the direction was worked out, not chosen, and any level overrides it.

    `script` is passed in rather than resolved here so one caller can resolve
    the script once and use it for both facts; when it is omitted the script is
    resolved from the same records.
    """
    if requested and _norm(requested) not in {"", "auto"}:
        assert_known_direction(requested.strip())
        return LanguageResolution(
            language=requested.strip(),
            status=RESOLVED,
            source="requested",
            basis="pinned on the workflow node",
            level=None,
        )

    for holder, level, noun in (
        (reading, LEVEL_READING, "reading"),
        (segment, LEVEL_SEGMENT, "segment"),
        (document, LEVEL_DOCUMENT, "document"),
        (source, LEVEL_DOCUMENT, "source"),
        (project, LEVEL_PROJECT, "project"),
    ):
        if holder is None:
            continue
        stated = _stated_fact(
            holder, value_field="direction", meta_field="direction_meta",
            level=level, noun=noun,
        )
        if stated is not None:
            return stated

    script_from_letters = False
    if script is None:
        resolved_script = resolve_script(
            reading=reading, segment=segment, document=document, project=project, text=text
        )
        script = resolved_script.language
        # A script READ FROM THE LETTERS (#5176) is the letters' evidence, not a statement: the
        # letters' own bidi class still decides the direction below, exactly as before it was
        # named, so this changes the basis a caller sees and not the answer.
        script_from_letters = resolved_script.source == SOURCE_DETECTED

    if lines_are_vertical and (
        script_may_be_vertical(script) or (script is None and text_may_be_vertical(text))
    ):
        # A script that MAY be vertical resolves `ltr` because "may be" is not a direction
        # (see `_MAYBE_VERTICAL_SCRIPTS`). But a page whose lines are columns -- far taller than
        # wide -- has answered the question itself (#5147: the BULAC Chinese pages came out
        # horizontal). The shape is evidence about THIS page, so it decides; anything stated
        # anywhere still wins above, and the basis says where the answer came from.
        return LanguageResolution(
            language=DIRECTION_TTB,
            status=RESOLVED,
            source=SOURCE_DERIVED_FROM_SCRIPT,
            basis="from the shape of the lines: this page's lines are columns, taller than wide",
            level=None,
        )

    from_text = first_strong_direction(text) if (script is None or script_from_letters) else None
    if from_text is not None:
        derived = from_text
        basis = (
            f"from the letters of its text ({script}): the first strongly directional character decides (Unicode bidi P2)"
            if script else
            "no script is recorded, so the text's first strongly directional character decides (Unicode bidi P2)"
        )
    else:
        derived = DIRECTION_RTL if script in _RTL_SCRIPTS else DIRECTION_LTR
        basis = (
            f"worked out from the script ({script})" if script
            else "no script is recorded either, so the reading order of the text is assumed"
        )
    return LanguageResolution(
        language=derived,
        status=RESOLVED,
        source=SOURCE_DERIVED_FROM_SCRIPT,
        basis=basis,
        # No rung stated this. The distinction a reader needs -- a direction
        # worked out versus one a person chose -- is carried by `source`, which
        # is the field a caller already inspects to decide whether to trust a
        # value, and `level` stays four pure rungs.
        level=None,
    )
