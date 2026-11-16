"""The `security` rung's readers, thresholds and waiver lints (#6600, Step 2.30, `security-scan-rung` and `scan-thresholds-and-waivers`).

Five existing scanners do the finding (bandit, semgrep, osv-scanner, gitleaks); each reports only what is NEW by its own baseline or
diff feature. This module only READS their JSON into one table and applies the written thresholds; it writes no scanner. The waiver
lints judge a batch's diff. `scripts/security_scan_run.py` runs the tools on the runner; `check_tool.security` applies these."""
import datetime as _dt
import re
import tomllib
from collections.abc import Callable

SCANNERS = ("bandit", "semgrep", "osv-scanner", "gitleaks")
WAIVER_MAX_DAYS = 90
GATE = {"bandit": "HIGH severity at MEDIUM confidence or better", "semgrep": "ERROR", "osv-scanner": "CVSS 7.0 or above, known-exploited, "
        "or a fix for a direct dependency", "gitleaks": "any finding"}
_CONF = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def _row(scanner: str, rule: str, severity: str, where: str, red: bool, detail: str = "") -> dict:
    return {"scanner": scanner, "rule": rule, "severity": severity, "where": where, "red": red, "detail": detail}


def read_bandit(doc: dict, baseline: dict | None = None) -> list[dict]:
    """New bandit findings. `-b` already drops the baselined ones; a baseline given here is subtracted again by (file, test, code)
    so a fixture or a run without `-b` is judged the same way."""
    known = {(r["filename"], r["test_id"], r.get("code", "")) for r in (baseline or {}).get("results", [])}
    rows = []
    for r in doc.get("results", []):
        if (r["filename"], r["test_id"], r.get("code", "")) in known:
            continue
        sev, conf = r["issue_severity"].upper(), r["issue_confidence"].upper()
        red = sev == "HIGH" and _CONF.get(conf, 0) >= _CONF["MEDIUM"]
        rows.append(_row("bandit", r["test_id"], sev, f"{r['filename']}:{r['line_number']}", red, r.get("issue_text", "")))
    return rows


def read_semgrep(doc: dict) -> list[dict]:
    """Findings of a `--baseline-commit` run (only those the range introduced): ERROR red, WARNING reported."""
    rows = []
    for r in doc.get("results", []):
        sev = r.get("extra", {}).get("severity", "").upper()
        rows.append(_row("semgrep", r["check_id"], sev, f"{r['path']}:{r['start']['line']}", sev == "ERROR", r.get("extra", {}).get("message", "")))
    return rows


def read_osv(doc: dict, known_exploited: frozenset = frozenset(), direct_fixable: frozenset = frozenset()) -> list[dict]:
    """osv-scanner advisories. Red: CVSS 7.0 or above (the group's `max_severity`), an id in CISA's known-exploited list however
    scored (`known_exploited`, ids or aliases), or an advisory with a fix for a direct dependency (`direct_fixable`, package names)."""
    rows = []
    for res in doc.get("results", []):
        for pkg in res.get("packages", []):
            name = pkg["package"]["name"]
            score = {i: float(g["max_severity"]) for g in pkg.get("groups", []) if g.get("max_severity") for i in g.get("ids", [])}
            for v in pkg.get("vulnerabilities", []):
                ids = {v["id"], *v.get("aliases", [])}
                cvss = score.get(v["id"], 0.0)
                reasons = [t for t, hit in ((f"CVSS {cvss:g}", cvss >= 7.0), ("known exploited", bool(ids & known_exploited)),
                                           ("fix for a direct dependency", name in direct_fixable)) if hit]
                rows.append(_row("osv-scanner", v["id"], f"CVSS {cvss:g}" if cvss else "unscored", f"{name} {pkg['package'].get('version', '')}".strip(),
                                 bool(reasons), "; ".join(reasons)))
    return rows


def read_gitleaks(findings: list, baseline: list | None = None) -> list[dict]:
    """Every gitleaks finding is red; the secret is never printed (redacted)."""
    known = {f.get("Fingerprint") for f in baseline or [] if f.get("Fingerprint")}
    return [_row("gitleaks", f["RuleID"], "secret", f"{f['File']}:{f.get('StartLine', 0)}", True, "REDACTED")
            for f in findings if f.get("Fingerprint") not in known]


def table(rows: list[dict]) -> str:
    """The rung's one table, and the one the review prompt carries under SECURITY SCAN: scanner, rule, severity, file:line, red or reported."""
    if not rows:
        return "none"
    return "\n".join(f"{r['scanner']} | {r['rule']} | {r['severity']} | {r['where']} | {'RED' if r['red'] else 'reported'}" for r in rows)


def refused_tools(found: dict[str, str | None], pins: dict[str, str]) -> list[str]:
    """REFUSED lines: a scanner missing on the runner (found[name] is None), unpinned in harness.toml, or at a version it did not pin.
    Never a quiet green."""
    out = []
    for name in SCANNERS:
        if name == "osv-scanner" and not pins.get("osv-scanner-enabled", True):
            continue  # OFF until the dependency alerts are cleared (owner ruling 2026-11-14)
        if not pins.get(name):
            out.append(f"REFUSED: {name} has no pinned version in harness.toml [check.security]")
        elif found.get(name) is None:
            out.append(f"REFUSED: {name} is not installed on the runner")
        elif found[name] != pins[name]:
            out.append(f"REFUSED: {name} is {found[name]} on the runner, the pin is {pins[name]}")
    return out


# ---- waivers: each tool's own mechanism, each with a reason and an issue ---------------------------------------------------------

_NOSEC = re.compile(r"#\s*nosec\b(?P<rest>.*)$")
_NOSEMGREP = re.compile(r"(?://|#)\s*nosemgrep\b(?P<rest>.*)$")
_GOOD_NOSEC = re.compile(r"^\s+B\d+(?:,\s*B\d+)*\s+--\s+\S.*\(#\d+\)\s*$")
_GOOD_NOSEMGREP = re.compile(r"^:\s*\S+\s+--\s+\S.*\(#\d+\)\s*$")


def waiver_lint(added: list[tuple[str, int, str]]) -> list[str]:
    """Lines (file, line number, text) a batch ADDS that carry a waiver without a reason and an issue: `# nosec B602 -- <reason> (#N)`,
    `// nosemgrep: <rule-id> -- <reason> (#N)`. A bare `# nosec` is refused naming the line."""
    out = []
    for f, n, text in added:
        for rx, good, shape in ((_NOSEC, _GOOD_NOSEC, "# nosec B602 -- <reason> (#N)"), (_NOSEMGREP, _GOOD_NOSEMGREP, "nosemgrep: <rule-id> -- <reason> (#N)")):
            m = rx.search(text)
            if m and not good.match(m.group("rest")):
                out.append(f"{f}:{n}: a waiver needs a rule, a reason and an issue ({shape}): {text.strip()[:100]}")
    return out


def waiver_counts(texts: dict[str, str]) -> dict[str, int]:
    """In-code waivers per tool in a tree's files: {"nosec": n, "nosemgrep": n}."""
    c = {"nosec": 0, "nosemgrep": 0}
    for text in texts.values():
        for line in text.splitlines():
            c["nosec"] += bool(_NOSEC.search(line))
            c["nosemgrep"] += bool(_NOSEMGREP.search(line))
    return c


def waiver_ratchet(base: dict[str, int], head: dict[str, int], added_issues: list[int], approved: Callable[[int], bool]) -> list[str]:
    """A batch that raises a tool's waiver count is red unless every issue it names on its added waivers is labelled
    `security-waiver-approved` (applied only by the owner or the manager). `approved` is the lookup; one that cannot answer is False."""
    out = []
    for tool in ("nosec", "nosemgrep"):
        if head[tool] > base[tool] and not (added_issues and all(approved(i) for i in added_issues)):
            out.append(f"the batch raises the {tool} waivers from {base[tool]} to {head[tool]} and no issue it names carries the "
                       "`security-waiver-approved` label (only the owner or the manager applies it)")
    return out


def baseline_raised(name: str, old_n: int, new_n: int) -> list[str]:
    """`scripts/bandit_baseline.json` and `scripts/gitleaks_baseline.json` may only shrink (`ratchets-held-exactly`)."""
    return [f"{name} lists {new_n} findings, base {old_n}: a baseline may only shrink"] if new_n > old_n else []


def osv_config_problems(text: str, today: _dt.date | None = None) -> list[str]:
    """`osv-scanner.toml` `[[IgnoredVulns]]`: each with `id`, a `reason`, and `ignoreUntil` no more than 90 days out."""
    today = today or _dt.date.today()
    out = []
    for i, e in enumerate(tomllib.loads(text).get("IgnoredVulns", []), 1):
        who = e.get("id") or f"entry {i}"
        if not e.get("id") or not e.get("reason"):
            out.append(f"osv-scanner.toml {who}: an ignore needs an id and a reason")
        until = e.get("ignoreUntil")
        if isinstance(until, _dt.datetime):
            until = until.date()
        if not isinstance(until, _dt.date):
            out.append(f"osv-scanner.toml {who}: no ignoreUntil date: an ignore always ends")
        elif (until - today).days > WAIVER_MAX_DAYS:
            out.append(f"osv-scanner.toml {who}: ignoreUntil {until} is {(until - today).days} days out, the limit is {WAIVER_MAX_DAYS}")
    return out


def gitleaks_config_problems(text: str) -> list[str]:
    """`.gitleaks.toml` allowlists: every one by `regexes` or `paths` and carrying a `description` (the reason)."""
    doc = tomllib.loads(text)
    lists = [*([doc["allowlist"]] if "allowlist" in doc else []), *doc.get("allowlists", [])]
    out = []
    for i, a in enumerate(lists, 1):
        if not a.get("description"):
            out.append(f".gitleaks.toml allowlist {i}: no description: the reason is written there")
        if not (a.get("regexes") or a.get("paths")):
            out.append(f".gitleaks.toml allowlist {i}: an allowlist is by regexes or paths, never a blanket")
    return out
