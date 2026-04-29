import Foundation
import OpenAPIRuntime

/// Accepts strict ISO-8601 as well as legacy backend timestamps without timezone.
struct LenientISO8601DateTranscoder: DateTranscoder, @unchecked Sendable {
    private let iso8601WithFractional = ISO8601DateTranscoder(
        options: [.withInternetDateTime, .withFractionalSeconds]
    )
    private let iso8601 = ISO8601DateTranscoder(options: [.withInternetDateTime])

    func encode(_ date: Date) throws -> String {
        try iso8601WithFractional.encode(date)
    }

    func decode(_ dateString: String) throws -> Date {
        if let date = try? iso8601WithFractional.decode(dateString) {
            return date
        }
        if let date = try? iso8601.decode(dateString) {
            return date
        }

        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")

        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
        if let date = formatter.date(from: dateString) {
            return date
        }

        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        if let date = formatter.date(from: dateString) {
            return date
        }

        throw DecodingError.dataCorrupted(
            .init(codingPath: [], debugDescription: "Expected date string to be ISO8601-formatted.")
        )
    }
}
