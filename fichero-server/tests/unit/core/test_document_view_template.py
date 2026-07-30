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


# ---------------------------------------------------------------------------
# Transcript wrapping (#4385)
# ---------------------------------------------------------------------------
#
# `white-space: pre-wrap` wraps at existing whitespace but cannot break an
# unbroken token, and nothing set `overflow-wrap`. One long OCR/HTR run — a
# numeric string, an unspaced sequence where the model inferred no word
# boundaries, a whole paragraph returned as one line — set a min-content width
# for the page, so the pane scrolled sideways instead of wrapping. On a
# handwriting-transcription corpus that input is the normal case.
#
# The true contract is `document.scrollWidth <= document.clientWidth` at a
# narrow pane width with a 4000-character unbroken token. That needs a headless
# browser; the backend suite has none and playwright is not a declared
# dependency, so adding one is not this lane's call (see the report on #4385 —
# it belongs with the Swift lane's WebKit tests, which already run a real
# engine). These assert the CSS properties that make that contract hold, which
# is what this suite can honestly check.


def test_transcript_body_can_break_an_unbreakable_token() -> None:
    source = _template_source()

    assert ".transcript-page-body {" in source
    assert "overflow-wrap: anywhere;" in source


def test_transcript_body_uses_anywhere_not_break_word() -> None:
    """`break-word` is the plausible-looking wrong answer.

    Both break an otherwise unbreakable token, but only `anywhere` shrinks the
    element's min-content width. With `break-word` the body still reports a
    minimum as wide as its longest token, the page resolves to content width,
    and the pane scrolls — i.e. the bug survives a fix that looks correct.
    """
    source = _template_source()
    start = source.index(".transcript-page-body {")
    body_rule = source[start : source.index("}", start)]

    assert "overflow-wrap: anywhere" in body_rule
    # The DECLARATION, not the bare word — the rule's own comment explains why
    # `break-word` is wrong, so a substring check on it matches the prose.
    assert "overflow-wrap: break-word" not in body_rule, (
        "overflow-wrap: break-word does not shrink min-content width, so the "
        "page can still force the container wider (#4385)"
    )


def test_page_and_root_cannot_resolve_to_content_width() -> None:
    """Defence in depth: a definite max width on the page, and a root that
    refuses to scroll horizontally so a future rule cannot reintroduce it."""
    source = _template_source()

    assert "html, body {" in source
    assert "overflow-x: hidden;" in source
    assert "max-width: 100%;" in source


def test_the_scroll_container_scrolls_vertically_only() -> None:
    source = _template_source()

    content_index = source.index(".content {")
    content_rule = source[content_index : content_index + 400]
    assert "overflow-y: auto;" in content_rule
    assert "overflow-x: hidden;" in content_rule
    assert "overflow: auto;" not in content_rule, (
        "`overflow: auto` on both axes is what turned an over-wide page into "
        "a horizontal scrollbar instead of a wrap (#4385)"
    )


def test_claim_source_excerpt_wraps_like_the_transcript() -> None:
    """It is a verbatim slice of the same OCR text, so it carries the same
    unbreakable runs and had the same half-configured wrap."""
    source = _template_source()

    start = source.index(".claim-source {")
    claim_rule = source[start : source.index("}", start)]
    assert "white-space: pre-wrap;" in claim_rule
    assert "overflow-wrap: anywhere;" in claim_rule


def test_unwrappable_content_has_a_sanctioned_escape_hatch() -> None:
    """Content that truly cannot wrap must scroll inside its own box rather
    than widening the page."""
    source = _template_source()

    hatch_index = source.index(".overflow-scroll-x {")
    hatch_rule = source[hatch_index : hatch_index + 200]
    assert "overflow-x: auto;" in hatch_rule
    assert "max-width: 100%;" in hatch_rule
