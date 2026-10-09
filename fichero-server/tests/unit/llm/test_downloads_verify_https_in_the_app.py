"""A download from inside the app verifies HTTPS with the bundled CA list (2026-10-09).

The embedded engine's Python has no system certificate store wired up, so a bare `urlopen` failed in the
Dev Embedded build with CERTIFICATE_VERIFY_FAILED on a spaCy download. Every `urllib` download now passes
`core.tls.https_context()` (certifi's bundle). What breaks without this: the app's Download button for a
spaCy model fails in every embedded build while passing in a dev engine.
"""

from __future__ import annotations

import ssl
import urllib.request

import pytest

from fichero_server.core.tls import https_context
from fichero_server.llm import local_models


def test_the_context_verifies_certificates_and_hostnames():
    ctx = https_context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname
    assert ctx.cert_store_stats()["x509_ca"] > 0, "certifi's CA list is loaded"


def test_a_spacy_download_passes_the_verifying_context(monkeypatch, tmp_path):
    seen = {}

    def fake_urlopen(url, timeout=None, context=None):
        seen["context"] = context
        raise OSError("stop after the request is made")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(local_models, "MODELS_BASE", tmp_path)
    name = next(iter(local_models.SPACY_MODELS))
    with pytest.raises(OSError):
        local_models.download_spacy_pipeline(name)
    assert seen["context"] is https_context()
