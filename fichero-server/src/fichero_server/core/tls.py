"""HTTPS for the standard library's `urllib` inside the app.

The bundled engine's Python has no system certificate store wired up, so a plain `urlopen` of an
https URL fails in the app with CERTIFICATE_VERIFY_FAILED (seen 2026-10-09 on a spaCy download from
the Dev Embedded build). certifi's bundle ships with the engine (httpx needs it), so every `urllib`
download passes this context. httpx already uses certifi by itself.
"""

from __future__ import annotations

import functools
import ssl


@functools.cache
def https_context() -> ssl.SSLContext:
    """A verifying TLS context on certifi's CA bundle."""
    import certifi  # noqa: PLC0415 (lazy: importing this module stays cheap)

    return ssl.create_default_context(cafile=certifi.where())
