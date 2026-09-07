"""Offline tests for the script_coverage PRODUCER.

No real tokenizer, no network. A tiny FakeTokenizer wires each character to a
specific loove tier so classification and the coverage/fertility math are
deterministic. The key assertion is the round-trip: the JSON this module
produces is loaded back by llm.language_coverage and yields the expected
LanguageCoverageRecord (status "derived", correct ScoreBand, tier counts).
"""

from __future__ import annotations

import re

from fichero_server.llm import script_coverage as sc
from fichero_server.llm import language_coverage as lc

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
            m = _BYTE_RE.fullmatch(piece)
            if m:
                buf.append(int(m.group(1), 16))
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


def test_payload_shape_and_tier_counts() -> None:
    greek = sc.SCRIPT_EXEMPLARS["Greek"]
    tok = _tok_all_tier0(greek, sc.SCRIPT_SAMPLES["Greek"])
    lang = lc.language_spec("el")  # Greek
    payload = sc.language_coverage_payload(tok, lang)
    assert payload is not None
    assert payload["coverage_score"] == 1.0
    tc = payload["tier_counts"]
    assert tc["tier_0_native"] == len(greek)
    assert tc["total_chars"] == len(greek)
    assert payload["fertility"]["sample_chars"] == len(sc.SCRIPT_SAMPLES["Greek"])


def test_unknown_char_lowers_score() -> None:
    greek = sc.SCRIPT_EXEMPLARS["Greek"]
    tok = _tok_all_tier0(greek[:-1])  # last exemplar left unregistered -> tier3
    payload = sc.language_coverage_payload(tok, lc.language_spec("el"))
    n = len(greek)
    assert payload["coverage_score"] == (n - 1) / n
    assert payload["tier_counts"]["tier_3_unreachable"] == 1


def test_unmapped_script_is_skipped() -> None:
    # Hindi -> Devanagari, which has no exemplar table -> None (consumer falls back).
    tok = FakeTokenizer()
    assert sc.language_coverage_payload(tok, lc.language_spec("hi")) is None


def test_roundtrip_producer_to_consumer_excellent(tmp_path) -> None:
    """Produce JSON, load it via language_coverage, assert 'derived' + band."""
    greek = sc.SCRIPT_EXEMPLARS["Greek"]
    tok = _tok_all_tier0(greek, sc.SCRIPT_SAMPLES["Greek"])
    path = sc.write_coverage_file(
        "openai", "gpt-fake", [lc.language_spec("el")],
        tokenizer=tok, coverage_dir=tmp_path,
    )
    assert path is not None and path.is_file()

    record = lc.evaluate_language_fit(
        lc.normalize_model_spec("openai", "gpt-fake"),
        lc.language_spec("el"),
        coverage_dir=tmp_path,
    )
    assert record.status == "derived"
    assert record.coverage_score == 1.0
    assert record.score_band == "excellent"  # >= 0.90
    assert record.tier_counts.tier_0_native == len(greek)
    assert record.source.kind == "loove_derived_json"


def test_roundtrip_byte_fallback_lowers_band(tmp_path) -> None:
    """A script that only byte-falls-back scores 0.2 -> 'poor' after round-trip."""
    cyr = sc.SCRIPT_EXEMPLARS["Cyrillic"]
    tok = FakeTokenizer()
    for ch in cyr:
        tok.add_tier2(ch)  # every exemplar is byte fallback (weight 0.2)
    for ch in sc.SCRIPT_SAMPLES["Cyrillic"]:
        if ch not in cyr and ch != " ":
            tok.add_tier2(ch)
    tok.add_tier0(" ")
    sc.write_coverage_file(
        "hf", "cyr-fake", [lc.language_spec("ru")],
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


def test_no_tokenizer_writes_no_file(tmp_path) -> None:
    """Honest absence: no tokenizer -> no file, and the consumer falls back."""
    original = sc.load_tokenizer
    try:
        sc.load_tokenizer = lambda model_id: None  # type: ignore[assignment]
        path = sc.write_coverage_file(
            "cloud", "no-tokenizer-model", [lc.language_spec("en")],
            coverage_dir=tmp_path,
        )
        assert path is None
        assert not any(tmp_path.iterdir())
    finally:
        sc.load_tokenizer = original  # type: ignore[assignment]

    # Consumer with no derived file falls back to heuristic, never crashes.
    record = lc.evaluate_language_fit(
        lc.normalize_model_spec("cloud", "no-tokenizer-model"),
        lc.language_spec("en"),
        coverage_dir=tmp_path,
    )
    assert record.status == "heuristic"


def test_filename_matches_consumer_lookup(tmp_path) -> None:
    """The produced filename must be the one _coverage_file_for looks up."""
    tok = _tok_all_tier0(sc.SCRIPT_EXEMPLARS["Latin"], sc.SCRIPT_SAMPLES["Latin"])
    path = sc.write_coverage_file(
        "OpenAI", "GPT 4o", [lc.language_spec("en")],
        tokenizer=tok, coverage_dir=tmp_path,
    )
    expected = lc._coverage_file_for(
        lc.normalize_model_spec("OpenAI", "GPT 4o"), tmp_path
    )
    assert path == expected
