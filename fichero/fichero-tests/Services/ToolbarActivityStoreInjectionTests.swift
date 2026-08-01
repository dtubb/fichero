import XCTest

/// Guardrail for #4448 ("CRASH: deleting an item in the sidebar crashes the app").
///
/// The crash reports (build 2026.07.30) all trap the same way: `_assertionFailure`
/// from `EnvironmentValues.subscript.getter`, reached through
/// `EnvironmentBox.update(property:phase:)` — SwiftUI's "No Observable object of
/// type X found" — while `GraphHost.updatePreferences()` combines HOST
/// PREFERENCES inside `NSHostingView.layout()`. Host preferences are the
/// toolbar / navigationTitle / focusedValue channel, so the view that trapped was
/// one contributing toolbar content, not one in the ordinary content tree.
///
/// `DocumentTabView` is an EXPLICIT environment host: it re-forwards the
/// library-scoped values `ContentView` and its subtree read, because relying on
/// inheritance past this host has already produced the same fatalError three
/// times — #3350 (ArtifactService), #1561 (WorkflowExecutionObserver), and #3298
/// (KGQueryStore). Each was fixed by adding one more forwarding line.
///
/// Two library-scoped stores were still missing from that list, and both are read
/// NON-OPTIONALLY by views that mount under this host:
///   • `ActivityStore` — `StatusIslandToolbarItem` and `ActivityStatusToolbarItem`,
///     which are toolbar items. Toolbar content is laid out by the WINDOW and can
///     be updated after the content subtree beneath it has changed, which is
///     exactly the `HostPreferencesCombiner` frame in the crash reports.
///   • `WorkflowExecutionStore` — `ActivityBrowserView`.
///
/// These source-reading assertions fail the moment either forward is deleted,
/// catching the regression before it ships as a runtime fatalError — the same
/// approach as `ArtifactServiceInjectionTests`.
final class ToolbarActivityStoreInjectionTests: XCTestCase {
    func testDocumentTabViewForwardsActivityStore() throws {
        let source = try Self.appSource("Views/Shell/DocumentTabView.swift")
        XCTAssertTrue(
            source.contains(".environment(library.activityStore)"),
            """
            DocumentTabView must forward library.activityStore. StatusIslandToolbarItem \
            and ActivityStatusToolbarItem read @Environment(ActivityStore.self) \
            non-optionally and mount as toolbar items under this host (#4448).
            """
        )
    }

    func testDocumentTabViewForwardsWorkflowExecutionStore() throws {
        let source = try Self.appSource("Views/Shell/DocumentTabView.swift")
        XCTAssertTrue(
            source.contains(".environment(library.workflowExecutionStore)"),
            """
            DocumentTabView must forward library.workflowExecutionStore. \
            ActivityBrowserView reads @Environment(WorkflowExecutionStore.self) \
            non-optionally under this host (#4448).
            """
        )
    }

    /// The host binds the LIBRARY, not just its `apiClient`. Every library-scoped
    /// value forwarded from the branch then comes off ONE resolved reference, so a
    /// later forward cannot be added from a second, independently-resolved lookup
    /// that might disagree with the first.
    func testDocumentTabViewBindsTheLibraryReference() throws {
        let source = try Self.appSource("Views/Shell/DocumentTabView.swift")
        XCTAssertTrue(
            source.contains("if let library {"),
            "DocumentTabView's content branch must bind the library reference itself (#4448)."
        )
        XCTAssertFalse(
            source.contains("if let apiClient = apiClient {"),
            """
            DocumentTabView must not gate its environment chain on apiClient alone — \
            library-scoped forwards need the library reference in scope (#4448).
            """
        )
    }

    /// The stores must be forwarded INSIDE the branch that renders ContentView,
    /// not after the `else`. A forward that lands outside the resolved-library
    /// branch would not compile against `library`, but pinning the order keeps a
    /// future edit from moving the chain onto the "Library not found" placeholder.
    func testActivityForwardsPrecedeTheNotFoundPlaceholder() throws {
        let source = try Self.appSource("Views/Shell/DocumentTabView.swift")
        guard let activityRange = source.range(of: ".environment(library.activityStore)"),
              let placeholderRange = source.range(of: "Text(\"Library not found\")") else {
            return XCTFail("Expected both the activityStore forward and the not-found placeholder (#4448).")
        }
        XCTAssertTrue(
            activityRange.lowerBound < placeholderRange.lowerBound,
            "library.activityStore must be forwarded in the resolved-library branch (#4448)."
        )
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("../fichero")
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
