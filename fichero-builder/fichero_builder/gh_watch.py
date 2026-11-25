"""`builder github-watch` (local.github.watch, owner ruling 2026-11-25: watching GitHub is the builder's job, not a manager habit).
One pass, with the manager's gh (workers hold none):
1. the tests workflow on the land branch: its newest COMPLETED run (a cancelled one skipped); each failed job is one alert per
   (workflow, job, head) naming the failing tests from `gh run view --log-failed` (pytest FAILED/ERROR lines); a later green run
   of that job clears it. A run still going after [github_watch].stuck_min minutes is one alert.
2. the security workflow on the land branch: a failed job is one alert with the job's annotations; "not acquired by Runner" is
   said to be GitHub's capacity, not our code.
3. Xcode Cloud: the newest build run of [github_watch].xcode_workflow (App Store Connect API, a JWT signed by `openssl` with the
   key [github_watch].asc_key_path; the key is never printed): each failed action is one alert with its issues.
4. Dependabot is `builder deps`'s (local.deps.weekly); nothing here.
5. The release branch's red runs are expected until a release: one `gh-watch` info row a day, never an alert.
Alerts are the loop's ordinary alert rows (lane "-"), so the manager's watch and the console see them; the owner is texted only
for an alert whose words match [github_watch].owner_words (a release or TestFlight build). Config: harness.toml [github_watch];
absent or `enabled = false` leaves the loop's job off."""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import tempfile
import time
import tomllib
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from fichero_builder import journal

TEST_LINE = re.compile(r"Z (?:FAILED|ERROR) (\S+::\S+)")
NOT_ACQUIRED = "not acquired by Runner"
SEEN = "gh-watch.json"  # step -> the head or build it alerted at (dedupe across passes)


@dataclass(frozen=True)
class Cfg:
    enabled: bool = False
    every_s: int = 600
    branch: str = ""                 # [land].branch
    tests_workflow: str = "Tests"
    security_workflow: str = "Security"
    release_branch: str = ""         # its red runs are info, once a day ('' = none)
    stuck_min: int = 60
    xcode_workflow: str = ""         # an App Store Connect ciWorkflow id ('' = no Xcode Cloud watch)
    asc_key_id: str = ""
    asc_issuer_id: str = ""
    asc_key_path: str = ""           # ~ and $HOME are expanded
    owner_words: tuple = field(default=("release", "TestFlight"))


def load(root) -> Cfg:
    f = Path(root) / "harness.toml"
    rules = tomllib.loads(f.read_text()) if f.is_file() else {}
    d = rules.get("github_watch", {})
    known = {k for k in Cfg.__dataclass_fields__} - {"branch"}
    if bad := sorted(set(d) - known):
        raise ValueError(f"harness.toml [github_watch]: unknown keys {bad}")
    return Cfg(**{**{k: v for k, v in d.items()}, "branch": str(rules.get("land", {}).get("branch", "")),
                  "owner_words": tuple(d.get("owner_words", Cfg.owner_words))})


class World:
    """What one pass reads and does; the tests fake each part."""

    def __init__(self, root, cfg: Cfg, gh: str = "gh", run=subprocess.run, asc=None, text=None):
        self.root, self.cfg, self.gh, self._run = root, cfg, gh, run
        self.asc = asc or (lambda path: asc_get(cfg, path))
        self.text = text

    def gh_out(self, *args) -> str:
        r = self._run([self.gh, *args], cwd=str(self.root), capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(f"gh {' '.join(args[:3])} failed: {(r.stderr or '').strip()[-200:]}")
        return r.stdout

    def gh_json(self, *args):
        return json.loads(self.gh_out(*args) or "null")


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _der_to_raw(der: bytes) -> bytes:
    """An ECDSA DER signature (SEQUENCE of two INTEGERs) as the 64-byte r||s a JWT carries."""
    i = 2 + (der[1] & 0x7F if der[1] & 0x80 else 0)
    out = b""
    for _ in range(2):
        n = der[i + 1]
        out += der[i + 2:i + 2 + n].lstrip(b"\0").rjust(32, b"\0")
        i += 2 + n
    return out


def asc_get(cfg: Cfg, path: str) -> dict:
    """GET an App Store Connect API path with a 15-minute ES256 token signed by `openssl` (stdlib only: no JWT package)."""
    key = os.path.expandvars(os.path.expanduser(cfg.asc_key_path))
    now = int(time.time())
    head = _b64(json.dumps({"alg": "ES256", "kid": cfg.asc_key_id, "typ": "JWT"}).encode())
    body = _b64(json.dumps({"iss": cfg.asc_issuer_id, "iat": now, "exp": now + 900, "aud": "appstoreconnect-v1"}).encode())
    sig = subprocess.run(["openssl", "dgst", "-sha256", "-sign", key], input=f"{head}.{body}".encode(), capture_output=True)
    if sig.returncode:
        raise RuntimeError("openssl could not sign the App Store Connect token (the key file is unreadable or not an EC key)")
    req = urllib.request.Request("https://api.appstoreconnect.apple.com" + path,
                                 headers={"Authorization": f"Bearer {head}.{body}.{_b64(_der_to_raw(sig.stdout))}"})
    with urllib.request.urlopen(req, timeout=60) as f:
        return json.loads(f.read() or b"{}")


def _seen() -> dict:
    try:
        return json.loads((journal.STATE / SEEN).read_text())
    except (OSError, ValueError):
        return {}


def _slug(s: str) -> str:
    return re.sub(r"[^\w.-]+", "-", s).strip("-")[:60]


class Pass:
    def __init__(self, w: World):
        self.w, self.seen, self.said = w, _seen(), []

    def raise_(self, step: str, at: str, why: str, evidence: str) -> None:
        """One alert per (step, at): a step already alerted at the same head or build says nothing."""
        from fichero_builder import queue

        if self.seen.get(step) == at:
            return
        if step in self.seen:
            queue.close_alerts("-", step, f"superseded by the run at {at[:12]}")
        self.seen[step] = at
        queue.alert("-", step, why, evidence, ["dismiss"])
        self.said.append(why)
        if self.w.text and any(x.lower() in why.lower() for x in self.w.cfg.owner_words):
            try:
                self.w.text(why[:300])
            except Exception as e:  # noqa: BLE001 - a text that fails is a row, never a lost alert
                journal.append("gh-watch", state="text-failed", detail=str(e)[:200])

    def clear(self, prefix: str, keep: set, why: str) -> None:
        from fichero_builder import queue

        for step in [s for s in self.seen if s.startswith(prefix) and s not in keep]:
            queue.close_alerts("-", step, why)
            del self.seen[step]

    def workflow(self, name: str, security: bool) -> None:
        cfg, prefix = self.w.cfg, f"gh-{_slug(name)}-"
        runs = self.w.gh_json("run", "list", "--workflow", name, "--branch", cfg.branch, "--limit", "20",
                              "--json", "databaseId,status,conclusion,headSha,createdAt") or []
        now = datetime.now(timezone.utc)
        for r in runs:
            if r.get("status") != "completed":
                age = (now - datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))).total_seconds() / 60
                if age > cfg.stuck_min:
                    self.raise_(f"{prefix}stuck", str(r["databaseId"]), f"{name} run {r['databaseId']} on {cfg.branch} has run {age:.0f} min "
                                f"(over {cfg.stuck_min}): stuck in GitHub's queue or a hung job", f"gh run view {r['databaseId']}")
        done = next((r for r in runs if r.get("status") == "completed" and r.get("conclusion") != "cancelled"), None)
        if done is None:
            return
        rid, head = str(done["databaseId"]), done.get("headSha", "")
        jobs = (self.w.gh_json("run", "view", rid, "--json", "jobs") or {}).get("jobs") or []
        bad = [j for j in jobs if j.get("conclusion") in (("failure", "cancelled") if security else ("failure",))]
        if security and done.get("conclusion") != "failure":
            bad = [j for j in bad if j.get("conclusion") == "failure"]
        keep = set()
        for j in bad:
            step = prefix + _slug(j["name"])
            keep.add(step)
            if self.seen.get(step) == head:
                continue
            if security:
                notes = self.w.gh_json("api", f"repos/{{owner}}/{{repo}}/check-runs/{j['databaseId']}/annotations") or []
                msgs = list(dict.fromkeys(n.get("message", "") for n in notes if n.get("annotation_level") == "failure"))
                if any(NOT_ACQUIRED in m for m in msgs):
                    why = f"{name} job '{j['name']}' at {head[:9]}: GitHub capacity, not our code (the job was not acquired by a hosted runner)"
                else:
                    why = f"{name} job '{j['name']}' failed at {head[:9]}: " + ("; ".join(msgs)[:220] or "no annotation")
            else:
                try:
                    log = self.w.gh_out("run", "view", rid, "--log-failed", "--job", str(j["databaseId"]))
                except RuntimeError as e:  # one job's log that GitHub drops (a connection reset) still alerts, without its names
                    log = ""
                    journal.append("gh-watch", state="error", part="log", detail=str(e)[:300])
                tests = list(dict.fromkeys(TEST_LINE.findall(log)))
                why = (f"{name} job '{j['name']}' failed at {head[:9]}: {len(tests)} test(s): " + ", ".join(t.split("::")[-1] for t in tests[:4])
                       if tests else f"{name} job '{j['name']}' failed at {head[:9]} (no pytest FAILED/ERROR line: read the log)")
            self.raise_(step, head, why, f"gh run view {rid} --log-failed --job {j['databaseId']}")
        self.clear(prefix, keep | {f"{prefix}stuck"}, f"{name} run {rid} at {head[:9]} has no such failed job")

    def xcode(self) -> None:
        cfg = self.w.cfg
        if not cfg.xcode_workflow:
            return
        runs = (self.w.asc(f"/v1/ciWorkflows/{cfg.xcode_workflow}/buildRuns?limit=1&sort=-number"
                           "&fields[ciBuildRuns]=number,executionProgress,completionStatus") or {}).get("data") or []
        if not runs or runs[0]["attributes"].get("executionProgress") != "COMPLETE":
            return
        b, keep = runs[0], set()
        n = b["attributes"].get("number")
        if b["attributes"].get("completionStatus") in ("FAILED", "ERRORED"):
            acts = (self.w.asc(f"/v1/ciBuildRuns/{b['id']}/actions?fields[ciBuildActions]=name,completionStatus") or {}).get("data") or []
            for a in acts:
                if a["attributes"].get("completionStatus") not in ("FAILED", "ERRORED"):
                    continue
                name = a["attributes"].get("name", "?")
                step = f"xcode-cloud-{_slug(name)}"
                keep.add(step)
                if self.seen.get(step) == f"build {n}":
                    continue
                issues = (self.w.asc(f"/v1/ciBuildActions/{a['id']}/issues?limit=20") or {}).get("data") or []
                msgs = list(dict.fromkeys(i["attributes"].get("message", "")[:160] for i in issues  # warnings are not why it failed
                                          if i["attributes"].get("issueType") in ("ERROR", "TEST_FAILURE", None)))
                self.raise_(step, f"build {n}", f"Xcode Cloud build {n} '{name}' failed: " + ("; ".join(msgs)[:220] or "no issue reported"),
                            f"App Store Connect ciBuildRuns/{b['id']}")
        self.clear("xcode-cloud-", keep, f"Xcode Cloud build {n} has no such failed action")

    def release_info(self) -> None:
        cfg, day = self.w.cfg, time.strftime("%Y-%m-%d")
        if not cfg.release_branch or self.seen.get("info-release") == day:
            return
        red = self.w.gh_json("run", "list", "--branch", cfg.release_branch, "--status", "failure", "--limit", "20",
                             "--json", "databaseId,workflowName") or []
        self.seen["info-release"] = day
        journal.append("gh-watch", state="info", detail=f"{len(red)} red run(s) on {cfg.release_branch}, expected until the next release: "
                       + ", ".join(sorted({r.get('workflowName', '?') for r in red}))[:200])


def main_run(root, *, world: World | None = None, out=print) -> int:
    cfg = load(root)
    if not cfg.branch:
        out("builder github-watch: harness.toml [land].branch is not set")
        return 1
    w = world or World(root, cfg, text=_texter())
    p = Pass(w)
    for part, fn in (("tests", lambda: p.workflow(cfg.tests_workflow, False)), ("security", lambda: p.workflow(cfg.security_workflow, True)),
                     ("xcode", p.xcode), ("release", p.release_info)):
        try:
            fn()
        except Exception as e:  # noqa: BLE001 - one part failing (gh down, ASC refusing) leaves the others watched
            journal.append("gh-watch", state="error", part=part, detail=str(e)[:300])
    journal.STATE.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=journal.STATE, delete=False) as f:
        json.dump(p.seen, f)
    os.replace(f.name, journal.STATE / SEEN)
    for s in p.said:
        out(s)
    return 0


def _texter():
    from fichero_builder import nightly

    return nightly.text_owner


def main(a) -> int:
    return main_run(a.root)
