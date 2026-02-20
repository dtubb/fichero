import SwiftUI

// MARK: - WelcomeView

struct WelcomeView: View {
    let onCreateLibrary: () -> Void
    let onOpenLibrary: () -> Void

    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "doc.richtext")
                .font(.system(size: 64))
                .foregroundColor(.accentColor)

            Text("Welcome to Fichero")
                .font(.largeTitle)
                .fontWeight(.semibold)

            Text("Create a new library or open an existing one to get started.")
                .font(.body)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)

            HStack(spacing: 16) {
                Button(action: onCreateLibrary) {
                    Label("New Library", systemImage: "plus")
                }
                .buttonStyle(.borderedProminent)

                Button(action: onOpenLibrary) {
                    Label("Open Library", systemImage: "folder")
                }
                .buttonStyle(.bordered)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(40)
    }
}
