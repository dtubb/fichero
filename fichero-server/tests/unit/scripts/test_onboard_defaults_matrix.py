"""The pure parts of scripts/onboard_defaults_matrix.py (#5969): the truth table, PAGE and ALTO text, the error rates, the verdict."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "onboard_defaults_matrix.py"
spec = importlib.util.spec_from_file_location("onboard_defaults_matrix", SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

PAGE = """<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"><Page><TextRegion primaryLanguage="Syriac">
<TextLine><Word><TextEquiv><Unicode>no</Unicode></TextEquiv></Word><TextEquiv><Unicode>uno dos</Unicode></TextEquiv></TextLine>
<TextLine><TextEquiv><Unicode>tres</Unicode></TextEquiv></TextLine></TextRegion></Page></PcGts>"""
ALTO = """<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#"><Layout><Page><PrintSpace><TextBlock LANG="hi"><TextLine>
<String CONTENT="un"/><String CONTENT="dos"/></TextLine><TextLine><String CONTENT="tres"/></TextLine></TextBlock></PrintSpace></Page></Layout></alto>"""


def test_page_text_takes_the_lines_own_text_not_its_words(tmp_path):
    f = tmp_path / "a.xml"
    f.write_text(PAGE)
    got = m.page_truth(f)
    assert got["text"] == "uno dos tres" and got["lines"] == 2 and got["languages"] == ["Syriac"]


def test_alto_text_joins_the_strings_of_each_line(tmp_path):
    f = tmp_path / "a.xml"
    f.write_text(ALTO)
    got = m.page_truth(f)
    assert got["text"] == "un dos tres" and got["languages"] == ["hi"]


def test_a_file_that_is_not_xml_gives_no_text(tmp_path):
    f = tmp_path / "a.xml"
    f.write_text("not xml")
    assert m.page_truth(f) == {"text": "", "lines": 0, "languages": []}


def test_error_rates_count_characters_and_words():
    assert m.error_rates("abcd", "abcd") == {"cer": 0.0, "wer": 0.0}
    got = m.error_rates("uno dos", "uno dis")
    assert abs(got["cer"] - 1 / 7) < 1e-9 and got["wer"] == 0.5
    assert m.error_rates("", "x") == {"cer": None, "wer": None}


def test_the_longest_matching_prefix_gives_the_truth_and_an_unknown_set_gives_none():
    assert m.truth_for("Syriac - Jerusalem MS 36, eScriptorium ALTO (right-to-left)")["scripts"] == ["Syrc"]
    assert m.truth_for("Syriac - Vienna Cod. Syr. 1 (right-to-left)")["direction"] == "rtl"
    assert m.truth_for("Klingon - a set nobody listed") is None


def test_every_truth_row_is_complete():
    for key, row in m.TRUTH.items():
        assert row["languages"] and row["scripts"] and row["direction"] in {"ltr", "rtl", "ttb", "ttb-lr"}, key
        assert row["material"] in {"handwriting", "print", "typescript"} and row["classes"], key


def test_the_verdict_names_a_wrong_direction_and_a_missing_reader_in_words():
    truth = {"direction": "rtl", "classes": ["rtl"]}
    assert m.judge(truth, {"direction": {"Arab": "ltr"}, "steps": {}}) == "WRONG-direction"
    assert m.judge(truth, {"direction": {"Arab": "rtl"}, "steps": {"read-a-line": {"card": "kraken:x"}}}) == "ok"
    assert m.judge(truth, {"direction": {"Arab": "rtl"}, "steps": {"read-a-line": {"card": None, "problem": "no-model-for-script"}}}) == "none-says-so"
    assert m.judge(truth, {"refused": "words"}) == "refused"


def test_apple_vision_stuck_stops_the_vision_arm_for_the_rest_of_the_run(tmp_path, monkeypatch):
    """Past its ceiling the engine refuses Apple Vision calls at once (#5392): the matrix stops asking (stall of 2026-10-21)."""
    import sys
    import types

    class AppleVisionStuck(RuntimeError):
        pass

    calls = []
    fake = types.ModuleType("ab_kraken_cloud")
    fake.kraken_lines = lambda image, reader: [{"id": "0", "text": "a"}]

    def free_reader(arm, fake):
        async def read(image, lines):
            calls.append(image.name)
            raise AppleVisionStuck("did not finish")
        return read

    fake.free_reader = free_reader
    monkeypatch.setitem(sys.modules, "ab_kraken_cloud", fake)
    monkeypatch.setattr(m, "_VISION_STUCK", [])
    pages = [(tmp_path / f"{n}.png", None) for n in "abc"]
    first = m.read_pages("vision", pages, "reader")
    assert calls == ["a.png"] and len(first) == 3  # the first page timed out; the others were not tried
    assert first[0]["error"].startswith("AppleVisionStuck: did not") and "not tried" in first[1]["error"]
    again = m.read_pages("vision", pages, "reader")  # the next set of the run
    assert calls == ["a.png"] and all("not tried" in r["error"] for r in again)
    assert m.read_pages("seed", pages, "reader")[0].get("error", "").startswith("AppleVisionStuck") is False  # the seed arm still reads
