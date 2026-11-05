import Testing

@testable import Fichero

/// `sharing.people.settings-screen` (#2083): the access view says owner, editor, viewer or no access, in those words.
struct AccountsAccessMatrixTests {
    @Test func rolesReadInTheSpecsWords() {
        #expect(AccessWords.role("owner") == "Owner")
        #expect(AccessWords.role("editor") == "Editor")
        #expect(AccessWords.role("viewer") == "Viewer")
    }

    @Test func noRoleIsNoAccessNotBlank() {
        #expect(AccessWords.role(nil) == "No access")
        #expect(AccessWords.role("") == "No access")
    }
}
