// swift-tools-version:6.0
import PackageDescription

let package = Package(
    name: "InMemoryASGITransport",
    platforms: [.macOS(.v13)],
    // Swift 5 language mode: PythonObject is not Sendable, and we guarantee
    // thread-affinity for all Python calls ourselves via PythonWorker. Strict
    // Swift 6 concurrency checking would otherwise reject ferrying PythonObjects
    // across the worker-thread boundary. Correctness is enforced by design, not
    // by the type system, here.
    products: [
        .library(name: "InMemoryASGITransport", targets: ["InMemoryASGITransport"]),
    ],
    dependencies: [
        .package(url: "https://github.com/apple/swift-openapi-runtime", from: "1.0.0"),
        .package(url: "https://github.com/pvieito/PythonKit", branch: "main"),
    ],
    targets: [
        .target(
            name: "InMemoryASGITransport",
            dependencies: [
                .product(name: "OpenAPIRuntime", package: "swift-openapi-runtime"),
                .product(name: "PythonKit", package: "PythonKit"),
            ]
        ),
        .testTarget(
            name: "InMemoryASGITransportTests",
            dependencies: ["InMemoryASGITransport"]
        ),
    ],
    swiftLanguageModes: [.v5]
)
