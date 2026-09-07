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

import json
import re

import pytest

from fichero_server.llm import script_coverage as sc
from fichero_server.llm import language_coverage as lc
from fichero_server.llm.language_coverage import LanguageCoverageRecord


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """No test hits the network by default. Andy tests opt in via _stub_andy.

    Also clears the Andy-doc lru cache before/after each test so a fixture doc
    from one test can't leak into another.
    """
    def _no_net(*a, **k):
        raise OSError("offline: network disabled in unit tests")

    monkeypatch.setattr(sc, "_http_get_bytes", _no_net)
    sc._fetch_andy_doc.cache_clear()
    yield
    sc._fetch_andy_doc.cache_clear()


# --- Andy Janco (apjanco/loove) published-coverage fixtures ------------------
# A tiny doc in his REAL schema so the fetch/adapter path is tested offline.


def _andy_doc(model_id: str = "fake/model") -> dict:
    return {
        "model_id": model_id,
        "source": "huggingface",
        "vocab_size": 1000,
        "has_byte_fallback": True,
        "computed_at": "2026-09-04T00:00:00+00:00",
        "languages": {
            "en": {
                "name": "English",
                "script": "Latn",
                "main": {
                    "total": 26,
                    "weighted_score": 0.88,  # distinct from a full-tier0 local score (1.0)
                    "tier0_count": 22,
                    "tier1_count": 2,
                    "tier2_count": 2,
                    "tier3_count": 0,
                },
                "glottocode": "stan1293",
                "iso639_3": "eng",
                "family_name": "Indo-European",
                "latitude": 53.0,
                "longitude": -1.0,
                "is_historical": False,
                "fertility": {
                    "tokens_per_char": 0.222,
                    "tokens_per_word": 1.15,
                    "sample_chars": 3351,
                    "sample_tokens": 744,
                },
            },
            "cop": {
                "name": "Coptic",
                "script": "Copt",
                "main": {
                    "total": 32,
                    "weighted_score": 0.2,
                    "tier0_count": 4,
                    "tier1_count": 0,
                    "tier2_count": 28,
                    "tier3_count": 0,
                },
                "glottocode": "copt1239",
                "family_name": "Afro-Asiatic",
                "latitude": 29.472,
                "longitude": 31.2053,
                "is_historical": True,
            },
            "zz": {  # present in his file, but we won't request it
                "name": "Zzz",
                "script": "Zzzz",
                "main": {
                    "total": 10, "weighted_score": 0.5,
                    "tier0_count": 5, "tier1_count": 0, "tier2_count": 5, "tier3_count": 0,
                },
            },
        },
    }


def _stub_andy(monkeypatch, doc: dict | None, expect_name: str | None = None):
    """Stub the HTTP fetch. doc=None => always 404. Returns a call counter."""
    calls = {"n": 0}

    def fake_get(url, timeout=30.0):
        calls["n"] += 1
        if doc is not None and (expect_name is None or expect_name in url):
            return json.dumps(doc).encode("utf-8")
        raise OSError("404 not found")

    monkeypatch.setattr(sc, "_http_get_bytes", fake_get)
    sc._fetch_andy_doc.cache_clear()  # avoid cross-test lru contamination
    return calls

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


def test_arabic_produces_real_record() -> None:
    ar = sc.SCRIPT_EXEMPLARS["Arabic"]
    tok = _tok_all_tier0(ar, sc.SCRIPT_SAMPLES["Arabic"])
    record = sc.coverage_for_model("gpt-fake", lc.language_spec("ar"), tokenizer=tok)
    assert record.status == "derived"  # not "unknown"
    assert record.language.script == "Arabic"
    assert record.coverage_score == 1.0
    assert record.tier_counts.total_chars == len(ar)


def test_pre1918_russian_scores_distinctly_from_modern() -> None:
    # A tokenizer that covers MODERN Russian but has no token for the pre-1918
    # letters (yat/izhitsa/decimal-i/fita). Modern Russian scores full; the
    # pre-1918 script scores strictly lower — proving the historical script is
    # scored as its own thing, the demo-gold distinction.
    modern = sc.SCRIPT_EXEMPLARS["Cyrillic"]
    tok = _tok_all_tier0(modern)  # pre-1918 chars left unregistered -> tier3

    ru = sc.coverage_for_model("m", lc.language_spec("ru"), tokenizer=tok)
    pre = sc.coverage_for_model("m", lc.language_spec("ru-petr1708"), tokenizer=tok)

    assert ru.language.script == "Cyrillic"
    assert pre.language.script == "Cyrillic_Pre1918"
    assert ru.status == "derived" and pre.status == "derived"
    assert ru.coverage_score == 1.0
    assert pre.coverage_score < ru.coverage_score  # historical letters are lost


def test_demo_languages_resolve_to_expected_scripts() -> None:
    # Stable codes the window requests -> the scripts we have exemplars for.
    assert lc.language_spec("ru-petr1708").script == "Cyrillic_Pre1918"
    assert lc.language_spec("cop").script == "Coptic"
    assert lc.language_spec("ka").script == "Georgian"
    assert lc.language_spec("hy").script == "Armenian"
    assert lc.language_spec("ar").script == "Arabic"
    assert lc.language_spec("he").script == "Hebrew"


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


# --- End-to-end: the fit path lazily generates and returns "derived" ---------
# These prove generation->read is wired into language_coverage, not just the
# producer in isolation. load_tokenizer is patched to a fake so it stays offline.


def test_fit_path_generates_derived(tmp_path) -> None:
    greek = sc.SCRIPT_EXEMPLARS["Greek"]
    tok = _tok_all_tier0(greek, sc.SCRIPT_SAMPLES["Greek"])
    original = sc.load_tokenizer
    try:
        sc.load_tokenizer = lambda model_id: tok  # type: ignore[assignment]
        # No coverage file exists yet -> the fit path must generate one.
        assert not any(tmp_path.iterdir())
        record = lc.evaluate_language_fit(
            lc.normalize_model_spec("openai", "gpt-fake"),
            lc.language_spec("el"),
            coverage_dir=tmp_path,
        )
        assert record.status == "derived"  # NOT "heuristic"
        assert record.score_band == "excellent"
        assert record.coverage_score == 1.0
        assert record.source.kind == "loove_derived_json"
        assert any(tmp_path.iterdir())  # generation actually wrote a file
    finally:
        sc.load_tokenizer = original  # type: ignore[assignment]


def test_fit_path_no_tokenizer_returns_unknown_not_heuristic(tmp_path) -> None:
    # Genuinely-no-tokenizer model (Apple/vision-only/gated) -> honest UNKNOWN,
    # NOT a heuristic guess, and nothing written to disk.
    original = sc.load_tokenizer
    try:
        sc.load_tokenizer = lambda *a, **k: None  # type: ignore[assignment]
        record = lc.evaluate_language_fit(
            lc.normalize_model_spec("apple", "apple-intelligence"),
            lc.language_spec("en"),
            coverage_dir=tmp_path,
        )
        assert record.coverage_score is None
        assert record.score_band == "unknown"
        assert record.status != "heuristic"
        assert record.source.kind != "heuristic_fallback"
        assert not any(tmp_path.iterdir())  # nothing fabricated/cached
    finally:
        sc.load_tokenizer = original  # type: ignore[assignment]


def test_fit_caches_second_call_does_not_recompute(tmp_path) -> None:
    # First fit computes (loads tokenizer, writes file); a second fit must read
    # the cached file WITHOUT loading the tokenizer again — proving per-(provider,
    # model) caching. We prove "no recompute" by making the loader explode on the
    # second call: if the cache weren't used, this would raise / go unknown.
    greek = sc.SCRIPT_EXEMPLARS["Greek"]
    tok = _tok_all_tier0(greek, sc.SCRIPT_SAMPLES["Greek"])
    calls: list[str] = []

    def counting_loader(model_id, *a, **k):
        calls.append(model_id)
        return tok

    original = sc.load_tokenizer
    try:
        sc.load_tokenizer = counting_loader  # type: ignore[assignment]
        spec = lc.normalize_model_spec("hf", "greek-fake")
        r1 = lc.evaluate_language_fit(spec, lc.language_spec("el"), coverage_dir=tmp_path)
        assert r1.status == "derived"
        assert len(calls) == 1  # computed once

        def exploding_loader(*a, **k):
            raise AssertionError("cache miss: tokenizer should not reload")

        sc.load_tokenizer = exploding_loader  # type: ignore[assignment]
        r2 = lc.evaluate_language_fit(spec, lc.language_spec("el"), coverage_dir=tmp_path)
        assert r2.status == "derived"  # served from the cached file
        assert r2.coverage_score == r1.coverage_score
    finally:
        sc.load_tokenizer = original  # type: ignore[assignment]


def test_fit_path_pre1918_variant_returns_derived(tmp_path) -> None:
    # The historical variant (not in _COMMON_LANGUAGES) must pass the generation
    # gate and return derived — proving the widened gate + resolver wiring.
    pre = sc.SCRIPT_EXEMPLARS["Cyrillic_Pre1918"]
    tok = _tok_all_tier0(pre, sc.SCRIPT_SAMPLES["Cyrillic_Pre1918"])
    original = sc.load_tokenizer
    try:
        sc.load_tokenizer = lambda *a, **k: tok  # type: ignore[assignment]
        record = lc.evaluate_language_fit(
            lc.normalize_model_spec("hf", "cyr-fake"),
            lc.language_spec("ru-petr1708"),
            coverage_dir=tmp_path,
        )
        assert record.status == "derived"
        assert record.language.script == "Cyrillic_Pre1918"
        assert record.coverage_score == 1.0
    finally:
        sc.load_tokenizer = original  # type: ignore[assignment]


def test_fit_path_recommend_returns_derived(tmp_path) -> None:
    """The public recommend_language_fit surface also gets derived results."""
    cyr = sc.SCRIPT_EXEMPLARS["Cyrillic"]
    tok = _tok_all_tier0(cyr, sc.SCRIPT_SAMPLES["Cyrillic"])
    original = sc.load_tokenizer
    try:
        sc.load_tokenizer = lambda model_id: tok  # type: ignore[assignment]
        response = lc.recommend_language_fit(
            "ru",
            [lc.LanguageFitModelSpec(provider="hf", model="cyr-fake")],
            coverage_dir=tmp_path,
        )
        assert len(response.results) == 1
        assert response.results[0].status == "derived"
        assert response.results[0].score_band == "excellent"
    finally:
        sc.load_tokenizer = original  # type: ignore[assignment]


# --- Andy Janco published-coverage consumption (offline, HTTP stubbed) -------


def test_andy_adapter_and_filter(monkeypatch) -> None:
    _stub_andy(monkeypatch, _andy_doc("fake/model"), expect_name="fake__model.json")
    entries = sc.fetch_andy_coverage("fake/model", ["en", "cop"])
    assert set(entries) == {"en", "cop"}  # filtered — "zz" NOT included

    en = entries["en"]
    assert en["coverage_score"] == 0.88
    assert en["script"] == "Latn"  # Andy's ISO-15924 carried through
    assert en["tier_counts"]["tier_0_native"] == 22
    assert en["tier_counts"]["tier_2_byte_fallback"] == 2
    assert en["tier_counts"]["total_chars"] == 26
    assert en["fertility"]["tokens_per_word"] == 1.15
    # Geo/provenance extras carried for a future map.
    assert en["glottocode"] == "stan1293"
    assert en["latitude"] == 53.0
    assert entries["cop"]["is_historical"] is True


def test_andy_missing_model_returns_none(monkeypatch) -> None:
    _stub_andy(monkeypatch, None)  # every fetch 404s
    assert sc.fetch_andy_coverage("no/such-model", ["en"]) is None


def test_fit_prefers_andy_over_local(tmp_path, monkeypatch) -> None:
    # Andy has en at 0.88; our local tokenizer would score 1.0. If Andy wins,
    # the result is 0.88 with the apjanco provenance note.
    _stub_andy(monkeypatch, _andy_doc("fake/model"), expect_name="fake__model.json")
    monkeypatch.setattr(
        sc, "load_tokenizer",
        lambda *a, **k: _tok_all_tier0(sc.SCRIPT_EXEMPLARS["Latin"], sc.SCRIPT_SAMPLES["Latin"]),
    )
    record = lc.evaluate_language_fit(
        lc.normalize_model_spec("hf", "fake/model"),
        lc.language_spec("en"),
        coverage_dir=tmp_path,
    )
    assert record.status == "derived"
    assert record.coverage_score == 0.88  # Andy's number, not local's 1.0
    assert record.score_band == "good"
    assert record.source.kind == "loove_derived_json"
    assert any("apjanco/loove" in n for n in record.source.notes)
    # Only the requested language is cached — never the whole 5 MB file.
    cached = json.loads((tmp_path / "hf__fake__model.json").read_text(encoding="utf-8"))
    assert set(cached["coverage"]) == {"en"}


def test_fit_falls_back_to_local_when_andy_404(tmp_path, monkeypatch) -> None:
    _stub_andy(monkeypatch, None)  # Andy has nothing -> our own compute
    monkeypatch.setattr(
        sc, "load_tokenizer",
        lambda *a, **k: _tok_all_tier0(sc.SCRIPT_EXEMPLARS["Latin"], sc.SCRIPT_SAMPLES["Latin"]),
    )
    record = lc.evaluate_language_fit(
        lc.normalize_model_spec("hf", "no/such-model"),
        lc.language_spec("en"),
        coverage_dir=tmp_path,
    )
    assert record.status == "derived"
    assert record.coverage_score == 1.0  # local full-tier0 compute
    assert not any("apjanco/loove" in n for n in record.source.notes)


def test_andy_cache_hit_second_call_no_refetch(tmp_path, monkeypatch) -> None:
    calls = _stub_andy(monkeypatch, _andy_doc("fake/model"), expect_name="fake__model.json")
    spec = lc.normalize_model_spec("hf", "fake/model")
    r1 = lc.evaluate_language_fit(spec, lc.language_spec("en"), coverage_dir=tmp_path)
    assert r1.status == "derived"
    assert calls["n"] == 1  # fetched once

    # Drop the in-memory doc cache so only the on-DISK cache can serve the 2nd call.
    sc._fetch_andy_doc.cache_clear()
    r2 = lc.evaluate_language_fit(spec, lc.language_spec("en"), coverage_dir=tmp_path)
    assert r2.status == "derived"
    assert r2.coverage_score == r1.coverage_score
    assert calls["n"] == 1  # no refetch — served from the cached file


# --- Arbitrary "choose any language" path ------------------------------------
# The loove window lets a user pick ANY language, not just the curated ~30 in
# _COMMON_LANGUAGES. A chosen code our local resolver can't map to a script must
# still reach Andy's published coverage (keyed by the same short code), and fall
# back to an HONEST unknown — never a guess — when he lacks it.


def test_fit_path_arbitrary_language_scores_from_andy(tmp_path, monkeypatch) -> None:
    """A code with no local script still scores from Andy's authoritative data.

    'zz' is absent from _COMMON_LANGUAGES, so language_spec gives it no script;
    before the widened gate it was refused outright. Andy's file has it at 0.5,
    so the window's free-choice column now shows a real, derived number.
    """
    _stub_andy(monkeypatch, _andy_doc("fake/model"), expect_name="fake__model.json")
    monkeypatch.setattr(sc, "load_tokenizer", lambda *a, **k: None)
    lang = lc.language_spec("zz")
    assert lang.script is None  # unknown to our local resolver
    record = lc.evaluate_language_fit(
        lc.normalize_model_spec("hf", "fake/model"), lang, coverage_dir=tmp_path
    )
    assert record.status == "derived"
    assert record.coverage_score == 0.5  # straight from Andy's published file
    assert record.language.code == "zz"
    assert record.source.kind == "loove_derived_json"


def test_fit_path_arbitrary_language_without_andy_is_honest_unknown(
    tmp_path, monkeypatch
) -> None:
    """No Andy data + no local script table => honest unsupported_language.

    'sw' (Swahili) is not curated locally; with Andy 404ing and no tokenizer the
    fit path must return an explicit unknown with warnings, never a fabricated
    score.
    """
    _stub_andy(monkeypatch, None)  # every fetch 404s
    monkeypatch.setattr(sc, "load_tokenizer", lambda *a, **k: None)
    lang = lc.language_spec("sw")
    assert lang.script is None
    record = lc.evaluate_language_fit(
        lc.normalize_model_spec("hf", "no/such-model"), lang, coverage_dir=tmp_path
    )
    assert record.status == "unsupported_language"
    assert record.coverage_score is None
    assert record.warnings
