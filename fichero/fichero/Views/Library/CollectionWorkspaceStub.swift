import SwiftUI

struct CollectionWorkspaceStub: View {
    let collectionId: String

    var body: some View {
        ContentUnavailableView(
            "Workspace",
            systemImage: "square.stack.3d.up",
            description: Text("Workspace mode for collection \(collectionId) is coming soon.")
        )
    }
}
