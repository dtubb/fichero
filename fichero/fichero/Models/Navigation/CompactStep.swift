import Foundation

/// One screen of the iPhone drill-down (`ios.nav.one-path`, #6944).
enum CompactStep: Hashable {
    case folder(String)
    case item(String)
    case reader
    case info
}
