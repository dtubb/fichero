@testable import Fichero
import XCTest

/// #5015 (`magnifier.per-pane-switches`): each Preview pane owns its magnifier and loupe. What breaks without it:
/// the switches were one `@AppStorage` key, so closing the magnifier in one of two Previews closed it in both.
final class PreviewMagnifierPerPaneShapeTests: XCTestCase {
    func testThePreviewKeepsItsSwitchesPerPane() throws {
        let view = try AppSource.code("Views/Preview/ImageViewer/ZoomableImagePreviewMac.swift")
        for name in ["magnifierEnabled", "loupeEnabled", "magnifierLocked", "loupeLocked"] {
            XCTAssertTrue(view.contains("@PaneOnlyStorage(\"imagePreview.\(name)\"") && view.contains(") var \(name) = false"), name)
            XCTAssertFalse(view.contains("@AppStorage(\"imagePreview.\(name)\")"), name)
        }
    }

    func testTheMenuActsOnTheFocusedPaneNotASharedFlag() throws {
        let menu = try AppSource.code("App/Menus/ImagePreviewMenuCommands.swift")
        for name in ["magnifierEnabled", "loupeEnabled", "magnifierLocked", "loupeLocked"] {
            XCTAssertFalse(menu.contains("@AppStorage(\"imagePreview.\(name)\")"), name)
        }
        XCTAssertTrue(menu.contains("zoomActions?.magnifier?.toggle()"))
        XCTAssertTrue(menu.contains("zoomActions?.loupe?.toggle()"))
    }

    func testTheMenuValueRepublishesWhenASwitchChanges() {
        func actions(magnifierOn: Bool) -> ImageZoomActions {
            ImageZoomActions(
                zoomIn: {}, zoomOut: {}, actualSize: {}, zoomToFit: {}, canZoomIn: true, canZoomOut: true,
                magnifier: .init(isOn: magnifierOn, isLocked: false, toggle: {}, toggleLock: {})
            )
        }
        XCTAssertEqual(actions(magnifierOn: true), actions(magnifierOn: true))
        XCTAssertNotEqual(actions(magnifierOn: true), actions(magnifierOn: false))
    }

    func testTheOnOffIsRememberedAsTheStartValueOfANewPane() throws {
        let view = try AppSource.code("Views/Preview/ImageViewer/ZoomableImagePreviewMac.swift")
        XCTAssertTrue(view.contains("@PaneOnlyStorage(\"imagePreview.magnifierEnabled\", remembers: true)"))
        XCTAssertTrue(view.contains("@PaneOnlyStorage(\"imagePreview.loupeEnabled\", remembers: true)"))
        XCTAssertTrue(view.contains("_magnifierEnabled.adoptSeed()"))
    }

    func testAnEntryIsPerPane() {
        let a = UUID(), b = UUID()
        let map = PaneScopedOption.setting(true, in: "{}", pane: a)
        XCTAssertTrue(PaneScopedOption.hasEntry(map, pane: a))
        XCTAssertFalse(PaneScopedOption.hasEntry(map, pane: b))
        XCTAssertFalse(PaneScopedOption.value(map, pane: b, shared: false))
    }
}
