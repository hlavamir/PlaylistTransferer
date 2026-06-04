// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "PlaylistTransferer",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(
            name: "PlaylistTransferer",
            path: "Sources/PlaylistTransferer"
        )
    ]
)
