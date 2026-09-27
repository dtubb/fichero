"""The known-red banner must name EVERY issue it is holding debt for (#5121).

WHY this test exists: the banner's only job is to stop known-red specifications from going
unnoticed. On 2026-09-27 it was doing the opposite. The parse read
`tok.startswith("#4")`, so when #5121's four entries were added they xfailed correctly and
the banner still printed "Open: #4395, #4420" — the debt was real, listed, and invisible.
Every issue from #5000 on was silently dropped, and nothing would have said so.

If this test is ever failing, do not relax it: the banner is undercounting again.
"""

from __future__ import annotations

import sys
from pathlib import Path

_CONFTEST_DIR = Path(__file__).resolve().parents[2]  # fichero-server/tests
sys.path.insert(0, str(_CONFTEST_DIR))
from conftest import spec_failure_issues  # noqa: E402


class TestEveryIssueNumberIsFound:
    def test_a_five_thousand_issue_is_not_dropped(self):
        """The actual defect. #5121 was invisible while its tests were xfailing."""
        assert spec_failure_issues("# ---- #5121 (4) ----") == ["#5121"]

    def test_the_four_thousand_issues_still_work(self):
        assert spec_failure_issues("# ---- #4395 (5) ----") == ["#4395"]

    def test_issues_sort_NUMERICALLY_not_as_strings(self):
        """String sorting would put #5121 before #999 and #10000 before #999 — the banner
        would still be correct but would read as scrambled, and a reader who cannot trust
        the order stops reading the line."""
        text = "# ---- #999 (1) ----\n# ---- #5121 (4) ----\n# ---- #4395 (5) ----\n"
        assert spec_failure_issues(text) == ["#999", "#4395", "#5121"]

    def test_only_section_headers_are_read(self):
        """A test node id or prose mentioning an issue must not invent a section."""
        text = (
            "# ---- #4395 (1) ----\n"
            "tests/unit/x/test_y.py::test_z  # see #9999\n"
            "# a comment about #8888\n"
        )
        assert spec_failure_issues(text) == ["#4395"]

    def test_a_header_naming_two_issues_yields_both(self):
        assert spec_failure_issues("# ---- #4382 #4395 (2) ----") == ["#4382", "#4395"]

    def test_the_count_in_parens_is_not_mistaken_for_an_issue(self):
        """`(4)` has no `#`, so it must not become issue #4."""
        assert spec_failure_issues("# ---- #5121 (4) ----") == ["#5121"]

    def test_no_headers_means_no_issues_not_a_crash(self):
        assert spec_failure_issues("just prose\n") == []


class TestTheRealFileAgrees:
    def test_the_shipped_file_names_5121(self):
        """End-to-end on the real file: the four App Store tests are held against #5121, so
        the banner must say so or the debt is hidden again."""
        real = (_CONFTEST_DIR / "known_specification_failures.txt").read_text()
        assert "#5121" in spec_failure_issues(real)
