#if os(iOS) || os(tvOS) || os(visionOS)
import AVFoundation
import SwiftUI
import UIKit

#if !os(tvOS) && !os(visionOS)
// Promoted private → internal: constructed by `QRCodeScannerSheet`
// (IOSPairingViews.swift) after this type was split out of FicheroApp_iOS.swift
// for file_length.
struct QRCodeScannerView: UIViewControllerRepresentable {
    let onMessage: (String) -> Void
    let onFailure: (String) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(onMessage: onMessage, onFailure: onFailure)
    }

    func makeUIViewController(context: Context) -> ScannerViewController {
        let controller = ScannerViewController()
        controller.coordinator = context.coordinator
        return controller
    }

    func updateUIViewController(_ uiViewController: ScannerViewController, context: Context) {}

    final class Coordinator: NSObject, AVCaptureMetadataOutputObjectsDelegate {
        private let onMessage: (String) -> Void
        private let onFailure: (String) -> Void
        private var hasCompleted = false

        init(onMessage: @escaping (String) -> Void, onFailure: @escaping (String) -> Void) {
            self.onMessage = onMessage
            self.onFailure = onFailure
        }

        func metadataOutput(
            _ output: AVCaptureMetadataOutput,
            didOutput metadataObjects: [AVMetadataObject],
            from connection: AVCaptureConnection
        ) {
            guard !hasCompleted else { return }
            guard let message = metadataObjects
                .compactMap({ $0 as? AVMetadataMachineReadableCodeObject })
                .first(where: { $0.type == .qr })?
                .stringValue else {
                return
            }
            hasCompleted = true
            onMessage(message)
        }

        func fail(_ message: String) {
            guard !hasCompleted else { return }
            onFailure(message)
        }
    }

    final class ScannerViewController: UIViewController {
        var coordinator: Coordinator?

        private let session = AVCaptureSession()
        private var previewLayer: AVCaptureVideoPreviewLayer?

        override func viewDidLoad() {
            super.viewDidLoad()
            view.backgroundColor = .black
            configureSession()
        }

        override func viewDidLayoutSubviews() {
            super.viewDidLayoutSubviews()
            previewLayer?.frame = view.bounds
        }

        override func viewWillAppear(_ animated: Bool) {
            super.viewWillAppear(animated)
            if !session.isRunning {
                session.startRunning()
            }
        }

        override func viewWillDisappear(_ animated: Bool) {
            super.viewWillDisappear(animated)
            if session.isRunning {
                session.stopRunning()
            }
        }

        private func configureSession() {
            guard let device = AVCaptureDevice.default(for: .video) else {
                coordinator?.fail("This device does not have a camera available for QR scanning.")
                return
            }

            do {
                let input = try AVCaptureDeviceInput(device: device)
                guard session.canAddInput(input) else {
                    coordinator?.fail("Fichero could not access the camera input.")
                    return
                }
                session.addInput(input)

                let output = AVCaptureMetadataOutput()
                guard session.canAddOutput(output) else {
                    coordinator?.fail("Fichero could not configure QR scanning.")
                    return
                }
                session.addOutput(output)
                output.setMetadataObjectsDelegate(coordinator, queue: .main)
                output.metadataObjectTypes = [.qr]

                let previewLayer = AVCaptureVideoPreviewLayer(session: session)
                previewLayer.videoGravity = .resizeAspectFill
                previewLayer.frame = view.bounds
                view.layer.addSublayer(previewLayer)
                self.previewLayer = previewLayer
            } catch {
                coordinator?.fail("Camera setup failed: \(error.localizedDescription)")
            }
        }
    }
}
#endif
#endif
