import SwiftUI

// MARK: - General Settings

/// General application settings
struct GeneralSettingsView: View {
    @AppStorage("thumbnailSize") private var thumbnailSize: Double = 120
    @AppStorage("autoExtractText") private var autoExtractText: Bool = true
    @AppStorage("autoCreateEmbeddings") private var autoCreateEmbeddings: Bool = true

    var body: some View {
        Form {
            Section("Display") {
                Slider(value: $thumbnailSize, in: 80...200) {
                    Text("Thumbnail Size")
                }
            }

            Section("Ingestion") {
                Toggle("Auto-extract text from documents", isOn: $autoExtractText)
                Toggle("Auto-create search embeddings", isOn: $autoCreateEmbeddings)
            }
        }
        .padding()
    }
}
