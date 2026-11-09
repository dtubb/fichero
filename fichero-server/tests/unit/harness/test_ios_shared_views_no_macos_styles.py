"""#6444: `.buttonStyle(.link)` is macOS-only; Views/Components is compiled by the iOS target too, so one use breaks the iOS build."""

from pathlib import Path

COMPONENTS = Path(__file__).resolve().parents[4] / "fichero" / "fichero" / "Views" / "Components"


def test_shared_components_use_no_macos_only_link_button_style():
    assert COMPONENTS.is_dir()
    bad = [str(p.relative_to(COMPONENTS)) for p in COMPONENTS.rglob("*.swift") if ".buttonStyle(.link)" in p.read_text()]
    assert bad == [], f"use .borderless (iOS has no .link): {bad}"
