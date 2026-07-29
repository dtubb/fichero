"""Cloud placeholders are refused at ingest, per file, loudly (#4233).

152 of 157 files in a real imported folder had zero allocated blocks — iCloud
placeholders, because "Desktop & Documents in iCloud" was on. A placeholder
passes every existing check: it exists, it is a file, and `stat` reports the
FULL logical size. LINK mode copies nothing, so no read ever happens and
nothing detects it; the user gets a document that can never render.

Real dataless files need an iCloud account and eviction to produce, so the
detection is split into a pure `dataless_reason_from_stat` (fed a synthetic
stat here) and the syscall wrapper around it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fichero.importers.dataless import (
    SF_DATALESS,
    UF_COMPRESSED,
    DatalessSourceError,
    dataless_reason,
    dataless_reason_from_stat,
    require_local_bytes,
)


class FakeStat:
    """Just the three fields the detection reads."""

    def __init__(self, *, size: int = 3_000_000, blocks: int | None = 5860, flags: int = 0):
        self.st_size = size
        self.st_blocks = blocks
        self.st_flags = flags


class TestTheDetection:
    def test_a_fully_local_file_is_not_dataless(self):
        assert dataless_reason_from_stat("IMG_001.jpg", FakeStat()) is None

    def test_the_kernel_dataless_flag_is_authoritative(self):
        """SF_DATALESS, even when the block count looks normal."""
        reason = dataless_reason_from_stat("IMG_001.jpg", FakeStat(flags=SF_DATALESS))

        assert reason is not None
        assert "SF_DATALESS" in reason

    def test_zero_allocated_blocks_with_a_nonzero_size(self):
        """The measured shape: `ls` says 3 MB, `du` says 0 blocks."""
        reason = dataless_reason_from_stat("IMG_001.jpg", FakeStat(blocks=0))

        assert reason is not None
        assert "ZERO allocated blocks" in reason

    def test_a_compressed_file_with_zero_blocks_is_NOT_refused(self):
        """An APFS-compressed file keeps its bytes in com.apple.decmpfs and can
        also report zero blocks — it is entirely local. Without this the check
        would refuse legitimate files.

        Read from UF_COMPRESSED in st_flags, not from the xattr: os.listxattr
        is Linux-only, so on macOS — the platform this whole issue is about —
        an xattr-based check would silently never fire.
        """
        assert (
            dataless_reason_from_stat(
                "report.pdf", FakeStat(blocks=0, flags=UF_COMPRESSED)
            )
            is None
        )

    def test_an_empty_file_is_not_a_placeholder(self):
        """0 bytes / 0 blocks is a genuinely empty file, not a stub."""
        assert dataless_reason_from_stat("empty.txt", FakeStat(size=0, blocks=0)) is None

    def test_the_visible_icloud_stub_is_refused_by_name(self):
        reason = dataless_reason_from_stat(".IMG_001.jpg.icloud", FakeStat())

        assert reason is not None
        assert ".icloud" in reason

    def test_a_file_merely_named_icloud_is_fine(self):
        assert dataless_reason_from_stat("icloud-notes.txt", FakeStat()) is None

    def test_a_platform_without_st_flags_still_works(self):
        """Linux stat has no st_flags; the block check must carry it."""

        class LinuxStat:
            st_size = 3_000_000
            st_blocks = 0

        assert dataless_reason_from_stat("IMG_001.jpg", LinuxStat()) is not None


class TestTheSyscallWrapper:
    def test_a_real_local_file_passes(self, tmp_path):
        f = tmp_path / "IMG_001.jpg"
        f.write_bytes(b"x" * 4096)

        assert dataless_reason(f) is None
        require_local_bytes(f)  # must not raise

    def test_a_real_empty_file_passes(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.touch()

        assert dataless_reason(f) is None

    def test_a_simulated_placeholder_is_refused(self, tmp_path, monkeypatch):
        f = tmp_path / "IMG_001.jpg"
        f.write_bytes(b"x" * 4096)
        monkeypatch.setattr(Path, "stat", lambda self, **kw: FakeStat(blocks=0))

        with pytest.raises(DatalessSourceError) as excinfo:
            require_local_bytes(f)

        message = str(excinfo.value)
        assert "IMG_001.jpg" in message, "the message must name the file"
        assert "no local bytes" in message
        # Actionable, not just a diagnosis.
        assert "Download" in message

    def test_compression_rescues_a_zero_block_file(self, tmp_path, monkeypatch):
        f = tmp_path / "report.pdf"
        f.write_bytes(b"x" * 4096)
        monkeypatch.setattr(
            "fichero.importers.dataless.Path.stat",
            lambda self, **kw: FakeStat(blocks=0, flags=UF_COMPRESSED),
        )

        assert dataless_reason(f) is None


class TestIngestRefusesPerFile:
    def test_ingest_file_refuses_a_placeholder(self, tmp_path, monkeypatch):
        from fichero.importers.ingest import IngestMode, ingest_file

        source = tmp_path / "IMG_001.jpg"
        source.write_bytes(b"x" * 4096)
        # Patch the detection, not Path.stat: ingest_file lstats for the
        # symlink check first, and a fake stat there breaks the wrong thing.
        monkeypatch.setattr(
            "fichero.importers.dataless.dataless_reason",
            lambda p: "the file reports 3000000 bytes but has ZERO allocated blocks",
        )

        with pytest.raises(DatalessSourceError):
            ingest_file(
                source,
                mode=IngestMode.LINK,
                save=False,
                package_path=tmp_path / "L.fichero",
                extract_text=False,
            )

    def test_link_mode_is_covered_not_just_copy(self, tmp_path, monkeypatch):
        """LINK copies nothing, so the write-verification work (7022aea08)
        cannot catch it — the check must run before the mode branch."""
        from fichero.importers import ingest as ingest_module
        from fichero.importers.ingest import IngestMode, ingest_file

        source = tmp_path / "IMG_001.jpg"
        source.write_bytes(b"x" * 4096)
        called: list[Path] = []
        monkeypatch.setattr(
            ingest_module, "_copy_to_library", lambda *a, **k: pytest.fail("copied")
        )
        monkeypatch.setattr(
            ingest_module,
            "require_local_bytes",
            lambda p: called.append(p) or (_ for _ in ()).throw(DatalessSourceError("no")),
        )

        with pytest.raises(DatalessSourceError):
            ingest_file(
                source,
                mode=IngestMode.LINK,
                save=False,
                package_path=tmp_path / "L.fichero",
                extract_text=False,
            )

        assert called, "LINK mode must be checked too"

    def test_a_folder_import_records_a_per_file_error_and_keeps_going(
        self, db, test_package, tmp_path, monkeypatch
    ):
        """One placeholder must not fail the whole folder, and must be
        attributable: a failed stub with an ingest_error naming the file."""
        from fichero.importers.ingest import IngestMode, ingest_folder
        from fichero.models import Document, Status

        folder = tmp_path / "NCM_Diary_1925"
        folder.mkdir()
        good = folder / "local.jpg"
        good.write_bytes(b"x" * 4096)
        placeholder = folder / "evicted.jpg"
        placeholder.write_bytes(b"y" * 4096)

        real_reason = dataless_reason

        def only_the_placeholder(path: Path):
            if path.name == "evicted.jpg":
                return "the file reports 3000000 bytes but has ZERO allocated blocks"
            return real_reason(path)

        monkeypatch.setattr(
            "fichero.importers.dataless.dataless_reason", only_the_placeholder
        )

        ingest_folder(
            folder,
            mode=IngestMode.LINK,
            db=db,
            package_path=Path(test_package),
            extract_text=False,
            auto_embed=False,
        )

        by_name = {d.name: d for d in db.query(Document)}
        assert by_name["local.jpg"].status != Status.failed
        failed = by_name["evicted.jpg"]
        assert failed.status == Status.failed
        assert "no local bytes" in (failed.metadata or {}).get("ingest_error", "")
