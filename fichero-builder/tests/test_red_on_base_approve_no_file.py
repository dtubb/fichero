

def test_an_approve_at_this_head_excuses_a_refusal_naming_no_test_file(tmp_path):
    # 2026-11-22: kg-conf conf-2 was asked about "no test file changed" three times at one sha: the approve had become a tuple of
    # other files (accumulated at that head), and a refusal naming no file never matched it
    import pytest
    from fichero_builder import check_tool
    refused = check_tool.red_on_base(tmp_path, "HEAD", "HEAD", [], None, approve_red=False)
    assert "no test file changed" in refused["stderr_tail"]
    with pytest.raises(RuntimeError, match="scratch tree"):  # excused: it goes on to the base tree (none in tmp_path)
        check_tool.red_on_base(tmp_path, "HEAD", "HEAD", [], None, approve_red=("tests/test_other.py",))
