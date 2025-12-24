"""Sheets - Modal sheet dialogs.

Available sheets:
- ProviderSheet: Mac Mail-style Add Provider flow

Usage:
    from fichero.app.main_window.sheets import ProviderSheet

    def on_complete(provider, models):
        print(f"Added {provider.name}")

    sheet = ProviderSheet(parent_window, on_complete=on_complete)
    sheet.show()
"""

from fichero.app.main_window.sheets.provider_sheet import ProviderSheet

__all__ = [
    "ProviderSheet",
]
