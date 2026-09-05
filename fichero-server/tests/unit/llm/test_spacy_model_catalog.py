"""spaCy's models are rows in the local-model catalog (#4671).

Daniel: "spaCy would be in the AI/model provider settings interface." The
first half of that is the model catalog, and `ModelType.SPACY` plus a reserved
directory have sat in this module marked "future" since it was written. This
is that future — extending the catalog every other local model already uses
rather than standing a second one beside it.

The one thing that is NOT like Whisper or FastEmbed: spaCy models are pip
PACKAGES. Installed-state is asked of the runtime, there is no directory of
ours to delete, and they are excluded from the disk-usage total because that
number answers "how much can this app free" and it cannot free them.
"""

from __future__ import annotations

import pytest

from fichero_server.llm.local_models import (
    SPACY_MODELS,
    LocalModelManager,
    ModelType,
)


@pytest.fixture
def manager():
    return LocalModelManager()


class TestTheCatalog:
    def test_the_gate_s_default_model_is_listed(self):
        assert "es_core_news_sm" in SPACY_MODELS

    def test_every_row_says_what_it_is_for(self):
        # A model row with no "why" is a size and a name; the user cannot
        # choose between them.
        for model_id, info in SPACY_MODELS.items():
            assert info["note"].strip(), model_id
            assert info["disk_mb"] > 0, model_id
            assert info["language"] in {"es", "en"}, model_id

    def test_the_large_model_admits_it_is_unmeasured(self):
        # It carries word vectors this gate does not use, and nobody has
        # tested whether it reads 16th-century orthography better. Saying so
        # on the row is the difference between a choice and a guess.
        assert "UNMEASURED" in SPACY_MODELS["es_core_news_lg"]["note"]


class TestListing:
    def test_spacy_rows_join_the_other_local_models(self, manager):
        assert ModelType.SPACY.value in {m.model_type for m in manager.list_all()}

    def test_each_catalogued_model_produces_one_row(self, manager):
        rows = manager.list_spacy_models()
        assert {r.model_id for r in rows} == set(SPACY_MODELS)

    def test_installed_state_comes_from_the_runtime_not_from_disk(self, manager):
        from fichero_server.llm.local_models import _spacy_installed_models

        installed = _spacy_installed_models()
        for row in manager.list_spacy_models():
            assert row.is_downloaded == (row.model_id in installed)
            # These live in site-packages; claiming a path in OUR store would
            # be a fiction the delete path would then act on.
            assert row.path is None

    def test_a_row_with_no_runtime_says_why_rather_than_going_quiet(
        self, manager, monkeypatch
    ):
        import fichero_server.llm.local_models as mod

        monkeypatch.setattr(mod, "_spacy_runtime_available", lambda: False)
        for row in manager.list_spacy_models():
            assert row.available is False
            assert "spaCy is not installed" in (row.unavailable_reason or "")


class TestWritesRefuseRatherThanPretend:
    def test_an_unknown_model_is_rejected(self, manager):
        with pytest.raises(ValueError):
            manager.download_spacy_model("fr_core_news_sm")

    def test_downloading_without_the_runtime_raises(self, manager, monkeypatch):
        import fichero_server.llm.local_models as mod

        monkeypatch.setattr(mod, "_spacy_runtime_available", lambda: False)
        # A download that quietly does nothing is the shape a user reads as
        # "it worked".
        with pytest.raises(RuntimeError, match="nowhere to go"):
            manager.download_spacy_model("es_core_news_sm")

    def test_delete_says_it_is_pip_s_job(self, manager):
        with pytest.raises(RuntimeError, match="pip uninstall"):
            manager.delete_spacy_model("es_core_news_sm")

    def test_disk_usage_does_not_count_what_it_cannot_free(self, manager):
        usage = manager.total_disk_usage()
        assert set(usage) == {"whisper", "embeddings", "total"}
        assert usage["total"] == usage["whisper"] + usage["embeddings"]


class TestItActuallyShips:
    """The gate is only free if the runtime is there (#4671).

    Daniel ruled the ~54 MB into the bundle on 2026-09-04 precisely so the
    shipped app stops running this gate on half power. Everything in the code
    degrades gracefully when spaCy is absent — which is right, and which is
    also exactly what would let a future "trim the bundle" pass remove it
    without a single test going red. This is that test.
    """

    @staticmethod
    def _briefcase_requires() -> list[str]:
        import tomllib
        from pathlib import Path as _Path

        root = _Path(__file__).resolve().parents[3]
        data = tomllib.loads((root / "pyproject.toml").read_text())
        return data["tool"]["briefcase"]["app"]["fichero_server"]["requires"]

    def test_the_runtime_is_bundled(self):
        assert "spacy" in self._briefcase_requires()

    @pytest.mark.parametrize("model", ["es_core_news_sm", "en_core_web_sm"])
    def test_both_small_models_are_bundled(self, model):
        # Bundled, not downloaded: the gate must work on first launch,
        # offline, with nothing to configure.
        assert any(r.startswith(f"{model} @ ") for r in self._briefcase_requires()), model

    def test_the_large_model_is_not_bundled(self):
        # 568 MB for word vectors this gate does not use, and an unmeasured
        # benefit. It stays a catalog row someone can choose.
        assert not any(
            r.startswith("es_core_news_lg") for r in self._briefcase_requires()
        )

    def test_the_expensive_neighbours_stay_out(self):
        # spaCy shipping is not a precedent for pykeen (torch) or OpenCV —
        # an order of magnitude more, each.
        requires = " ".join(self._briefcase_requires())
        assert "pykeen" not in requires
        assert "opencv" not in requires
