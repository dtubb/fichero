# www.tubb.ca — Let's Encrypt renewal failure

**Date:** 2026-09-03
**Symptom:** Netlify: `Certificate renewal incomplete: missing domains www.tubb.ca`.
Cert covers only `tubb.ca`, expires **2026-09-15** (12 days out). Apex HTTPS is fine.

## Root cause — TWO independent defects

### 1. PRIMARY (blocker): `www.tubb.ca` is broken in Hover's DNS zone

`www.tubb.ca` returns **SERVFAIL for every record type at all three authoritative
Hover nameservers**. This is not a missing record — a missing record returns NXDOMAIN.
SERVFAIL means the `www` node exists in the zone but its data is malformed/unservable.

Evidence (all against the authoritative servers, so no resolver caching involved):

| Query | Status |
|---|---|
| `tubb.ca A` @ns1.hover.com | **NOERROR** → `75.2.60.5` (correct Netlify LB) |
| `zzz-nope.tubb.ca A` @ns1.hover.com | **NXDOMAIN** (correct "does not exist") |
| `mail` / `www2` / `blog .tubb.ca` @ns1.hover.com | NXDOMAIN (correct) |
| `www.tubb.ca` A/AAAA/CNAME/TXT/MX @ns1/ns2/ns3.hover.com | **SERVFAIL** (all types, UDP + TCP) |
| `www.tubb.ca` @1.1.1.1 and @8.8.8.8, incl. `+cd` | SERVFAIL |

Zone is **not** DNSSEC-signed (no DS, no DNSKEY), so this is not a signing failure —
`+cd` (checking disabled) still SERVFAILs, which rules DNSSEC out entirely.

Nameservers are `ns1/ns2/ns3.hover.com` → DNS is at **Hover**, not Netlify DNS.
So Let's Encrypt cannot validate `www.tubb.ca`, and renewal fails exactly as reported.

`curl` confirms the user-visible effect: both `https://www.tubb.ca` and
`http://www.tubb.ca` fail at **"Resolving timed out"** — never reach Netlify at all.

### 2. SECONDARY (fixed below): `www.tubb.ca` was not a Netlify domain alias

Site `tubb-ca` (id `10752494-c42a-4963-b17c-49bc58eec585`) had
`custom_domain: tubb.ca` with `domain_aliases: []`.
The working sibling site `undigital-ca` correctly has `domain_aliases: ['www.undigital.ca']`.
Without the alias Netlify would not route `www` to the site even once DNS is fixed.

## What I changed

- `netlify api updateSite` → added `www.tubb.ca` to `domain_aliases` on site `tubb-ca`.
  Verified: `custom_domain=tubb.ca`, `domain_aliases=['www.tubb.ca']`.

**I deliberately did NOT re-provision the certificate.** While DNS SERVFAILs, an ACME
validation attempt is guaranteed to fail, and Let's Encrypt rate-limits failed
validations (5/hour). Provision only *after* the DNS fix has propagated.

## What Daniel must do (Hover — ~2 minutes)

The record must be **deleted and recreated**; editing in place often leaves the same
corrupt row that is causing the SERVFAIL.

1. Go to <https://hover.com> → sign in → **tubb.ca** → **DNS** tab.
2. Find the existing **`www`** row. It may look blank, malformed, or have an odd type.
   **Delete it.**
3. **Add New Record** with exactly:
   - **Hostname:** `www`
   - **Type:** `CNAME`
   - **Target / Value:** `tubb-ca.netlify.app`
   - **TTL:** default (or 900)
4. Save.

Apex `tubb.ca` is already correct (`A → 75.2.60.5`) — **do not touch it.**

> Alternative if Hover's UI refuses a CNAME at `www`: add **`www` A → `75.2.60.5`**
> instead. The CNAME is preferred (survives Netlify LB IP changes), but the A record
> works and is enough to unblock the cert.

## Then, once DNS resolves

Netlify usually re-attempts renewal on its own, but force it:

Netlify UI → site **tubb-ca** → **Domain management** → **HTTPS** →
**Verify DNS configuration**, then **Renew certificate**.

Or from the CLI:

```sh
netlify api provisionSiteTLSCertificate \
  --data '{"site_id":"10752494-c42a-4963-b17c-49bc58eec585"}'
```

## Verification commands

**Step 1 — DNS is fixed (must return an answer, not SERVFAIL):**
```sh
dig @ns1.hover.com www.tubb.ca        # expect NOERROR + the CNAME/A, NOT SERVFAIL
dig +short www.tubb.ca                # expect 75.2.60.5 (or the netlify.app CNAME chain)
```

**Step 2 — cert now covers both names (the proof it worked):**
```sh
curl -sI https://www.tubb.ca          # expect HTTP/2 200, no TLS error
echo | openssl s_client -connect www.tubb.ca:443 -servername www.tubb.ca 2>/dev/null \
  | openssl x509 -noout -dates -text | grep -A1 "Subject Alternative Name"
```
Expect the SAN list to show **both** `DNS:tubb.ca` and `DNS:www.tubb.ca`, and
`notAfter` to be ~90 days out rather than 2026-09-15.

**Step 3 — Netlify agrees:**
```sh
netlify api showSiteTLSCertificate \
  --data '{"site_id":"10752494-c42a-4963-b17c-49bc58eec585"}'
```
Expect `"domains": ["tubb.ca","www.tubb.ca"]` and no `renewal_error_message`.

For reference, the pre-fix state was:
`"domains":["tubb.ca"]`, `"renewable": false`,
`"renewal_error_message": "Certificate renewal incomplete: missing domains www.tubb.ca"`.
