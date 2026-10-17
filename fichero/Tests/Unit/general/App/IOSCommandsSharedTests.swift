import XCTest

/// spec: menus-and-commands §`menus.ipad-full-parity` (#3307). The iOS App declares its menu bar
/// from the SAME command structs as the Mac, never a second set. A source scan, because the iOS
/// App type does not compile into the Mac test host.
final class IOSCommandsSharedTests: XCTestCase {

    func testIOSAppDeclaresTheSharedMenus() throws {
        let source = try String(
            contentsOf: AppSource.root().appendingPathComponent("FicheroApp_iOS.swift"), encoding: .utf8)
        XCTAssertTrue(source.contains(".commands {"), "the iOS App must declare .commands (#3307)")
        for shared in ["FileMenuCommands()", "ViewMenuCommands()", "GoMenuCommands()", "PageAndProjectMenuCommands()"] {
            XCTAssertTrue(source.contains(shared), "iOS menu bar is missing the shared \(shared)")
        }
    }
}
