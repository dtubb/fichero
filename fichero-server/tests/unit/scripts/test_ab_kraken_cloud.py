"""The A/B harness (#5894, `source.recipe.reader-variants-measured`): its measures, its cap, and a dry run with the fake
model over drawn pages and a stub Kraken, end to end. No network, no key, no Kraken model."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "ab_kraken_cloud.py"
_SPEC = importlib.util.spec_from_file_location("ab_kraken_cloud", _SCRIPT)
assert _SPEC and _SPEC.loader
ab = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = ab
_SPEC.loader.exec_module(ab)  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def _restore_vision():
    from fichero_server import llm

    real = llm.vision
    yield
    llm.vision = real
    ab._REAL_VISION = None


def test_rates_are_total_errors_over_total_reference_length():
    got = ab.rates([("abcd", "abxd"), ("hola mundo", "hola mundo"), ("", "ignored: no reference")])
    assert got["cer"] == pytest.approx(1 / 14) and got["wer"] == pytest.approx(1 / 3) and got["lines"] == 3


def test_calibration_says_whether_the_bad_lines_are_the_unsure_ones():
    lines = [{"reference": "abcdefghij", "kraken": "xxxxxxxxxx", "confidence": 0.2}]  # garbled and unsure
    lines += [{"reference": "abcdefghij", "kraken": "abcdefghij", "confidence": 0.9} for _ in range(9)]  # good and sure
    cal = ab.calibration(lines, bar=0.6)
    assert cal["worst_decile_lines"] == 1 and cal["worst_decile_below_bar"] == 1.0 and cal["good_below_bar"] == 0.0
    assert cal["share_sent"] == pytest.approx(0.1)
    confident = [dict(lines[0], confidence=0.95)] + lines[1:]  # Kraken confidently wrong: A cannot find it
    assert ab.calibration(confident, bar=0.6)["worst_decile_below_bar"] == 0.0
    unstated = [dict(lines[0], confidence=None)] + lines[1:]
    assert ab.calibration(unstated, bar=0.6)["worst_decile_below_bar"] == 1.0, "no stated certainty counts as unsure"


def test_the_ledger_refuses_a_call_that_would_pass_the_cap_before_it_is_made():
    ledger = ab.Ledger(cap=1.0)
    ledger.add(0.95)
    ledger.check(0.05)
    with pytest.raises(ab.CapReached):
        ledger.check(0.06)


def test_a_model_with_no_price_is_refused_because_a_cap_cannot_be_kept(monkeypatch):
    from fichero_server.llm import model_types

    monkeypatch.setattr(model_types, "estimate_cost", lambda *a, **k: None)
    with pytest.raises(SystemExit, match="no price"):
        ab.install_model("anthropic:made-up", ab.Ledger(cap=1.0))


def _pages(tmp_path: Path, n: int = 2) -> Path:
    folder = tmp_path / "pages"
    folder.mkdir()
    for i in range(n):
        im = Image.new("RGB", (400, 200), "white")
        ImageDraw.Draw(im).text((10, 10), f"page {i}", fill="black")
        im.save(folder / f"p{i}.png")
    return folder


def _stub_kraken(image, reader):
    """Three lines per page: one Kraken is sure of, one unsure, one with no stated certainty."""
    from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel

    out = []
    for i, (text, conf) in enumerate((("hola", 0.95), ("mundo", 0.30), ("adios", None))):
        y = 10 + 40 * i
        poly = [[10, y], [390, y], [390, y + 30], [10, y + 30]]
        box = OCRGeometryBox(text=text, bbox=[0.0, y / 200, 1.0, 0.15], level=OCRGeometryLevel.LINE, provider="kraken",
                             model="m", source="kraken-htr", confidence=conf,
                             metadata={"polygon_px": poly, "baseline_px": [[10, y + 25], [390, y + 25]],
                                       "pixel_frame": {"width": 400, "height": 200}})
        out.append({"id": str(i), "text": text, "confidence": conf, "polygon": poly, "box": box})
    return out


def test_the_dry_run_with_the_fake_model_measures_all_three_and_labels_the_reference(tmp_path):
    report = ab.run(_pages(tmp_path), tmp_path / "out", model="fake", reference_model=None, bar=0.6, cap=1.0,
                    reader_ref="unused", language="es", kraken=_stub_kraken)
    assert report["label"] == "model reference, not ground truth" and report["pages_done"] == 2
    assert (report["A_lines_sent"], report["A_lines_total"]) == (4, 6), "the unsure line and the one with no certainty"
    assert report["cost"]["total"] == 0 and report["cost"]["estimated"] is False and not report["stopped"]
    assert report["B"]["cer"] is not None and report["kraken"]["cer"] is not None
    text = (tmp_path / "out" / "report.md").read_text()
    assert "model reference, not ground truth" in text and "Calibration" in text and "Cost" in text
    rows = json.loads((tmp_path / "out" / "lines.json").read_text())["lines"]
    by = {(r["page"], r["id"]): r for r in rows}
    sure = by[("p0.png", "0")]
    assert sure["A"] == "hola" and not sure["sent_in_A"], "a sure line is not sent and keeps Kraken's text"
    assert by[("p0.png", "1")]["A"] == ab.FAKE_TEXT and by[("p0.png", "1")]["sent_in_A"]
    assert all(r["B"] == ab.FAKE_TEXT for r in rows) and all(r["reference"] == ab.FAKE_REFERENCE_TEXT for r in rows)
    assert "model reference, not ground truth" in (tmp_path / "out" / "sheet.html").read_text()


def test_a_real_model_is_priced_and_the_run_stops_at_the_cap_reporting_what_it_has(tmp_path, monkeypatch):
    from fichero_server import llm
    from fichero_server.llm import model_types

    monkeypatch.setattr(model_types, "estimate_cost", lambda model, i, o: (i + o) * 1e-3)
    calls = []

    async def real(images, prompt, config, **kw):
        calls.append(len(images))
        return json.dumps(["texto"] * len(images))

    monkeypatch.setattr(llm, "vision", real)
    report = ab.run(_pages(tmp_path, 3), tmp_path / "out", model="anthropic:cheap", reference_model=None, bar=0.6,
                    cap=1.0, reader_ref="unused", language="es", kraken=_stub_kraken)
    assert report["stopped"] and report["cost"]["total"] <= 1.0, report["cost"]
    assert report["pages_done"] < 3 and report["cost"]["estimated"] is True
    assert (tmp_path / "out" / "report.md").exists(), "a stopped run still writes what it has"
