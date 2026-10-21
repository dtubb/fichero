/// When the iPhone offers Reconnect and Change Server (`m2p.ios.connect-failure-offers-recovery`): in every phase in which
/// the connection is not working, and in no other. Pure, so it is tested without a device.
enum IOSConnectionRecoveryPolicy {
    static func offersRecovery(phase: EngineSession.Phase) -> Bool {
        switch phase {
        case .portConflict, .authRejected, .unreachable, .failed:
            true
        case .setupNeeded, .starting, .ready:
            false
        }
    }
}
