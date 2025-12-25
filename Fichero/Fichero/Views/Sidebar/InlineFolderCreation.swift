import SwiftUI
import AppKit

/// A reusable inline folder creation field component for the sidebar
struct InlineFolderCreation: View {
    let section: SidebarSection
    let parentId: String?
    let onCommit: (String) async throws -> Void
    let onCancel: () -> Void
    
    @State private var folderName: String = "untitled folder"
    @State private var isCreating = false
    @State private var errorMessage: String?
    @FocusState private var isFocused: Bool

    init(
        section: SidebarSection,
        parentId: String?,
        onCommit: @escaping (String) async throws -> Void,
        onCancel: @escaping () -> Void = {}
    ) {
        self.section = section
        self.parentId = parentId
        self.onCommit = onCommit
        self.onCancel = onCancel
    }

    var body: some View {
        HStack {
            TextField("Enter folder name", text: $folderName, onCommit: {
                createFolder()
            })
            .textFieldStyle(.plain)
            .font(.body)
            .disableAutocorrection(true)
            .focused($isFocused)
            .onAppear {
                isFocused = true
                DispatchQueue.main.async {
                    // Select all text when field appears
                    if let textField = NSApp.keyWindow?.firstResponder as? NSTextField {
                        textField.currentEditor()?.selectAll(nil)
                    }
                }
            }
            .onChange(of: folderName) { _, newValue in
                // Limit length to reasonable size
                if newValue.count > 100 {
                    self.folderName = String(newValue.prefix(100))
                }
            }

            if isCreating {
                ProgressView()
                    .scaleEffect(0.6)
                    .padding(.leading, 4)
            } else {
                Button(action: {
                    createFolder()
                }) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(.green)
                }
                .buttonStyle(.plain)
                .keyboardShortcut(.defaultAction)
                .disabled(folderName.isEmpty)
            }
        }
        .padding(4)
        .background(
            RoundedRectangle(cornerRadius: 4)
                .fill(Color(.textBackgroundColor))
                .stroke(Color.accentColor, lineWidth: 1)
        )
        .overlay(
            // Error message overlay
            Group {
                if let errorMessage = errorMessage {
                    VStack {
                        Spacer()
                        Text(errorMessage)
                            .font(.caption)
                            .foregroundColor(.red)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, 4)
                    }
                }
            }
        )
        .onExitCommand {
            // Handle Escape key
            onCancel()
        }
    }

    private func createFolder() {
        guard !folderName.isEmpty else {
            onCancel()
            return
        }

        isCreating = true
        errorMessage = nil

        Task {
            do {
                try await onCommit(folderName)
                isCreating = false
            } catch {
                errorMessage = error.localizedDescription
                isCreating = false
                // Keep focused for retry
                isFocused = true
            }
        }
    }
}

#Preview {
    InlineFolderCreation(
        section: .library,
        parentId: nil,
        onCommit: { folderName in
            print("Create folder: \(folderName)")
        },
        onCancel: {
            print("Folder creation cancelled")
        }
    )
    .padding()
    .previewLayout(.sizeThatFits)
}