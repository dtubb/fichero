import SwiftUI
import AppKit

/// A reusable inline rename field component for the sidebar
struct InlineRenameField: View {
    let currentName: String
    let placeholder: String
    let onCommit: (String) async throws -> Void
    let onCancel: () -> Void
    
    @State private var newName: String = ""
    @State private var isEditing = false
    @State private var isRenaming = false
    @State private var errorMessage: String?
    @FocusState private var isFocused: Bool

    init(
        currentName: String,
        placeholder: String = "Enter new name",
        onCommit: @escaping (String) async throws -> Void,
        onCancel: @escaping () -> Void = {}
    ) {
        self.currentName = currentName
        self.placeholder = placeholder
        self.onCommit = onCommit
        self.onCancel = onCancel
        self._newName = State(initialValue: currentName)
    }

    var body: some View {
        HStack {
            TextField(placeholder, text: $newName, onCommit: {
                commitRename()
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
            .onChange(of: newName) { _, newValue in
                // Limit length to reasonable size
                if newValue.count > 100 {
                    self.newName = String(newValue.prefix(100))
                }
            }

            if isRenaming {
                ProgressView()
                    .scaleEffect(0.6)
                    .padding(.leading, 4)
            } else {
                Button(action: {
                    commitRename()
                }) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(.green)
                }
                .buttonStyle(.plain)
                .keyboardShortcut(.defaultAction)
                .disabled(newName.isEmpty || newName == currentName)
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

    private func commitRename() {
        guard !newName.isEmpty, newName != currentName else {
            onCancel()
            return
        }

        isRenaming = true
        errorMessage = nil

        Task {
            do {
                try await onCommit(newName)
                isRenaming = false
            } catch {
                errorMessage = error.localizedDescription
                isRenaming = false
                // Keep focused for retry
                isFocused = true
            }
        }
    }
}

#Preview {
    @State var testName = "Test Document"
    
    return InlineRenameField(
        currentName: testName,
        onCommit: { newName in
            print("Renamed to: \(newName)")
            return testName = newName
        },
        onCancel: {
            print("Rename cancelled")
        }
    )
    .padding()
    .previewLayout(.sizeThatFits)
}