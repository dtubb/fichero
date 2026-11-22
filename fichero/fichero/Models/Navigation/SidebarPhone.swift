import Foundation
#if canImport(UIKit)
import UIKit
#endif

/// The sidebar's phone rule (`ios.nav.sidebar-drills`, #6946): on the iPhone no row expands in place; a tap on a
/// project or a folder pushes that folder's screen. The iPad and the Mac keep the tree.
enum SidebarPhone {
    /// Whether this device is a phone.
    static var isPhone: Bool {
        #if canImport(UIKit) && !os(macOS)
        UIDevice.current.userInterfaceIdiom == .phone
        #else
        false
        #endif
    }

    /// Whether a row with children is drawn as an expandable group: only off the phone.
    nonisolated static func rowExpandsInPlace(isPhone: Bool) -> Bool {
        !isPhone
    }
}
