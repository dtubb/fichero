"""Offline tests for the script_coverage PRODUCER.

No real tokenizer, no network. A tiny FakeTokenizer wires each character to a
loove tier so classification and coverage/fertility math are deterministic.

Two things are asserted:
  1. coverage_for_model returns a valid language_coverage.LanguageCoverageRecord.
  2. write_coverage_record → evaluate_language_fit round-trips: the JSON the
     producer writes is read back by the existing consumer and yields the
     expected status / score_band / tier counts.
"""

from __future__ import annotations

import re

from fichero_server.llm import script_coverage as sc
from fichero_server.llm import language_coverage as lc
from fichero_server.llm.language_coverage import LanguageCoverageRecord

_BYTE_RE = re.compile(r"<0x([0-9A-Fa-f]{2})>")


class FakeTokenizer:
    """Configurable char->token mapping mimicking tiktoken/HF surface.

    - tier 0: one dedicated token decoding to the char
    - tier 1: >1 clean token (char + empty token) that round-trip together
    - tier 2: raw UTF-8 byte-fallback tokens (pieces like ``<0xD1>``)
    - tier 3: unregistered char -> unk token decoding to "" (no round-trip)
    """

    def __init__(self) -> None:
        self._pieces: dict[int, str] = {}
        self._char_ids: dict[str, list[int]] = {}
        self._next = 1
        self._unk = self._add_piece("")
        self._empty = self._add_piece("")

    def _add_piece(self, piece: str) -> int:
        i = self._next
        self._next += 1
        self._pieces[i] = piece
        return i

    def add_tier0(self, char: str) -> None:
        self._char_ids[char] = [self._add_piece(char)]

    def add_tier1(self, char: str) -> None:
        self._char_ids[char] = [self._add_piece(char), self._empty]

    def add_tier2(self, char: str) -> None:
        ids = [self._add_piece(f"<0x{b:02X}>") for b in char.encode("utf-8")]
        self._char_ids[char] = ids

    def encode(self, text: str) -> list[int]:
        ids: list[int] = []
        for ch in text:
            ids.extend(self._char_ids.get(ch, [self._unk]))
        return ids

    def decode(self, ids: list[int]) -> str:
        out = ""
        buf = bytearray()
        for i in ids:
            piece = self._pieces.get(i, "")
            if _BYTE_RE.fullmatch(piece):
                buf.append(int(piece[3:5], 16))
                continue
            if buf:
                out += buf.decode("utf-8", errors="replace")
                buf = bytearray()
            out += piece
        if buf:
            out += buf.decode("utf-8", errors="replace")
        return out


def _tok_all_tier0(*strings: str) -> FakeTokenizer:
    tok = FakeTokenizer()
    seen: set[str] = set()
    for s in strings:
        for ch in s:
            if ch not in seen:
                tok.add_tier0(ch)
                seen.add(ch)
    return tok


def test_classify_char_all_tiers() -> None:
    tok = FakeTokenizer()
    tok.add_tier0("a")
    tok.add_tier1("b")
    tok.add_tier2("я")  # 2-byte UTF-8 -> byte fallback
    assert sc.classify_char(tok, "a") == 0
    assert sc.classify_char(tok, "b") == 1
    assert sc.classify_char(tok, "я") == 2
    assert sc.classify_char(tok, "z") == 3  # unregistered


def test_coverage_for_model_returns_valid_record() -> None:
    greek = sc.SCRIPT_EXEMPLARS["Greek"]
    tok = _tok_all_tier0(greek, sc.SCRIPT_SAMPLES["Greek"])
    record = sc.coverage_for_model("gpt-fake", lc.language_spec("el"), tokenizer=tok)
    assert isinstance(record, LanguageCoverageRecord)
    assert record.status == "derived"
    assert record.coverage_score == 1.0
    assert record.score_band == "excellent"
    assert record.tier_counts.tier_0_native == len(greek)
    assert record.tier_counts.total_chars == len(greek)
    assert record.fertility.sample_chars == len(sc.SCRIPT_SAMPLES["Greek"])


def test_unknown_char_lowers_score_and_band() -> None:
    greek = sc.SCRIPT_EXEMPLARS["Greek"]
    tok = _tok_all_tier0(greek[:-1])  # last exemplar unregistered -> tier3
    record = sc.coverage_for_model("gpt-fake", lc.language_spec("el"), tokenizer=tok)
    n = len(greek)
    assert record.coverage_score == (n - 1) / n
    assert record.tier_counts.tier_3_unreachable == 1


def test_unmapped_script_is_unsupported() -> None:
    # Hindi -> Devanagari, no exemplar table -> unsupported_language, no guess.
    tok = FakeTokenizer()
    record = sc.coverage_for_model("gpt-fake", lc.language_spec("hi"), tokenizer=tok)
    assert record.status == "unsupported_language"
    assert record.coverage_score is None
    assert record.score_band == "unknown"


def test_no_tokenizer_is_honest_unknown() -> None:
    original = sc.load_tokenizer
    try:
        sc.load_tokenizer = lambda model_id: None  # type: ignore[assignment]
        record = sc.coverage_for_model("no-tokenizer-model", lc.language_spec("en"))
        assert record.coverage_score is None
        assert record.score_band == "unknown"
        assert sc.TOKENIZER_UNAVAILABLE in record.source.notes
        assert record.tier_counts is None
    finally:
        sc.load_tokenizer = original  # type: ignore[assignment]


def test_roundtrip_producer_to_consumer_excellent(tmp_path) -> None:
    """Produce JSON, load via evaluate_language_fit, assert derived + band."""
    greek = sc.SCRIPT_EXEMPLARS["Greek"]
    tok = _tok_all_tier0(greek, sc.SCRIPT_SAMPLES["Greek"])
    path = sc.write_coverage_record(
        "gpt-fake", lc.language_spec("el"), provider="openai",
        tokenizer=tok, coverage_dir=tmp_path,
    )
    assert path.is_file()

    record = lc.evaluate_language_fit(
        lc.normalize_model_spec("openai", "gpt-fake"),
        lc.language_spec("el"),
        coverage_dir=tmp_path,
    )
    assert record.status == "derived"
    assert record.coverage_score == 1.0
    assert record.score_band == "excellent"
    assert record.tier_counts.tier_0_native == len(greek)
    assert record.source.kind == "loove_derived_json"


def test_roundtrip_byte_fallback_is_poor(tmp_path) -> None:
    """A byte-fallback-only script scores 0.2 -> 'poor' after round-trip."""
    cyr = sc.SCRIPT_EXEMPLARS["Cyrillic"]
    tok = FakeTokenizer()
    for ch in cyr:
        tok.add_tier2(ch)
    tok.add_tier0(" ")
    for ch in sc.SCRIPT_SAMPLES["Cyrillic"]:
        if ch not in cyr and ch != " ":
            tok.add_tier2(ch)
    sc.write_coverage_record(
        "cyr-fake", lc.language_spec("ru"), provider="hf",
        tokenizer=tok, coverage_dir=tmp_path,
    )
    record = lc.evaluate_language_fit(
        lc.normalize_model_spec("hf", "cyr-fake"),
        lc.language_spec("ru"),
        coverage_dir=tmp_path,
    )
    assert record.status == "derived"
    assert abs(record.coverage_score - 0.2) < 1e-9
    assert record.score_band == "poor"
    assert record.tier_counts.tier_2_byte_fallback == len(cyr)


def test_roundtrip_two_scripts_accumulate_in_one_file(tmp_path) -> None:
    """A model file accrues one entry per detected script (merge, no clobber)."""
    tok = _tok_all_tier0(
        sc.SCRIPT_EXEMPLARS["Latin"], sc.SCRIPT_SAMPLES["Latin"],
        sc.SCRIPT_EXEMPLARS["Greek"], sc.SCRIPT_SAMPLES["Greek"],
    )
    sc.write_coverage_record("m", lc.language_spec("en"), tokenizer=tok, coverage_dir=tmp_path)
    p = sc.write_coverage_record("m", lc.language_spec("el"), tokenizer=tok, coverage_dir=tmp_path)
    import json
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert set(doc["coverage"]) == {"en", "el"}  # both languages present
    for code in ("en", "el"):
        rec = lc.evaluate_language_fit(
            lc.normalize_model_spec("x", "m"), lc.language_spec(code), coverage_dir=tmp_path,
        )
        assert rec.status == "derived"
        assert rec.coverage_score == 1.0


def test_written_filename_matches_consumer_lookup(tmp_path) -> None:
    tok = _tok_all_tier0(sc.SCRIPT_EXEMPLARS["Latin"], sc.SCRIPT_SAMPLES["Latin"])
    path = sc.write_coverage_record(
        "GPT 4o", lc.language_spec("en"), provider="OpenAI",
        tokenizer=tok, coverage_dir=tmp_path,
    )
    expected = lc._coverage_file_for(
        lc.normalize_model_spec("OpenAI", "GPT 4o"), tmp_path
    )
    assert path == expected
