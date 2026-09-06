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
///
/// UPDATE (db887a111): the separate MLX Runtime block was later retired — all
/// managed-local runtimes (MLX/spaCy/Kraken/Whisper) are provider ROWS now, so
/// providersTab is a single ProvidersView pane. The #4531 collapse is
/// structurally impossible with one child; the guards below pin the single-pane
/// shape and that local runtimes stay peers rather than being evicted (#4503).
@MainActor
final class ProvidersTabLayoutTests: XCTestCase {

    /// #4493: routed through the shared `AppSource` walk instead of
    /// counting `deletingLastPathComponent()` calls. Counting is correct
    /// only for this file's CURRENT depth — move the file and it resolves
    /// somewhere else and fails later as an unrelated file-not-found.
    private static func appSource(_ relativePath: String) throws -> String {
        let source = try AppSource.text(relativePath)
        XCTAssertFalse(source.isEmpty, "\(relativePath) is empty — this guard measures nothing")
        return source
    }

    /// Slice out `providersTab`'s body so the assertions below cannot be
    /// satisfied (or broken) by an unrelated ScrollView elsewhere in the file.
    private static func providersTabBody() throws -> String {
        let source = try Self.appSource("Views/Settings/AI/AISettingsView+Tabs.swift")
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

    /// After the MLX Runtime block was retired (db887a111 — all local
    /// runtimes folded into provider rows), providersTab is a SINGLE pane:
    /// ProvidersView, handed the flexible height. The original collapse
    /// (#4531) needed TWO greedy children competing for unbounded height; a
    /// lone child cannot collapse itself. Guard that the single pane takes
    /// the flexible frame and no second greedy Form sibling comes back.
    func testProvidersTabHandsTheBrowserTheFlexibleHeight() throws {
        let body = try Self.providersTabBody()

        XCTAssertTrue(
            body.contains("maxHeight: .infinity"),
            "the providers browser must take the flexible height — it is the subject of the screen"
        )
        XCTAssertFalse(
            body.contains("LocalInferenceSettingsView"),
            """
            the separate MLX Runtime Form is back in providersTab — db887a111 \
            retired it (MLX is a provider ROW now). A second greedy Form here \
            competing for unbounded height is exactly the #4531 collapse.
            """
        )
    }

    /// #4503's intent must survive the redesign: MLX (and the other managed-
    /// local runtimes) still render on this tab and there is no separate Local
    /// LLM tab. The mechanism changed — they are provider ROWS inside
    /// ProvidersView now, not a LocalInferenceSettingsView beside it
    /// (db887a111) — so the guard follows them into the provider detail pane.
    func testLocalRuntimesRenderAsProviderRows() throws {
        let body = try Self.providersTabBody()
        XCTAssertTrue(
            body.contains("ProvidersView()"),
            "the provider list must render on the Models & Providers tab"
        )

        let source = try Self.appSource("Views/Settings/AI/AISettingsView+Tabs.swift")
        XCTAssertFalse(
            source.contains("var localLLMTab: some View {"),
            "the separate Local LLM tab must stay deleted (#4503)"
        )

        // MLX/spaCy/Kraken/Whisper are peers in the provider list now — the
        // detail pane keys off ManagedLocalRuntime to give them their local
        // model/provisioning UI instead of a Server URL + API key. If that
        // branch is gone, local runtimes have been evicted from the rows and
        // #4503 is reopened by a different route.
        let detail = try Self.appSource(
            "Views/Settings/AI/AIProviders/ProvidersView+ProviderDetailView.swift"
        )
        XCTAssertTrue(
            detail.contains("ManagedLocalRuntime"),
            "managed-local runtimes (MLX/spaCy/Kraken/Whisper) must still be handled as provider rows (#4503)"
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
