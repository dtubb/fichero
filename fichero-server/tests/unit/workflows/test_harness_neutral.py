"""dev-workflows.project.neutral: harness code carries no first-project strings."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location("check_harness_neutral", ROOT / "scripts" / "check_harness_neutral.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def test_a_first_project_string_is_a_hit_but_docstrings_and_the_import_path_are_not(tmp_path):
    f = tmp_path / "x.py"
    f.write_text('"""about integration"""\nimport sys\nsys.path.insert(0, "fichero-server")\nB = "refs/heads/integration"\n')
    hits = guard.violations(f)
    assert len(hits) == 1 and "integration" in hits[0] and ":4:" in hits[0]


def test_the_real_harness_files_are_clean():
    assert guard.main() == 0
