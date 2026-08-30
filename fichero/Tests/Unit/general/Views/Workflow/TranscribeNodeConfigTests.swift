@testable import Fichero
import Testing

struct TranscribeNodeConfigTests {
    @Test("Transcribe language picker exposes canonical locales")
    func languagePickerLocales() {
        let codes = Set(TranscribeLanguageChoice.all.map(\.code))

        #expect(codes.contains("en-US"))
        #expect(codes.contains("auto"))
        #expect(codes.contains("es-ES"))
        #expect(codes.contains("es-MX"))
        #expect(TranscribeLanguageChoice.normalize("es") == "es-ES")
        #expect(TranscribeLanguageChoice.normalize("es_mx") == "es-MX")
        #expect(TranscribeLanguageChoice.normalize("en") == "en-US")
        #expect(TranscribeLanguageChoice.normalize("auto") == "auto")
        #expect(TranscribeNodeConfig.defaultMaxImageDimension == 2048)
    }
}
