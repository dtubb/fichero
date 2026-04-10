# Security Review: Phase 5 Integration — CORS and MCP Authorization

**Date:** 2026-04-10  
**Issue:** #400  
**Scope:** `fichero-api/src/fichero/api/main.py`, `fichero-api/src/fichero/mcp_server.py`  
**Reviewer:** Agent (autonomous session)  

---

## Executive Summary

Phase 5 Integration contains **HIGH severity security vulnerabilities** in CORS configuration and MCP server authorization. The CORS middleware allows all origins with credentials, enabling cross-origin attacks. The MCP server lacks authorization checks, potentially exposing all API functionality to any connected agent.

**Overall Risk Rating: HIGH**

---

## Findings

### 🔴 HIGH-1: CORS Wildcard with Credentials Enabled

**Location:** `fichero-api/src/fichero/api/main.py` lines 105-111

**Issue:** The CORS middleware is configured with overly permissive settings:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # ← Allows ANY origin
    allow_credentials=True,     # ← Allows cookies/auth headers
    allow_methods=["*"],        # ← Allows ALL HTTP methods
    allow_headers=["*"],        # ← Allows ALL headers
)
```

**Impact:** This configuration enables:
- **Cross-origin attacks** from malicious websites
- **CSRF bypass** via authenticated cross-origin requests
- **Information disclosure** if APIs return sensitive data
- The combination of `allow_origins=["*"]` + `allow_credentials=True` is explicitly discouraged by security standards

**CVSS Score:** 7.1 (High)

**Remediation:**
```python
# Production: Restrict to specific origins
allow_origins=[
    "http://localhost:8765",
    "https://localhost:8765",
    # Add your domain here
]

# Or if running locally only, validate origin against localhost
```

---

### 🔴 HIGH-2: MCP Server Missing Authorization

**Location:** `fichero-api/src/fichero/mcp_server.py` (entire file)

**Issue:** The MCP server exposes all Fichero API functionality without any authorization layer. Any process that can connect to the MCP server can:
- List and search all documents
- Execute any workflow
- Modify document metadata
- Access research data (projects, plans, tasks)

**Code Evidence:**
```python
class FicheroAPIClient:
    def __init__(self, api_url: str = DEFAULT_API_URL, library_path: str | None = None):
        # No authentication check
        self.api_url = api_url.rstrip("/")
        self.library_path = library_path or os.environ.get("FICHERO_LIBRARY_PATH")

    def _get_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.library_path:
            headers["X-Fichero-Library-Path"] = self.library_path
        # No auth token added
        return headers
```

**Impact:** Complete API exposure to any local process or connected agent.

**CVSS Score:** 7.5 (High)

**Remediation:**
- Add API key/token authentication to MCP server
- Validate agent identity before allowing tool calls
- Implement permission scopes (read-only vs read-write)

---

### 🟡 MEDIUM-1: Feature Tier Bypass via Environment Variable

**Location:** `fichero-api/src/fichero/api/main.py` lines 254-265

**Issue:** The feature tier system reads from an environment variable without validation that the user is authorized to change it:

```python
tier = os.environ.get("FICHERO_FEATURE_TIER", "release").strip().lower()
if tier == "dev":
    return [*_CORE_ROUTE_SPECS, *_DEV_ROUTE_SPECS]
return _CORE_ROUTE_SPECS
```

**Impact:** Any user with shell access can enable dev routes by setting `FICHERO_FEATURE_TIER=dev`.

**Risk Assessment:** Low in single-user local deployment, higher in shared/multi-user scenarios.

**CVSS Score:** 5.3 (Medium)

**Remediation:**
- Add runtime validation of tier changes
- Log tier changes with user attribution
- Consider file-based config instead of environment-only

---

### 🟡 MEDIUM-2: Library Path Header Injection

**Location:** `fichero-api/src/fichero/api/main.py` lines 118-135

**Issue:** The `get_library_database` dependency reads the library path from a header without validation:

```python
async def get_library_database(
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
) -> Database:
    db = db_manager.get_database(x_fichero_library_path)
    return db
```

**Potential Issues:**
- Path traversal if the header contains `../` sequences
- Access to unintended directories
- No validation that the path is within allowed bounds

**CVSS Score:** 5.3 (Medium)

**Remediation:**
```python
from pathlib import Path

def validate_library_path(path: str) -> str:
    # Resolve to absolute path
    resolved = Path(path).resolve()
    # Check against allowed base directories
    allowed_bases = [Path.home() / "Documents", Path.home() / "Desktop"]
    if not any(str(resolved).startswith(str(base)) for base in allowed_bases):
        raise HTTPException(403, "Library path not in allowed location")
    return str(resolved)
```

---

## Recommended Mitigations

### Priority 1: CORS Restriction

1. **Environment-based CORS config:**
   ```python
   # In production, restrict origins
   if os.environ.get("FICHERO_ENV") == "production":
       allow_origins = ["https://yourdomain.com"]
   else:
       allow_origins = ["http://localhost:*", "https://localhost:*"]
   ```

2. **Never allow credentials with wildcard origins**

### Priority 2: MCP Authorization

1. **Add API key validation:**
   ```python
   def _get_headers(self) -> dict[str, str]:
       headers = {"Content-Type": "application/json"}
       if self.library_path:
           headers["X-Fichero-Library-Path"] = self.library_path
       # Add authentication
       api_key = os.environ.get("FICHERO_API_KEY")
       if api_key:
           headers["X-API-Key"] = api_key
       return headers
   ```

2. **Add permission scopes to MCP tools**

### Priority 3: Path Validation

1. Add path traversal protection
2. Validate library paths against allowed directories
3. Log access to sensitive paths

---

## Test Coverage

Current tests DO NOT cover:
- CORS preflight requests from unauthorized origins
- MCP tool authorization
- Feature tier bypass attempts
- Path traversal in library headers

---

## Conclusion

Phase 5 Integration has **HIGH severity vulnerabilities** that should be addressed before production deployment. The CORS configuration is the most critical issue, followed by MCP authorization.

**Next Steps:**
1. Implement CORS origin restriction
2. Add MCP authorization layer
3. Add path validation to library header
4. Create security tests for all findings
5. Security re-review after fixes
