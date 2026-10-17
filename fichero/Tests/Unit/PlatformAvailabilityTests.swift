import Foundation
import Testing

/// macOS/iOS 26 and 27 are both supported; the floor is 26 (#5730).
/// spec: xcode-build-configs: platform.supports-tahoe-and-golden-gate, platform.27-only-api-gated.
struct PlatformAvailabilityTests {
    private static let repo = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()

    private func swiftSources(under sub: String) -> [URL] {
        let root = Self.repo.appendingPathComponent(sub)
        let walk = FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil)
        return (walk?.allObjects as? [URL] ?? []).filter { $0.pathExtension == "swift" }
    }

    @Test("the api-client package targets macOS 26 and iOS 26")
    func packageFloorIs26() throws {
        let manifest = Self.repo.appendingPathComponent("fichero/fichero-api-client/Package.swift")
        let text = try String(contentsOf: manifest, encoding: .utf8)
        #expect(text.contains(".macOS(\"26.0\")") && text.contains(".iOS(\"26.0\")"))
    }
}
