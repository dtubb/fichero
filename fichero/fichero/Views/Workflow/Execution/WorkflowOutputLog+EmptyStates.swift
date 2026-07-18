import SwiftUI

// MARK: - Empty State Views

extension WorkflowOutputLog {

    var defaultEmptyStateView: some View {
        VStack(spacing: 8) {
            Image(systemName: "doc.text.magnifyingglass")
                .font(.title2)
                .foregroundColor(.secondary)

            Text("No output yet")
                .font(.caption)
                .foregroundColor(.secondary)

            Text("Run the workflow to see processing results")
                .font(.caption2)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(.textBackgroundColor))
    }

    func errorStateView(error: String?) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.title)
                .foregroundColor(.red)

            Text("Workflow Failed")
                .font(.headline)
                .foregroundColor(.primary)

            if let error = error {
                Text(error)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 20)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(.textBackgroundColor))
    }

    var warningStateView: some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.circle.fill")
                .font(.title)
                .foregroundColor(.orange)

            Text("No Documents Processed")
                .font(.headline)
                .foregroundColor(.primary)

            Text("""
                The workflow completed but didn't process any documents.
                Check that the source node has a valid collection selected.
                """)
                .font(.caption)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 20)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(.textBackgroundColor))
    }

}
