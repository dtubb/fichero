"""The Xcode warning ratchet (#6610, perf-sweep.warnings.from-the-result-bundle and perf-sweep.warnings.ratchet).

Fixtures only: a canned build-results JSON (what `xcrun xcresulttool get build-results` prints) and a canned log. Nothing here
runs a build or Xcode.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "scripts" / "check_xcode_warning_ratchet.py"

PHASE_LINE = (
    "warning: Run script build phase 'Validate App Store Bundle' will be run during every build because it does not "
    "specify any outputs. To address this warning, either add output dependencies to the script phase, or configure "
    "it to run in every build by unchecking \"Based on dependency analysis\" in the script phase."
)


def _mod():
    spec = importlib.util.spec_from_file_location("check_xcode_warning_ratchet", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _w(message, file="fichero/fichero/A.swift", line=3, issue="Swift Compiler Warning", target="fichero"):
    return {"issueType": issue, "message": message, "targetName": target,
            "sourceURL": f"file:///work/{file}#StartingLineNumber={line}&EndingLineNumber={line}"}


def _bundle(path: Path, *warnings) -> Path:
    path.write_text(json.dumps({"warnings": list(warnings), "errors": [], "warningCount": len(warnings)}), encoding="utf-8")
    return path


def _twelve():
    return [
        _w("'old' is deprecated: use new", line=1), _w("'older' is deprecated: use newer", line=2),
        _w("capture of 'self' with non-sendable type 'X' in a `@Sendable` closure", line=3),
        _w("capture of 'y' with non-sendable type 'Y' in a `@Sendable` closure", file="fichero/fichero/B.swift", line=4),
        _w("variable 'z' was never used; consider replacing with '_' or removing it", line=5),
        _w("variable 'q' was never mutated; consider changing to 'let' constant", line=6),
        _w("main actor-isolated property 'p' can not be referenced from a nonisolated context", line=7),
        _w("unused result at 3", line=8),
        _w("implicit conversion loses precision [-Wimplicit-int-conversion]", file="fichero/clib/c.c", line=9, issue="Compiler Warning"),
        _w("unused variable 'k' [-Wunused-variable]", file="fichero/clib/c.c", line=10, issue="Compiler Warning"),
        _w("Run script build phase 'Validate App Store Bundle' will be run during every build because it does not specify "
           "any outputs.", file="fichero/fichero.xcodeproj", line=0, issue="Build System Warning", target="fichero"),
        _w("Multiple commands produce '/x/y.o'; duplicate output file", file="fichero/fichero.xcodeproj", line=0,
           issue="Build System Warning"),
    ]


def test_warnings_are_read_from_the_bundle_normalised_to_kinds_and_blind_without_input(tmp_path, capsys):
    m = _mod()
    bundle = _bundle(tmp_path / "mac.json", *_twelve())
    rows = m.read_bundle(bundle, "mac")
    assert len(rows) == 12 and all(set(r) >= {"platform", "kind", "file", "line", "message"} for r in rows)
    assert {r["platform"] for r in rows} == {"mac"}
    counts = m.count_kinds(rows)
    assert sum(counts.values()) == 12
    # two deprecations of different symbols are one kind with count 2; two Sendable captures likewise
    dep = [k for k in counts if k.startswith("deprecated")]
    assert len(dep) == 1 and counts[dep[0]] == 2
    snd = [k for k in counts if k.startswith("Sendable")]
    assert len(snd) == 1 and counts[snd[0]] == 2
    assert any(k.startswith("unused") for k in counts) and any(k.startswith("concurrency") for k in counts)
    assert counts["-Wimplicit-int-conversion"] == 1 and counts["-Wunused-variable"] == 1
    assert counts["duplicate output file"] == 1
    phase = [k for k in counts if k.startswith("script phase without outputs")]
    assert phase == ["script phase without outputs: 'Validate App Store Bundle'"]
    assert rows[0]["file"] == "work/fichero/fichero/A.swift" or rows[0]["file"].endswith("fichero/fichero/A.swift")
    assert rows[0]["line"] == 1

    # the owner's example line, read from a kept log when the bundle is missing: the phase is named
    log = tmp_path / "build.log"
    log.write_text("\n".join([
        "/w/fichero/fichero/A.swift:12:5: warning: 'foo' is deprecated: use bar",
        "/w/fichero/fichero/A.swift:20:5: warning: 'baz' is deprecated: use bar",
        PHASE_LINE, "note: not a warning", ""]), encoding="utf-8")
    rows = m.read_log(log, "mac")
    kinds = m.count_kinds(rows)
    assert sum(kinds.values()) == 3
    assert kinds["script phase without outputs: 'Validate App Store Bundle'"] == 1
    assert next(v for k, v in kinds.items() if k.startswith("deprecated")) == 2

    # no bundle and no log is BLIND (exit 2), never green; an unreadable bundle is blind too
    baseline = tmp_path / "b.json"
    baseline.write_text("{}", encoding="utf-8")
    assert m.main(["--platform", "mac", "--baseline", str(baseline)]) == 2
    assert m.main(["--platform", "mac", "--baseline", str(baseline), "--bundle", str(tmp_path / "gone.json"),
                   "--log", str(tmp_path / "gone.log")]) == 2
    (tmp_path / "bad.json").write_text("not json", encoding="utf-8")
    assert m.main(["--platform", "mac", "--baseline", str(baseline), "--bundle", str(tmp_path / "bad.json")]) == 2
    assert "BLIND" in capsys.readouterr().err


def _seed(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_the_count_per_kind_and_platform_may_only_fall_and_since_names_the_item_s_lines(tmp_path, capsys):
    m = _mod()
    sendable = "capture of 'a' with non-sendable type 'X' in a `@Sendable` closure"
    base = [_w(sendable, line=3), _w("'old' is deprecated: use new", line=5)]
    kinds = m.count_kinds(m.read_bundle(_bundle(tmp_path / "base.json", *base), "mac"))
    baseline = _seed(tmp_path / "baseline.json", {"mac": kinds, "ios": {"linker": 4}})

    # held: the same bundle is green and the baseline is untouched
    same = _bundle(tmp_path / "same.json", *base)
    assert m.main(["--platform", "mac", "--bundle", str(same), "--baseline", str(baseline)]) == 0

    # one more Sendable warning is red naming the platform, kind, file and line, and both counts
    more = _bundle(tmp_path / "more.json", *base, _w(sendable, file="fichero/fichero/New.swift", line=77))
    assert m.main(["--platform", "mac", "--bundle", str(more), "--baseline", str(baseline)]) == 1
    out = capsys.readouterr().out
    assert "mac" in out and "Sendable" in out and "New.swift:77" in out and "2" in out and "1" in out
    assert json.loads(baseline.read_text())["mac"] == kinds  # a red never moves the baseline

    # a warning that only moves file is not new
    moved = _bundle(tmp_path / "moved.json", _w(sendable, file="fichero/fichero/Moved.swift", line=9), base[1])
    assert m.main(["--platform", "mac", "--bundle", str(moved), "--baseline", str(baseline)]) == 0

    # a platform is held on its own: mac's bundle never touches ios's counts; a kind the baseline never had is new
    fresh = _bundle(tmp_path / "fresh.json", *base, _w("something 'new' happened"))
    assert m.main(["--platform", "mac", "--bundle", str(fresh), "--baseline", str(baseline)]) == 1
    assert json.loads(baseline.read_text())["ios"] == {"linker": 4}

    # one fewer is green, prints the lower count, and lowers the baseline
    capsys.readouterr()
    fewer = _bundle(tmp_path / "fewer.json", base[0])
    assert m.main(["--platform", "mac", "--bundle", str(fewer), "--baseline", str(baseline)]) == 0
    out = capsys.readouterr().out
    assert "fewer" in out.lower() or "lower" in out.lower()
    lowered = json.loads(baseline.read_text())["mac"]
    assert sum(lowered.values()) == 1 and all(v <= kinds[k] for k, v in lowered.items())

    # an explicit baseline that does not exist yet is a first run (as the SwiftLint ratchet's); --update-baseline writes it;
    # the DEFAULT baseline missing is BLIND (the tree moved), shown by the empty-directory run below
    gone = tmp_path / "nothing.json"
    assert m.main(["--platform", "mac", "--bundle", str(same), "--baseline", str(gone), "--update-baseline"]) == 0
    assert json.loads(gone.read_text())["mac"] == kinds

    # a baseline edit that raises a count is refused; a lowered one passes
    old = _seed(tmp_path / "old.json", {"mac": {"Sendable: x": 3, "linker": 1}, "ios": {"linker": 4}})
    raised = _seed(tmp_path / "raised.json", {"mac": {"Sendable: x": 4, "linker": 1}, "ios": {"linker": 4}})
    lower = _seed(tmp_path / "lower.json", {"mac": {"Sendable: x": 2}, "ios": {"linker": 4}})
    newkind = _seed(tmp_path / "newkind.json", {"mac": {"Sendable: x": 3, "linker": 1, "other": 1}, "ios": {"linker": 4}})
    capsys.readouterr()
    assert m.main(["--check-baseline", str(raised), "--was", str(old)]) == 1
    assert "Sendable: x" in capsys.readouterr().out
    assert m.main(["--check-baseline", str(newkind), "--was", str(old)]) == 1
    assert m.main(["--check-baseline", str(lower), "--was", str(old)]) == 0

    # --since over a fixture pair reports only the item's own new lines, per kind (netting by kind, not file)
    head = _bundle(tmp_path / "head.json", *base, _w(sendable, file="fichero/fichero/Item.swift", line=40),
                   _w("'also' is deprecated: x", line=6, file="fichero/fichero/Item.swift"))
    capsys.readouterr()
    assert m.main(["--platform", "mac", "--bundle", str(head), "--since", str(tmp_path / "base.json")]) == 1
    out = capsys.readouterr().out
    assert "Item.swift:40" in out and "Item.swift:6" in out and "A.swift:3" not in out and "A.swift:5" not in out
    assert m.main(["--platform", "mac", "--bundle", str(moved), "--since", str(tmp_path / "base.json")]) == 0
    # a --since with no head bundle is BLIND
    assert m.main(["--platform", "mac", "--since", str(tmp_path / "base.json")]) == 2


def test_the_script_runs_as_a_program_and_is_blind_in_an_empty_directory(tmp_path):
    r = subprocess.run(["python3", str(SCRIPT), "--platform", "mac"], cwd=str(tmp_path), capture_output=True, text=True, timeout=60)
    assert r.returncode == 2 and "BLIND" in r.stderr
