@testable import Fichero
import Foundation
import Testing

@Suite("MobileCaptureQueueRouting")
struct MobileCaptureQueueRoutingTests {

    @Test("uploads cannot resume without a remote host and paired library")
    func requiresHostAndLibrary() {
        #expect(!MobileCaptureQueueRouting.canResumeUploads(backendHost: nil, hasPairedLibraryPath: true))
        #expect(
            !MobileCaptureQueueRouting.canResumeUploads(
                backendHost: URL(string: "https://remote.example.com")!,
                hasPairedLibraryPath: false
            )
        )
    }

    @Test("a valid remote host with a paired library can resume uploads")
    func acceptsPairedRemoteHost() {
        #expect(
            MobileCaptureQueueRouting.canResumeUploads(
                backendHost: URL(string: "https://remote.example.com")!,
                hasPairedLibraryPath: true
            )
        )
    }

    @Test("loopback hosts never resume mobile uploads")
    func rejectsLoopbackHost() {
        #expect(
            !MobileCaptureQueueRouting.canResumeUploads(
                backendHost: URL(string: "https://127.0.0.1:8765")!,
                hasPairedLibraryPath: true
            )
        )
    }
}
