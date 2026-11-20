"""Kraken's memory guard is sized by the page's network megapixels, not a flat 2.5 GB (runner.measured, perf-1)."""
from fichero_server.llm import kraken_runtime as kr

GIB = 1024**3


def test_network_megapixels_scale_the_page_to_1800_rows():
    assert kr.network_megapixels(1272, 1800) == 1272 * 1800 / 1e6
    assert abs(kr.network_megapixels(2480, 3508) - 1272 * 1800 / 1e6) < 0.01  # A4 at 300 dpi, the review's portrait page


def test_a_portrait_page_needs_about_1_9_gb_and_a_spread_about_3_4_gb(monkeypatch):
    monkeypatch.delenv(kr._MEMORY_NEED_ENV_VAR, raising=False)
    monkeypatch.setattr(kr, "_RESIDENT", {})
    token = kr._PAGE_MEGAPIXELS.set(kr.network_megapixels(2480, 3508))
    try:
        portrait = kr.kraken_need_bytes() / GIB
        kr._PAGE_MEGAPIXELS.set(kr.network_megapixels(4960, 3508))
        spread = kr.kraken_need_bytes() / GIB
    finally:
        kr._PAGE_MEGAPIXELS.reset(token)
    assert 1.8 < portrait < 2.0 and 3.1 < spread < 3.6


def test_no_page_known_keeps_the_flat_figure_and_the_env_override_wins(monkeypatch):
    monkeypatch.setattr(kr, "_RESIDENT", {})
    monkeypatch.delenv(kr._MEMORY_NEED_ENV_VAR, raising=False)
    assert kr.kraken_need_bytes() == int(2.5 * GIB)
    monkeypatch.setenv(kr._MEMORY_NEED_ENV_VAR, "1000")
    token = kr._PAGE_MEGAPIXELS.set(5.0)
    try:
        assert kr.kraken_need_bytes() == 1000 * 1024 * 1024
    finally:
        kr._PAGE_MEGAPIXELS.reset(token)


def test_segment_lines_sets_the_page_size_for_the_guard(tmp_path):
    from PIL import Image

    path = tmp_path / "p.png"
    Image.new("L", (360, 500)).save(path)
    seen = []

    def stop(op):
        seen.append(kr._PAGE_MEGAPIXELS.get())
        raise RuntimeError("stop")

    try:
        kr.segment_lines(path, run_call=stop)
    except Exception:  # noqa: BLE001 -- the call is stopped after the guard's figure is read
        pass
    assert seen == [kr.network_megapixels(360, 500)]
    assert kr._PAGE_MEGAPIXELS.get() is None  # restored
