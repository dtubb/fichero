"""The security-header contract, asserted so it can actually fail.

``tests/unit/mcp/test_integration_security.py::test_security_headers_present``
loops over required headers and calls ``pytest.skip`` the moment one is
absent. Absence is the *only* thing that test could ever have reported, and
absence is routed into a skip — so it has reported SKIPPED on every run since
it was written, and would keep doing so if the headers were removed
tomorrow. It is a green line that means nothing.

Verified live: that test currently skips with "Security header
x-content-type-options not implemented yet". The header really is missing;
the vacuous test concealed a genuine gap rather than a hypothetical one.

This module pins the contract instead. It asserts ONE header —
``X-Content-Type-Options: nosniff`` — deliberately:

* It is the header that matters for this server. Every API response here is
  JSON; without ``nosniff`` a browser may MIME-sniff a response body and
  execute it as another type, which is a live concern for a server that
  returns user-supplied document text and is reachable from a browser over
  the Tailscale/loopback transport.
* The original list also demanded ``X-XSS-Protection``. That header is
  obsolete and browsers have removed it; some legacy implementations
  introduced vulnerabilities of their own. Reproducing it would be pinning
  bad advice, so it is deliberately not asserted.
* ``X-Frame-Options`` is worth adding too, but it is a framing-policy
  decision with a modern CSP alternative (``frame-ancestors``). Choosing
  between them is product design, not a test's call, so this module leaves
  it out rather than forcing a hand.

EXPECTED TO FAIL until the header is added — that failure is the finding.
The assertion is on the response header, never on any message text.
"""

from __future__ import annotations

import pytest

# Endpoints chosen to cover both a data route and a system route, so a
# header added by one router alone does not look like global coverage.
API_PATHS = [
    "/api/workflows",
    "/api/entities",
]


@pytest.mark.parametrize("path", API_PATHS)
def test_api_responses_declare_nosniff(client, path: str):
    """Every API response must forbid MIME sniffing."""
    response = client.get(path)

    # Precondition: the route must actually answer, or this test would pass
    # or fail for the wrong reason. A 404 here means the path moved and the
    # assertion below is measuring nothing.
    assert response.status_code != 404, (
        f"{path} returned 404 — this test is no longer exercising a real "
        "endpoint and would be vacuous"
    )

    header = response.headers.get("x-content-type-options")
    assert header is not None, (
        f"{path} response carries no X-Content-Type-Options header; a browser "
        "may MIME-sniff the JSON body and treat it as another content type"
    )
    assert header.lower() == "nosniff", (
        f"{path} sent X-Content-Type-Options: {header!r}, expected 'nosniff'"
    )
