"""A Kraken reader reads lines in the engine's own process (2026-10-10, overnight check in the Dev Embedded app).

Kraken's default `num_line_workers` (2) extracts lines in a multiprocessing Pool; creating its semaphore raises
"[Errno 1] Operation not permitted" in the app sandbox, so every reader failed in the app and worked in a
terminal. With 0, Kraken takes its own in-process path. Proven in the app by reading pages in a sandboxed
Dev Embedded build; this pins the setting.
"""

from __future__ import annotations

import pytest

kraken_configs = pytest.importorskip("kraken.configs")


def test_the_reader_config_extracts_lines_in_process():
    from fichero_server.llm.kraken_runtime import _reader_config

    assert _reader_config(kraken_configs.RecognitionInferenceConfig).num_line_workers == 0
