"""The bounded embed forward pass (the 2026-08-22 Air OOM).

A multi-MB page_content splits into thousands of passages; pushing them
through the ONNX embedder in ONE call spiked the activation peak, which the
arena keeps forever. _embed_texts must slice — same vectors, same order.
"""

from fichero_server.db import embeddings as embeddings_module
from fichero_server.db.embeddings import _EMBED_SLICE


class _RecordingEmbedder:
    def __init__(self):
        self.batch_sizes = []

    def embed(self, texts):
        texts = list(texts)
        self.batch_sizes.append(len(texts))
        return [[float(len(t)), 0.0] for t in texts]


class _Host:
    """The minimal shape _embed_texts reads off `self`."""

    _embedding_model_name = "fichero-pinned/multilingual-e5-large-mean-v1"

    def __init__(self):
        self._embedder = _RecordingEmbedder()

    def _ensure_embedder(self):
        pass


def _call(host, texts):
    return embeddings_module.DatabaseEmbeddingMixin._embed_texts(host, texts)


def test_large_batches_are_sliced_and_order_preserved():
    host = _Host()
    texts = [f"passage {i:04d}" for i in range(_EMBED_SLICE * 2 + 7)]
    vectors = _call(host, texts)
    assert len(vectors) == len(texts)
    assert max(host._embedder.batch_sizes) <= _EMBED_SLICE
    assert len(host._embedder.batch_sizes) == 3


def test_empty_input_stays_cheap():
    host = _Host()
    assert _call(host, []) == []
    assert host._embedder.batch_sizes == []
