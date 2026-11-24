"""red-on-base-tests-only (building-fichero-locally.md, dev-workflows.run.auto-rules): a batch with no path under red_paths owes no red."""
import subprocess

from fichero_builder import check_tool as ct

CFG = dict(red_paths=("src/",), auto=("red-on-base-tests-only",))


def _repo(tmp_path):
    def g(*a):
        subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)
    g("init", "-q"), g("config", "user.email", "a@b"), g("config", "user.name", "a")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "m.py").write_text("x = 1\n")
    (tmp_path / "test_m.py").write_text("def test_m():\n    assert 1\n")
    g("add", "."), g("commit", "-qm", "base")
    base = subprocess.run(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    return g, base


def test_a_batch_changing_only_tests_owes_no_red_and_one_touching_red_paths_does(tmp_path):
    g, base = _repo(tmp_path)
    (tmp_path / "test_m.py").write_text("def test_m():\n    assert 1\n\n\ndef test_n():\n    assert 2\n")
    g("commit", "-qam", "tests")
    cfg = ct.Config(**CFG)
    assert ct.tests_only(tmp_path, base, "HEAD", cfg)
    (tmp_path / "src" / "m.py").write_text("x = 2\n")
    g("commit", "-qam", "source")
    assert not ct.tests_only(tmp_path, base, "HEAD", cfg), "a source change keeps the red owed"


def test_a_deleted_or_renamed_source_file_is_a_source_change(tmp_path):
    g, base = _repo(tmp_path)
    g("rm", "-q", "src/m.py"), g("commit", "-qm", "gone")
    assert not ct.tests_only(tmp_path, base, "HEAD", ct.Config(**CFG))


def test_the_rule_needs_its_name_in_auto_and_red_paths_set(tmp_path):
    g, base = _repo(tmp_path)
    (tmp_path / "test_m.py").write_text("def test_m():\n    assert 2\n")
    g("commit", "-qam", "tests")
    assert not ct.tests_only(tmp_path, base, "HEAD", ct.Config(red_paths=("src/",)))
    assert not ct.tests_only(tmp_path, base, "HEAD", ct.Config(auto=("red-on-base-tests-only",))), "no red_paths: every file is source"
    assert "red-on-base-tests-only" in ct.AUTO_RULES
