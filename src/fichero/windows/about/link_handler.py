"""
Link Handler for WebView

Handles link clicks in the acknowledgments WebView.
"""

import webbrowser
import asyncio


class LinkHandler:
    """Handles link clicks in WebView components"""
    
    def __init__(self, webview):
        """Initialize with webview reference"""
        self.webview = webview
    
    def setup_link_monitoring(self):
        """Set up link click monitoring"""
        # JavaScript to intercept link clicks and store URL for Python to access
        js_code = """
        window.pendingUrl = null;
        document.addEventListener('click', function(e) {
            if (e.target.tagName === 'A') {
                e.preventDefault();
                // Store the URL so Python can access it
                window.pendingUrl = e.target.href;
                // Trigger a small change to notify Python
                document.title = 'LINK_CLICKED:' + Date.now();
            }
        });
        """
        try:
            self.webview.evaluate_javascript(js_code)
            # Start checking for link clicks
            self._start_link_monitoring()
        except Exception:
            pass  # Ignore if JavaScript evaluation fails
    
    def _start_link_monitoring(self):
        """Start monitoring for link clicks"""
        async def check_for_links():
            while True:
                try:
                    # Check if there's a pending URL to open
                    result = await self.webview.evaluate_javascript("window.pendingUrl")
                    if result and result != "null":
                        # Open the URL in browser
                        webbrowser.open(result)
                        # Clear the pending URL
                        await self.webview.evaluate_javascript("window.pendingUrl = null")
                except Exception:
                    pass
                # Wait a bit before checking again
                await asyncio.sleep(0.5)
        
        # Start the monitoring task
        try:
            asyncio.create_task(check_for_links())
        except Exception:
            pass 