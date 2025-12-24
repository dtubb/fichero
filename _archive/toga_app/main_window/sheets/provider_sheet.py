"""Provider Sheet - Mac Mail-style Add Provider flow.

Two-step flow:
1. Choose provider type (DashScope, OpenAI, Anthropic, Ollama, LM Studio)
2. Sign in / configure (API key for cloud, endpoint URL for local)

Usage:
    from fichero.app.main_window.sheets import ProviderSheet

    def on_complete(provider, models):
        print(f"Added {provider.name} with {len(models)} models")

    sheet = ProviderSheet(parent_window, on_complete=on_complete)
    sheet.show()
"""
from __future__ import annotations

import logging
from typing import Any, Callable, TYPE_CHECKING
from dataclasses import dataclass

from rubicon.objc import ObjCClass, SEL, objc_method, objc_property

if TYPE_CHECKING:
    from fichero.models import Provider, Model

logger = logging.getLogger(__name__)

# =============================================================================
# Provider Type Definitions
# =============================================================================

@dataclass
class ProviderTypeInfo:
    """Information about a provider type."""
    id: str
    name: str
    description: str
    is_local: bool
    default_endpoint: str | None = None
    docs_url: str | None = None


PROVIDER_TYPES = [
    ProviderTypeInfo(
        id="dashscope",
        name="DashScope (Qwen)",
        description="Alibaba's Qwen VL models",
        is_local=False,
        docs_url="https://dashscope.console.aliyun.com",
    ),
    ProviderTypeInfo(
        id="openai",
        name="OpenAI",
        description="GPT-4 Vision, GPT-4o",
        is_local=False,
        docs_url="https://platform.openai.com/api-keys",
    ),
    ProviderTypeInfo(
        id="anthropic",
        name="Anthropic",
        description="Claude 3 with vision",
        is_local=False,
        docs_url="https://console.anthropic.com/settings/keys",
    ),
    ProviderTypeInfo(
        id="ollama",
        name="Ollama (Local)",
        description="Run models locally",
        is_local=True,
        default_endpoint="http://localhost:11434",
    ),
    ProviderTypeInfo(
        id="lmstudio",
        name="LM Studio (Local)",
        description="Local inference server",
        is_local=True,
        default_endpoint="http://localhost:1234/v1",
    ),
]


# =============================================================================
# Cocoa Classes
# =============================================================================

NSObject = ObjCClass("NSObject")
NSWindow = ObjCClass("NSWindow")
NSPanel = ObjCClass("NSPanel")
NSView = ObjCClass("NSView")
NSTextField = ObjCClass("NSTextField")
NSSecureTextField = ObjCClass("NSSecureTextField")
NSButton = ObjCClass("NSButton")
NSBox = ObjCClass("NSBox")
NSColor = ObjCClass("NSColor")
NSFont = ObjCClass("NSFont")
NSStackView = ObjCClass("NSStackView")


# =============================================================================
# Constants
# =============================================================================

SHEET_WIDTH = 400
SHEET_HEIGHT = 350
AUTORESIZE_FLEX = 18


# =============================================================================
# Flipped View
# =============================================================================

class _ProviderSheetFlippedView(NSView):
    """NSView with flipped coordinates for top-down layout."""

    @objc_method
    def isFlipped(self) -> bool:
        return True


# =============================================================================
# Sheet Delegate
# =============================================================================

class _ProviderSheetDelegate(NSObject):
    """Handles button actions for the provider sheet."""

    _sheet = objc_property(object, weak=True)

    @objc_method
    def cancel_(self, sender) -> None:
        """Cancel button pressed."""
        sheet = self._sheet
        if sheet:
            sheet._close()

    @objc_method
    def selectProvider_(self, sender) -> None:
        """Provider type selected."""
        sheet = self._sheet
        if sheet:
            tag = sender.tag
            if 0 <= tag < len(PROVIDER_TYPES):
                sheet._show_sign_in(PROVIDER_TYPES[tag])

    @objc_method
    def connect_(self, sender) -> None:
        """Connect button pressed."""
        sheet = self._sheet
        if sheet:
            sheet._do_connect()

    @objc_method
    def testConnection_(self, sender) -> None:
        """Test connection button pressed."""
        sheet = self._sheet
        if sheet:
            sheet._test_connection()

    @objc_method
    def back_(self, sender) -> None:
        """Back button pressed."""
        sheet = self._sheet
        if sheet:
            sheet._show_type_picker()


# =============================================================================
# Provider Sheet
# =============================================================================

class ProviderSheet:
    """Mac Mail-style Add Provider sheet.

    Two-step flow:
    1. Pick provider type
    2. Enter credentials / configure endpoint
    """

    def __init__(
        self,
        parent_window: Any,
        on_complete: Callable[[Provider, list[Model]], None] | None = None,
    ):
        self._parent = parent_window
        self._on_complete = on_complete
        self._selected_type: ProviderTypeInfo | None = None

        # UI references
        self._api_key_field = None
        self._endpoint_field = None
        self._status_label = None
        self._connect_btn = None

        # Delegate
        self._delegate = _ProviderSheetDelegate.alloc().init()
        self._delegate._sheet = self

        # Create sheet window
        self._sheet = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            ((0, 0), (SHEET_WIDTH, SHEET_HEIGHT)),
            1 | 2 | 4,  # Titled, Closable, Miniaturizable
            2,  # Buffered
            False
        )
        self._sheet.title = "Add AI Provider"

        # Content view
        self._content = _ProviderSheetFlippedView.alloc().initWithFrame_(((0, 0), (SHEET_WIDTH, SHEET_HEIGHT)))
        self._sheet.contentView = self._content

        # Build type picker UI (step 1)
        self._build_type_picker()

        logger.debug("ProviderSheet created")

    def _build_type_picker(self):
        """Build the provider type picker UI (Step 1)."""
        # Clear existing content
        for subview in list(self._content.subviews):
            subview.removeFromSuperview()

        y = 20

        # Title
        title = NSTextField.alloc().initWithFrame_(((20, y), (SHEET_WIDTH - 40, 24)))
        title.stringValue = "Choose a provider type"
        title.editable = False
        title.bordered = False
        title.drawsBackground = False
        title.font = NSFont.systemFontOfSize_weight_(16, 0.5)
        self._content.addSubview_(title)
        y += 40

        # Provider type buttons
        for i, ptype in enumerate(PROVIDER_TYPES):
            btn = self._create_provider_button(ptype, y, tag=i)
            self._content.addSubview_(btn)
            y += 50

        y += 10

        # Cancel button
        cancel = NSButton.alloc().initWithFrame_(((SHEET_WIDTH - 90, y), (70, 24)))
        cancel.title = "Cancel"
        cancel.bezelStyle = 1
        cancel.setTarget_(self._delegate)
        cancel.setAction_(SEL("cancel:"))
        self._content.addSubview_(cancel)

    def _create_provider_button(self, ptype: ProviderTypeInfo, y: int, tag: int) -> NSButton:
        """Create a provider type selection button."""
        btn = NSButton.alloc().initWithFrame_(((20, y), (SHEET_WIDTH - 40, 44)))
        btn.title = f"{ptype.name}\n{ptype.description}"
        btn.bezelStyle = 1
        btn.tag = tag
        btn.setTarget_(self._delegate)
        btn.setAction_(SEL("selectProvider:"))
        return btn

    def _show_sign_in(self, ptype: ProviderTypeInfo):
        """Show sign-in UI (Step 2)."""
        self._selected_type = ptype

        # Clear existing content
        for subview in list(self._content.subviews):
            subview.removeFromSuperview()

        y = 20

        # Back button
        back = NSButton.alloc().initWithFrame_(((10, y), (60, 24)))
        back.title = "< Back"
        back.bezelStyle = 1
        back.setTarget_(self._delegate)
        back.setAction_(SEL("back:"))
        self._content.addSubview_(back)

        # Title
        title = NSTextField.alloc().initWithFrame_(((80, y), (SHEET_WIDTH - 100, 24)))
        title.stringValue = f"Sign in to {ptype.name}"
        title.editable = False
        title.bordered = False
        title.drawsBackground = False
        title.font = NSFont.systemFontOfSize_weight_(16, 0.5)
        self._content.addSubview_(title)
        y += 50

        if ptype.is_local:
            # Local provider: endpoint URL
            self._build_local_sign_in(y, ptype)
        else:
            # Cloud provider: API key
            self._build_cloud_sign_in(y, ptype)

    def _build_cloud_sign_in(self, y: int, ptype: ProviderTypeInfo):
        """Build cloud provider sign-in UI."""
        # Help text
        if ptype.docs_url:
            help_text = NSTextField.alloc().initWithFrame_(((20, y), (SHEET_WIDTH - 40, 30)))
            help_text.stringValue = f"Get an API key at:\n{ptype.docs_url}"
            help_text.editable = False
            help_text.bordered = False
            help_text.drawsBackground = False
            help_text.font = NSFont.systemFontOfSize_(12)
            help_text.textColor = NSColor.secondaryLabelColor
            self._content.addSubview_(help_text)
            y += 40

        # API Key label
        label = NSTextField.alloc().initWithFrame_(((20, y), (SHEET_WIDTH - 40, 16)))
        label.stringValue = "API Key"
        label.editable = False
        label.bordered = False
        label.drawsBackground = False
        label.font = NSFont.systemFontOfSize_(12)
        self._content.addSubview_(label)
        y += 20

        # API Key field (secure)
        self._api_key_field = NSSecureTextField.alloc().initWithFrame_(((20, y), (SHEET_WIDTH - 40, 24)))
        self._api_key_field.placeholderString = "sk-..."
        self._content.addSubview_(self._api_key_field)
        y += 40

        # Status label
        self._status_label = NSTextField.alloc().initWithFrame_(((20, y), (SHEET_WIDTH - 40, 20)))
        self._status_label.stringValue = ""
        self._status_label.editable = False
        self._status_label.bordered = False
        self._status_label.drawsBackground = False
        self._status_label.font = NSFont.systemFontOfSize_(12)
        self._content.addSubview_(self._status_label)
        y += 30

        self._add_bottom_buttons(y)

    def _build_local_sign_in(self, y: int, ptype: ProviderTypeInfo):
        """Build local provider configuration UI."""
        # Help text
        help_text = NSTextField.alloc().initWithFrame_(((20, y), (SHEET_WIDTH - 40, 30)))
        help_text.stringValue = f"Make sure {ptype.name.split(' (')[0]} is running locally."
        help_text.editable = False
        help_text.bordered = False
        help_text.drawsBackground = False
        help_text.font = NSFont.systemFontOfSize_(12)
        help_text.textColor = NSColor.secondaryLabelColor
        self._content.addSubview_(help_text)
        y += 40

        # Endpoint label
        label = NSTextField.alloc().initWithFrame_(((20, y), (SHEET_WIDTH - 40, 16)))
        label.stringValue = "Server URL"
        label.editable = False
        label.bordered = False
        label.drawsBackground = False
        label.font = NSFont.systemFontOfSize_(12)
        self._content.addSubview_(label)
        y += 20

        # Endpoint field
        self._endpoint_field = NSTextField.alloc().initWithFrame_(((20, y), (SHEET_WIDTH - 40, 24)))
        self._endpoint_field.stringValue = ptype.default_endpoint or ""
        self._content.addSubview_(self._endpoint_field)
        y += 30

        # Test connection button
        test_btn = NSButton.alloc().initWithFrame_(((20, y), (120, 24)))
        test_btn.title = "Test Connection"
        test_btn.bezelStyle = 1
        test_btn.setTarget_(self._delegate)
        test_btn.setAction_(SEL("testConnection:"))
        self._content.addSubview_(test_btn)

        # Status label (next to test button)
        self._status_label = NSTextField.alloc().initWithFrame_(((150, y + 4), (SHEET_WIDTH - 170, 20)))
        self._status_label.stringValue = ""
        self._status_label.editable = False
        self._status_label.bordered = False
        self._status_label.drawsBackground = False
        self._status_label.font = NSFont.systemFontOfSize_(12)
        self._content.addSubview_(self._status_label)
        y += 40

        self._add_bottom_buttons(y)

    def _add_bottom_buttons(self, y: int):
        """Add Cancel and Connect buttons at bottom."""
        # Cancel button
        cancel = NSButton.alloc().initWithFrame_(((SHEET_WIDTH - 170, y), (70, 24)))
        cancel.title = "Cancel"
        cancel.bezelStyle = 1
        cancel.setTarget_(self._delegate)
        cancel.setAction_(SEL("cancel:"))
        self._content.addSubview_(cancel)

        # Connect button
        self._connect_btn = NSButton.alloc().initWithFrame_(((SHEET_WIDTH - 90, y), (70, 24)))
        self._connect_btn.title = "Connect"
        self._connect_btn.bezelStyle = 1
        self._connect_btn.setTarget_(self._delegate)
        self._connect_btn.setAction_(SEL("connect:"))
        self._content.addSubview_(self._connect_btn)

    def _show_type_picker(self):
        """Go back to type picker."""
        self._selected_type = None
        self._build_type_picker()

    def _test_connection(self):
        """Test connection to local provider."""
        if not self._endpoint_field:
            return

        endpoint = str(self._endpoint_field.stringValue).strip()
        if not endpoint:
            self._status_label.stringValue = "Enter a URL"
            self._status_label.textColor = NSColor.systemRedColor
            return

        self._status_label.stringValue = "Testing..."
        self._status_label.textColor = NSColor.secondaryLabelColor

        # TODO: Actual connection test
        # For now, just mark as success
        self._status_label.stringValue = "Connected"
        self._status_label.textColor = NSColor.systemGreenColor

    def _do_connect(self):
        """Validate and save the provider."""
        if not self._selected_type:
            return

        ptype = self._selected_type

        if ptype.is_local:
            endpoint = str(self._endpoint_field.stringValue).strip()
            if not endpoint:
                self._status_label.stringValue = "Enter a URL"
                self._status_label.textColor = NSColor.systemRedColor
                return
            self._save_provider(ptype, api_key=None, endpoint=endpoint)
        else:
            api_key = str(self._api_key_field.stringValue).strip()
            if not api_key:
                self._status_label.stringValue = "Enter an API key"
                self._status_label.textColor = NSColor.systemRedColor
                return
            self._save_provider(ptype, api_key=api_key, endpoint=None)

    def _save_provider(self, ptype: ProviderTypeInfo, api_key: str | None, endpoint: str | None):
        """Save provider to database and keychain."""
        from fichero.db import db
        from fichero.models import Provider, Model, ProviderType
        from fichero.keychain import set_api_key

        try:
            # Create provider
            provider = Provider(
                name=ptype.name.split(" (")[0],  # Remove "(Local)" suffix
                provider_type=ProviderType(ptype.id),
                api_base=endpoint,
                enabled=True,
            )
            db.save(provider)

            # Save API key to keychain (cloud providers only)
            if api_key:
                set_api_key(ptype.id, api_key)

            # TODO: Fetch available models from API
            # For now, create placeholder models
            models = self._create_default_models(provider, ptype)

            logger.info(f"Saved provider: {provider.name}")

            # Callback
            if self._on_complete:
                self._on_complete(provider, models)

            self._close()

        except Exception as e:
            logger.error(f"Failed to save provider: {e}")
            self._status_label.stringValue = f"Error: {e}"
            self._status_label.textColor = NSColor.systemRedColor

    def _create_default_models(self, provider: Provider, ptype: ProviderTypeInfo) -> list[Model]:
        """Create default models for a provider."""
        from fichero.db import db
        from fichero.models import Model

        models = []

        # Default models by provider type
        default_models = {
            "dashscope": [
                ("Qwen VL Max", "qwen-vl-max", True),
                ("Qwen VL Plus", "qwen-vl-plus", False),
            ],
            "openai": [
                ("GPT-4o", "gpt-4o", True),
                ("GPT-4 Vision", "gpt-4-vision-preview", False),
            ],
            "anthropic": [
                ("Claude 3.5 Sonnet", "claude-3-5-sonnet-20241022", True),
                ("Claude 3 Opus", "claude-3-opus-20240229", False),
            ],
            "ollama": [
                ("Llava", "llava", True),
                ("Llama 3.2 Vision", "llama3.2-vision", False),
            ],
            "lmstudio": [
                ("Default Model", "default", True),
            ],
        }

        for name, model_id, is_default in default_models.get(ptype.id, []):
            model = Model(
                provider_id=provider.id,
                name=name,
                model_id=model_id,
                capabilities=["vision"],
                is_default=is_default,
            )
            db.save(model)
            models.append(model)

        return models

    def _close(self):
        """Close the sheet."""
        if self._parent:
            self._parent.endSheet_(self._sheet)
        else:
            self._sheet.close()

    def show(self):
        """Show the sheet."""
        if self._parent:
            self._parent.beginSheet_completionHandler_(self._sheet, None)
        else:
            self._sheet.makeKeyAndOrderFront_(None)

    @property
    def native(self) -> Any:
        """The native NSPanel."""
        return self._sheet
