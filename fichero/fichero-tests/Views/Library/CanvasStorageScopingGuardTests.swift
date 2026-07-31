import XCTest

/// Regression guards for #4160: canvas/Spatial thumbnails must load through
/// the CURRENT library's `StorageService`, never unconditionally through the
/// global library's — the global-only path 404'd every non-global library's
/// page thumbnails, and a sourceId-only texture cache let two libraries'
/// images collide. Source-surface, mirroring `ShellLayoutGuardTests`.
final class CanvasStorageScopingGuardTests: XCTestCase {
    /// Every Swift file under a directory, concatenated.
    ///
    /// A guard that names ONE file breaks the moment that file is split, and
    /// reports a broken INVARIANT when all that moved was a declaration: the
    /// #4353 split moved both storage injections from `LibraryView.swift` to
    /// `LibraryView+CanvasModes.swift` and this suite failed while the app was
    /// correct. Scanning the directory asks the question that actually matters
    /// — does the app do this anywhere — and survives the next split.
    private static func appSources(inDirectory relativePath: String) throws -> String {
        let dir = appRoot().appendingPathComponent(relativePath)
        let files = try FileManager.default.subpathsOfDirectory(atPath: dir.path)
            .filter { $0.hasSuffix(".swift") }
        return try files
            .map { try String(contentsOf: dir.appendingPathComponent($0), encoding: .utf8) }
            .joined(separator: "\n")
    }

    private static func appRoot() -> URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testSpaceTextureCacheIsLibraryScoped() throws {
        let source = try Self.appSource("Views/Library/ViewModes/Canvas/3D/SpaceSceneView.swift")
        XCTAssertTrue(
            source.contains("libraryScopeKey"),
            "SpaceTextureCache must key textures by library scope + sourceId — "
                + "a sourceId-only key collides across libraries (#4160)."
        )
        XCTAssertTrue(
            source.contains("storageService: storageService"),
            "SpaceSceneView's 2D fallback must forward the injected storageService (#4160)."
        )
    }

    func testSpatialThumbnailAcceptsInjectedService() throws {
        let source = try Self.appSource(
            "Views/Library/ViewModes/Canvas/2D/Legacy/SpatialNodeThumbnail.swift"
        )
        XCTAssertTrue(
            source.contains("var storageService: StorageService?"),
            "SpatialNodeThumbnail must accept the current library's service (#4160)."
        )
        XCTAssertTrue(
            source.contains("storageService ?? LibraryManager.shared.globalLibrary?.storageService"),
            "Global-library storage is a FALLBACK only, never the unconditional path (#4160)."
        )
    }

    func testLibraryViewInjectsActiveLibraryStorage() throws {
        let source = try Self.appSources(inDirectory: "Views/Library")
        XCTAssertEqual(
            source.components(separatedBy: "storageService: activeLibraryReference?.storageService").count - 1,
            2,
            "Both SpaceSceneView and Spatial2DCanvas must receive the ACTIVE library's storage (#4160)."
        )
    }
}
