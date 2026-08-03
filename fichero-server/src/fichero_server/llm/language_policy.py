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

from dataclasses import dataclass, field
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
    """

    language: str | None
    status: str
    source: str
    basis: str

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
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble a ``language_meta`` payload."""
    meta: dict[str, Any] = {"status": status, "source": source}
    if confidence is not None:
        meta["confidence"] = float(confidence)
    if basis:
        meta["basis"] = basis
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


def resolve_language(
    *,
    requested: str | None = None,
    document: Any = None,
    text: str = "",
    policy: LanguagePolicy | None = None,
    detect: bool = True,
) -> LanguageResolution:
    """Resolve the language to use for one document.

    Precedence, highest first:

    1. ``requested`` — an explicit language pinned on the workflow node. The
       user typed it into this run; nothing outranks that. ``""``/``auto`` mean
       "no request".
    2. A **user-set** document language. A human correction outranks the global
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
        )

    doc_language = read_document_language(document) if document is not None else None

    if doc_language is not None and doc_language.is_known and doc_language.source == SOURCE_USER:
        return LanguageResolution(
            language=doc_language.language,
            status=RESOLVED,
            source=SOURCE_USER,
            basis="set on this document by a user",
        )

    if policy.mode == "one":
        return LanguageResolution(
            language=policy.languages[0],
            status=RESOLVED,
            source="policy",
            basis="the library's language policy",
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
            )
        return LanguageResolution(
            language=None,
            status=UNKNOWN,
            source="policy",
            basis=(
                f"the document's language ({doc_language.language}) is not one of "
                f"the languages this library processes ({', '.join(policy.languages)})"
            ),
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
