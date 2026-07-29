from pathlib import Path


TEMPLATE = (
    Path(__file__).parents[3]
    / "src"
    / "fichero_server"
    / "api"
    / "templates"
    / "document_view.html"
)


def _template_source() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def test_graph_defaults_to_active_page_claim_scope() -> None:
    source = _template_source()

    assert "showAllClaims: false" in source
    assert "function graphPageMatches(claim)" in source
    assert "return Number(claim.page_number) === Number(state.activePage);" in source
    assert "const scopedClaims = graphClaims();" in source
    assert "scopedClaims.forEach((claim)" in source


def test_graph_has_show_all_claims_toggle() -> None:
    source = _template_source()

    assert "Show all claims" in source
    assert "Show current page only" in source
    assert "data-graph-scope-toggle" in source
    assert "state.showAllClaims = !state.showAllClaims;" in source


def test_graph_uses_pane_size_for_layout() -> None:
    source = _template_source()

    assert "min-height: calc(100vh - 24px)" in source
    assert "const panelRect = panel.getBoundingClientRect();" in source
    assert "forceLayout(nodes, edges, width, height);" in source
    assert 'viewBox="0 0 ${width} ${height}"' in source
    assert "requestAnimationFrame(renderGraph)" in source


def test_graph_neighborhood_fetch_uses_relative_api_path() -> None:
    source = _template_source()

    assert "fetch(`/api/kg/graph/neighborhood/${entityId}`" in source
    assert "http://localhost:8765/api/kg/graph/neighborhood" not in source


def test_transcript_page_cards_keep_scroll_sync_anchors() -> None:
    source = _template_source()

    assert "function transcriptPages()" in source
    assert 'class="transcript-page" data-page="${page.number}"' in source
    assert "scroll-margin-block-start" in source
