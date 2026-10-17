"""#5572: the heuristic is the detector; a text it cannot tell is 'not reliable', never 'en'."""
from __future__ import annotations

import fichero_server.llm.multilingual as multilingual
from fichero_server.llm.multilingual import detect_language


def test_latin_script_is_not_reliable_rather_than_english():
    result = detect_language("Hello, this is English text")
    assert (result.language, result.is_reliable) == ("und", False)


def test_empty_text_is_not_reliable_rather_than_english():
    result = detect_language("")
    assert (result.language, result.confidence, result.is_reliable) == ("und", 0.0, False)


def test_a_script_the_heuristic_can_tell_keeps_its_code():
    assert detect_language("한국어를 테스트합니다").language == "ko"
    assert detect_language("Привет, мир").language == "ru"


def test_there_is_no_cld3_import():
    assert not hasattr(multilingual, "cld3") and not hasattr(multilingual, "CLD3_AVAILABLE")


def test_an_undetermined_query_is_still_lowercased_for_matching():
    from fichero_server.llm.multilingual import normalize_text

    assert normalize_text("  London  Bridge ", detect_language("London Bridge").language) == "london bridge"
