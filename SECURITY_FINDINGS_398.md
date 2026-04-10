# Security Review: Phase 4 Agent Research — SSRF Vulnerabilities

**Date:** 2026-04-10  
**Issue:** #398  
**Scope:** `fichero-api/src/fichero/workflows/tools/research.py`  
**Reviewer:** Agent (autonomous session)  

---

## Executive Summary

The research tools (`research_web_search`, `research_browser_navigate`, `research_document_fetch`) contain **CRITICAL SSRF vulnerabilities** that could allow an attacker to access internal services, cloud metadata endpoints, and local filesystem. The current sandbox validation (`_is_sandbox_violation`) is insufficient and bypassable through multiple vectors.

**Overall Risk Rating: CRITICAL**

---

## Findings

### 🔴 CRITICAL-1: Open Redirect SSRF via `follow_redirects=True`

**Location:** `research.py` lines 155, 265, 396

**Issue:** All three tools use `httpx.AsyncClient(follow_redirects=True)`, but validation only happens on the **initial URL**. An attacker can bypass restrictions by:
1. Using an open redirect on a legitimate site (e.g., `https://bit.ly/xyz`, `https://example.com/redirect?url=...`)
2. Submitting a URL that returns a 30X redirect to an internal address

**Example Attack:**
```python
# Attacker submits this URL (passes validation)
url = "https://tinyurl.com/xyz"  # redirects to http://169.254.169.254

# Client follows redirect to cloud metadata
# Exploit succeeds — attacker can now access AWS/GCP metadata
```

**Impact:** Complete bypass of sandbox, access to internal services, cloud metadata, localhost APIs.

**CVSS Score:** 9.1 (Critical)

---

### 🔴 CRITICAL-2: No Internal IP Address Blocking

**Location:** All HTTP requests in research.py

**Issue:** No validation of resolved IP addresses before connection. Tools accept any URL that resolves to:
- `127.0.0.0/8` (localhost): Access to local services, admin panels
- `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` (RFC1918): Internal services
- `169.254.169.254` (AWS/Azure/GCP metadata endpoints): Cloud credentials
- `0.0.0.0`, `::1`, `fc00::/7`, etc.

**Example Attacks:**
```python
"http://169.254.169.254/latest/meta-data/"  # AWS metadata
"http://localhost:5432/"  # PostgreSQL without auth
"http://10.0.0.1/admin"  # Internal admin panel
"http://127.0.0.1:9000/api"  # Internal API
```

**Impact:** Credential theft (cloud metadata), unauthorized access to internal databases and services.

**CVSS Score:** 9.1 (Critical)

---

### 🟠 HIGH-1: Path Traversal via URL Parsing Bypass

**Location:** `_is_sandbox_violation()` function (lines 40-46)

**Issue:** The check `url.startswith(blocked)` can be bypassed:

```python
def _is_sandbox_violation(url: str) -> bool:
    for blocked in _SANDBOX_BLOCKED_DOMAINS:
        if url.startswith(blocked):  # Bypassable!
            return True
    return False
```

**Bypass Vectors:**
1. URL-encoded characters: `fi%6ce:///etc/passwd` (if decoded before check)
2. Double slashes: `http://localhost/file://etc/passwd` (depending on parsing)
3. Case variations: `FILE:///etc/passwd` (not checked)
4. Whitespace/noise: `file:// /etc/passwd` (depends on URL parsing)

**Impact:** Filesystem read access (depending on OS and library behavior).

**CVSS Score:** 7.5 (High)

---

### 🟠 HIGH-2: DNS Rebinding Attack

**Location:** All HTTP requests in research.py

**Issue:** The code checks URL scheme but not DNS resolution behavior. Attacker can:
1. Create DNS record `attacker.com` → `203.0.113.1` (external IP, passes check)
2. Submit URL `http://attacker.com/internal`
3. Rebind DNS during request: `attacker.com` → `169.254.169.254`
4. Request reaches internal service

Even with IP validation, this requires DNS validation before each request.

**Impact:** Same as CRITICAL-2 (internal access) but more difficult to exploit.

**CVSS Score:** 7.1 (High)

---

### 🟡 MEDIUM-1: Excessive Error Information

**Location:** Error handling throughout (lines 178-184, etc.)

**Issue:** Error messages like `"Web search failed: {str(e)}"` could leak:
- Internal service URLs (if internal DNS is tried and fails)
- File system paths (if file:// URL is attempted)
- Network topology (error codes/timings from different services)

**Recommendation:** Log full details internally, return generic messages to caller.

**CVSS Score:** 5.3 (Medium)

---

### 🟡 MEDIUM-2: No Request Size Limits

**Location:** Document fetch (line 396+)

**Issue:** No maximum content size limits on document fetch. An attacker can:
- Request a multi-GB file (memory DoS)
- Request a never-ending response (slowloris-style DoS)

**Recommendation:** Add content-length checks and streaming with limits.

**CVSS Score:** 5.3 (Medium)

---

## Recommended Mitigations

### Priority 1: Fix CRITICAL Issues

1. **Disable Redirect Following OR Validate Full Chain**
   ```python
   # Option A: Disable redirects entirely
   follow_redirects=False
   
   # Option B: Intercept and validate each redirect
   # Custom redirect handling with re-validation
   ```

2. **Add Internal IP Blocking**
   ```python
   import ipaddress
   
   _BLOCKED_NETWORKS = [
       ipaddress.ip_network("127.0.0.0/8"),      # loopback
       ipaddress.ip_network("10.0.0.0/8"),        # private A
       ipaddress.ip_network("172.16.0.0/12"),     # private B
       ipaddress.ip_network("192.168.0.0/16"),    # private C
       ipaddress.ip_network("169.254.0.0/16"),    # link-local
       ipaddress.ip_network("0.0.0.0/8"),         # current network
       # ... IPv6 equivalents
   ]
   
   def _is_internal_ip(hostname: str) -> bool:
       try:
           addr = ipaddress.ip_address(hostname)
           return any(addr in net for net in _BLOCKED_NETWORKS)
       except ValueError:
           # It's a hostname, resolve it
           try:
               resolved = socket.getaddrinfo(hostname, None)
               for _, _, _, _, sock_addr in resolved:
                   ip = ipaddress.ip_address(sock_addr[0])
                   if any(ip in net for net in _BLOCKED_NETWORKS):
                       return True
           except socket.gaierror:
               pass
       return False
   ```

3. **Comprehensive URL Scheme Validation**
   ```python
   from urllib.parse import urlparse
   
   _ALLOWED_SCHEMES = {"http", "https"}
   
   def _is_safe_url(url: str) -> bool:
       parsed = urlparse(url)
       # Must be http or https (case-insensitive)
       if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
           return False
       # Must have netloc (not just a path)
       if not parsed.netloc:
           return False
       # Block usernames/passwords in URLs
       if parsed.username or parsed.password:
           return False
       # Check host doesn't resolve to internal IP
       if _is_internal_ip(parsed.hostname):
           return False
       return True
   ```

### Priority 2: Fix HIGH Issues

1. **DNS Rebinding Protection**
   - Cache DNS resolution before connecting
   - Validate IP after resolution, before HTTP request
   - Consider `resolve_address` parameter in httpx

2. **Path Traversal Prevention**
   - URL-decode before validation (handle percent-encoding)
   - Use proper URL parsing, not string matching
   - Validate hostname:port format strictly

### Priority 3: Fix MEDIUM Issues

1. **Error Message Sanitization**
   - Log full exception details internally
   - Return generic error messages to callers

2. **Resource Limits**
   - Add maximum response size (e.g., 10MB)
   - Add request timeout limits

---

## Test Coverage

The current test `test_sandbox_blocks_dangerous_urls` only tests basic URL scheme blocking. It does NOT test:
- ✅ URL scheme blocking (covered)
- ❌ Open redirect attacks (not covered)
- ❌ Internal IP access (not covered)
- ❌ DNS rebinding (not covered)
- ❌ Path traversal (not covered)
- ❌ Large content DoS (not covered)

---

## Conclusion

The current sandbox implementation provides **false security**. While basic URL scheme checks are in place, multiple bypass vectors allow complete SSRF exploitation. **These tools should not be exposed to untrusted input until fixed.**

**Next Steps:**
1. Implement IP-based validation before HTTP requests
2. Add redirect chain validation
3. Add comprehensive SSRF test suite
4. Security re-review before enabling in production
