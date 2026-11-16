import Foundation

extension SharedLibraryOpener {
    struct Failure: Equatable {
        let title: String
        let sentence: String
        let canRetry: Bool
    }

    /// Why a shared library would not open, in words (`sharing.alerts.one-alert-per-failure`, #6459): off or asleep, slow,
    /// no longer paired, or a changed certificate. Each one says what the person can do; none says only "isn't responding".
    static func failureWords(for error: Error, host name: String) -> Failure {
        if case .httpError(let status, _)? = error as? APIError, status == 401 || status == 403 {
            // The spec's `deviceForgotten` row: pairing again is the fix, so no Try Again.
            return Failure(title: "\(name) no longer knows this device", sentence: "The owner removed it; pair again.",
                           canRetry: false)
        }
        switch SharingFailurePrompt.transportCode(error) {
        case URLError.timedOut.rawValue?:
            return Failure(
                title: "\(name) is slow to answer",
                sentence: "It may be busy opening a large library. Wait a moment and Try Again; "
                    + "Fichero stayed on this Mac's projects.",
                canRetry: true)
        case let code? where (-1206 ... -1200).contains(code):
            // The spec's `certificateName` row.
            return Failure(title: "\(name)'s certificate doesn't match",
                           sentence: "Turn Sharing off and on there so it makes a new one.", canRetry: true)
        default:
            return Failure(
                title: "\(name) isn't responding",
                sentence: "It is off, asleep, or Sharing is off there. Fichero stayed on this Mac's projects.",
                canRetry: true)
        }
    }
}
