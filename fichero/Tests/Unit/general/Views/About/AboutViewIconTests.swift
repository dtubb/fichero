@testable import Fichero
import XCTest

/// Tests for AboutView.appIconAssetName (#3236) — resolving the bundled app-icon
/// asset name from an Info.plist CFBundleIcons dictionary so the iOS About box
/// shows the real icon, not an SF Symbol placeholder. Pure dictionary parsing;
/// no live bundle.
final class AboutViewIconTests: XCTestCase {

    private func infoDict(iconFiles: [String]?) -> [String: Any] {
        var primary: [String: Any] = [:]
        if let iconFiles { primary["CFBundleIconFiles"] = iconFiles }
        return ["CFBundleIcons": ["CFBundlePrimaryIcon": primary]]
    }

    /// The last CFBundleIconFiles entry is the highest resolution.
    func testReturnsLastIconFile() {
        let dict = infoDict(iconFiles: ["AppIcon20x20", "AppIcon40x40", "AppIcon60x60"])
        XCTAssertEqual(AboutView.appIconAssetName(from: dict), "AppIcon60x60")
    }

    func testSingleIconFile() {
        XCTAssertEqual(AboutView.appIconAssetName(from: infoDict(iconFiles: ["AppIcon-iOS"])),
                       "AppIcon-iOS")
    }

    func testNilInfoDictionary() {
        XCTAssertNil(AboutView.appIconAssetName(from: nil))
    }

    func testMissingCFBundleIcons() {
        XCTAssertNil(AboutView.appIconAssetName(from: ["CFBundleName": "Fichero"]))
    }

    func testMissingPrimaryIcon() {
        XCTAssertNil(AboutView.appIconAssetName(from: ["CFBundleIcons": [:]]))
    }

    func testEmptyIconFilesArray() {
        XCTAssertNil(AboutView.appIconAssetName(from: infoDict(iconFiles: [])))
    }

    /// A present-but-empty trailing name is rejected (would resolve to no asset).
    func testEmptyTrailingNameRejected() {
        XCTAssertNil(AboutView.appIconAssetName(from: infoDict(iconFiles: ["AppIcon", ""])))
    }
}
