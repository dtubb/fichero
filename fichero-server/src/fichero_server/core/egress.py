"""One check for anything that carries library content off this Mac (`source.egress.every-call-site`).

A model call meets `llm._enforce_local_only_provider`; every OTHER place the engine sends something the person's library
holds (a place name to a geocoder, a name to Wikidata, a DOI to Crossref, an agent's web query, a copy to another Mac)
meets `check_egress`, which reads the same two things: the local-only setting and the Set Up answer on where pages may go.
A place is `cloud` (a service on the internet) or `another-mac` (the person's own machine). A refusal is in words.
Fichero's own fetches that carry no library content (model downloads, the price list, Hub searches) do not call it; the
guardrail (`tests/unit/llm/test_egress_gate_every_call_site.py`) lists each one with its reason.
"""
from __future__ import annotations

from fichero_server.recipes.places import PLACE_WORDS, allows


class EgressRefused(RuntimeError):
    """The person's answer does not let this leave the Mac."""


def check_egress(place: str, *, what: str, to: str) -> None:
    """Raise `EgressRefused`, in words, if `what` may not be sent to `to` (a `place`: `cloud` or `another-mac`)."""
    from fichero_server.llm import is_local_only

    if not allows(place):
        raise EgressRefused(
            f"Your places do not include {PLACE_WORDS.get(place, place)}, so {what} is not sent to {to}. "
            "Allow it in Set Up Fichero… under where models may run."
        )
    if is_local_only():
        raise EgressRefused(f"Local-only mode is on, so {what} is not sent to {to}.")


def install_handler(app) -> None:
    """Answer `EgressRefused` as 403 with its words."""
    from fastapi import Request
    from fastapi.responses import JSONResponse

    @app.exception_handler(EgressRefused)
    async def _refuse(_request: Request, exc: EgressRefused) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})
