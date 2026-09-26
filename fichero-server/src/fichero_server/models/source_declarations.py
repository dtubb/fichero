"""Source-model slice 9 — a project's own languages and scripts (spec:
``languages-scripts-signs.md``, `source.lang.project-declared`; #4938).

WHAT THIS MODULE IS FOR. A registry is a list somebody else finished. ISO 15924
has no code for the shorthand one nineteenth-century clerk used, and BCP 47 has
no tag for a language whose name is still being argued over — and a project
whose sources are written in those is not a project with bad data. It needs to
be able to say "this script, the one I am calling *the Marshall hand*, is a
thing in this library", and have every later reader of that value find out what
it means rather than a four-letter code nobody can resolve.

**The two halves are not symmetrical, and that is the finding, not an oversight.**

*Scripts* are stored as codes (``Segment.script``, ``Document.script``,
``ContentRepresentation.script``), so a project-declared script needs somewhere
to record what its code MEANS. Both standards reserve a range for exactly this:
ISO 15924 keeps ``Qaaa``–``Qabx`` private-use, so a project can mint a code that
will never collide with a real one. :class:`LibraryScript` is where the meaning
lives, and :func:`assert_known_script` refuses a private-use code that has no
declaration — an undeclared ``Qaaa`` is not a script, it is a value nobody can
read back.

*Languages* need no record at all, because ``Document.language`` holds a
canonical NAME (#2092), not a tag: a project that works in an unregistered
language already writes its name into the field and the cascade carries it. The
declaration and the value are the same string. Adding a language table here
would be a second place to keep one fact, which is the duplication this
programme exists to remove. What IS missing is the other direction — a
registered BCP 47 tag has nowhere to live at document level — and that is
reported against `source.lang.registries`, not patched here.

So the only predicate the language half needs is "is this value the project's
own?", which BCP 47 answers the same way ISO 15924 does: a private-use range.

ENCODING. :attr:`LibraryScript.encoding` is a stored fact with the spec's three
values and no computation behind it. Whether Fichero *works out* a script's
encoding from ``llm/script_coverage.py``'s exemplar sets is the open question on
item 4; nothing here presumes an answer either way, and a stored ``None`` reads
as "not established", consistent with every other fact in this slice.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from fichero_server.core.timeutil import utc_now
from fichero_server.models.knowledge import LibrarySetting
from fichero_server.llm.language_policy import (
    SOURCE_DERIVED_FROM_SCRIPT,
    NEVER_DETERMINED,
    RESOLVED,
    SCRIPT_PRIVATE_USE_PREFIX,
    UNKNOWN,
    LanguageResolution,
    resolve_script,
    script_is_private_use,
)


def _new_id() -> str:
    """Same minting as every other model (see ``segments.py``)."""
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# The private-use ranges both standards reserve
# ---------------------------------------------------------------------------

#: ISO 15924's private-use range, ``Qaaa`` to ``Qabx``. IMPORTED, not
#: redefined: the cascade in ``llm/language_policy.py`` already owns this
#: constant and its predicate, and a second copy here would be two answers to
#: "is this a project's own script" that could drift apart. (``models``
#: importing ``llm`` is the direction this package already uses — see
#: ``models/__init__.py``'s ``ProviderType``.)

#: BCP 47 reserves ``qaa``–``qtz`` for private use (by way of ISO 639-3), and
#: separately allows an ``x-`` private-use subtag on any tag. Both mean "this
#: identifier is meaningful inside one community and nowhere else", which is
#: exactly what a project declaring its own language is doing.
LANGUAGE_PRIVATE_USE_FIRST = "qaa"
LANGUAGE_PRIVATE_USE_LAST = "qtz"

#: How much of a script Fichero can encode as characters (`source.lang.three-facts`).
#: ``None`` — not one of these — means it has not been established, which is a
#: different state from ``none`` (established: this script cannot be encoded).
#:
#: NEVER DERIVED FROM ``llm/script_coverage.py``, and ruled so 2026-09-26. That
#: module asks whether a MODEL's tokenizer handles a script; this fact asks
#: whether the signs have Unicode code points, and a Maya glyph with no code
#: point is unencoded whichever model you ask. If it is ever computed it is
#: computed page-against-Unicode, never model-against-tokenizer — an archival
#: fact must not change meaning because somebody swapped a model, and this one
#: gets exported. What it DOES take from `script_coverage` is the precedent, not
#: the code: that module's honest-unknown rule (say "cannot tell" rather than
#: produce a number nobody can trust) is the discipline followed here.
ENCODING_FULL = "full"
ENCODING_PART = "part"
ENCODING_NONE = "none"
ENCODINGS: tuple[str, ...] = (ENCODING_FULL, ENCODING_PART, ENCODING_NONE)


def script_code_is_well_formed(code: str | None) -> bool:
    """Whether a value has ISO 15924's shape: four letters, ``Titlecase``.

    Shape only. Fichero ships no copy of the registry's ~220 codes, so "is this
    a real script code" is a question this engine cannot answer offline, and a
    guard that pretended otherwise would refuse honest values. See
    :func:`assert_known_script` for what that means for refusals.
    """
    return bool(code) and len(code) == 4 and code.isalpha() and code == code.title()


def language_is_project_declared(value: str | None) -> bool:
    """Whether a language value is one a project declared rather than a registered tag.

    True for BCP 47's private-use range (``qaa``–``qtz``) and for any tag
    carrying an ``x-`` private-use subtag. A canonical name — what
    ``Document.language`` actually holds — is neither: a name is not a claim
    about a registry at all, so it reads as False rather than as declared.
    """
    if not value:
        return False
    lowered = value.strip().lower()
    if not lowered:
        return False
    subtags = lowered.split("-")
    if "x" in subtags[1:]:
        return True
    return LANGUAGE_PRIVATE_USE_FIRST <= subtags[0] <= LANGUAGE_PRIVATE_USE_LAST and len(
        subtags[0]
    ) == 3


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------


class LibraryScript(BaseModel):
    """One script this library knows about. Table ``libraryscripts``.

    Follows :class:`~fichero_server.models.readings.LibraryReadingKind` exactly:
    a per-library vocabulary table that ``_ensure_table`` creates at open.

    ponytail: a TABLE, where the build notes said a ``LibrarySetting`` row
    holding a JSON list under key ``source.scripts``. The information is the
    same; the table is queryable, typed, migrated by the mechanism every other
    model already uses, and cannot drift into two parsers of one blob. The
    k/v row would need a serialiser, a deserialiser and a hand-written
    migration for a shape that is already a model. Reported as a departure, not
    taken silently.

    NOT seeded with ISO 15924: a library holds rows for the scripts it has
    something to say about, which is the declared ones plus any a project chose
    to name. An absent row is not a refusal — see :func:`assert_known_script`.
    """

    model_config = {"from_attributes": True}

    id: str = Field(default_factory=_new_id)
    #: The value stored in ``Segment.script`` / ``Document.script``.
    code: str
    #: What a person reading this library should see instead of the code. For a
    #: declared script this is the whole point of the row.
    name: str
    #: ``full`` | ``part`` | ``none``, or ``None`` for not established.
    #:
    #: ONE FACT AT TWO LEVELS, ruled 2026-09-26: encoding is a property of the
    #: SCRIPT — whether that writing system has code points at all — and a
    #: page's encoding is its script's, read through the cascade
    #: (:func:`resolve_encoding`). There is deliberately NO per-page encoding
    #: storage, because no case needs it yet and a field nothing writes is a gap
    #: rather than a feature.
    #:
    #: The upgrade path, written down so the next person finds the reasoning
    #: instead of re-deriving the question: when a real mixed case appears — a
    #: page using only the encoded subset of a partly-encoded script, or one
    #: unencoded glyph in an otherwise-encoded script — the page's encoding
    #: becomes a second, genuinely different fact and earns its own storage and
    #: provenance. At that point the two must have DISTINGUISHABLE NAMES in the
    #: code, because a page's encoding and a script's encoding both spelled
    #: `encoding` is the two-spellings-of-one-idea hazard this programme exists
    #: to remove.
    encoding: str | None = None
    #: True when this project minted the code, False when the code is a
    #: registered one this library merely named.
    declared: bool = False
    created_at: datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Typed refusals
# ---------------------------------------------------------------------------


class UnknownScript(ValueError):
    """Raised when a write names a script this library cannot make sense of.

    Says how to declare one, because the caller who hit this is usually a
    project that MEANT to, and being told only "unknown" leaves them guessing
    at a code instead.
    """

    def __init__(self, code: str, reason: str) -> None:
        self.code = code
        self.reason = reason
        super().__init__(
            f"cannot use script {code!r}: {reason}. A script no registry has is "
            f"declared with a private-use code ({SCRIPT_PRIVATE_USE_PREFIX}aaa to "
            f"{SCRIPT_PRIVATE_USE_PREFIX}abx) and a name."
        )


class CannotDeclareRegisteredScript(ValueError):
    """Raised when a project tries to declare a code outside the private-use range.

    Naming a registered script is fine and is what ``declared=False`` rows are
    for; REDEFINING one is not. A library whose ``Latn`` means something local
    exports data that every other tool reads wrongly, silently.
    """

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(
            f"{code!r} is not a code this project may define: it is outside ISO "
            f"15924's private-use range. Use {SCRIPT_PRIVATE_USE_PREFIX}aaa to "
            f"{SCRIPT_PRIVATE_USE_PREFIX}abx for a script of your own, or record a "
            "name for the registered script instead."
        )


class DeclarationNeedsAName(ValueError):
    """Raised when a declaration arrives without a name.

    A private-use code with no name is unreadable by construction: nothing in
    the world can resolve ``Qaaa``, so the name is not metadata about the
    declaration, it IS the declaration.
    """

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"declaring {code!r} needs a name: nothing can resolve the code alone")


class UnknownEncoding(ValueError):
    """Raised when an encoding outside the three values is recorded."""

    def __init__(self, encoding: str) -> None:
        self.encoding = encoding
        super().__init__(
            f"unknown encoding {encoding!r}; allowed: " + ", ".join(ENCODINGS) + " (or unset)"
        )


# ---------------------------------------------------------------------------
# Reading and writing declarations
# ---------------------------------------------------------------------------


def library_scripts(db: Any) -> list[LibraryScript]:
    """Every script row this library holds, declared or merely named."""
    return list(db.query(LibraryScript))


def script_row(db: Any, code: str) -> LibraryScript | None:
    """The row for one code, or None."""
    for row in library_scripts(db):
        if row.code == code:
            return row
    return None


def script_display_name(db: Any, code: str | None) -> str | None:
    """What to show a person for a script code, or None if the library cannot say.

    `source.lang.says-where-from`'s sibling problem: a value shown as ``Qaaa``
    tells a reader nothing, and a declared script's whole purpose is that the
    library knows what its code means.
    """
    if not code:
        return None
    row = script_row(db, code)
    return row.name if row else None


def assert_known_script(db: Any, code: str) -> None:
    """Refuse a script value this library cannot make sense of.

    Three refusals, and one deliberate non-refusal:

    * malformed — not ISO 15924's four-letter ``Titlecase`` shape;
    * a private-use code with no declaration in this library;
    * nothing else.

    A well-formed code that is not in the registry and not declared PASSES, and
    that is honest rather than lax: Fichero ships no copy of ISO 15924, so the
    engine cannot tell ``Latn`` from ``Lxtn`` offline. Refusing every code it
    could not confirm would refuse real ones; pretending a short hand-kept list
    is the registry would be worse, because it would look authoritative. The
    refusal that matters is the second one, which is what keeps a declared
    script honest.
    """
    if not script_code_is_well_formed(code):
        return _refuse(code, "it is not four letters in ISO 15924's Titlecase shape")
    if script_is_private_use(code) and script_row(db, code) is None:
        return _refuse(code, "it is a private-use code this library has not declared")


def _refuse(code: str, reason: str) -> None:
    raise UnknownScript(code, reason)


def declare_script(
    db: Any, code: str, name: str, *, encoding: str | None = None
) -> LibraryScript:
    """Declare a script no registry has, or update one already declared.

    Idempotent on the code: declaring twice records the later name and encoding
    on the SAME row rather than leaving two rows disagreeing about what a stored
    value means.
    """
    return _record_script(db, code, name, encoding=encoding, declared=True)


def name_registered_script(
    db: Any, code: str, name: str, *, encoding: str | None = None
) -> LibraryScript:
    """Record this library's name (and encoding) for a registered script code.

    The other half of the same table, and why the rows carry ``declared``: a
    library that wants to show "Latin" for ``Latn``, or to record that its
    Arabic sources are only partly encodable, is not declaring anything.
    """
    if script_is_private_use(code):
        raise CannotDeclareRegisteredScript(code)
    return _record_script(db, code, name, encoding=encoding, declared=False)


def _record_script(
    db: Any, code: str, name: str, *, encoding: str | None, declared: bool
) -> LibraryScript:
    if declared and not script_is_private_use(code):
        raise CannotDeclareRegisteredScript(code)
    if not script_code_is_well_formed(code):
        raise UnknownScript(code, "it is not four letters in ISO 15924's Titlecase shape")
    if not (name or "").strip():
        raise DeclarationNeedsAName(code)
    if encoding is not None and encoding not in ENCODINGS:
        raise UnknownEncoding(encoding)

    existing = script_row(db, code)
    row = LibraryScript(
        id=existing.id if existing else _new_id(),
        code=code,
        name=name.strip(),
        encoding=encoding,
        declared=declared,
        created_at=existing.created_at if existing else utc_now(),
    )
    db.save(row)
    return row


# ---------------------------------------------------------------------------
# Encoding, read through the cascade (`source.lang.three-facts`, item 4)
# ---------------------------------------------------------------------------


def resolve_encoding(
    db: Any,
    *,
    reading: Any = None,
    segment: Any = None,
    document: Any = None,
    project: Any = None,
    script: str | None = None,
) -> LanguageResolution:
    """How much of this thing's script Fichero can encode, and why it says so.

    Ruled 2026-09-26 as **one fact at two levels**: the script row holds it, and
    a page's encoding is its script's, read through the same cascade. So this
    resolves the SCRIPT first (`resolve_script`, unchanged and uncopied) and then
    reads the row for whatever script won. Nothing is stored per page.

    Three answers, and keeping them apart is the whole point:

    * **resolved** — the library recorded an encoding for this script.
    * **unknown, because no script is established** — there is nothing to look
      up yet. Not the same as an unencodable script.
    * **unknown, because nobody has recorded one for that script** — the script
      is known and its encoding is simply not established. Also not the same as
      ``none``, which is the positive claim that this writing system cannot be
      encoded at all.

    And ``Zxxx`` is a fourth thing again: unwritten, so the question does not
    arise. It resolves like any other script and its row (if a library made one)
    is where that is said — this function does not special-case it, because
    inventing an answer for it here would be exactly the guess the three states
    above exist to avoid.

    An encoding that is found is reported with `source=derived-from-script` and
    `level=None`, for the same reason direction is: no RUNG stated it — it was
    computed from the script row — and `level` holds rungs only. (This was
    briefly a fifth `level` value and that was the conflation `level` exists to
    prevent: a derivation is a way of determining, not a place it came from.)
    """
    if script is None:
        resolved_script = resolve_script(
            reading=reading, segment=segment, document=document, project=project
        )
        script = resolved_script.language

    if not script:
        return LanguageResolution(
            language=None,
            status=UNKNOWN,
            source=NEVER_DETERMINED,
            basis="no script is established, so there is no encoding to read",
            level=None,
        )

    row = script_row(db, script)
    if row is None or row.encoding is None:
        return LanguageResolution(
            language=None,
            status=UNKNOWN,
            source=NEVER_DETERMINED,
            basis=f"this library has not recorded an encoding for {script}",
            level=None,
        )

    return LanguageResolution(
        language=row.encoding,
        status=RESOLVED,
        source=SOURCE_DERIVED_FROM_SCRIPT,
        basis=f"recorded for the script {script} in this library",
        level=None,
    )


# ---------------------------------------------------------------------------
# The project rung (`source.lang.cascade`; the project level of the three facts)
# ---------------------------------------------------------------------------

#: The `LibrarySetting` ids the project's own language, script and direction live
#: under. Prefixed `source.` so a library's settings table stays readable when
#: other programmes add their own.
PROJECT_FACT_KEYS: tuple[str, ...] = ("language", "script", "direction")


def project_setting_id(key: str) -> str:
    """The `LibrarySetting.id` one project-level fact is stored under."""
    return f"source.{key}"


class UnknownProjectFact(ValueError):
    """Raised when a project-level write names something that is not one of the three."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(
            f"{key!r} is not a fact a project can state; allowed: "
            + ", ".join(PROJECT_FACT_KEYS)
        )


class ProjectFacts(BaseModel):
    """What the PROJECT says about language, script and direction.

    A HOLDER, shaped so the cascade's existing `_stated_fact` reader works on it
    unchanged — the same `value`/`value_meta` attribute pairing a `Segment`, a
    `Document` and a `ContentRepresentation` already present. That is the whole
    reason it is a record rather than a dict: adding a project rung then costs
    the resolvers one more entry in a tuple they already walk, instead of a
    branch that reads settings a different way.

    Read ONCE by a caller and passed in, rather than the resolvers taking a `db`:
    resolving a page's segments would otherwise re-read the settings table per
    row, and keeping `language_policy` free of database access is what lets it be
    tested with plain objects.
    """

    model_config = {"from_attributes": True}

    language: str | None = None
    script: str | None = None
    direction: str | None = None
    language_meta: dict[str, Any] | None = None
    script_meta: dict[str, Any] | None = None
    direction_meta: dict[str, Any] | None = None

    @property
    def states_nothing(self) -> bool:
        """True when the project has stated none of the three.

        Worth a name: a project that has stated nothing must fall THROUGH to the
        app-wide policy, and a caller that tested truthiness of the record itself
        would always see a value.
        """
        return not any((self.language, self.script, self.direction))


def project_facts(db: Any) -> ProjectFacts:
    """Read the project's three facts out of its own settings rows.

    Tolerates a row written by an older or newer build: a value that will not
    parse as this shape is IGNORED rather than raised over, because a settings
    table is shared with every other programme and one unreadable row must not
    make a page unreadable. A refusal belongs on the WRITE, where somebody can
    still fix it.
    """
    facts: dict[str, Any] = {}
    for key in PROJECT_FACT_KEYS:
        row = db.get(LibrarySetting, project_setting_id(key))
        if row is None or not row.value:
            continue
        try:
            payload = json.loads(row.value)
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        value = payload.get("value")
        if isinstance(value, str) and value:
            facts[key] = value
        meta = payload.get("meta")
        if isinstance(meta, dict):
            facts[f"{key}_meta"] = meta
    return ProjectFacts(**facts)


def set_project_fact(
    db: Any, key: str, value: str, *, meta: dict[str, Any] | None = None
) -> ProjectFacts:
    """Record one of the project's three facts. Returns the facts as they now read.

    Validation is the caller's, and deliberately so: this is the storage, and the
    action above it is where a script is checked against the library's
    declarations and a direction against the six. Two validating layers would be
    two places to keep one rule.
    """
    if key not in PROJECT_FACT_KEYS:
        raise UnknownProjectFact(key)
    db.save(
        LibrarySetting(
            id=project_setting_id(key),
            value=json.dumps({"value": value, "meta": meta or {}}),
        )
    )
    return project_facts(db)


def clear_project_fact(db: Any, key: str) -> ProjectFacts:
    """Return one of the project's facts to NOT STATED.

    The row is REMOVED rather than written empty: an empty row would be a project
    saying "I have considered this and have nothing to say", which is a claim, and
    `unknown-is-not-unexamined` is the rule that claim would quietly break.
    """
    if key not in PROJECT_FACT_KEYS:
        raise UnknownProjectFact(key)
    row = db.get(LibrarySetting, project_setting_id(key))
    if row is not None:
        db.delete(row)
    return project_facts(db)
