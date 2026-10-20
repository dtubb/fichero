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
def _restore_vision(monkeypatch, tmp_path):
    from fichero_server import llm

    monkeypatch.setenv("FICHERO_BASE_PATH", str(tmp_path / "state"))  # a scratch dir, as the guard demands
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
    ledger.reserve(0.05)
    with pytest.raises(ab.CapReached):
        ledger.reserve(0.01)  # the held 0.05 counts: spent + held + this > cap
    ledger.settle(0.05, 0.02)
    assert ledger.spent == pytest.approx(0.97) and ledger.reserved == 0


def test_four_calls_at_once_at_a_cap_that_fits_two_make_only_two(monkeypatch):
    """Review 485: each passed the check before any settled; the worst case is now reserved at check time."""
    import asyncio

    from fichero_server import llm
    from fichero_server.llm import model_types

    monkeypatch.setattr(model_types, "estimate_cost", lambda model, i, o: (i + o) * 2e-4)
    made = []

    async def real(images, prompt, config, **kw):
        made.append(1)
        await asyncio.sleep(0.05)  # every call is under way before any ends
        return "[]"

    monkeypatch.setattr(llm, "vision", real)
    ledger = ab.Ledger(cap=1.0)
    config = ab.install_model("anthropic:cheap", ledger)
    config.max_tokens = 1000  # worst case: (1000 prompt tokens + 1000 answer) * 2e-4 = 0.40

    async def four():
        return await asyncio.gather(*(llm.vision(images=[], prompt="x" * 4000, config=config) for _ in range(4)),
                                    return_exceptions=True)

    results = asyncio.run(four())
    assert sum(isinstance(r, ab.CapReached) for r in results) == 2 and len(made) == 2, results
    assert ledger.reserved == 0 and ledger.spent <= 1.0


def test_the_real_cost_is_the_calls_reported_tokens_when_it_reports_any(monkeypatch):
    import asyncio

    from fichero_server import llm
    from fichero_server.llm import model_types

    monkeypatch.setattr(model_types, "estimate_cost", lambda model, i, o: (i + o) * 1e-3)

    async def real(images, prompt, config, **kw):
        llm._usage_collector.get().append({"input_tokens": 100, "output_tokens": 50})
        return "[]"

    monkeypatch.setattr(llm, "vision", real)
    ledger = ab.Ledger(cap=10.0)
    config = ab.install_model("anthropic:cheap", ledger)
    asyncio.run(llm.vision(images=[], prompt="x" * 4000, config=config))
    assert ledger.spent == pytest.approx(0.15), "100 + 50 reported tokens, not the 1000-token estimate"


def test_it_refuses_to_run_without_a_scratch_state_dir_or_inside_the_owners_places(monkeypatch, tmp_path):
    monkeypatch.delenv("FICHERO_BASE_PATH", raising=False)
    with pytest.raises(SystemExit, match="FICHERO_BASE_PATH"):
        ab.require_scratch_state()
    for place in ("Library/Application Support/Fichero", "Fichero", "Fichero Projects/Mosquera.fichero", "Library"):
        monkeypatch.setenv("FICHERO_BASE_PATH", str(Path.home() / place))
        with pytest.raises(SystemExit, match="scratch"):
            ab.require_scratch_state()
    monkeypatch.setenv("FICHERO_BASE_PATH", str(tmp_path))
    ab.require_scratch_state()


def test_a_symlink_dotdot_or_other_case_cannot_slip_past(monkeypatch, tmp_path):
    link = tmp_path / "innocent"
    link.symlink_to(Path.home() / "Fichero Projects")
    sneaky = [str(link), str(Path.home() / "Fichero" / ".." / "Fichero" / "sub"), str(Path.home() / "fichero projects")]
    for value in sneaky:
        monkeypatch.setenv("FICHERO_BASE_PATH", value)
        with pytest.raises(SystemExit, match="scratch"):
            ab.require_scratch_state()

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


def test_run_itself_refuses_without_the_guard_not_only_main(monkeypatch, tmp_path):
    monkeypatch.delenv("FICHERO_BASE_PATH", raising=False)
    with pytest.raises(SystemExit, match="FICHERO_BASE_PATH"):
        ab.run(_pages(tmp_path), tmp_path / "out", model="fake", reference_model=None, bar=0.6, cap=1.0,
               reader_ref="unused", language="es", kraken=_stub_kraken)


# ---------------------------------------------------------------- the free arms (#5894, the bake-off)


def _reader(texts: dict[str, str]):
    """A fake arm reader: line id -> text, whatever the page."""
    async def read(image, lines):
        return {line["id"]: texts[line["id"]] for line in lines if line["id"] in texts}

    return read


def _free_run(tmp_path, arms, readers, **kw):
    return ab.run(_pages(tmp_path, 1), tmp_path / "out", model="fake", reference_model=None, bar=0.6, cap=1.0,
                  reader_ref="unused", language="es", kraken=_stub_kraken, arms=arms, readers=readers, **kw)


def test_arms_parse_with_kraken_always_first_and_a_bad_arm_refused():
    assert ab.parse_arms("kraken,A,B") == ["kraken", "A", "B"]
    assert ab.parse_arms("vision,mlx:auto") == ["kraken", "vision", "mlx:auto"], "kraken is always an arm: the lines are its"
    with pytest.raises(SystemExit, match="--arms"):
        ab.parse_arms("kraken,gpt")


def test_each_arm_text_lands_on_its_line_id_and_the_reference_is_the_strongest_free_arm(tmp_path):
    readers = {"vision": _reader({"0": "hola", "1": "mundo", "2": "adios"}),
               "mlx:Qwen2.5-VL-7B": _reader({"0": "hola", "1": "mundo!", "2": "adiós"})}
    report = _free_run(tmp_path, ["kraken", "vision", "mlx:Qwen2.5-VL-7B"], readers)
    assert report["reference_arm"] == "mlx:Qwen2.5-VL-7B", "mlx is the strongest present"
    assert report["label"] == "model reference (mlx:Qwen2.5-VL-7B), not ground truth"
    assert json.loads((tmp_path / "out" / "lines.json").read_text())["arms"] == ["kraken", "vision", "mlx:Qwen2.5-VL-7B"]
    by = {r["id"]: r for r in json.loads((tmp_path / "out" / "lines.json").read_text())["lines"]}
    assert (by["1"]["kraken"], by["1"]["vision"], by["1"]["mlx:Qwen2.5-VL-7B"]) == ("mundo", "mundo", "mundo!")
    assert by["2"]["reference"] == "adiós" and report["cost"]["total"] == 0
    assert report["per_arm"]["vision"]["cer"] > 0 and report["per_arm"]["kraken"]["lines"] == 3
    assert all(report["per_arm"][a]["s_per_page"] is not None and report["per_arm"][a]["usd_per_page"] == 0
               for a in ("kraken", "vision"))


def test_reference_arm_can_be_named_and_a_arm_that_is_not_a_full_reading_is_refused(tmp_path):
    readers = {"vision": _reader({"0": "hola"}), "mlx:m": _reader({"0": "hola"})}
    assert _free_run(tmp_path, ["kraken", "vision", "mlx:m"], readers, reference_arm="vision")["reference_arm"] == "vision"
    with pytest.raises(SystemExit, match="reference-arm"):
        ab.reference_arm_for(["kraken", "A"], "A", False)
    with pytest.raises(SystemExit, match="only kraken"):
        ab.reference_arm_for(["kraken"], None, False)
    assert ab.reference_arm_for(["kraken", "A", "B"], None, True) is None, "with a cloud model it is the reference"


def test_a_failing_arm_leaves_its_cells_empty_with_a_reason_and_the_others_go_on(tmp_path):
    async def boom(image, lines):
        raise RuntimeError("Apple Vision can't read Spanish on this Mac")

    readers = {"vision": boom, "mlx:m": _reader({"0": "hola", "1": "mundo", "2": "adios"})}
    report = _free_run(tmp_path, ["kraken", "vision", "mlx:m"], readers)
    assert report["failures"] == [{"arm": "vision", "page": "p0.png", "why": "RuntimeError: Apple Vision can't read "
                                   "Spanish on this Mac"}]
    rows = json.loads((tmp_path / "out" / "lines.json").read_text())["lines"]
    assert all(r["vision"] == "" and r["mlx:m"] for r in rows)
    assert report["per_arm"]["vision"]["lines_read"] == 0 and report["per_arm"]["mlx:m"]["lines_read"] == 3
    md = (tmp_path / "out" / "report.md").read_text()
    assert "Arms that failed" in md and "Apple Vision can't read Spanish" in md


def test_agreement_counts_all_agree_and_split_lines_and_the_sheet_lists_the_splits_first(tmp_path):
    readers = {"vision": _reader({"0": "hola", "1": "mundo", "2": "xdios"}),
               "mlx:m": _reader({"0": "Hola ", "1": "mundo", "2": "adios"})}  # case and spacing do not split
    report = _free_run(tmp_path, ["kraken", "vision", "mlx:m"], readers)
    ag = report["agreement"]
    assert (ag["scored"], ag["all_agree"], ag["split"]) == (3, 2, 1) and ag["share_agree"] == pytest.approx(2 / 3)
    assert "A" not in ag["readers"]
    sheet = (tmp_path / "out" / "sheet.html").read_text()
    assert sheet.index("xdios") < sheet.index("<td>mundo"), "the split line comes first"
    assert "1 split" in (tmp_path / "out" / "report.md").read_text()


def test_two_readers_report_no_agreement_and_a_is_never_one(tmp_path):
    assert ab.agreement([{"kraken": "a", "A": "b", "B": "a"}], ["kraken", "A", "B"])["scored"] == 0
    rows = [{"kraken": "a", "B": "a", "vision": "a"}]
    assert ab.agreement(rows, ["kraken", "vision", "A", "B"])["all_agree"] == 1 and rows[0]["agreement"] == "agree"


def test_the_fake_arms_dry_run_works_anywhere_and_the_cloud_arms_are_unchanged(tmp_path):
    report = ab.run(_pages(tmp_path), tmp_path / "out", model="fake", reference_model=None, bar=0.6, cap=1.0,
                    reader_ref="unused", language="es", kraken=_stub_kraken,
                    arms=ab.parse_arms("vision,mlx:auto,A,B"), fake_arms=True)
    assert report["reference_arm"] is None and report["label"] == "model reference, not ground truth"
    rows = json.loads((tmp_path / "out" / "lines.json").read_text())["lines"]
    assert all(r["vision"] == ab.FAKE_ARM_TEXT["vision"] and r["mlx:auto"] == ab.FAKE_ARM_TEXT["mlx"] for r in rows)
    assert (report["A_lines_sent"], report["A_lines_total"]) == (4, 6) and report["agreement"]["scored"] == 6


def test_mlx_picks_only_an_installed_qwen_vl_inside_the_memory_gate_and_logs_why(monkeypatch):
    from fichero_server.llm import local_model_choice as choice
    from fichero_server.llm import mlx_model_store
    from fichero_server.llm.mlx_model_store import MANAGED_MLX_MODELS

    class Store:
        def __init__(self, done):
            self.done = done

        def is_complete(self, spec):
            return spec.model_id in self.done

    seven = MANAGED_MLX_MODELS["Qwen2.5-VL-7B"]
    monkeypatch.setattr(choice, "runs_here", lambda spec, cap="text", **k: (spec.model_id != "mlx-community/Qwen3-VL-8B",
                                                                           "needs 24 GB to read a page"))
    monkeypatch.setattr(mlx_model_store, "get_mlx_model_store", lambda: Store({seven.model_id}))
    logged = []
    name, config, why = ab.pick_mlx("auto", log=logged.append)
    assert name == f"mlx:{seven.model_id}" and config.provider == "omlx" and why["repo"] == seven.repo_id
    assert seven.repo_id in logged[0], "the repo id is logged"
    with pytest.raises(SystemExit, match="memory gate"):
        ab.pick_mlx("mlx-community/Qwen3-VL-8B")
    monkeypatch.setattr(mlx_model_store, "get_mlx_model_store", lambda: Store(set()))
    with pytest.raises(SystemExit, match="never downloads"):
        ab.pick_mlx("Qwen2.5-VL-7B")
    with pytest.raises(SystemExit, match="not a Qwen VL"):
        ab.pick_mlx("Chandra-OCR")


def test_the_reference_arm_is_not_scored_against_itself(tmp_path):
    readers = {"vision": _reader({"0": "hola", "1": "mundo", "2": "adios"}), "mlx:m": _reader({"0": "hola", "1": "mundo", "2": "adios"})}
    report = _free_run(tmp_path, ["kraken", "vision", "mlx:m"], readers)
    assert report["per_arm"]["mlx:m"]["cer"] is None and report["per_arm"]["mlx:m"]["is_reference"]
    assert report["per_arm"]["vision"]["cer"] == 0.0
    assert "| the reference | the reference |" in (tmp_path / "out" / "report.md").read_text()


def test_a_cloud_reference_that_fails_leaves_its_cells_empty_and_the_run_goes_on(tmp_path, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("the reference model is unreachable")

    monkeypatch.setattr(ab, "reading_by_model", boom)
    report = ab.run(_pages(tmp_path), tmp_path / "out", model="fake", reference_model="fake", bar=0.6, cap=1.0,
                    reader_ref="unused", language="es", kraken=_stub_kraken, arms=["kraken", "B"])
    assert {f["arm"] for f in report["failures"]} >= {"reference", "B"} and report["pages_done"] == 2
    assert report["lines_with_reference"] == 0


def test_cer_is_also_reported_over_lines_at_least_120_px_wide_and_the_fragments_are_counted(tmp_path):
    """`source.recipe.reader-variants-measured`: a polygon under 120 px wide is a fragment, not a line; a reader that
    rightly returns nothing for it must not look as if it failed, so every arm is scored a second time without them."""
    def kraken(image, reader):
        lines = _stub_kraken(image, reader)
        lines[1]["polygon"] = [[10, 50], [60, 50], [60, 80], [10, 80]]  # 50 px wide: a fragment
        return lines

    readers = {"vision": _reader({"0": "hola", "1": "", "2": "adios"}),
               "mlx:m": _reader({"0": "hola", "1": "mundo", "2": "adios"})}
    report = ab.run(_pages(tmp_path, 1), tmp_path / "out", model="fake", reference_model=None, bar=0.6, cap=1.0,
                    reader_ref="unused", language="es", kraken=kraken, arms=["kraken", "vision", "mlx:m"], readers=readers)
    assert report["fragments"] == {"px": 120, "lines": 1, "of": 3}
    assert report["per_arm"]["vision"]["cer"] > 0, "over every line the fragment's empty read counts as a deletion"
    assert report["per_arm"]["vision"]["wide"]["cer"] == 0.0 and report["per_arm"]["vision"]["wide"]["lines"] == 2
    assert report["per_arm"]["mlx:m"]["wide"] is None, "the reference arm is not scored against itself"
    md = (tmp_path / "out" / "report.md").read_text()
    assert "at least 120 px wide" in md and "1 of 3 lines are narrower" in md
