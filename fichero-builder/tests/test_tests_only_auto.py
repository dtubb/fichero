"""red-on-base-tests-only (building-fichero-locally.md, dev-workflows.run.auto-rules): a batch of only tests (and docs) owes no red."""
from fichero_builder import check_tool as ct

CFG = ct.Config(red_paths=("src/",), auto=("red-on-base-tests-only",), test_globs=("test_*.py", "*_test.py"))


def test_a_batch_of_only_tests_and_docs_owes_no_red():
    assert ct.tests_only(["test_m.py", "pkg/tests/helper.py", "docs/a.md", "x_test.py"], CFG)


def test_source_anywhere_keeps_the_red_owed_scripts_and_pipeline_included():
    for src in ("src/m.py", "scripts/check_x.py", "pipeline/core.py", "tool.swift"):
        assert not ct.tests_only(["test_m.py", src], CFG), src


def test_the_rule_needs_its_name_in_auto_red_paths_set_and_a_non_empty_diff():
    assert not ct.tests_only(["test_m.py"], ct.Config(red_paths=("src/",)))
    assert not ct.tests_only(["test_m.py"], ct.Config(auto=("red-on-base-tests-only",))), "no red_paths: every file is source"
    assert not ct.tests_only([], CFG), "a failed git call is not a test-only diff"
    assert "red-on-base-tests-only" in ct.AUTO_RULES
