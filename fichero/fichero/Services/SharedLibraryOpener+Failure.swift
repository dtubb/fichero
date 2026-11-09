import Foundation

extension SharedLibraryOpener {
    /// Why a shared library would not open, in words (`sharing.alerts.one-alert-per-failure`, #6459): off or asleep, slow,
    /// no longer paired, or a changed certificate. Each one says what the person can do; none says only "isn't responding".
    static func failureWords(for error: Error, host name: String) -> (title: String, sentence: String) {
        if case .httpError(let status, _)? = error as? APIError, status == 401 || status == 403 {
            return ("\(name) no longer lets this Mac in",
                    "Its key for this Mac was removed or has expired. Pair this Mac with \(name) again from Settings ▸ Sharing.")
        }
        switch SharingFailurePrompt.transportCode(error) {
        case URLError.timedOut.rawValue?:
            return ("\(name) is slow to answer",
                    "It may be busy opening a large library. Wait a moment and Try Again; Fichero stayed on this Mac's projects.")
        case let code? where (-1206 ... -1200).contains(code):
            return ("\(name)'s identity changed",
                    "Its security certificate no longer matches the one saved when you paired. Pair this Mac with \(name) again.")
        default:
            return ("\(name) isn't responding",
                    "It is off, asleep, or Sharing is off there. Fichero stayed on this Mac's projects.")
        }
    }
}
