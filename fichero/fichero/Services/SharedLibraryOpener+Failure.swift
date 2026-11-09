import Foundation

extension SharedLibraryOpener {
    /// Why a shared library would not open, in words (`sharing.alerts.one-alert-per-failure`, #6459): off or asleep, slow,
    /// no longer paired, or a changed certificate. Each one says what the person can do; none says only "isn't responding".
    static func failureWords(for error: Error, host name: String) -> (title: String, sentence: String, canRetry: Bool) {
        if case .httpError(let status, _)? = error as? APIError, status == 401 || status == 403 {
            // The spec's `deviceForgotten` row: pairing again is the fix, so no Try Again.
            return ("\(name) no longer knows this device", "The owner removed it; pair again.", false)
        }
        switch SharingFailurePrompt.transportCode(error) {
        case URLError.timedOut.rawValue?:
            return ("\(name) is slow to answer",
                    "It may be busy opening a large library. Wait a moment and Try Again; Fichero stayed on this Mac's projects.", true)
        case let code? where (-1206 ... -1200).contains(code):
            // The spec's `certificateName` row.
            return ("\(name)'s certificate doesn't match", "Turn Sharing off and on there so it makes a new one.", true)
        default:
            return ("\(name) isn't responding",
                    "It is off, asleep, or Sharing is off there. Fichero stayed on this Mac's projects.", true)
        }
    }
}
