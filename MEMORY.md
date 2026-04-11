# Durable Lessons Learned / Decisions

*   **SSRF Security Pattern for Research Tools (2026-04-10):** Security audit of research tools (research.py) revealed critical SSRF vulnerabilities:
    - `follow_redirects=True` without redirect chain validation allows open redirect attacks
    - `_is_sandbox_violation()` using `startswith()` is insufficient — must validate resolved IPs
    - Must block RFC1918 ranges (10.x, 172.16-31.x, 192.168.x), loopback (127.x), link-local (169.254.x), cloud metadata
    - URL scheme checks are case-sensitive — need case-normalization
    - DNS rebinding requires resolution-time IP validation, not just hostname checks
    - Security tests should be written *before* fixes to document known vulnerabilities

*   **Agent Research Pattern**: Following the established pattern from knowledge_graph.py, hermeneutics.py, and mind_palace.py, the Agent Research implementation uses:
    - Pydantic models with `model_config = ConfigDict(from_attributes=True, extra="allow")`
    - Separate request/response models for API endpoints
    - Full CRUD with soft-delete (archiving) pattern
    - Status tracking with enums matching other modules
    - Placeholder tool implementations that return example data

*   **Skills Relocation:** Skills moved from `.agents/skills/` to `plugins/fs_session/skills/`. All script invocations now use `SCRIPT_ROOT` resolver that checks both `$HOME/.pi/agent/skills/fs_session/scripts` and repo `plugins/fs_session/skills/...`.

*   **Backend Task Prioritization (2026-04-10):** Created 21 backend-focused GitHub issues for milestones 0.0.3 through 0.1.0. All issues use only pre-configured labels (`area:backend-api`, `type:task`) since custom labels like `area:operations` don't exist in the project. Issues are properly organized by milestone and ready for AI agent claiming. Backend-only work available: #419-440 excluding Swift-requiring tasks.

*   **Branch Convention (2026-04-10):** Implementation work happens on milestone branches (e.g., `0.0.2`, `feature/388-hermeneutics`), not planning branches. The `0.0.2` branch IS the active implementation branch. State is now tracking backend implementation work for 0.0.3-0.1.0 milestones with 21 issues created for AI agent claiming.

## Orchestration Policy Pattern — 2026-04-12

**Pattern:** Priority-based policy rules for AI agent write operations with human-in-the-loop approval

**Policy Rule Matching:**
- Priority order (lower number = higher priority, evaluated first)
- Conditions stack: entity_type AND confidence_threshold AND requires_source AND min_evidence_count
- First matching rule wins
- Fallback: require_approval if no rules match

**Rule Conditions:**
- confidence_threshold: confidence >= threshold to pass
- requires_source: must have non-empty sources list
- min_evidence_count: evidence items must >= count
- is_active: rule must be enabled

**Approval Workflow:**
```
submit_request() → evaluate() → [auto_approve | require_approval | deny]
  ↓ require_approval
  → pending state → approve() or reject() by human
  ↓ audit logging for all state transitions
```

**Policy Actions:**
- auto_approve: Immediate approval (high confidence, validated sources)
- require_approval: Human review required (risk operations, medium confidence)
- deny: Blocked (low confidence, missing validation)

**Default Priority Levels:**
- 1-10: Auto-approve rules (highest confidence, deletion protection)
- 11-100: Review rules (medium confidence thresholds)
- 100+: Fallback/catch-all rules

**Audit Record Fields:**
- request metadata (agent, operation, confidence)
- policy matching (rule_id, policy_action)
- approval decision (approved_by, reason, timestamp)
- execution result (executed_at, error_message)
