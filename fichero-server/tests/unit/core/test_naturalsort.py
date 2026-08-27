"""Natural sort for user-visible names (Daniel's live bug, 2026-08-25:
"page10 sorts before page2")."""

from __future__ import annotations

from fichero_server.core.naturalsort import natural_key


def test_numbers_compare_numerically():
    names = ["page10", "page2", "page1"]
    assert sorted(names, key=natural_key) == ["page1", "page2", "page10"]


def test_archive_style_names_match_finder():
    # Same-precision date stamps stay chronological; a YEAR-ONLY stamp sorts
    # before full dates because 1923 < 19140101 numerically — which is also
    # exactly what Finder does with these names. Mixed-precision stamps are
    # inherently ambiguous; we pin Finder's answer.
    names = [
        "NCM_Diary_19310101-19311231",
        "NCM_Diary_19140101-19141231",
        "NCM_Diary_1923",
    ]
    assert sorted(names, key=natural_key) == [
        "NCM_Diary_1923",
        "NCM_Diary_19140101-19141231",
        "NCM_Diary_19310101-19311231",
    ]


def test_case_insensitive_like_the_sort_it_replaced():
    assert sorted(["Beta", "alpha"], key=natural_key) == ["alpha", "Beta"]


def test_none_and_empty_sort_first_and_never_raise():
    assert sorted(["a", None, ""], key=natural_key) == [None, "", "a"]


def test_mixed_numeric_and_alpha_chunks_never_type_error():
    # int/str at the same position raised TypeError before chunk tagging.
    sorted(["2fast", "afast", "fast2", "fast"], key=natural_key)


def test_pathological_digit_run_is_bounded():
    # 300 digits split into 30-char runs — must sort, not hang or raise.
    a = "doc" + "9" * 300
    b = "doc" + "9" * 299 + "8"
    assert sorted([a, b], key=natural_key) == sorted([a, b], key=natural_key)


def test_list_endpoint_helper_uses_natural_order():
    from fichero_server.api.routes.document.documents import _ordered_by_sort_order
    from fichero_server.models import Document

    def doc(name):
        return Document(name=name, expected_thumbnail_path="t", expected_display_path="d")

    docs = [doc("page10"), doc("page2")]
    assert [d.name for d in _ordered_by_sort_order(docs)] == ["page2", "page10"]
