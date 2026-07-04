import SwiftUI

/// Input area for chat messages.
///
/// The caller supplies a `leading` accessory — the composer paperclip attach
/// menu (#2449 step 2). It's always present now (was a compact-only button),
/// so every width can attach context; pass `EmptyView` for no accessory.
struct ChatInputView<Leading: View>: View {
    @Binding var inputText: String
    let isLoading: Bool
    let onSend: () -> Void
    private let leading: Leading

    init(
        inputText: Binding<String>,
        isLoading: Bool,
        onSend: @escaping () -> Void,
        @ViewBuilder leading: () -> Leading
    ) {
        self._inputText = inputText
        self.isLoading = isLoading
        self.onSend = onSend
        self.leading = leading()
    }

    var body: some View {
        HStack(spacing: 12) {
            leading

            TextField("Ask a question about your documents...", text: $inputText, axis: .vertical)
                .textFieldStyle(.plain)
                .lineLimit(1...5)
                .onSubmit {
                    onSend()
                }

            Button(action: onSend) {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.title2)
                    .foregroundColor(inputText.isEmpty ? .secondary : .accentColor)
            }
            .buttonStyle(.plain)
            .help("Send your message (Return)")
            .disabled(inputText.isEmpty || isLoading)
            .keyboardShortcut(.return, modifiers: [])
        }
        .padding()
        .background(Color(.windowBackgroundColor))
    }
}
