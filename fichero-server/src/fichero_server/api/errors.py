"""The body a refusal sends (#5094).

`engine.error-detail-reaches-the-caller`: an undeclared status leaves the generated client unable to decode the
sentence a refusal sends. The app-wide declaration of these statuses was withdrawn (review 112): it made every
operation's 400/403/404/409 a typed case, which broke the Swift branches that read those statuses through
`.undocumented(...)`. Declare `responses={400: {"model": ErrorDetail}, ...}` per route where a client reads the body.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """The body this route's refusals actually send: `{"detail": "<a sentence>"}`.

    **Declared because it was not, and the omission ate the sentence** (#5089). Without
    a `responses=` entry FastAPI documents 422 as its own `HTTPValidationError`, whose
    `detail` is an ARRAY of field errors — and the generated Swift client decodes the
    body while producing the response, so a person picking the wrong file got a client
    decoding error instead of *"nothing recognises 'x.xml'. This build reads: …"*.
    **That sentence is the whole value of the refusal**: a scholar who chose the wrong
    file needs to be told what this build can read.

    The 409 is declared for the same reason even though it works today: it works only
    because nothing declared it, which is the same accident facing the other way.

    Some refusals carry a STRUCTURED detail instead of a sentence (a stale note's
    `current_body`, an ingest 403's `code`), so `detail` is a string or an object.
    """

    detail: str | dict[str, Any]
