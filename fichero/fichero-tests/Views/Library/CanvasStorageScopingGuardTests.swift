import XCTest

/// Regression guards for #4160: canvas/Spatial thumbnails must load through
/// the CURRENT library's `StorageService`, never unconditionally through the
/// global library's — the global-only path 404'd every non-global library's
/// page thumbnails, and a sourceId-only texture cache let two libraries'
/// images collide. Source-surface, mirroring `ShellLayoutGuardTests`.
final class CanvasStorageScopingGuardTests: XCTestCase {
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
        let source = try Self.appSource("Views/Library/LibraryView.swift")
        XCTAssertEqual(
            source.components(separatedBy: "storageService: activeLibraryReference?.storageService").count - 1,
            2,
            "Both SpaceSceneView and Spatial2DCanvas must receive the ACTIVE library's storage (#4160)."
        )
    }
}
