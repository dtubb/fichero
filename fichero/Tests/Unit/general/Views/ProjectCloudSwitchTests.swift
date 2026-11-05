@testable import Fichero
import Testing

/// `ai.cloud.switch-in-the-project` (#6022 place 1, #6348): the three states from a served answer.
@Suite("Project cloud switch")
struct ProjectCloudSwitchTests {
    @Test("an answered project shows its own yes or no")
    func answered() {
        #expect(ProjectCloudSwitch.state(answered: true, allowed: true) == .allowed)
        #expect(ProjectCloudSwitch.state(answered: true, allowed: false) == .refused)
    }

    @Test("an unanswered project follows Settings and says so")
    func inherited() {
        let state = ProjectCloudSwitch.state(answered: false, allowed: true)
        #expect(state == .asSettings(true))
        #expect(state.words == "As Settings: on.")
        #expect(ProjectCloudSwitch.state(answered: false, allowed: false).words == "As Settings: off.")
    }
}
