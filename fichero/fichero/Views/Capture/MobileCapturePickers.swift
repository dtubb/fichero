//  Extracted from MobileCaptureQueueView.swift for file_length (#5113). Byte-for-byte.
//
//  The OUTER `#if os(iOS) || os(tvOS) || os(visionOS)` is reproduced here because the split
//  would otherwise separate an `#if` from its `#endif` — the first cut landed INSIDE two
//  nested conditional-compilation blocks and produced "Expected #else or #endif at end of
//  conditional compilation block" in one file and "Unexpected conditional compilation block
//  terminator" in the other. A split point has to be a brace boundary AND a preprocessor
//  boundary.

#if os(iOS) || os(tvOS) || os(visionOS)
import SwiftUI
import UIKit
import UniformTypeIdentifiers
#if canImport(VisionKit) && !os(visionOS)
import VisionKit
#endif

#if !os(tvOS)
struct MobileCaptureImagePicker: UIViewControllerRepresentable {
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

#if canImport(VisionKit) && !os(visionOS)
struct MobileDocumentScanner: UIViewControllerRepresentable {
    let onImages: ([UIImage]) -> Void
    let onCancel: () -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(onImages: onImages, onCancel: onCancel)
    }

    func makeUIViewController(context: Context) -> VNDocumentCameraViewController {
        let controller = VNDocumentCameraViewController()
        controller.delegate = context.coordinator
        return controller
    }

    func updateUIViewController(_ uiViewController: VNDocumentCameraViewController, context: Context) {}

    final class Coordinator: NSObject, VNDocumentCameraViewControllerDelegate {
        private let onImages: ([UIImage]) -> Void
        private let onCancel: () -> Void

        init(onImages: @escaping ([UIImage]) -> Void, onCancel: @escaping () -> Void) {
            self.onImages = onImages
            self.onCancel = onCancel
        }

        func documentCameraViewController(
            _ controller: VNDocumentCameraViewController,
            didFinishWith scan: VNDocumentCameraScan
        ) {
            let images = (0..<scan.pageCount).map { scan.imageOfPage(at: $0) }
            onImages(images)
        }

        func documentCameraViewControllerDidCancel(_ controller: VNDocumentCameraViewController) {
            onCancel()
        }

        func documentCameraViewController(
            _ controller: VNDocumentCameraViewController,
            didFailWithError _: Error
        ) {
            onCancel()
        }
    }
}
#endif
#endif
#endif
