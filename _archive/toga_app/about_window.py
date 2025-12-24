"""
About Window for Fichero application.

Displays app info, version, acknowledgments, and website link.
Uses native WKWebView for styled, scrollable HTML content with proper link handling.
"""

from __future__ import annotations

import logging
import re
import webbrowser
from typing import TYPE_CHECKING

import toga
from toga.style import Pack
from toga.constants import COLUMN, CENTER

from fichero.ui.i18n import _

if TYPE_CHECKING:
    from toga.app import App

logger = logging.getLogger(__name__)


# =============================================================================
# Native WKWebView with Link Handling
# =============================================================================

# Cache the delegate class (created once at module load)
_NavigationDelegate = None


def _get_navigation_delegate_class():
    """Get or create the WKNavigationDelegate class."""
    global _NavigationDelegate
    if _NavigationDelegate is not None:
        return _NavigationDelegate

    from rubicon.objc import ObjCClass, ObjCBlock, objc_method

    NSObject = ObjCClass('NSObject')

    # Policy constants
    WKNavigationActionPolicyCancel = 0
    WKNavigationActionPolicyAllow = 1

    class NavigationDelegate(NSObject):
        """WKNavigationDelegate that opens http/https links in system browser."""

        @objc_method
        def webView_decidePolicyForNavigationAction_decisionHandler_(
            self, webView, navigationAction, decisionHandler
        ) -> None:
            url = navigationAction.request.URL
            url_str = str(url) if url else ""

            if url_str.startswith(("http://", "https://")):
                webbrowser.open(url_str)
                ObjCBlock(decisionHandler, None, int)(WKNavigationActionPolicyCancel)
            else:
                ObjCBlock(decisionHandler, None, int)(WKNavigationActionPolicyAllow)

    _NavigationDelegate = NavigationDelegate
    return _NavigationDelegate


def _create_native_webview(html: str):
    """Create a native WKWebView that opens links in system browser.

    Returns (webview, delegate) - caller must keep delegate reference alive.
    """
    from rubicon.objc import ObjCClass
    from rubicon.objc.types import CGRect, CGPoint, CGSize

    WKWebView = ObjCClass('WKWebView')
    WKWebViewConfiguration = ObjCClass('WKWebViewConfiguration')
    NSURL = ObjCClass('NSURL')

    # Create webview with zero frame (will be constrained to container)
    config = WKWebViewConfiguration.alloc().init()
    rect = CGRect(CGPoint(0, 0), CGSize(0, 0))
    webview = WKWebView.alloc().initWithFrame_configuration_(rect, config)

    # Set delegate
    NavigationDelegate = _get_navigation_delegate_class()
    delegate = NavigationDelegate.alloc().init()
    webview.navigationDelegate = delegate

    # Load HTML
    base_url = NSURL.URLWithString_("about:blank")
    webview.loadHTMLString_baseURL_(html, base_url)

    return webview, delegate


# =============================================================================
# Constants
# =============================================================================

APP_NAME = "Fichero"
COPYRIGHT = "© 2025 Daniel Tubb"
WEBSITE_URL = "https://www.tubb.ca/fichero/"

WINDOW_SIZE = (306, 470)
ICON_PATH = "resources/icons/fichero.png"
ICON_SIZE = 96

FONT_TITLE = 10
FONT_BODY = 9
FONT_SMALL = 8

COLOR_MUTED = "#666666"
COLOR_LINK = "#007bff"


# =============================================================================
# HTML Template
# =============================================================================

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
* {{ margin: 0; padding: 0; }}
body {{
    font: {font_size}pt -apple-system, BlinkMacSystemFont, sans-serif;
    padding: 15px;
    text-align: center;
    line-height: 1.1;
}}
h2 {{ font-weight: bold; }}
a {{ color: {link_color}; text-decoration: none; }}
</style>
</head>
<body>{body}</body>
</html>
"""

# =============================================================================
# Markdown Converter
# =============================================================================

_RE_LINK = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
_RE_BOLD = re.compile(r'\*\*(.+?)\*\*')
_RE_ITALIC = re.compile(r'\*([^*\n]+?)\*')


def _md_to_html(text: str) -> str:
    """Convert simple markdown to HTML."""
    text = _RE_LINK.sub(r'<a href="\2">\1</a>', text)
    text = _RE_BOLD.sub(r'<strong>\1</strong>', text)
    text = _RE_ITALIC.sub(r'<em>\1</em>', text)

    lines = []
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            lines.append('<br>')
        elif line.startswith('## '):
            lines.append(f'<h2>{line[3:]}</h2>')
        else:
            lines.append(f'<p>{line}</p>')
    return '\n'.join(lines)


# =============================================================================
# AboutWindow
# =============================================================================

class AboutWindow:
    """About window with app info and acknowledgments."""

    __slots__ = ('app', 'window', '_webview_container', '_native_webview', '_delegate')

    def __init__(self, app: App) -> None:
        self.app = app
        self._native_webview = None
        self._delegate = None
        self._webview_container = None

        self.window = toga.Window(
            title=_("about_window_title"),
            size=WINDOW_SIZE,
            resizable=False,
            on_close=self._on_close
        )
        self.window.content = self._build_ui()
        self.app.windows.add(self.window)
        self._center()

    # -------------------------------------------------------------------------
    # Public
    # -------------------------------------------------------------------------

    def show(self) -> None:
        self.window.show()

    def hide(self) -> None:
        self.window.hide()

    def close(self) -> None:
        if self.window:
            self._cleanup()
            self.window.close()

    # -------------------------------------------------------------------------
    # UI
    # -------------------------------------------------------------------------

    def _build_ui(self) -> toga.Box:
        box = toga.Box(style=Pack(direction=COLUMN, flex=1))

        # Icon
        try:
            icon = toga.ImageView(
                toga.Image(ICON_PATH),
                style=Pack(width=ICON_SIZE, height=ICON_SIZE, margin=(10, 0, 20, 0))
            )
        except (FileNotFoundError, OSError):
            icon = toga.Label("📁", style=Pack(font_size=48, text_align=CENTER))

        # Header
        header = toga.Box(style=Pack(direction=COLUMN, align_items=CENTER, margin=(10, 0, 20, 0)))
        header.add(icon)
        header.add(toga.Label(APP_NAME, style=Pack(
            font_size=FONT_TITLE, font_weight='bold', text_align=CENTER, margin=(0, 0, 5, 0)
        )))
        header.add(toga.Label(f"version {self._version}", style=Pack(
            font_size=FONT_BODY, text_align=CENTER, margin=(0, 0, 5, 0)
        )))
        header.add(toga.Label(COPYRIGHT, style=Pack(
            font_size=FONT_BODY, text_align=CENTER, color=COLOR_MUTED
        )))
        box.add(header)

        # Container for native webview
        self._webview_container = toga.Box(style=Pack(flex=1))
        box.add(self._webview_container)

        # Defer native webview attachment until layout ready
        self.app.loop.call_soon(self._attach_native_webview)

        # Footer link
        footer = toga.Button(
            WEBSITE_URL,
            style=Pack(font_size=FONT_SMALL, color=COLOR_LINK, margin=4),
            on_press=lambda w: webbrowser.open(WEBSITE_URL)
        )
        box.add(footer)

        return box

    def _attach_native_webview(self) -> None:
        """Attach native WKWebView to the container."""
        try:
            html = HTML_TEMPLATE.format(
                font_size=FONT_SMALL,
                link_color=COLOR_LINK,
                body=_md_to_html(_("about_acknowledgments"))
            )
            self._native_webview, self._delegate = _create_native_webview(html)

            native_container = self._webview_container._impl.native
            self._native_webview.setTranslatesAutoresizingMaskIntoConstraints_(False)
            native_container.addSubview_(self._native_webview)

            # Pin webview to container edges
            from rubicon.objc import ObjCClass
            NSLayoutConstraint = ObjCClass('NSLayoutConstraint')
            NSLayoutConstraint.activateConstraints_([
                self._native_webview.topAnchor.constraintEqualToAnchor_(native_container.topAnchor),
                self._native_webview.bottomAnchor.constraintEqualToAnchor_(native_container.bottomAnchor),
                self._native_webview.leadingAnchor.constraintEqualToAnchor_(native_container.leadingAnchor),
                self._native_webview.trailingAnchor.constraintEqualToAnchor_(native_container.trailingAnchor),
            ])
        except Exception as e:
            logger.warning(f"Could not attach native webview: {e}")

    def _cleanup(self) -> None:
        """Release native resources."""
        if self._native_webview:
            self._native_webview.removeFromSuperview()
            self._native_webview = None
        self._delegate = None

    # -------------------------------------------------------------------------
    # Events
    # -------------------------------------------------------------------------

    def _on_close(self, widget: toga.Window) -> bool:
        """Handle window close."""
        self._cleanup()
        self._save_state()
        return True

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @property
    def _version(self) -> str:
        if hasattr(self.app, 'version'):
            return self.app.version
        try:
            from fichero import __version__
            return __version__
        except ImportError:
            return "0.0.1"

    def _center(self) -> None:
        try:
            screen = self.app.screens[0]
            w, h = WINDOW_SIZE
            self.window.position = ((screen.size.width - w) // 2, (screen.size.height - h) // 2)
        except (IndexError, AttributeError):
            pass

    def _save_state(self) -> None:
        tracker = getattr(self.app, 'window_state_tracker', None)
        if tracker:
            tracker.save_window_state("about")
