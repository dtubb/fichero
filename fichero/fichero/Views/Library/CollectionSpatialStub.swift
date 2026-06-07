import SwiftUI

struct CollectionSpatialStub: View {
    let collectionId: String

    var body: some View {
        ContentUnavailableView(
            "Spatial",
            systemImage: "square.3.layers.3d",
            description: Text("Spatial mode for collection \(collectionId) is coming soon.")
        )
    }
}
