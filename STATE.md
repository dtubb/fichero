# Current Focus
Phase 2 (#412): Architecture Compliance — Review 6 security PRs

# Branch
- Active branch: `0.0.2` (pushes to `origin/0.0.2`)

# Next Session — Start Here
**Phase 2: Architecture Compliance Review**

Review FastAPI/Python patterns in each security PR:

| PR | Branch | Review Focus |
|----|--------|--------------|
| #399 | feature/issue-398 | SSRF protection in research_agents.py, research.py |
| #401 | feature/issue-400 | CORS/MCP auth in main.py, mcp_server.py |
| #403 | feature/issue-402 | Knowledge Graph patterns (knowledge_graph.py) |
| #405 | feature/issue-404 | Hermeneutics endpoints (hermeneutics.py) |
| #407 | feature/issue-406 | Mind Palace patterns (mind_palace.py) |
| #409 | feature/issue-408 | HIGH severity fixes (main.py, mcp_server.py) |

### Checklist
- FastAPI dependency injection
- Pydantic models for request/response
- HTTPException handling (400, 404, 500)
- Async/await for I/O
- Type hints on all functions
- Docstrings on endpoints
- No hardcoded paths

### Reference
- Issue #412: Architecture Compliance
- Issue #416: Tracking issue
