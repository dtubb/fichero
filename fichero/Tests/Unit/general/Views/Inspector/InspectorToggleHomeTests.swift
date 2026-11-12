@testable import Fichero
import SwiftUI
import Testing

/// Where the Show/Hide Inspector button sits (#6561, `shell.inspector.toggle-reachable-on-ipad`): the Mac keeps it in
/// the docked inspector column's toolbar section; iOS, whose docked column has no bar of its own, keeps it in the
/// content's navigation bar at every width.
struct InspectorToggleHomeTests {
    @Test func theMacDockedInspectorCarriesItsOwnToggle() {
        #expect(InspectorToggleHome.home(usesDockedInspector: true, isMac: true) == .inspectorColumn)
    }

    @Test func anIPadDockedInspectorIsToggledFromTheContentBar() {
        #expect(InspectorToggleHome.home(usesDockedInspector: true, isMac: false) == .detailBar)
    }

    @Test func anIPhoneSheetInspectorIsToggledFromTheContentBar() {
        #expect(InspectorToggleHome.home(usesDockedInspector: false, isMac: false) == .detailBar)
    }

    /// Every regular-width placement on iOS leads to the content bar: the docked column is what a regular iPad gets.
    @Test func aRegularIPadPlacementLeadsToTheContentBar() {
        let placement = InspectorPlacement.adaptiveDefault(horizontalSizeClass: .regular)
        #expect(InspectorToggleHome.home(usesDockedInspector: placement != .sheet, isMac: false) == .detailBar)
    }
}
