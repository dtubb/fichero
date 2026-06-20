#if canImport(UIKit) && !os(macOS)
import SwiftUI
import UIKit
import UniformTypeIdentifiers

struct MobileCaptureQueueView: View {
    @ObservedObject var queue: MobileCaptureQueueStore
    var retryPendingUploads: (() async -> Void)?

    @Environment(\.dismiss) private var dismiss
    @State private var pickerSource: CaptureSource?
    @State private var captureError: String?

    var body: some View {
        NavigationStack {
            List {
                Section("Capture") {
                    #if os(visionOS)
                    Button {
                        pickerSource = .library
                    } label: {
                        Label("Choose From Library", systemImage: "photo.on.rectangle")
                    }
                    #else
                    Button {
                        pickerSource = .camera
                    } label: {
                        Label("Take Photo", systemImage: "camera")
                    }

                    Button {
                        pickerSource = .library
                    } label: {
                        Label("Choose From Library", systemImage: "photo.on.rectangle")
                    }
                    #endif

                    if let captureError {
                        Text(captureError)
                            .font(.caption)
                            .foregroundStyle(.red)
                    }
                }

                Section("Queue") {
                    if queue.items.isEmpty {
                        ContentUnavailableView(
                            "No Captures Yet",
                            systemImage: "camera",
                            description: Text("Save photos, PDFs, and web pages here before the paired library is reachable.")
                        )
                    } else {
                        ForEach(queue.items) { item in
                            MobileCaptureQueueItemCard(
                                item: item,
                                queue: queue
                            )
                        }
                        .onDelete { indexSet in
                            for index in indexSet {
                                queue.removeItem(id: queue.items[index].id)
                            }
                        }
                    }
                }

                Section("Status") {
                    LabeledContent("Pending") {
                        Text("\(queue.pendingCount)")
                    }
                    LabeledContent("Uploaded") {
                        Text("\(queue.uploadedCount)")
                    }

                    Text("Uploads stay on this device until Fichero can reach the paired library again.")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    if let retryPendingUploads {
                        Button {
                            Task { await retryPendingUploads() }
                        } label: {
                            Label("Retry Pending Uploads", systemImage: "arrow.clockwise")
                        }
                        .disabled(queue.pendingCount == 0)
                    }
                }
            }
            .navigationTitle("Capture Queue")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") {
                        dismiss()
                    }
                }
            }
            .sheet(item: $pickerSource) { source in
                MobileCaptureImagePicker(
                    sourceType: source.sourceType,
                    onImage: { image in
                        handleCapturedImage(image, source: source)
                    },
                    onCancel: {
                        pickerSource = nil
                    }
                )
            }
        }
    }

    private func handleCapturedImage(_ image: UIImage, source: CaptureSource) {
        pickerSource = nil
        let imageData = image.jpegData(compressionQuality: 0.9)
        let fallbackData = imageData ?? image.pngData()
        guard let data = fallbackData else {
            captureError = "Could not encode the captured image."
            return
        }

        do {
            let catalog = MobileCaptureCatalogFields(sourceArchiveHint: source.defaultSourceHint)
            _ = try queue.enqueueCapturedImage(
                data,
                catalog: catalog,
                fileExtension: imageData == nil ? "png" : "jpg"
            )
            captureError = nil
        } catch {
            captureError = error.localizedDescription
        }
    }
}

private struct MobileCaptureQueueItemCard: View {
    let item: MobileCaptureQueueItem
    @ObservedObject var queue: MobileCaptureQueueStore

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                preview

                VStack(alignment: .leading, spacing: 4) {
                    TextField("Title", text: titleBinding)
                        .textInputAutocapitalization(.words)
                        .textFieldStyle(.roundedBorder)

                    TextField("Folder", text: folderBinding)
                        .textFieldStyle(.roundedBorder)

                    TextField("Series", text: seriesBinding)
                        .textFieldStyle(.roundedBorder)
                }
            }

            HStack(spacing: 12) {
                TextField("Page / order", text: pageOrderBinding)
                    .textFieldStyle(.roundedBorder)
                    .keyboardType(.numberPad)

                TextField("Source / archive hint", text: sourceHintBinding)
                    .textFieldStyle(.roundedBorder)
            }

            TextField("Notes", text: notesBinding, axis: .vertical)
                .textFieldStyle(.roundedBorder)

            HStack {
                statusBadge
                Spacer()
                Button("Remove", role: .destructive) {
                    queue.removeItem(id: item.id)
                }
            }
        }
        .padding(.vertical, 4)
    }

    private var preview: some View {
        Group {
            if let image = UIImage(contentsOfFile: queue.imageURL(for: item).path) {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
            } else {
                ZStack {
                    RoundedRectangle(cornerRadius: 12)
                        .fill(Color.secondary.opacity(0.12))
                    Image(systemName: "photo")
                        .foregroundStyle(.secondary)
                }
            }
        }
        .frame(width: 72, height: 72)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private var statusBadge: some View {
        Text(item.uploadState.rawValue.capitalized)
            .font(.caption2.weight(.semibold))
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(Capsule().fill(Color.secondary.opacity(0.15)))
    }

    private var titleBinding: Binding<String> {
        Binding(
            get: { item.catalog.title },
            set: { newValue in
                queue.updateCatalog(id: item.id) { $0.title = newValue }
            }
        )
    }

    private var folderBinding: Binding<String> {
        Binding(
            get: { item.catalog.folderName },
            set: { newValue in
                queue.updateCatalog(id: item.id) { $0.folderName = newValue }
            }
        )
    }

    private var seriesBinding: Binding<String> {
        Binding(
            get: { item.catalog.seriesName },
            set: { newValue in
                queue.updateCatalog(id: item.id) { $0.seriesName = newValue }
            }
        )
    }

    private var pageOrderBinding: Binding<String> {
        Binding(
            get: {
                item.catalog.pageOrder.map(String.init) ?? ""
            },
            set: { newValue in
                queue.updateCatalog(id: item.id) { catalog in
                    let trimmed = newValue.trimmingCharacters(in: .whitespacesAndNewlines)
                    catalog.pageOrder = Int(trimmed)
                }
            }
        )
    }

    private var notesBinding: Binding<String> {
        Binding(
            get: { item.catalog.notes },
            set: { newValue in
                queue.updateCatalog(id: item.id) { $0.notes = newValue }
            }
        )
    }

    private var sourceHintBinding: Binding<String> {
        Binding(
            get: { item.catalog.sourceArchiveHint },
            set: { newValue in
                queue.updateCatalog(id: item.id) { $0.sourceArchiveHint = newValue }
            }
        )
    }
}

private enum CaptureSource: Identifiable {
    case camera
    case library

    var id: Int {
        switch self {
        case .camera:
            return 0
        case .library:
            return 1
        }
    }

    var sourceType: UIImagePickerController.SourceType {
#if os(visionOS)
        return .photoLibrary
#else
        switch self {
        case .camera:
            return .camera
        case .library:
            return .photoLibrary
        }
#endif
    }

    var defaultSourceHint: String {
        switch self {
        case .camera:
            return "camera"
        case .library:
            return "photo-library"
        }
    }
}

private struct MobileCaptureImagePicker: UIViewControllerRepresentable {
    let sourceType: UIImagePickerController.SourceType
    let onImage: (UIImage) -> Void
    let onCancel: () -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(onImage: onImage, onCancel: onCancel)
    }

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let controller = UIImagePickerController()
        controller.delegate = context.coordinator
        controller.sourceType = UIImagePickerController.isSourceTypeAvailable(sourceType) ? sourceType : .photoLibrary
        controller.allowsEditing = false
        controller.mediaTypes = [UTType.image.identifier]
        return controller
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let onImage: (UIImage) -> Void
        let onCancel: () -> Void

        init(onImage: @escaping (UIImage) -> Void, onCancel: @escaping () -> Void) {
            self.onImage = onImage
            self.onCancel = onCancel
        }

        func imagePickerController(
            _ picker: UIImagePickerController,
            didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]
        ) {
            if let image = info[.originalImage] as? UIImage {
                onImage(image)
            } else {
                onCancel()
            }
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            onCancel()
        }
    }
}
#endif
