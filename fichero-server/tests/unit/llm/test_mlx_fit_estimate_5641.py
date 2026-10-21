"""An MLX model's fit is estimated before it loads, by one rule the finder and the load share (#5641), tested to the
spec: `runtime.mlx.fit-estimate`, `runtime.mlx.refuse-only-what-would-crash`, `runtime.mlx.offer-a-way-to-fit`
(docs/contributor_manual/specs/ai/local-runtimes.md).

WHY: the only check was weights + 1 GB against 75% of memory, made at load time; nothing said before a download
whether a model would run, a long context was not counted, and a refusal never named a smaller build of the same
model. The machine is never read: physical memory is passed in.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fichero_server.llm import local_inference as li
from fichero_server.llm.local_inference import (
    FITS,
    TIGHT,
    WONT_FIT,
    LocalModelMemoryUnavailableError,
    assert_memory_available_for_model,
    fit_estimate,
)
from fichero_server.llm.mlx_model_store import MANAGED_MLX_MODELS, kv_bytes_per_token

GB = 1024**3
THREE_B = MANAGED_MLX_MODELS["Qwen2.5-VL-3B"]
SEVEN_B = MANAGED_MLX_MODELS["Qwen2.5-VL-7B"]
EIGHT_B = MANAGED_MLX_MODELS["mlx-community/Qwen3-VL-8B"]


def test_the_need_is_weights_plus_the_kv_cache_for_the_context_plus_overhead():
    short, long = fit_estimate(THREE_B, 2048, 16 * GB), fit_estimate(THREE_B, 32768, 16 * GB)
    assert short.need_bytes == THREE_B.download_size_bytes + 2048 * THREE_B.kv_bytes_per_token + li.MLX_OVERHEAD_BYTES
    assert long.need_bytes - short.need_bytes == (32768 - 2048) * THREE_B.kv_bytes_per_token  # a long page needs more
    assert "tokens of context" in short.reason


def test_on_an_8_gb_mac_the_3b_fits_and_the_7b_wont_fit_in_words():
    """This Mac's case: an 8 GB Air read pages with the 3B; the 7B 4-bit never loaded there."""
    assert fit_estimate(THREE_B, physical_memory=8 * GB).word == FITS
    seven = fit_estimate(SEVEN_B, physical_memory=8 * GB)
    assert seven.word == WONT_FIT
    assert "8.0 GB" in seven.reason and "6.0 GB" in seven.reason  # this Mac's memory, and what it can give a model


def test_on_a_16_gb_mac_the_7b_loads_for_text_but_wont_fit_to_read_a_page():
    """The 7B card's page floor is 24 GB (#5641): as a reader it is refused in the same words `runs_here` gives, so the finder
    never says "Fits" for a reader Fichero refuses; for text it still fits."""
    assert fit_estimate(SEVEN_B, physical_memory=16 * GB).word == TIGHT  # the floor is only a note when no page is read
    reader = fit_estimate(SEVEN_B, physical_memory=16 * GB, reads_pages=True)
    assert reader.word == WONT_FIT and "24.0 GB" in reader.reason and "16.0 GB" in reader.reason
    assert fit_estimate(SEVEN_B, physical_memory=32 * GB, reads_pages=True).word == FITS
    eight = fit_estimate(EIGHT_B, physical_memory=16 * GB)  # its note: reading a page needs a 24 GB Mac
    assert eight.word == TIGHT and "it runs" in eight.reason


def test_between_the_comfort_line_and_the_ceiling_is_tight_and_still_runs():
    model = SimpleNamespace(repo_id="x/big-4bit", display_name="Big", download_size_bytes=11 * GB,
                            kv_bytes_per_token=36 * 1024)
    made = fit_estimate(model, physical_memory=16 * GB)  # about 12 GB: above 10.7 GB, below 14 GB
    assert made.comfort_bytes < made.need_bytes <= made.ceiling_bytes and made.word == TIGHT


def test_a_model_that_wont_fit_is_offered_a_smaller_build_of_the_same_model():
    eight_bit = SimpleNamespace(repo_id="mlx-community/Qwen2.5-VL-7B-Instruct-8bit", display_name="Qwen2.5 VL 7B 8-bit",
                                download_size_bytes=int(8.3 * GB), kv_bytes_per_token=SEVEN_B.kv_bytes_per_token)
    three_bit = SimpleNamespace(repo_id="mlx-community/Qwen2.5-VL-7B-Instruct-3bit", display_name="Qwen2.5 VL 7B 3-bit",
                                download_size_bytes=int(3.4 * GB), kv_bytes_per_token=SEVEN_B.kv_bytes_per_token)
    other = SimpleNamespace(repo_id="mlx-community/Llama-3.2-1B-4bit", display_name="Llama 1B",
                            download_size_bytes=GB, kv_bytes_per_token=None)
    made = fit_estimate(eight_bit, physical_memory=8 * GB, catalog=[eight_bit, SEVEN_B, three_bit, other])
    assert made.word == WONT_FIT and made.smaller == "Qwen2.5 VL 7B 3-bit"  # the largest build that fits, same model
    assert "Qwen2.5 VL 7B 3-bit fits" in made.reason


def test_with_no_smaller_build_a_shorter_context_is_offered_when_it_would_fit():
    model = SimpleNamespace(repo_id="x/only-4bit", display_name="Only", download_size_bytes=int(4.5 * GB),
                            kv_bytes_per_token=144 * 1024)
    made = fit_estimate(model, context_tokens=32768, physical_memory=8 * GB, catalog=[model])
    assert made.word == WONT_FIT and made.smaller is None and "with a context of" in made.reason


def test_the_load_refuses_exactly_what_the_estimate_calls_wont_fit():
    """One rule: the finder's 'won't fit' is the load's refusal, and nothing else is refused for size."""
    for spec, ram in ((THREE_B, 8), (SEVEN_B, 8), (SEVEN_B, 16), (EIGHT_B, 16)):
        word = fit_estimate(spec, physical_memory=ram * GB).word
        check = lambda: assert_memory_available_for_model(  # noqa: E731
            spec, available_bytes=lambda: ram * GB, pressure_level=lambda: 1, physical_bytes=lambda: ram * GB)
        if word == WONT_FIT:
            with pytest.raises(LocalModelMemoryUnavailableError):
                check()
        else:
            check()


def test_a_models_kv_cache_is_read_from_its_own_config():
    qwen_vl = {"text_config": {"num_hidden_layers": 28, "num_attention_heads": 28, "num_key_value_heads": 4,
                               "hidden_size": 3584}}
    assert kv_bytes_per_token(qwen_vl) == SEVEN_B.kv_bytes_per_token == 56 * 1024
    assert kv_bytes_per_token({"model_type": "unknown"}) is None


def test_the_finder_says_whether_each_mlx_model_fits_this_mac(client):
    # An 8 GB Mac is 8 GiB (#5833): the 7B needs 6.45 GiB against a 6.0 GiB ceiling; 8.6 was a decimal-GB figure.
    answer = client.get("/api/recipes/candidates", params={"scripts": "Latn", "languages": "es",
                                                           "job": "read-a-page", "mac_memory_gb": 8.0})
    assert answer.status_code == 200, answer.text
    fits = {i["id"]: i["fit"] for i in answer.json()["items"]}
    seven = next(f for cid, f in fits.items() if "Qwen2.5-VL-7B-Instruct-4bit" in cid)
    three = next(f for cid, f in fits.items() if "Qwen2.5-VL-3B-Instruct-4bit" in cid)
    assert (seven["word"], three["word"]) == ("won't fit", "fits") and seven["reason"]
    assert all(f is None for cid, f in fits.items() if not cid.startswith("mlx:"))
    assert "8,192 tokens" in three["reason"]  # a page step that says nothing more: the default context


# --- the step's own context (#5641) -------------------------------------------------------------------


def test_a_steps_context_is_its_prompt_and_image_plus_its_answer():
    assert li.step_context_tokens(max_tokens=1024) == li.PROMPT_AND_IMAGE_TOKENS + 1024
    assert li.step_context_tokens(lines=40) == li.PROMPT_AND_IMAGE_TOKENS + 40 * li.TOKENS_PER_LINE
    assert li.step_context_tokens(max_tokens=1024, lines=40) == li.PROMPT_AND_IMAGE_TOKENS + 1024  # the bound
    assert li.step_context_tokens() == li.DEFAULT_CONTEXT_TOKENS  # a step that says neither


def test_the_load_judges_the_fit_by_the_calls_own_context():
    """A model that won't fit at the default context loads for a call whose context is short."""
    model = SimpleNamespace(model_id="x/mid-4bit", repo_id="x/mid-4bit", display_name="Mid", capabilities=("text",),
                            download_size_bytes=int(4.5 * GB), kv_bytes_per_token=144 * 1024, page_memory_bytes=None)
    check = lambda: assert_memory_available_for_model(  # noqa: E731
        model, catalog=[model], available_bytes=lambda: 8 * GB, pressure_level=lambda: 1, physical_bytes=lambda: 8 * GB)
    with pytest.raises(LocalModelMemoryUnavailableError):
        check()
    with li.reading_with_context(li.step_context_tokens(max_tokens=1024)):
        check()
    with pytest.raises(LocalModelMemoryUnavailableError):
        check()  # the context is the call's only


def test_the_finder_judges_a_line_step_by_a_lines_context(client):
    answer = client.get("/api/recipes/candidates", params={"scripts": "Latn", "languages": "es",
                                                           "job": "read-a-line", "mac_memory_gb": 8.6})
    assert answer.status_code == 200, answer.text
    said = [i["fit"]["reason"] for i in answer.json()["items"] if i["fit"]]
    line = li.step_context_tokens(lines=1)
    assert said and all(f"{line:,} tokens" in reason for reason in said)


def test_a_page_is_judged_by_its_own_working_lines(db, tmp_path):
    """A page read with a model on this Mac: its context is its working lines' answer, and a call is judged at the
    smaller of that and its own max_tokens."""
    from pathlib import Path

    from fichero_server.models import DocType, Document
    from fichero_server.llm.working_lines import working_lines
    from tests.unit.training.test_kraken_training_set import _page

    folder = Document(name="F", doc_type=DocType.folder)
    db.save(folder)
    lined, bare = _page(db, tmp_path, "1_Hoja", folder), _page(db, tmp_path, "2_Hoja", folder, read_by=None)
    library = str(Path(db.path).parent)
    count = len(working_lines(db, lined.id).lines)
    assert count and li.page_lines_context(library, lined.id) == li.step_context_tokens(lines=count)
    assert li.page_lines_context(library, bare.id) is None  # no lines: the call's own max_tokens decides

    with li.reading_with_context(li.step_context_tokens(lines=count)):
        assert li.call_context_tokens(8192) == li.step_context_tokens(lines=count)  # the page's, smaller
        assert li.call_context_tokens(16) == li.step_context_tokens(max_tokens=16)  # a short call's own
    assert li.call_context_tokens(8192) == li.step_context_tokens(max_tokens=8192)
