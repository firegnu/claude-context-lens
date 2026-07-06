// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "ContextLens",
    platforms: [.macOS(.v14)],
    targets: [
        .target(name: "ContextLensCore"),
        .executableTarget(
            name: "ContextLensApp",
            dependencies: ["ContextLensCore"]
        ),
        .testTarget(
            name: "ContextLensCoreTests",
            dependencies: ["ContextLensCore"],
            resources: [.copy("Fixtures")]
        ),
    ]
)
