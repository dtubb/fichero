@testable import Fichero
import Foundation
import Testing

/// `models.manage.add-by-id-or-url` (#6588): the sheet adds a model by its Hugging Face id or address; a refusal shows the
/// engine's own words.
struct ModelsWindowAddByAddressTests {
    @Test("an address is trimmed; a blank one is not sent")
    func trimmed() {
        #expect(ModelsWindowModel.addAddress("  acme/reader \n") == "acme/reader")
        #expect(ModelsWindowModel.addAddress("   ") == nil)
        #expect(ModelsWindowModel.addAddress("") == nil)
    }

    @Test("a refusal says the engine's words, else the status")
    func refusal() {
        #expect(ModelsWindowModel.addRefusal(code: 404, engineWords: "No such model on the Hub.") == "No such model on the Hub.")
        #expect(ModelsWindowModel.addRefusal(code: 403, engineWords: nil) == "The engine could not add this model (HTTP 403).")
    }
}
