"""#6589 item 21: the builder writes its logs, land snapshots and scratch under its state or scratch dir, never $HOME or the worktrees
folder. A builder module (or harness script) that calls mkdtemp/mkdir with dir=Path.home() (or on a path built from it) fails here."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULES = sorted((ROOT / "fichero-builder" / "fichero_builder").glob("*.py")) + sorted((ROOT / "fichero-builder" / "fichero_builder" / "scripts").glob("harness_*.py"))
MAKERS = {"mkdtemp", "mkstemp", "mkdir", "NamedTemporaryFile", "TemporaryDirectory"}
HOME_MARKERS = ("Path.home()", "expanduser", "environ[\"HOME\"]", "getenv(\"HOME\")")


def offenders(src: str, name: str = "<src>") -> list[str]:
    tree, out = ast.parse(src), []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        maker = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
        if maker not in MAKERS:
            continue
        parts = [ast.unparse(k.value) for k in n.keywords if k.arg == "dir"]
        if maker == "mkdir" and isinstance(f, ast.Attribute):
            parts.append(ast.unparse(f.value))  # (Path.home() / "x").mkdir()
        if any(m in p for p in parts for m in HOME_MARKERS):
            out.append(f"{name}:{n.lineno}: {maker} under $HOME")
    return out


def test_the_detector_sees_a_mkdtemp_in_home_and_a_mkdir_on_a_home_path():
    assert offenders('tempfile.mkdtemp(prefix="r-", dir=Path.home())')
    assert offenders('(Path.home() / "x").mkdir(parents=True)')
    assert not offenders('tempfile.mkdtemp(prefix="r-", dir=workroot)') and not offenders('journal.STATE.mkdir(parents=True)')


def test_no_builder_module_makes_a_dir_or_temp_file_under_home():
    bad = [o for p in MODULES for o in offenders(p.read_text(), str(p.relative_to(ROOT)))]
    assert not bad, "\n".join(bad)
