import Testing

/// Feature/domain tags for slicing the suite ACROSS platforms and plans.
///
/// Test PLANS pick platform × engine-mode (mac-local, iphone-local, …); TAGS
/// pick a feature area and cut across every plan. Run one feature with
/// `--filter-tag knowledgeGraph` instead of maintaining a per-feature plan file.
///
/// The vocabulary mirrors the `Tests/Unit/**` folder layout so a suite's tag is
/// obvious from where it lives. Adopt at the suite level:
///
///     @Suite(.tags(.knowledgeGraph))
///     struct EntitySourceGroupsLinkTests { … }
///
/// A suite may carry more than one tag (e.g. `.knowledgeGraph, .transport`).
extension Tag {
    // Knowledge graph: entities, claims, ontology, neighborhoods, sources.
    @Tag static var knowledgeGraph: Self
    // Workflows: nodes, fan-out, run traces, provider routing.
    @Tag static var workflow: Self
    // Reader surface: WebKit reader, find-in-page, highlight navigation.
    @Tag static var reader: Self
    // Library: tree, list/table view modes, sorting, selection.
    @Tag static var library: Self
    // Inspector: attribute panes, annotations, knowledge inspector.
    @Tag static var inspector: Self
    // Sidebar: source list, drag/drop, routing.
    @Tag static var sidebar: Self
    // Transport: client, TLS/pinning, change streams, engine readiness.
    @Tag static var transport: Self
    // Providers / models / runtimes availability + routing.
    @Tag static var providers: Self
    // Search.
    @Tag static var search: Self
    // Settings + feature-tier gating.
    @Tag static var settings: Self
    // Paleography: segmentation, transcription, representations.
    @Tag static var paleography: Self
    // Document/data model equality, migrations, stores.
    @Tag static var models: Self
    // Backend contract tests (need the spawned engine).
    @Tag static var contract: Self
}
