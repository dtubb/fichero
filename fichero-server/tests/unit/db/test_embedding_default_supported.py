"""Guards for the default embedding model (#1524).

The pre-warm path in api/main.py imports DEFAULT_MODEL from db.py, while the
real embedder uses db_embeddings.DEFAULT_MODEL. They must agree AND must be a
model that the installed fastembed actually supports — otherwise startup logs
"Model ... is not supported in TextEmbedding" and pre-warm never succeeds.
"""

from __future__ import annotations

import pytest


def test_default_embedding_model_stays_pinned_until_migration_exists() -> None:
    from fichero_server.db.embeddings import DEFAULT_MODEL

    assert DEFAULT_MODEL == "intfloat/multilingual-e5-large"


def _supported_models() -> set[str]:
    from fastembed import TextEmbedding

    return {m["model"] for m in TextEmbedding.list_supported_models()}


def test_db_default_model_is_fastembed_supported() -> None:
    from fichero_server.db import DEFAULT_MODEL

    supported = _supported_models()
    if DEFAULT_MODEL == "BAAI/bge-m3" and DEFAULT_MODEL not in supported:
        pytest.skip("installed fastembed TextEmbedding catalog does not include BAAI/bge-m3")
    assert DEFAULT_MODEL in supported, (
        f"db.DEFAULT_MODEL={DEFAULT_MODEL!r} is not supported by the installed "
        f"fastembed (this breaks the embeddings pre-warm, #1524)"
    )


def test_db_embeddings_default_model_is_fastembed_supported() -> None:
    from fichero_server.db.embeddings import DEFAULT_MODEL

    if DEFAULT_MODEL == "BAAI/bge-m3" and DEFAULT_MODEL not in _supported_models():
        pytest.skip("installed fastembed TextEmbedding catalog does not include BAAI/bge-m3")
    assert DEFAULT_MODEL in _supported_models(), (
        f"db_embeddings.DEFAULT_MODEL={DEFAULT_MODEL!r} is not supported by "
        f"the installed fastembed"
    )


def test_db_and_embeddings_defaults_agree() -> None:
    from fichero_server.db import DEFAULT_MODEL as db_default
    from fichero_server.db.embeddings import DEFAULT_MODEL as embed_default

    assert db_default == embed_default, (
        "db.DEFAULT_MODEL and db_embeddings.DEFAULT_MODEL diverged — the "
        "pre-warm model must match the model the real embedder uses (#1524)"
    )
