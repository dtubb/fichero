import Foundation

/// The sidebar's phone rule (`ios.nav.sidebar-drills`, #6946): on the iPhone no row expands in place; a tap on a
/// project or a folder pushes that folder's screen. The iPad and the Mac keep the tree.
enum SidebarPhone {
    /// Whether this device is a phone: the hardware model names an iPhone (the simulator names its model in the
    /// environment). Foundation only; SwiftUI has no device idiom and a size class is not one (a large iPhone in
    /// landscape is regular width).
    static let isPhone: Bool = {
        #if os(iOS)
        let env = ProcessInfo.processInfo.environment
        if let simulated = env["SIMULATOR_MODEL_IDENTIFIER"] { return simulated.hasPrefix("iPhone") }
        var size = 0
        sysctlbyname("hw.machine", nil, &size, nil, 0)
        var machine = [CChar](repeating: 0, count: size)
        sysctlbyname("hw.machine", &machine, &size, nil, 0)
        return String(cString: machine).hasPrefix("iPhone")
        #else
        false
        #endif
    }()

    /// Whether a row with children is drawn as an expandable group: only off the phone.
    nonisolated static func rowExpandsInPlace(isPhone: Bool) -> Bool {
        !isPhone
    }

    /// A row with children draws as a disclosure tree on the Mac and iPad; on the phone it is a flat row that pushes (#6946).
    nonisolated static func showsDisclosure(isExpandable: Bool, isPhone: Bool) -> Bool {
        isExpandable && rowExpandsInPlace(isPhone: isPhone)
    }
}
