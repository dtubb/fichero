"""The one body every refusal sends, and the statuses every operation declares it for (#5094).

`engine.error-detail-reaches-the-caller`: an undeclared status leaves the generated client unable to decode the
sentence a refusal sends. Declared once, on the app, so a new route is correct without remembering to.
"""
from __future__ import annotations

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
    """

    detail: str


#: Applied as `FastAPI(responses=...)`. 422 is FastAPI's own validation error and is left alone; a route's own
#: `responses=` entry wins over these.
REFUSAL_RESPONSES: dict[int | str, dict] = {
    status: {"model": ErrorDetail, "description": description}
    for status, description in (
        (400, "The request was refused; `detail` says why."),
        (403, "Not permitted; `detail` says why."),
        (404, "Not found; `detail` says what."),
        (409, "Conflicts with the current state; `detail` says how."),
    )
}
