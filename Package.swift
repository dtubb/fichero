// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "SwiftUISidebarDemo",
    platforms: [
        .iOS(.v17),
        .macOS(.v14),
        .watchOS(.v10),
        .tvOS(.v17)
    ],
    products: [
        .library(
            name: "SwiftUISidebarDemo",
            targets: ["SwiftUISidebarDemo"]),
    ],
    targets: [
        .target(
            name: "SwiftUISidebarDemo",
            swiftSettings: [
                .enableExperimentalFeature("StrictConcurrency"),
            ]),
        ),
    ]
)