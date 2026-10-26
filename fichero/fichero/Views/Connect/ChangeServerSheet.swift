#if os(iOS) || os(visionOS)
import SwiftUI

/// The Connect to a Mac sheet with Cancel: pairs with another Mac (or the first one) and reconnects.
/// Shared by the recovery bar and the connection menu (#6124).
struct ChangeServerSheet: View {
    @Environment(\.dismiss) private var dismiss
    let onConnected: @MainActor () async -> Void

    var body: some View {
        NavigationStack {
            RemoteConnectionSetupView {
                dismiss()
                await onConnected()
            }
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }
}

#Preview {
    ChangeServerSheet {}
        .environment(AppState())
        .environment(LibraryManager.shared)
        .environment(MobileCaptureQueueStore())
}
#endif
