import XCTest

/// Guardrail for #3386 ("No Observable object of type ArtifactService
/// found"). SwiftUI's environment does NOT flow across separate `Scene`s, so
/// every window/document scene root that can present a view reading
/// `@Environment(ArtifactService.self)` must inject
/// `library.artifactService` itself — exactly like the About window injects
/// `appState` (see `testMacAboutWindowInjectsAppState`).
///
/// The artifact-service consumers (`ContentView`, `DocumentTabView`,
/// `LibraryView`, `DocumentKGSurface`, `ArtifactEntitiesView`,
/// `ArtifactsInspectorPane`, `DocumentInspector`) are reached only through two
/// injecting roots:
///   • `LibraryWorkspaceRoot` — main window, Duplicate Window (WindowSeed), and
///     the iOS main window all funnel through it above `DocumentTabView`.
///   • `DocumentDetailWindow` — the detachable `document-detail` scene
///     (macOS + iOS), which self-injects per-library services.
/// These source-reading assertions fail the moment either injection is deleted,
/// catching the regression before it ships as a runtime fatalError.
final class ArtifactServiceInjectionTests: XCTestCase {
    func testWorkspaceRootInjectsArtifactService() throws {
        let source = try Self.appSource("Views/Library/Workspace/LibraryWorkspaceRoot.swift")
        // The main / Duplicate / iOS scene roots host DocumentTabView (and thus
        // ContentView, LibraryView, the inspector…) here; the service must ride
        // the same per-library environment chain.
        XCTAssertTrue(
            source.contains(".environment(library.artifactService)"),
            "LibraryWorkspaceRoot must inject library.artifactService so ContentView and its consumers resolve it (#3386)."
        )
    }

    func testDocumentDetailWindowInjectsArtifactService() throws {
        let source = try Self.appSource("Views/Inspector/FocusedDocument.swift")
        // The detached document-detail scene (macOS FicheroApp + iOS
        // FicheroAppIOS) presents DocumentInspector, which reads the service.
        // The one-service line became the WHOLE per-library chain
        // (.libraryServiceEnvironment, 2026-08-09 scene-injection sweep) —
        // artifactService rides in it along with every sibling service.
        XCTAssertTrue(
            source.contains(".libraryServiceEnvironment(library)")
                || source.contains(".environment(library.artifactService)"),
            "DocumentDetailWindow must inject library.artifactService for the detached DocumentInspector (#3386)."
        )
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = try AppSource.root()
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
