@testable import Fichero
import XCTest

/// #4531 — Settings ▸ Models & Providers showed ONLY the MLX section. The
/// provider list, the +/− buttons, and the detail pane were all gone, with no
/// error anywhere, because nothing failed.
///
/// #4503 folded MLX in with `ScrollView { VStack { ProvidersView();
/// LocalInferenceSettingsView } }`. The intent was right — MLX is a provider —
/// but a `ScrollView` offers its content UNBOUNDED height on the scroll axis,
/// and both children are greedy containers with no intrinsic height in that
/// axis:
///
/// - `ProvidersView`'s root is `PlatformHSplitView` (an `HStack`) whose panes
///   are a `List` and a `.frame(maxHeight: .infinity)` detail pane.
/// - `LocalInferenceSettingsView` is a `Form`, which is itself scrollable.
///
/// Given infinite height to fill, the providers browser collapsed. Only the
/// Form drew, which is exactly "shows only MLX".
///
/// The knock-on was the demo blocker: the API-key `SecureField` lives in
/// `ProviderDetailView`, reachable ONLY by selecting a row in the collapsed
/// list, so "I can't see how to add an api key again" was this same bug one
/// step downstream — not a missing field.
///
/// These are source-shape guards: the defect is in the LAYOUT declaration, and
/// a unit test cannot measure a rendered height without a window server. What
/// it can do is pin the shape that must never come back.
@MainActor
final class ProvidersTabLayoutTests: XCTestCase {

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // Settings
            .deletingLastPathComponent()   // Views
            .deletingLastPathComponent()   // fichero-tests
            .deletingLastPathComponent()   // fichero
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertFalse(source.isEmpty, "\(relativePath) is empty — this guard measures nothing")
        return source
    }

    /// Slice out `providersTab`'s body so the assertions below cannot be
    /// satisfied (or broken) by an unrelated ScrollView elsewhere in the file.
    private static func providersTabBody() throws -> String {
        let source = try appSource("Views/Settings/AI/AISettingsView+Tabs.swift")
        let start = try XCTUnwrap(
            source.range(of: "var providersTab: some View {"),
            "providersTab is gone — this guard no longer measures the Models & Providers tab"
        )
        let end = try XCTUnwrap(
            source.range(of: "var downloadsTab: some View {", range: start.upperBound..<source.endIndex),
            "downloadsTab no longer follows providersTab — the slice below would be wrong"
        )
        return String(source[start.upperBound..<end.lowerBound])
    }

    /// The regression itself.
    func testProvidersTabDoesNotWrapItsPanesInAScrollView() throws {
        let body = try Self.providersTabBody()

        XCTAssertFalse(
            body.contains("ScrollView"),
            """
            providersTab wraps its panes in a ScrollView again (#4531). Both \
            panes are greedy containers — an HStack-of-List and a Form — and \
            in unbounded height the providers browser collapses to nothing, \
            which is how Models & Providers came to show only MLX.
            """
        )
    }

    /// Bounds are the actual fix: each pane scrolls itself, so the tab must
    /// hand them a finite height rather than rearranging them.
    func testBothPanesAreGivenFiniteBounds() throws {
        let body = try Self.providersTabBody()

        XCTAssertTrue(
            body.contains("maxHeight: .infinity"),
            "the providers browser must take the flexible height — it is the subject of the screen"
        )
        XCTAssertTrue(
            body.contains("maxHeight: 300") || body.contains("idealHeight:"),
            "the MLX Form must be bounded, or it competes with the browser for unbounded space"
        )
    }

    /// #4503's intent must survive the layout fix: MLX still renders on this
    /// tab and there is still no separate Local LLM tab for it to drift back
    /// into. A "fix" that restored the provider list by evicting MLX would
    /// re-open the bug #4503 closed.
    func testMLXStillRendersBesideTheProviders() throws {
        let body = try Self.providersTabBody()

        XCTAssertTrue(
            body.contains("ProvidersView()"),
            "the provider list must render on the Models & Providers tab"
        )
        XCTAssertTrue(
            body.contains("LocalInferenceSettingsView(store:"),
            "MLX controls must still sit beside the providers (#4503)"
        )

        let source = try Self.appSource("Views/Settings/AI/AISettingsView+Tabs.swift")
        XCTAssertFalse(
            source.contains("var localLLMTab: some View {"),
            "the separate Local LLM tab must stay deleted (#4503)"
        )
    }

    /// The API-key field is reachable only through a provider row, so the
    /// collapsed list took the credential UI with it. Pin that the field still
    /// exists where the fix assumes it does — if it moves, "no way to enter a
    /// key" comes back for a different reason and this test should say so.
    func testAPIKeyEntryRemainsReachableFromTheProviderDetailPane() throws {
        let source = try Self.appSource("Views/Settings/AI/AIProviders/ProvidersView+ProviderDetailView.swift")

        XCTAssertTrue(source.contains("Section(\"API Key\")"), "the API Key section is gone")
        XCTAssertTrue(source.contains("SecureField("), "there is no field to type an API key into")
        XCTAssertTrue(source.contains("saveAPIKey()"), "a typed key has nowhere to go")
    }
}
