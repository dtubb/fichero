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
    assert 'data-page="${page.number}"' in source
    assert "scroll-margin-block-start" in source


def test_transcript_renders_every_page_including_empty_ones() -> None:
    """Empty pages render as empty PAGES, never as gaps (#4356)."""
    source = _template_source()

    # The page list comes from the structured `pages` payload (page children),
    # not from parsing the assembled transcript text.
    assert "Array.isArray(documentData.pages)" in source
    assert "No transcription yet" in source
    assert "empty-page" in source
    # The panel's empty state keys on the page list, not on transcript text —
    # a document whose pages are all untranscribed still shows its pages.
    assert "if (!pages.length) {" in source


def test_current_page_highlight_is_applied_in_place() -> None:
    """Preview -> reader current-page highlight, no re-render (#4356)."""
    source = _template_source()

    assert "function applyActivePageHighlight()" in source
    assert 'el.classList.toggle("current", isCurrent);' in source
    # setActivePage moves the highlight rather than only re-scoping the graph.
    assert "applyActivePageHighlight();\n        renderGraph();" in source
    assert ".transcript-page.current {" in source


def test_per_page_progress_and_live_patch_never_reload() -> None:
    """Per-page spinner + in-place page patch (#4357)."""
    source = _template_source()

    assert "function applyBusyPages()" in source
    assert "setBusyPages(pageNumbers)" in source
    assert "setPageContent(pageNumber, content)" in source
    assert "function patchPageContent(pageNumber, content)" in source
    # In place: the patch writes the page body's text, it does not re-render.
    assert "body.textContent = text;" in source
    assert "page-working-spinner" in source
