"""A Mac's memory and a model's size are said in the GB the Mac says (powers of 1024), from one helper (#5833)."""
from __future__ import annotations

from fichero_server.llm import local_model_facts as facts
from fichero_server.llm.mlx_model_store import _format_bytes
from fichero_server.recipes import places, train_offers

SIXTEEN = 16 * 1024**3


def test_16_gib_of_bytes_reads_16_gb():
    assert facts.gib(SIXTEEN) == 16.0
    assert facts._memory_gb_label(SIXTEEN) == "16 GB"


def test_this_mac_memory_is_in_gib(monkeypatch):
    monkeypatch.setattr("os.sysconf", lambda name: 16384 if name == "SC_PAGE_SIZE" else SIXTEEN // 16384)
    assert train_offers.this_mac_memory_gb() == 16.0
    assert "16 GB" in places.this_mac_line(train_offers.this_mac_memory_gb())


def test_a_model_size_is_in_gib():
    assert _format_bytes(SIXTEEN) == "16.0 GB"
