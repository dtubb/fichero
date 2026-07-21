// swift-tools-version: 5.9
import PackageDescription

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
        // In-memory ASGI transport (`.inMemory`, macOS only): drives the Python
        // engine in-process via PythonKit. iOS never resolves/links this — the
        // product dependency below is `.when(platforms: [.macOS])`, and every
        // source file under Sources/FicheroAPIClient/InMemory is `#if os(macOS)`.
        .package(url: "https://github.com/pvieito/PythonKit", branch: "main"),
    ],
    targets: [
        .target(
            name: "FicheroAPIClient",
            dependencies: [
                .product(name: "OpenAPIRuntime", package: "swift-openapi-runtime"),
                .product(name: "OpenAPIURLSession", package: "swift-openapi-urlsession"),
                .product(name: "HTTPTypes", package: "swift-http-types"),
                .product(name: "OpenAPIAsyncHTTPClient", package: "swift-openapi-async-http-client"),
                // macOS-only: iOS builds never pull PythonKit (no in-process engine).
                .product(name: "PythonKit", package: "PythonKit", condition: .when(platforms: [.macOS])),
            ],
            plugins: [
                .plugin(name: "OpenAPIGenerator", package: "swift-openapi-generator")
            ]
        ),
        .testTarget(
            name: "FicheroAPIClientTests",
            dependencies: ["FicheroAPIClient"]
        ),
    ]
)
