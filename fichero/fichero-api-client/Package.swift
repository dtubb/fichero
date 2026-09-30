// swift-tools-version: 5.9
import PackageDescription

// The in-process PythonKit transport (`.inMemory`) is OFF (#5271: the app ships HTTPS and UDS
// only). It is kept, not deleted: set this to true to link PythonKit and compile
// Sources/FicheroAPIClient/InMemory again (FICHERO_INMEMORY), then `FICHERO_FORCE_INMEMORY=1` selects it.
let inMemoryTransport = false
/// The compile condition the InMemory sources and their tests check. Explicit rather than
/// `canImport(PythonKit)`, which a stale module left in .build can answer true for.
let inMemorySettings: [SwiftSetting] = inMemoryTransport ? [.define("FICHERO_INMEMORY")] : []

let package = Package(
    name: "FicheroAPIClient",
    platforms: [
        .macOS(.v14),
        .iOS(.v17)
    ],
    products: [
        .library(
            name: "FicheroAPIClient",
            targets: ["FicheroAPIClient"]
        ),
    ],
    dependencies: [
        .package(url: "https://github.com/apple/swift-openapi-generator", from: "1.6.0"),
        .package(url: "https://github.com/apple/swift-openapi-runtime", from: "1.7.0"),
        .package(url: "https://github.com/apple/swift-openapi-urlsession", from: "1.0.0"),
        .package(url: "https://github.com/apple/swift-http-types", from: "1.0.0"),
        // UDS transport: AsyncHTTPClient (pulls SwiftNIO) can dial an AF_UNIX
        // socket via the `http+unix://` URL scheme. Used only for `.uds` mode;
        // the default `.https` path stays on URLSession.
        .package(url: "https://github.com/swift-server/swift-openapi-async-http-client", from: "1.1.0"),
        // Direct AsyncHTTPClient + NIOPosix (already in the graph transitively via
        // the line above) so the UDS transport can pin a NIOPosix (BSD-sockets)
        // event loop instead of AsyncHTTPClient's macOS default NIOTSEventLoopGroup
        // (Network.framework), whose AF_UNIX NWConnection flows fail to establish
        // under Xcode's debug launch. Versions match the resolved pins → no churn.
        .package(url: "https://github.com/swift-server/async-http-client", from: "1.35.0"),
        .package(url: "https://github.com/apple/swift-nio", from: "2.101.0"),
    ] + (inMemoryTransport
        // In-memory ASGI transport (`.inMemory`, macOS only): drives the Python engine
        // in-process via PythonKit. Every source under Sources/FicheroAPIClient/InMemory is
        // `#if os(macOS) && FICHERO_INMEMORY`, so it compiles only when this is linked.
        ? [.package(url: "https://github.com/pvieito/PythonKit", branch: "main")]
        : []),
    targets: [
        .target(
            name: "FicheroAPIClient",
            dependencies: [
                .product(name: "OpenAPIRuntime", package: "swift-openapi-runtime"),
                .product(name: "OpenAPIURLSession", package: "swift-openapi-urlsession"),
                .product(name: "HTTPTypes", package: "swift-http-types"),
                .product(name: "OpenAPIAsyncHTTPClient", package: "swift-openapi-async-http-client"),
                .product(name: "AsyncHTTPClient", package: "async-http-client"),
                .product(name: "NIOPosix", package: "swift-nio"),
            ] + (inMemoryTransport
                // macOS-only: iOS builds never pull PythonKit (no in-process engine).
                ? [.product(name: "PythonKit", package: "PythonKit", condition: .when(platforms: [.macOS]))]
                : []),
            swiftSettings: inMemorySettings,
            plugins: [
                .plugin(name: "OpenAPIGenerator", package: "swift-openapi-generator")
            ]
        ),
        .testTarget(
            name: "FicheroAPIClientTests",
            dependencies: ["FicheroAPIClient"],
            swiftSettings: inMemorySettings
        ),
    ]
)
