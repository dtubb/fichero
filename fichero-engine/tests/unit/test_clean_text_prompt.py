from fichero.workflows.tools.clean_text import build_clean_text_prompt


def test_clean_text_prompt_has_minimal_safe_mode_when_all_toggles_disabled() -> None:
    prompt = build_clean_text_prompt({
        "fix_ocr": False,
        "normalize_whitespace": False,
        "fix_hyphenation": False,
        "strip_artifacts": False,
    })

    assert "Tidy obvious whitespace issues only" in prompt
    assert "Do NOT summarize, paraphrase" in prompt
    assert "translate, reorder" in prompt
