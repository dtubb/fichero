import Foundation

/// What knowledge (entities + claims) a whole conversation drew on, aggregated
/// from each message's `RetrievalInfo` (#3 Knowledge tab, migration step 5).
///
/// Honest about its limits: `RetrievalInfo` carries *counts*, not identities, so
/// this reports usage **references** (a repeated entity counts each time), not a
/// distinct browsable set. When the engine returns entity/claim ids on the chat
/// response, the Knowledge tab upgrades from this summary to a real list.
/// Instrument, not interlocutor — it surfaces what was used, it does not narrate.
struct ConversationKnowledgeSummary: Hashable {
    /// Number of assistant replies that pulled any KG context.
    var repliesWithKnowledge: Int
    /// Cumulative entity references across those replies.
    var entityReferences: Int
    /// Cumulative claim references across those replies.
    var claimReferences: Int

    var isEmpty: Bool {
        repliesWithKnowledge == 0 && entityReferences == 0 && claimReferences == 0
    }

    static func summarize(_ conversation: Conversation) -> ConversationKnowledgeSummary {
        var replies = 0
        var entities = 0
        var claims = 0
        for message in conversation.messages {
            guard let retrieval = message.retrieval else { continue }
            let e = retrieval.kgEntitiesUsed
            let c = retrieval.kgClaimsUsed
            if e > 0 || c > 0 {
                replies += 1
                entities += e
                claims += c
            }
        }
        return ConversationKnowledgeSummary(
            repliesWithKnowledge: replies,
            entityReferences: entities,
            claimReferences: claims
        )
    }
}
