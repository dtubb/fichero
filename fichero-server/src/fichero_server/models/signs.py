"""Declared signs: a sign with no character, as a project record (slice 14, #4939).

Spec: `languages-scripts-signs.md`, "Signs without characters" (`source.sign.*`).

A **sign** is the unit of a script. Most are Unicode characters; one that is not is DECLARED:
a name, and a picture cut from a real segment on a real page -- the page it was first met
on. It may also carry references to sign lists (an authority and a number in its list: a
Maya catalogue, a cuneiform list, MUFI), a private-use code point (MUFI's, where MUFI has
one), the character it is a variant of, and notes. Unicode is one authority among several:
a sign's identity can be "number 561 in this catalogue" with no code point at all.

In a reading's TEXT the sign stays an ordinary private-use character (the ruled default), so
search, comparison and every existing reader of a reading keep working. This record is what
that character MEANS. One live sign per code point in a project: a code point that named two
signs would name neither.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from fichero_server.core.timeutil import utc_now
from fichero_server.models.knowledge import ProvenanceKind

#: `U+F1AC`: the form a code point is stored and exchanged in.
CODE_POINT = re.compile(r"^U\+[0-9A-F]{4,6}$")


def _new_id() -> str:
    return uuid.uuid4().hex


def code_point_char(code_point: str) -> str:
    """`"U+F1AC"` -> the character itself."""
    return chr(int(code_point[2:], 16))


def is_private_use(ch: str) -> bool:
    """The Basic Multilingual Plane's private-use block and the two supplementary planes."""
    cp = ord(ch)
    return 0xE000 <= cp <= 0xF8FF or 0xF0000 <= cp <= 0xFFFFD or 0x100000 <= cp <= 0x10FFFD


class SignListReference(BaseModel):
    """"Number 561 in this catalogue": the authority and the sign's number in its list."""

    authority: str
    number: str


class DeclaredSign(BaseModel):
    """One declared sign in a project's sign list (`source.sign.declared`, `.project-list`)."""

    id: str = Field(default_factory=_new_id)
    name: str
    #: The segment the sign was declared from: its picture is that segment's
    #: (`source.sign.declared`: "a picture cut from a real page").
    picture_segment_id: str
    #: `U+F1AC`, or None for a sign known only by a sign-list number.
    code_point: str | None = None
    #: Sign-list identities (`source.sign.list-authority`), none required.
    list_references: list[dict[str, Any]] = Field(default_factory=list)
    #: A VARIANT form of an encoded character (`source.sign.variants`): the character, and
    #: which variant -- a long s, one of a Chinese character's forms.
    variant_of: str | None = None
    variant: str | None = None
    notes: str | None = None
    #: Set by the engine from how the write arrived, never by the caller.
    provenance_kind: ProvenanceKind = ProvenanceKind.unknown
    created_by: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    #: Withdrawn, not deleted: a sign readings still use must stay resolvable.
    deleted_at: datetime | None = None

    @field_validator("code_point")
    @classmethod
    def _code_point_form(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        if not CODE_POINT.match(value):
            raise ValueError(f"a code point is written U+XXXX, not {value!r}")
        return value
