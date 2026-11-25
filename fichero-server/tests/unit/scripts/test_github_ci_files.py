"""Spec: docs/contributor_manual/specs/harness/github-ci.md (ci.dependabot, ci.security-workflow, ci.test-workflow)."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]


def test_dependabot_yml_targets_integration_weekly_over_directories_that_exist():
    doc = yaml.safe_load((ROOT / ".github/dependabot.yml").read_text())
    assert doc["version"] == 2
    assert {u["package-ecosystem"] for u in doc["updates"]} == {"uv", "swift", "github-actions"}
    for u in doc["updates"]:
        assert u["target-branch"] == "integration"
        assert u["schedule"]["interval"] == "weekly"
        d = ROOT / u["directory"].lstrip("/")
        assert d.is_dir(), u["directory"]
        if u["package-ecosystem"] == "swift":
            assert (d / "Package.swift").is_file(), u["directory"]


def _workflow(name):
    doc = yaml.safe_load((ROOT / ".github/workflows" / name).read_text())
    doc["on"] = doc.pop(True, doc.get("on"))  # YAML reads a bare `on` as True
    return doc


def test_security_workflow_runs_on_prs_and_nightly_reuses_the_rungs_scanner_and_adds_codeql():
    doc = _workflow("security.yml")
    assert set(doc["on"]) >= {"pull_request", "schedule"}
    assert doc["on"]["pull_request"]["branches"] == ["integration"]
    text = (ROOT / ".github/workflows/security.yml").read_text()
    assert "scripts/security_scan_run.py" in text
    assert 'sec["pins"]' in text and 'sec.get("osv"' in text and "uv tool install" in text and "install_security_tools" not in text
    assert 'if result["refused"]' in text
    assert {m["language"] for m in doc["jobs"]["codeql"]["strategy"]["matrix"]["include"]} == {"python"}, "Swift waits for a runner with Xcode 27"
    assert "Xcode 27" in text, "the matrix says why Swift is out"


def test_test_workflow_runs_on_prs_to_integration_report_only_with_a_cached_uv_engine_job_and_a_swift_job():
    doc = _workflow("tests.yml")
    assert doc["on"]["pull_request"]["branches"] == ["integration"]
    assert set(doc["on"]["push"]["branches"]) == {"lane-*", "integration"}, "lane pushes and integration pushes run it too"
    jobs = doc["jobs"]
    assert set(jobs) == {"engine", "engine-macos", "contracts", "builder", "swift"}
    assert all(j["continue-on-error"] is True for j in jobs.values()), "report-only: every job"
    assert "enable-cache: true" in (ROOT / ".github/workflows/tests.yml").read_text()


def _steps(job):
    return {s.get("name", ""): s for s in job["steps"]}


def test_each_python_tier_is_its_own_job_with_cached_uv_and_the_engine_job_keeps_the_steps_the_builder_reads():
    """ci.python-tiers: a red names its tier; ci.builder-reads-actions reads `engine`'s `Spec guards` and `Unit tests` steps."""
    jobs = _workflow("tests.yml")["jobs"]
    runs = {name: " ".join(s.get("run", "") for s in j["steps"]) for name, j in jobs.items()}
    assert {"Spec guards", "Unit tests"} <= set(_steps(jobs["engine"])) and "scripts/ci_shard_tests.py tests/unit" in runs["engine"]
    assert "pytest tests/contracts" in runs["contracts"]
    assert "python -m pytest tests -q" in runs["builder"] and _steps(jobs["builder"])["Builder tests"]["working-directory"] == "fichero-builder"
    for name in ("engine", "engine-macos", "contracts", "builder"):
        uv = next(s for s in jobs[name]["steps"] if s.get("uses", "").startswith("astral-sh/setup-uv"))
        assert uv["with"]["enable-cache"] is True, name
        assert "if" not in jobs[name], f"{name} runs on every trigger, lane pushes included"


def test_the_swift_job_selects_its_xcode_says_not_run_without_it_caches_by_package_resolved_and_skips_lane_pushes():
    """ci.swift-on-actions: the app scheme's build and unit tests (never the UI plans), on the newest macOS runner."""
    swift = _workflow("tests.yml")["jobs"]["swift"]
    assert swift["if"] == "github.event_name != 'push' || github.ref == 'refs/heads/integration'", "the Macs own Swift for lane checks"
    assert swift["runs-on"] == "macos-26"
    steps = _steps(swift)
    select = steps["Select Xcode"]["run"]
    assert "xcode-select -s" in select and "Swift NOT RUN" in select and "exit 0" in select and "available=false" in select
    gated = [s for s in swift["steps"] if s.get("name") not in ("Select Xcode", None)]
    assert gated and all(s["if"] == "steps.xcode.outputs.available == 'true'" for s in gated), "no Xcode: the rest is skipped, not red"
    cache = steps["DerivedData and SwiftPM cache"]
    assert cache["uses"].startswith("actions/cache@") and "swiftpm/Package.resolved" in cache["with"]["key"]
    assert {".ci/DerivedData", ".ci/SourcePackages"} <= set(cache["with"]["path"].split())
    build, test = steps["Build (scheme Dev Local, macOS)"]["run"], steps["Swift unit tests"]["run"]
    assert '-scheme "Fichero (Dev Local)"' in build and "-testPlan fichero " in build
    assert "-only-testing:FicheroTests" in test and "UITests" not in test.replace("-only-testing:FicheroTests", "")


def test_xcode_cloud_scripts_never_start_python():
    """ci.xcode-cloud-swift-only: every ci_scripts/ file Xcode Cloud runs skips the engine and starts no Python interpreter."""
    scripts = sorted((ROOT / "fichero" / "ci_scripts").glob("ci_*.sh"))
    assert [p.name for p in scripts] == ["ci_post_clone.sh"]
    for p in scripts:
        code = "\n".join(ln for ln in p.read_text().splitlines() if not ln.lstrip().startswith("#"))
        assert not any(w in code for w in ("python", "pip ", "uv ", "briefcase", "pytest")), p
        assert p.stat().st_mode & 0o111, f"{p.name} must be executable for Xcode Cloud to run it"


def test_the_python_tiers_run_on_linux_with_the_unit_tier_in_four_shards_and_macos_runs_only_the_macos_only_tests():
    """ci.python-tiers: Linux runs everything but `macos_only` (the unit tier as four shards that together are the whole tier,
    the spec guards once); engine-macos runs exactly the `macos_only` tests on a macOS runner."""
    jobs = _workflow("tests.yml")["jobs"]
    for name in ("engine", "contracts", "builder"):
        assert jobs[name]["runs-on"] == "ubuntu-latest", name
    engine = jobs["engine"]
    assert engine["strategy"]["matrix"]["shard"] == [1, 2, 3, 4] and engine["strategy"]["fail-fast"] is False
    steps = _steps(engine)
    assert steps["Spec guards"]["if"] == "matrix.shard == 1", "the guards run once, not four times"
    assert "ci_shard_tests.py tests/unit ${{ matrix.shard }} 4" in steps["Unit tests"]["run"]
    assert "-m 'not macos_only'" in steps["Unit tests"]["run"] and "-m 'not macos_only'" in _steps(jobs["contracts"])["Contract tests"]["run"]
    for name in ("engine", "engine-macos", "contracts"):
        assert _steps(jobs[name])["Install the engine"]["run"] == "uv sync --frozen --all-extras", name
    mac = jobs["engine-macos"]
    assert mac["runs-on"].startswith("macos-") and "-m macos_only" in _steps(mac)["macOS-only tests"]["run"]


def test_the_shards_together_are_the_whole_unit_tier_each_entry_once():
    import importlib.util
    spec = importlib.util.spec_from_file_location("ci_shard_tests", ROOT / "scripts" / "ci_shard_tests.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    items = mod.entries(ROOT / "fichero-server" / "tests" / "unit")
    shards = mod.shards(items, 4)
    flat = [p for s in shards for p in s]
    assert sorted(flat) == sorted(p for p, _ in items) and len(flat) == len(set(flat))
    assert all(shards), "no shard is empty"
    assert mod.shards([("a", 5), ("b", 3), ("c", 2), ("d", 1)], 2) == [["a", "d"], ["b", "c"]], "largest first, to the lightest shard, a tie to the lowest"


def test_apple_only_dependencies_carry_a_darwin_marker_so_the_lock_syncs_on_linux():
    """ci.python-tiers: PyObjC has no Linux wheel; unmarked, `uv sync --frozen --all-extras` fails on a Linux runner."""
    import tomllib
    project = tomllib.loads((ROOT / "fichero-server" / "pyproject.toml").read_text())["project"]
    deps = [*project["dependencies"], *(d for ds in project["optional-dependencies"].values() for d in ds)]
    apple = [d for d in deps if d.lower().startswith(("pyobjc", "mlx", "coremltools"))]
    assert apple and all("sys_platform == 'darwin'" in d for d in apple), apple
    lock = tomllib.loads((ROOT / "fichero-server" / "uv.lock").read_text())
    for pkg in lock["package"]:
        if pkg["name"] == "fichero-server":
            for d in pkg["metadata"]["requires-dist"]:
                if d["name"].startswith("pyobjc"):
                    assert "sys_platform == 'darwin'" in d.get("marker", ""), d


def test_macos_only_is_a_registered_marker_that_skips_off_darwin_with_its_reason(monkeypatch):
    import sys
    import tomllib
    markers = tomllib.loads((ROOT / "fichero-server" / "pyproject.toml").read_text())["tool"]["pytest"]["ini_options"]["markers"]
    assert any(m.startswith("macos_only") for m in markers)
    text = (ROOT / "fichero-server" / "tests" / "conftest.py").read_text()
    assert 'get_closest_marker("macos_only")' in text and 'sys.platform != "darwin"' in text and '"macOS only: "' in text
