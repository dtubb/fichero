"""What the endpoint coverage matrix counts as "the app reaches this endpoint".

The guard answered that question by looking for the endpoint's path string in Swift file text,
and every one of these tests exists because that answer was wrong in a specific way. It
reported 490 gaps of 742 operations; the honest figure is 236. The four defects, each with a
test below that fails if it comes back:

  1. A call through the generated client spells the OPERATION NAME, never the path — and the
     house rule forbids hand-rolled URLs, so that is how most calls look. Ten hand-written
     witness-table entries had accumulated patching this one endpoint at a time.
  2. File text includes comments, so a `///` line naming a path counted as calling it.
  3. `normalize_text` collapses `{...}` for OpenAPI paths. Run over Swift it eats every
     innermost brace block, so a single-statement function body vanished along with the call
     inside it.
  4. A substring test made a short path match a longer sibling and ordinary prose.

See #5108 and the module docstrings in scripts/matrix_guardrail_common.py.
"""
from __future__ import annotations

import functools
import importlib.util
import sys
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_endpoint_coverage_matrix.py"
sys.path.insert(0, str(_SCRIPT.parent))
_SPEC = importlib.util.spec_from_file_location("check_endpoint_coverage_matrix", _SCRIPT)
assert _SPEC and _SPEC.loader
check_endpoint_coverage_matrix = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = check_endpoint_coverage_matrix
_SPEC.loader.exec_module(check_endpoint_coverage_matrix)  # type: ignore[attr-defined]

sys.path.insert(0, str(_SCRIPT.parent))
from matrix_guardrail_common import (  # noqa: E402
    expand_swift_path_components,
    normalize_path,
    normalize_source,
    normalize_text,
    dialled_paths,
    path_is_dialled,
    source_identifiers,
    strip_swift_comments,
    swift_operation_name,
)


@functools.lru_cache(maxsize=1)
def _rows() -> dict:
    """One scan for the whole module — it reads every Swift file in the app target."""
    return {row.endpoint: row for row in check_endpoint_coverage_matrix.scan()}


class TestAGeneratedClientCallCounts:
    """Defect 1. The operation name is the primary witness, not a special case."""

    def test_the_operation_name_is_derived_from_the_operation_id(self):
        assert swift_operation_name("list_citation_usages_api_citation_usages_get") == (
            "listCitationUsagesApiCitationUsagesGet"
        )

    def test_endpoints_reached_only_through_the_generated_client_are_not_gaps(self):
        """These four have no path string in Swift at all; they used to need witness entries."""
        rows = _rows()
        for endpoint in (
            "GET /api/citation-usages",
            "GET /api/libraries/{lib}/entity-types",
            "POST /api/libraries/{lib}/entity-types",
            "DELETE /api/libraries/{lib}/entity-types/{entity_type_key}",
        ):
            assert rows[endpoint].store is True, endpoint
            assert rows[endpoint].gap is False, endpoint

    def test_the_witness_table_is_gone(self):
        """Its ten entries all became redundant the day operation names were matched.

        A table of hand-added exceptions is how a broken measure survives: each entry looks
        like a small correction, and nobody asks why corrections keep being needed.
        """
        assert not hasattr(check_endpoint_coverage_matrix, "SWIFT_OPERATION_WITNESSES")


class TestProseIsNotACall:
    """Defect 2. A doc comment naming an endpoint is a claim, and claims are not evidence."""

    def test_a_doc_comment_naming_a_path_is_stripped(self):
        assert strip_swift_comments('/// Backed by `/api/links`.\nlet x = 1') == "let x = 1"

    def test_a_block_comment_is_stripped(self):
        assert "/api/links" not in strip_swift_comments('/* calls /api/links */\nlet x = 1')

    def test_a_trailing_comment_leaves_the_code_beside_it(self):
        """Dropping the tail would mean parsing string literals to find the comment's start."""
        assert "endpointData" in strip_swift_comments('endpointData(p) // see /api/x')

    def test_the_health_endpoint_is_reached_even_though_swift_only_names_it_in_prose(self):
        """The regression this pair guards: fixing 2 without fixing 1 turns a real call into a gap.

        `/api/health` appears in Swift only inside log messages and comments, and is called
        three times as `healthCheckApiHealthGet`. Comment-stripping alone reported it unreached.
        """
        rows = _rows()
        assert rows["GET /api/health"].store is True


class TestSourceNormalisationKeepsTheCode:
    """Defect 3. The OpenAPI template collapse eats Swift function bodies."""

    def test_normalize_text_destroys_a_single_statement_body(self):
        """Pinning the defect itself, so the reason normalize_source exists stays legible."""
        body = 'func f() -> Data { try await endpointData(path: "/api/kg/pykeen/reviews") }'
        assert normalize_text(body) == "func f() -> Data {}"

    def test_normalize_source_keeps_the_call_inside_that_body(self):
        body = 'func f() -> Data { try await endpointData(path: "/api/kg/pykeen/reviews") }'
        assert "/kg/pykeen/reviews" in normalize_source(body)

    def test_interpolation_still_normalises_to_the_openapi_shape(self):
        """The two sides have to meet: Swift `\\(id)` and OpenAPI `{document_id}` both become {}."""
        assert normalize_source('p("/api/documents/\\(id)/pages")').endswith(
            '/documents/{}/pages")'
        )
        assert normalize_path("/api/documents/{document_id}/pages") == "/documents/{}/pages"

    def test_the_pykeen_review_endpoints_are_reached(self):
        """Two functions call these; the brace collapse hid both."""
        rows = _rows()
        assert rows["GET /api/kg/pykeen/reviews"].store is True
        assert rows["POST /api/kg/pykeen/reviews"].store is True


class TestTheLookupIsWholeTokens:
    """How the two witnesses are tested, and why it is a set and not 742 regex scans.

    Per-endpoint regex over a 10 MB blob made this the guardrail suite's slowest script — it
    ran for over ten minutes without finishing while the backend suite was also running, and
    `verify_all.sh` globs every `scripts/check_*.py`. Extracting whole tokens once gives the
    identical verdict (236 gaps) in under a second, and removes the boundary question rather
    than answering it more carefully.
    """

    def test_paths_are_extracted_as_whole_string_literals(self):
        blob = 'get("/links") get("/links/types") get("/search?q={}")'
        paths = dialled_paths(blob)
        assert "/links" in paths
        assert "/links/types" in paths
        assert "/search" in paths, "a query string must not hide the path"

    def test_prose_contributes_no_paths(self):
        """"inline code/links" used to answer for POST /api/links."""
        assert dialled_paths("bold/italic/inline code/links)") == frozenset()

    def test_a_reassembled_component_array_is_emitted_quoted(self):
        """Unquoted it would be invisible to the literal reader, and the SSE streams would
        read as unreached — which is exactly what happened on the first attempt."""
        expanded = expand_swift_path_components('streamLines(pathComponents: ["activity", "stream"])')
        assert '"/activity/stream"' in expanded
        assert "/activity/stream" in dialled_paths(expanded)

    def test_an_operation_name_lookup_is_exact(self):
        names = source_identifiers("client.api.listClaimsForDocument(x)")
        assert "listClaimsForDocument" in names
        assert "listClaims" not in names, "a prefix must not answer for a longer method"


class TestAPathMatchHasBothEnds:
    """The boundary rule `path_is_dialled` still backs guards that scan text directly."""

    """Defect 4. `normalize_text` strips `/api/`, which makes short paths match everything."""

    def test_an_exact_dial_matches(self):
        assert path_is_dialled("/links", 'get("/links")')
        assert path_is_dialled("/links", "get('/links?limit=5')")

    def test_a_longer_sibling_does_not_match(self):
        assert not path_is_dialled("/links", 'get("/links/types")')

    def test_a_shorter_path_is_not_matched_by_the_longer_one_containing_it(self):
        """`/links` is a suffix of `/claims/{}/links`, and `}` is legal inside a path."""
        assert not path_is_dialled("/links", "Backed by `/claims/{}/links`.")
        assert path_is_dialled("/claims/{}/links", 'p("/claims/{}/links")')

    def test_prose_does_not_match(self):
        """"bold/italic/inline code/links" was reporting POST /api/links as wired."""
        assert not path_is_dialled("/links", "bold/italic/inline code/links)")


class TestStreamsDialTheirPathAsComponents:
    """A third witness shape: SSE cannot go through the generated client."""

    def test_a_component_array_is_reassembled(self):
        expanded = expand_swift_path_components('streamLines(pathComponents: ["activity", "stream"])')
        assert "/activity/stream" in expanded

    def test_a_non_string_array_is_left_alone(self):
        assert expand_swift_path_components("let x = [1, 2]") == "let x = [1, 2]"

    def test_the_activity_and_change_streams_are_reached(self):
        rows = _rows()
        assert rows["GET /api/activity/stream"].store is True
        assert rows["GET /api/changes/stream"].store is True


class TestTheCliAxisDoesNotDecideGaps:
    """It compares the schema with a file generated from the schema, so it cannot fail."""

    def test_a_gap_is_store_only(self):
        row = check_endpoint_coverage_matrix.Row(
            endpoint="GET /api/x", store=False, cli=True, handwritten_cli=False
        )
        assert row.gap is True
        reached = check_endpoint_coverage_matrix.Row(
            endpoint="GET /api/y", store=True, cli=False, handwritten_cli=False
        )
        assert reached.gap is False, "a missing CLI entry is not a wiring gap"

    def test_the_generated_surface_is_excluded_from_the_handwritten_sources(self):
        generated = check_endpoint_coverage_matrix.GENERATED_CLI_SURFACE
        assert generated in check_endpoint_coverage_matrix.CLI_SOURCES
        assert generated not in check_endpoint_coverage_matrix.HANDWRITTEN_CLI_SOURCES

    def test_the_two_figures_differ_by_an_order_of_magnitude(self):
        """If these ever converge, the generated surface stopped being the whole cli axis.

        738 of 742 satisfy the generated axis; 116 appear in hand-written CLI code. The gap
        between them is the reason the cli axis is reported and not counted.
        """
        rows = list(_rows().values())
        generated = sum(row.cli for row in rows)
        handwritten = sum(row.handwritten_cli for row in rows)
        assert generated > handwritten * 3


class TestTheBaselineSaysSomething:
    def test_no_reason_is_the_bare_measurement_restated(self):
        """376 of the old 443 entries read "store missing", which is the column, not a reason.

        An unauditable baseline is how 261 false gaps stayed seeded for weeks: nobody could
        tell a deliberate deferral from a measurement artefact by reading it.
        """
        reasons = check_endpoint_coverage_matrix.KNOWN_GAPS.values()
        assert "store missing" not in {reason.strip() for reason in reasons}

    def test_the_baseline_is_smaller_than_the_defective_one_it_replaced(self):
        assert len(check_endpoint_coverage_matrix.KNOWN_GAPS) < 443
