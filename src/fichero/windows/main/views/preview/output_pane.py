"""
OutputPane - Reusable output display component

PHASE 4: Single reusable pane for displaying step outputs.
Uses Phase 2 renderer system for content generation.
Supports zoom, rotation, and can be embedded anywhere.
"""

import logging
from typing import Optional, Dict, Any
from pathlib import Path
import uuid

import toga
from toga.style import Pack
from fichero.shared.bars.path_bar import PathBar

logger = logging.getLogger(__name__)

# Module-level ScriptMessageHandler class (defined once for all panes)
# This avoids class redefinition issues when creating multiple panes
_ScriptMessageHandler = None
_CropEditHandler = None

try:
    from rubicon.objc import objc_method, NSObject
    from rubicon.objc.runtime import objc_id

    class ScriptMessageHandler(NSObject):
        """Handler for JavaScript-to-Python messages via WKWebView"""
        pane = None

        @objc_method
        def userContentController_didReceiveScriptMessage_(
            self, controller: objc_id, message: objc_id
        ) -> None:
            """Handle script message from JavaScript"""
            try:
                if self.pane and self.pane.on_click:
                    # Parse message body (now contains JSON with modifier keys)
                    import json
                    message_body = str(message.body)

                    # Try to parse as JSON (new format with modifiers)
                    try:
                        click_data = json.loads(message_body)
                        meta_key = click_data.get('metaKey', False)
                        ctrl_key = click_data.get('ctrlKey', False)
                        shift_key = click_data.get('shiftKey', False)
                        alt_key = click_data.get('altKey', False)

                        # Pass modifier keys to callback
                        self.pane.on_click(
                            self.pane,
                            meta_key=meta_key,
                            ctrl_key=ctrl_key,
                            shift_key=shift_key,
                            alt_key=alt_key
                        )
                        self.pane.logger.info(
                            f"✅ Click detected on pane {self.pane._pane_id} "
                            f"(Cmd={meta_key}, Ctrl={ctrl_key}, Shift={shift_key}, Alt={alt_key})"
                        )
                    except (json.JSONDecodeError, ValueError):
                        # Fallback: old format (just 'clicked' string)
                        self.pane.on_click(self.pane)
                        self.pane.logger.info(f"✅ Click detected on pane {self.pane._pane_id}")
            except Exception as e:
                if self.pane:
                    self.pane.logger.error(f"Error handling script message: {e}")

    class CropEditHandler(NSObject):
        """Handler for crop edit messages from JavaScript"""
        pane = None

        @objc_method
        def userContentController_didReceiveScriptMessage_(
            self, controller: objc_id, message: objc_id
        ) -> None:
            """Handle crop edit message from JavaScript"""
            try:
                if self.pane:
                    self.pane._handle_crop_edit_message(str(message.body))
            except Exception as e:
                if self.pane:
                    self.pane.logger.error(f"Error in crop edit handler: {e}")

    _ScriptMessageHandler = ScriptMessageHandler
    _CropEditHandler = CropEditHandler
except ImportError:
    # Rubicon not available (non-macOS platform)
    pass


class OutputPane:
    """
    Reusable output display pane (PHASE 4).

    Uses renderer system to display any step's output.
    Supports zoom, rotation, and scrolling.
    Can be embedded anywhere (OutputView, detached window, etc.)

    Example:
        pane = OutputPane(library_manager, renderer_registry)
        await pane.set_step("item-123", step_index=2)

        # Zoom controls
        pane.zoom_in()
        pane.zoom_fit()

        # Get container for embedding
        container.add(pane.as_box())
    """

    def __init__(self, library_manager, renderer_registry=None, on_click=None):
        """
        Initialize output pane.

        Args:
            library_manager: LibraryManager instance for data access
            renderer_registry: RendererRegistry instance for rendering (optional, will create if None)
            on_click: Optional callback when pane is clicked (for focus handling - PHASE 5)
        """
        self.library_manager = library_manager

        # Initialize renderer registry
        if renderer_registry is None:
            from fichero.library.renderers.renderer_registry import RendererRegistry
            self.renderer_registry = RendererRegistry()
        else:
            self.renderer_registry = renderer_registry

        self.logger = logging.getLogger(__name__)

        # Unique pane ID for message handler registration
        self._pane_id = str(uuid.uuid4())[:8]  # Short unique ID
        self.logger.info(f"🆔 Creating OutputPane with ID: {self._pane_id}")

        # Current state - FEATURE 1: Enhanced context tracking
        self.current_item_id: Optional[str] = None
        self.current_step_index: Optional[int] = None
        self.current_library_id: Optional[str] = None
        self.current_collection_id: Optional[str] = None

        # Viewer state
        self.scale: float = 1.0
        self.rotation: int = 0  # 0, 90, 180, 270
        self.scroll_x: int = 0
        self.scroll_y: int = 0

        # Click callback for focus handling (PHASE 5)
        self.on_click = on_click

        # Message handler tracking
        self._script_handler = None
        self._handler_name = None
        self._handler_registered = False

        # UI components
        self._outer_box = None  # Outer wrapper for focus border (PHASE 5)
        self._container = None  # Inner container for content
        self._webview = None
        self._error_label = None
        self._loading_label = None
        self._path_bar = None
        self._path_bar_visible = True  # Path bar visible by default

        self._build_ui()

    def _build_ui(self):
        """Build UI components - PHASE 5 with outer wrapper for focus"""
        # Inner container for actual content
        # flex=1 allows horizontal expansion but content (WebView) handles vertical
        self._container = toga.Box(
            style=Pack(direction='column', flex=1)
        )

        # Loading state
        self._loading_label = toga.Label(
            "Loading...",
            style=Pack(
                text_align='center',
                margin=20,
                font_size=14
            )
        )

        # Error state
        self._error_label = toga.Label(
            "",
            style=Pack(
                text_align='center',
                margin=20,
                color='#CC0000',
                font_size=12
            )
        )

        # WebView for HTML rendering
        self._webview = toga.WebView(
            style=Pack(flex=1),
            on_webview_load=self._handle_webview_interaction  # Detect webview interaction as focus trigger
        )

        # PathBar for showing file path
        self._path_bar = PathBar(platform='desktop')

        # Outer wrapper box - this is where focus border is applied
        self._outer_box = toga.Box(
            style=Pack(direction='column', flex=1)
        )

        self._outer_box.add(self._container)

        # Click detection will be set up after first content load (in _handle_webview_interaction)
        # to ensure WebView native implementation is ready

        # Start with blank pane - content will be loaded immediately if cloned from another pane
        # Show blank HTML page so the pane is clickable for focus
        self._show_blank()

    def _setup_click_detection(self):
        """
        Setup click detection using WKWebView's JavaScript message handler.

        Called when content is first loaded to ensure WebView is ready.
        Uses unique handler name per pane to avoid conflicts.
        """
        # Skip if already registered or no handler class available
        if self._handler_registered or _ScriptMessageHandler is None:
            if self._handler_registered:
                self.logger.debug(f"Pane {self._pane_id}: Handler already registered, skipping")
            return

        try:
            # Create handler instance using module-level class
            self._script_handler = _ScriptMessageHandler.alloc().init()
            self._script_handler.pane = self

            # Get the native WKWebView
            if not hasattr(self._webview, '_impl') or not hasattr(self._webview._impl, 'native'):
                self.logger.warning(f"Pane {self._pane_id}: WebView native implementation not ready")
                return

            native_webview = self._webview._impl.native

            # Get the WKUserContentController
            user_content_controller = native_webview.configuration.userContentController

            # Use unique handler name for this pane to avoid conflicts
            # Each pane gets its own handler name like "paneClick_a1b2c3d4"
            self._handler_name = f'paneClick_{self._pane_id}'

            # Add script message handler
            # JavaScript will call: window.webkit.messageHandlers.paneClick_XXXX.postMessage('clicked')
            user_content_controller.addScriptMessageHandler(
                self._script_handler,
                name=self._handler_name
            )

            self._handler_registered = True
            self.logger.info(f"✅ Pane {self._pane_id}: JavaScript message handler '{self._handler_name}' registered")

            # Also register crop edit handler for interactive crop editing
            self._setup_crop_edit_handler(user_content_controller)

        except Exception as e:
            self.logger.error(f"❌ Pane {self._pane_id}: Could not setup JavaScript message handler: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            # Fall back to webview load detection only
            pass

    def _inject_click_handler(self, html: str) -> str:
        """
        Inject JavaScript click handler into HTML to enable click-to-focus.

        The injected JavaScript uses this pane's unique message handler name.
        Must be called BEFORE setting HTML content.

        Args:
            html: Original HTML content

        Returns:
            HTML with injected click handler using pane-specific handler name
        """
        # Ensure handler is set up (will be registered when WebView loads)
        # We'll call this again after content loads to ensure it's registered
        if not self._handler_name:
            self._handler_name = f'paneClick_{self._pane_id}'

        # JavaScript that detects clicks and signals back to Python via WKWebView message handler
        # Uses this pane's unique handler name
        # Now includes modifier key detection for Cmd+Click to open in new pane
        click_handler_script = f"""
        <script>
        (function() {{
            var handlerName = '{self._handler_name}';
            console.log('Setting up click handler for pane:', handlerName);

            // Add click handler to entire document
            document.addEventListener('click', function(e) {{
                // Signal to Python via WKWebView message handler
                // This is the standard way to communicate from JavaScript to native code
                try {{
                    if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers[handlerName]) {{
                        // Send click event with modifier key info
                        var clickData = {{
                            clicked: true,
                            metaKey: e.metaKey,      // Cmd key on Mac
                            ctrlKey: e.ctrlKey,      // Ctrl key on Windows/Linux
                            shiftKey: e.shiftKey,    // Shift key
                            altKey: e.altKey         // Alt/Option key
                        }};
                        window.webkit.messageHandlers[handlerName].postMessage(JSON.stringify(clickData));
                        console.log('Click message sent to ' + handlerName + ' with modifiers:', clickData);
                    }} else {{
                        console.log('Handler ' + handlerName + ' not available yet');
                    }}
                }} catch (err) {{
                    console.log('Click handler error:', err);
                }}
            }}, true);  // Use capture phase to catch all clicks

            console.log('Click handler registered for ' + handlerName);
        }})();
        </script>
        """

        # Inject before closing </body> tag if it exists, otherwise before </html>
        if '</body>' in html:
            html = html.replace('</body>', f'{click_handler_script}</body>')
        elif '</html>' in html:
            html = html.replace('</html>', f'{click_handler_script}</html>')
        else:
            # No body or html tags, just append
            html += click_handler_script

        return html

    def _handle_webview_interaction(self, widget):
        """
        Handle WebView interaction - when user clicks/scrolls in WebView, focus this pane.

        This callback fires when:
        1. Page initially loads -> Set up click handler
        2. JavaScript sends message -> Focus the pane
        """
        # Set up click detection on first load (when WebView native is ready)
        if not self._handler_registered:
            self.logger.debug(f"Pane {self._pane_id}: WebView loaded, setting up click detection")
            self._setup_click_detection()

        # Also trigger focus on page load (fallback for when click handler isn't working)
        if self.on_click:
            self.on_click(self)
            self.logger.debug(f"Pane {self._pane_id}: Interaction detected, focus callback triggered")

    def _setup_crop_edit_handler(self, user_content_controller):
        """
        Set up message handler for crop edit events from JavaScript.

        Args:
            user_content_controller: WKUserContentController to register handler with
        """
        # Skip if no handler class available (non-macOS)
        if _CropEditHandler is None:
            self.logger.debug(f"Pane {self._pane_id}: CropEditHandler not available (non-macOS platform)")
            return

        try:
            # Create handler instance using module-level class
            self._crop_handler = _CropEditHandler.alloc().init()
            self._crop_handler.pane = self

            user_content_controller.addScriptMessageHandler(
                self._crop_handler,
                name='cropEdit'
            )

            self.logger.info(f"✅ Pane {self._pane_id}: Crop edit handler registered")

        except Exception as e:
            self.logger.error(f"Could not setup crop edit handler: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

    def _handle_crop_edit_message(self, message_body: str):
        """
        Handle crop edit message from JavaScript.

        Args:
            message_body: JSON string with crop data
        """
        try:
            import json
            crop_data = json.loads(message_body)

            self.logger.info(f"📐 Received crop edit: {crop_data}")

            # Validate required fields
            if 'action' not in crop_data or crop_data['action'] != 'apply_crop':
                self.logger.warning(f"Unknown crop action: {crop_data.get('action')}")
                return

            if 'box' not in crop_data:
                self.logger.error("Crop data missing 'box' field")
                return

            # Get item and step context
            item_id = crop_data.get('item_id')
            step_index = crop_data.get('step_index')

            if not item_id or step_index is None:
                self.logger.error("Crop data missing item_id or step_index")
                return

            # Apply the crop via renderer
            import asyncio
            asyncio.create_task(self._apply_crop_edit(item_id, step_index, crop_data['box']))

        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid crop message JSON: {e}")
        except Exception as e:
            self.logger.error(f"Error handling crop edit: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

    async def _apply_crop_edit(self, item_id: str, step_index: int, box: dict):
        """
        Apply crop edit by calling renderer's apply_json_edits.

        Args:
            item_id: Library item ID
            step_index: Step index for the crop
            box: Crop box coordinates {x1, y1, x2, y2}
        """
        try:
            self.logger.info(f"Applying crop edit for item {item_id}, step {step_index}")

            # Get item output data to find the step
            output_data = await self.library_manager.get_item_output_data(item_id)

            if not output_data or not output_data.get('processing_steps'):
                self.logger.error(f"No processing steps found for item {item_id}")
                return

            processing_steps = output_data.get('processing_steps', [])
            processing_step_index = step_index - 1  # Adjust for 0-indexed array

            if processing_step_index < 0 or processing_step_index >= len(processing_steps):
                self.logger.error(f"Step index {step_index} out of range")
                return

            # Get the specific processing step
            processing_step = processing_steps[processing_step_index]

            # Get renderer for this step
            from fichero.library.renderers.renderer_registry import RendererRegistry
            renderer = RendererRegistry.get_renderer_for_step(
                tool_name=processing_step.tool_name,
                file_type=processing_step.file_type,
                file_path=processing_step.file_path
            )

            if not renderer:
                self.logger.error(f"No renderer found for tool: {processing_step.tool_name}")
                return

            # Create render context
            from fichero.library.renderers.base_renderer import RenderContext
            context = RenderContext(
                item_id=item_id,
                step_index=step_index,
                step_name=processing_step.step_name,
                tool_name=processing_step.tool_name,
                file_path=processing_step.file_path,
                file_type=processing_step.file_type,
                manifest_entry=processing_step.manifest_entry,
                show_metadata=True,
                show_content=True,
                interactive=True
            )

            # Prepare JSON data for renderer (must match crop tool format)
            json_data = {
                'details': {
                    'box': box  # {x1, y1, x2, y2}
                },
                'source': processing_step.manifest_entry.get('source', '') if processing_step.manifest_entry else ''
            }

            # Apply the edit (await if renderer has async method)
            if hasattr(renderer.apply_json_edits, '__call__'):
                import inspect
                if inspect.iscoroutinefunction(renderer.apply_json_edits):
                    # Pass library_manager in context
                    context.library_manager = self.library_manager
                    success, error = await renderer.apply_json_edits(context, json_data)
                else:
                    success, error = renderer.apply_json_edits(context, json_data)
            else:
                success, error = False, "Renderer does not support apply_json_edits"

            if success:
                self.logger.info(f"✅ Crop applied successfully")
                # Reload the step to show updated crop
                await self.set_step(item_id, step_index)
            else:
                self.logger.error(f"❌ Failed to apply crop: {error}")
                # TODO: Show error to user in UI

        except Exception as e:
            self.logger.error(f"Error applying crop edit: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

    async def set_step(self, item_id: str, step_index: int, step=None):
        """
        Load and display a step's output.

        Uses renderer system to generate appropriate display.

        Args:
            item_id: Library item ID
            step_index: Index of step to display (-1 when using tree view with step object)
            step: Optional Step object (if not provided, will query library)
        """
        self.logger.info(f"🔵 OutputPane.set_step() called on pane {id(self)}: item_id={item_id}, step_index={step_index}, step={step.step_name if step else None}")
        self.current_item_id = item_id
        self.current_step_index = step_index

        # FEATURE 1: Update context with library and collection IDs
        try:
            item = await self.library_manager.get_item(item_id)
            if item:
                self.current_collection_id = item.collection_id
                # Get collection to find library_id
                collection = await self.library_manager.get_collection(item.collection_id)
                if collection:
                    self.current_library_id = getattr(collection, 'library_id', None)
        except Exception as e:
            self.logger.warning(f"Could not update full context: {e}")

        try:
            self._show_loading()

            # NEW: If step_index is -1 and step object is provided, render it directly
            # This is used by the tree view which provides the step object directly
            if step_index == -1 and step is not None:
                self.logger.info(f"🌳 Rendering step from tree view: {step.step_name}")

                # Render the provided step object
                if step.tool_name == 'original' or step.step_name == 'original':
                    # Original file
                    html_content = self._render_original_file(step)

                    # Update path bar
                    if self._path_bar:
                        await self._update_path_bar(item_id)
                else:
                    # Processing step - need to construct minimal output_data
                    # The renderer needs some context but we can provide a minimal version
                    output_data = {
                        'processing_steps': [],  # Not used when rendering single step
                        'item_id': item_id
                    }
                    html_content = self._render_step_with_renderer(step, output_data)

                    # Update path bar
                    if self._path_bar:
                        await self._update_path_bar(item_id, step)

                # Inject click handler and display
                html_content = self._inject_click_handler(html_content)
                self._webview.set_content("", html_content)
                self._show_content()
                return

            # If step 0 (original file), handle specially
            if step_index == 0:
                # If step not provided or not original, try to fetch it from library
                if not step or not hasattr(step, 'tool_name') or step.tool_name != 'original':
                    self.logger.debug(f"Step 0 requested but step not provided or not original, fetching from library")
                    # Get item data to access original file
                    item = await self.library_manager.get_item(item_id)
                    if not item:
                        self._show_error("Item not found")
                        return

                    # For step 0, use the item's source file as the original
                    # Create a minimal step object for rendering
                    class OriginalStep:
                        def __init__(self, file_path):
                            self.file_path = file_path
                            self.tool_name = 'original'

                            # Detect file_type from extension
                            # Path().suffix works on both Path objects and URL strings
                            from pathlib import Path
                            ext = Path(str(file_path)).suffix.lower()
                            self.file_type = 'image' if ext in ['.tif', '.tiff', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'] else 'unknown'

                    # CollectionItem has local_path (downloaded) or source_path (external)
                    file_path = item.local_path or item.source_path
                    step = OriginalStep(file_path)
                    self.logger.info(f"🔧 Created OriginalStep: file_path={step.file_path}, file_type={step.file_type}")

                # Display original file directly
                self.logger.info(f"🎬 About to call _render_original_file")
                html_content = self._render_original_file(step)
                self.logger.info(f"✅ Got HTML content, length={len(html_content)}")

                # Update path bar with library path (not filesystem path)
                if self._path_bar:
                    await self._update_path_bar(item_id)

                # Inject click handler for focus management
                html_content = self._inject_click_handler(html_content)

                # Use empty root URL with base64 data (matches old working implementation)
                self._webview.set_content("", html_content)
                self._show_content()
                return

            # For processed steps, get data from library
            output_data = await self.library_manager.get_item_output_data(item_id)

            if not output_data or not output_data.get('processing_steps'):
                # No processing outputs - this shouldn't happen if step_index > 0
                if step_index > 0:
                    self._show_error("No processing steps found")
                    return
                # If step_index is 0 but we don't have original step info, show error
                self._show_error("No step data available")
                return

            processing_steps = output_data.get('processing_steps', [])

            self.logger.debug(f"Total processing steps: {len(processing_steps)}, step_index: {step_index}")

            # Adjust index for processing steps (step 0 is original, so processing steps start at 1)
            processing_step_index = step_index - 1

            self.logger.debug(f"Accessing processing_step_index: {processing_step_index}")

            if processing_step_index < 0 or processing_step_index >= len(processing_steps):
                self.logger.error(f"Step index {step_index} out of range: processing_step_index={processing_step_index}, len(processing_steps)={len(processing_steps)}")
                self._show_error(f"Step index {step_index} out of range (have {len(processing_steps)} processing steps)")
                return

            # Get the specific processing step
            processing_step = processing_steps[processing_step_index]
            self.logger.info(f"📍 OutputPane: Rendering step {step_index}")
            self.logger.info(f"📍   Step name: {processing_step.step_name}")
            self.logger.info(f"📍   Tool name: {processing_step.tool_name}")
            self.logger.info(f"📍   File path: {processing_step.file_path}")
            self.logger.info(f"📍   File type: {processing_step.file_type}")

            # Update path bar with library path (not filesystem path)
            if self._path_bar:
                await self._update_path_bar(item_id, processing_step)

            # Use renderer system to generate HTML
            html_content = self._render_step_with_renderer(processing_step, output_data)

            self.logger.debug(f"HTML content length: {len(html_content)} bytes")

            # Inject click handler for focus management
            html_content = self._inject_click_handler(html_content)

            # Display in WebView with empty root URL (using base64 data)
            self._webview.set_content("", html_content)

            self._show_content()

        except Exception as e:
            self.logger.error(f"Error rendering step: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            self._show_error(str(e))

    async def set_content(self, file_path, file_type: str, context: Dict[str, Any]):
        """
        High-level method to set pane content from file_path and context.

        This bridges the PreviewView API (file_path, file_type, context)
        to the OutputPane rendering system.

        Args:
            file_path: Path to file (Path object or URL string)
            file_type: Type of file ('image', 'json', etc.)
            context: Dict with metadata like {'step_name': '...', 'tool_name': '...'}
        """
        self.logger.info(f"🔵 OutputPane.set_content() called: file_path={file_path}, file_type={file_type}")

        try:
            self._show_loading()

            # Extract context info
            step_name = context.get('step_name', 'Unknown')
            tool_name = context.get('tool_name', 'unknown')

            # Create a minimal step object for rendering
            class MinimalStep:
                def __init__(self, file_path, file_type, step_name, tool_name):
                    self.file_path = file_path
                    self.file_type = file_type
                    self.step_name = step_name
                    self.tool_name = tool_name
                    self.manifest_entry = None

            step = MinimalStep(file_path, file_type, step_name, tool_name)

            # Render based on tool type
            if tool_name in ['original', 'source']:
                # Original file
                html_content = self._render_original_file(step)
            else:
                # Processed step - create minimal output_data
                output_data = {
                    'processing_steps': [],  # Not used for direct rendering
                    'item_id': self.current_item_id
                }
                html_content = self._render_step_with_renderer(step, output_data)

            # Inject click handler and display
            html_content = self._inject_click_handler(html_content)
            self._webview.set_content("", html_content)
            self._show_content()

            self.logger.info(f"✅ Content rendered successfully: {step_name}")

        except Exception as e:
            self.logger.error(f"Error in set_content: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            self._show_error(f"Failed to load content: {str(e)}")

    async def load_item(self, item_id: str, step_index: int = 0):
        """
        Load an item's specific step in this pane.

        This is a convenience wrapper for LayoutManager compatibility.
        Delegates to set_step() internally.

        Args:
            item_id: Library item ID
            step_index: Step index to display (default: 0 for original)
        """
        self.logger.info(f"🔵 OutputPane.load_item() called: item_id={item_id}, step_index={step_index}")
        await self.set_step(item_id, step_index)

    def _render_step_with_renderer(self, step, output_data: Dict[str, Any]) -> str:
        """
        Render step to HTML using the renderer system.

        Uses RendererRegistry to get appropriate renderer for the step,
        then calls renderer.render_html() to generate HTML.

        Args:
            step: Step object
            output_data: Full output data from library

        Returns:
            HTML string
        """
        from fichero.library.renderers.base_renderer import RenderContext
        from fichero.library.renderers.renderer_registry import RendererRegistry

        # Extract step info
        step_name = step.step_name if hasattr(step, 'step_name') else 'Unknown'
        tool_name = step.tool_name if hasattr(step, 'tool_name') else step_name
        file_path = Path(step.file_path) if hasattr(step, 'file_path') and step.file_path else None
        file_type = step.file_type if hasattr(step, 'file_type') else 'unknown'
        manifest_entry = step.manifest_entry if hasattr(step, 'manifest_entry') else None

        # Create render context
        context = RenderContext(
            item_id=self.current_item_id,
            step_index=self.current_step_index,
            step_name=step_name,
            tool_name=tool_name,
            file_path=file_path if file_path else Path('/'),
            file_type=file_type,
            manifest_entry=manifest_entry,
            show_metadata=True,
            show_content=True,
            interactive=True  # GUI rendering with interactive controls
        )

        # Get renderer for this step
        # Try tool-specific renderer first, fall back to file type renderer
        self.logger.info(f"🎨 OutputPane: Requesting renderer for:")
        self.logger.info(f"🎨   tool_name: {tool_name}")
        self.logger.info(f"🎨   file_type: {file_type}")
        self.logger.info(f"🎨   file_path: {file_path}")

        renderer = RendererRegistry.get_renderer_for_step(
            tool_name=tool_name,
            file_type=file_type,
            file_path=file_path
        )

        self.logger.info(f"✅ Using renderer: {renderer.__class__.__name__} for tool '{tool_name}'")

        # Render HTML
        try:
            output = renderer.render_html(context)

            if output.is_error:
                self.logger.error(f"Renderer error: {output.error}")
                return self._render_error_html(output.error)

            if not output.html:
                self.logger.warning("Renderer returned empty HTML")
                return self._render_error_html("Renderer produced no output")

            return output.html

        except Exception as e:
            self.logger.error(f"Error in renderer: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return self._render_error_html(f"Rendering error: {str(e)}")

    def _render_error_html(self, error_message: str) -> str:
        """
        Render error message as HTML.

        Args:
            error_message: Error message to display

        Returns:
            HTML string
        """
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Error</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    padding: 40px;
                    background: #f5f5f5;
                }}
                .error {{
                    background: #fff;
                    border-left: 4px solid #e74c3c;
                    padding: 20px;
                    border-radius: 4px;
                    color: #c0392b;
                }}
                h2 {{
                    margin-top: 0;
                    color: #c0392b;
                }}
            </style>
        </head>
        <body>
            <div class="error">
                <h2>Rendering Error</h2>
                <p>{error_message}</p>
            </div>
        </body>
        </html>
        """

    def as_box(self) -> toga.Box:
        """Get container for embedding - PHASE 5 returns outer wrapper"""
        return self._outer_box

    # ==================== ZOOM METHODS ====================

    def zoom_in(self):
        """Zoom in by calling JavaScript function"""
        try:
            self._webview.evaluate_javascript("zoomIn();")
            self.logger.debug("Zoom: in")
        except Exception as e:
            self.logger.error(f"Error zooming in: {e}")

    def zoom_out(self):
        """Zoom out by calling JavaScript function"""
        try:
            self._webview.evaluate_javascript("zoomOut();")
            self.logger.debug("Zoom: out")
        except Exception as e:
            self.logger.error(f"Error zooming out: {e}")

    def zoom_fit(self):
        """Fit to window by calling JavaScript function"""
        try:
            self._webview.evaluate_javascript("fitToWindow();")
            self.logger.debug("Zoom: fit to window")
        except Exception as e:
            self.logger.error(f"Error fitting to window: {e}")

    def zoom_100(self):
        """Reset to 100% (actual size) by calling JavaScript function"""
        try:
            self._webview.evaluate_javascript("actualSize();")
            self.logger.debug("Zoom: 100%")
        except Exception as e:
            self.logger.error(f"Error setting actual size: {e}")

    def zoom_fit_width(self):
        """Fit to window width by calling JavaScript function"""
        try:
            self._webview.evaluate_javascript("fitToWidth();")
            self.logger.debug("Zoom: fit to width")
        except Exception as e:
            self.logger.error(f"Error fitting to width: {e}")

    def zoom_fit_height(self):
        """Fit to window height by calling JavaScript function"""
        try:
            self._webview.evaluate_javascript("fitToHeight();")
            self.logger.debug("Zoom: fit to height")
        except Exception as e:
            self.logger.error(f"Error fitting to height: {e}")

    # ==================== ROTATION METHODS ====================

    def rotate_left(self):
        """Rotate 90° counter-clockwise by calling JavaScript function"""
        try:
            self._webview.evaluate_javascript("rotateLeft();")
            self.logger.debug("Rotate: left (counter-clockwise)")
        except Exception as e:
            self.logger.error(f"Error rotating left: {e}")

    def rotate_right(self):
        """Rotate 90° clockwise by calling JavaScript function"""
        try:
            self._webview.evaluate_javascript("rotateRight();")
            self.logger.debug("Rotate: right (clockwise)")
        except Exception as e:
            self.logger.error(f"Error rotating right: {e}")

    def reset_rotation(self):
        """Reset rotation to 0° by calling JavaScript function"""
        try:
            self._webview.evaluate_javascript("rotation = 0; updateTransform();")
            self.logger.debug("Rotate: reset to 0°")
        except Exception as e:
            self.logger.error(f"Error resetting rotation: {e}")

    def activate_crop(self):
        """Activate crop tool by calling JavaScript function"""
        try:
            if not self._webview:
                self.logger.warning("Cannot activate crop: WebView not initialized")
                return

            # Check if there's content loaded
            if not hasattr(self, '_current_url') or not self._current_url:
                self.logger.warning("Cannot activate crop: No content loaded in WebView")
                return

            # Call JavaScript to activate crop tool
            self._webview.evaluate_javascript("activateTool('crop');")
            self.logger.info("✅ Crop tool activated via JavaScript")
        except Exception as e:
            self.logger.error(f"Error activating crop: {e}", exc_info=True)

    def flip_horizontal(self):
        """Flip image horizontally by calling JavaScript function"""
        try:
            self._webview.evaluate_javascript("flipImage('horizontal');")
            self.logger.info("✅ Flipped horizontally")
        except Exception as e:
            self.logger.error(f"Error flipping horizontally: {e}")

    def flip_vertical(self):
        """Flip image vertically by calling JavaScript function"""
        try:
            self._webview.evaluate_javascript("flipImage('vertical');")
            self.logger.info("✅ Flipped vertically")
        except Exception as e:
            self.logger.error(f"Error flipping vertically: {e}")

    def activate_straighten(self):
        """Activate straighten tool (fine rotation adjustment)"""
        try:
            if not self._webview:
                self.logger.warning("Cannot activate straighten: WebView not initialized")
                return

            # Check if there's content loaded
            if not hasattr(self, '_current_url') or not self._current_url:
                self.logger.warning("Cannot activate straighten: No content loaded in WebView")
                return

            # Call JavaScript to activate straighten tool
            self._webview.evaluate_javascript("activateTool('straighten');")
            self.logger.info("✅ Straighten tool activated via JavaScript")
        except Exception as e:
            self.logger.error(f"Error activating straighten: {e}", exc_info=True)

    # ==================== STATE MANAGEMENT ====================

    def get_viewer_state(self) -> Dict[str, Any]:
        """Get current viewer state for syncing"""
        return {
            'scale': self.scale,
            'rotation': self.rotation,
            'scroll_x': self.scroll_x,
            'scroll_y': self.scroll_y
        }

    def set_viewer_state(self, state: Dict[str, Any]):
        """Set viewer state (for syncing across panes)"""
        self.scale = state.get('scale', 1.0)
        self.rotation = state.get('rotation', 0)
        self.scroll_x = state.get('scroll_x', 0)
        self.scroll_y = state.get('scroll_y', 0)
        self._apply_viewer_state()

    def _apply_viewer_state(self):
        """Apply current zoom/rotation/scroll to WebView"""
        try:
            # Execute JavaScript to apply transform
            js = f"""
            if (document.body) {{
                document.body.style.transform =
                    'scale({self.scale}) rotate({self.rotation}deg)';
                window.scrollTo({self.scroll_x}, {self.scroll_y});
            }}
            """
            self._webview.evaluate_javascript(js)
        except Exception as e:
            self.logger.error(f"Error applying viewer state: {e}")

    # ==================== DISPLAY STATE METHODS ====================

    def _render_original_file(self, step) -> str:
        """
        Render the original file as HTML with interactive controls.

        Uses the full interactive viewer from html_templates module.

        Args:
            step: Step object for the original file

        Returns:
            HTML string
        """
        file_path = step.file_path
        file_type = step.file_type
        self.logger.info(f"🎨 _render_original_file: file_path={file_path}, file_type={file_type}")

        # Use interactive viewer for images
        if file_type == 'image':
            from fichero.library.renderers.html_templates import get_interactive_image_viewer

            # Get appropriate title based on whether file_path is a URL or Path
            if isinstance(file_path, str) and file_path.startswith(('http://', 'https://')):
                # URL - extract filename from URL
                title = f"Original: {file_path.split('/')[-1]}"
                self.logger.info(f"📸 Rendering URL image: {file_path}")
            else:
                # Convert to Path object if it's a string
                if isinstance(file_path, str):
                    file_path = Path(file_path)
                # Path object - use .name attribute
                title = f"Original: {file_path.name}"

            return get_interactive_image_viewer(
                image_path=file_path,
                title=title,
                use_base64=True  # Use base64 for security (ignored for URLs)
            )
        else:
            # For non-image files, show basic info
            # Get appropriate filename based on whether file_path is a URL or Path
            if isinstance(file_path, str) and file_path.startswith(('http://', 'https://')):
                # URL - extract filename from URL
                filename = file_path.split('/')[-1]
            else:
                # Path object - use .name attribute
                filename = file_path.name

            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Original File</title>
                <style>
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        padding: 40px;
                        background: #f5f5f5;
                    }}
                    .card {{
                        background: white;
                        padding: 30px;
                        border-radius: 8px;
                        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                    }}
                    h1 {{
                        margin-top: 0;
                        color: #333;
                    }}
                    .info {{
                        color: #666;
                        margin: 10px 0;
                    }}
                </style>
            </head>
            <body>
                <div class="card">
                    <h1>Original File</h1>
                    <div class="info"><strong>File:</strong> {filename}</div>
                    <div class="info"><strong>Type:</strong> {file_type}</div>
                    <div class="info"><strong>Path:</strong> {file_path}</div>
                </div>
            </body>
            </html>
            """

            return html

    def _show_blank(self):
        """Show blank clickable pane with light grey background"""
        self._container.clear()
        self._container.add(self._webview)

        # Ensure click handler is set up (safe to call multiple times)
        self._setup_click_detection()

        # Load blank HTML with light grey background and click detection
        blank_html = self._create_blank_html()
        self._webview.set_content("", blank_html)

        self.logger.debug(f"Pane {self._pane_id}: Showing blank clickable page")

    def _create_blank_html(self) -> str:
        """Create blank HTML page with click detection"""
        if not self._handler_name:
            self._handler_name = f'paneClick_{self._pane_id}'

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                html, body {{
                    width: 100%;
                    height: 100%;
                    background-color: #f5f5f5;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }}
                .message {{
                    color: #999;
                    font-size: 14px;
                    text-align: center;
                }}
            </style>
        </head>
        <body>
            <div class="message">Click to focus</div>
            <script>
            (function() {{
                var handlerName = '{self._handler_name}';
                console.log('Blank pane: Setting up click handler for', handlerName);

                document.addEventListener('click', function(e) {{
                    try {{
                        if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers[handlerName]) {{
                            window.webkit.messageHandlers[handlerName].postMessage('clicked');
                            console.log('Click message sent to ' + handlerName);
                        }} else {{
                            console.log('Handler ' + handlerName + ' not available yet');
                        }}
                    }} catch (err) {{
                        console.log('Click handler error:', err);
                    }}
                }}, true);
            }})();
            </script>
        </body>
        </html>
        """

        return html

    def _show_loading(self):
        """Show loading state"""
        self._container.clear()
        self._container.add(self._loading_label)

    def _show_error(self, error: str):
        """Show error state"""
        self._error_label.text = f"Error: {error}"
        self._container.clear()
        self._container.add(self._error_label)

    def _show_content(self):
        """Show content (WebView and PathBar)"""
        self._container.clear()
        self._container.add(self._webview)
        if self._path_bar_visible and self._path_bar:
            self.logger.debug(f"Adding path bar to container (visible={self._path_bar_visible})")
            self._container.add(self._path_bar.container)
            # Redraw the canvas after adding to ensure it renders
            self._path_bar._draw_path()
        else:
            self.logger.debug(f"Path bar not shown (visible={self._path_bar_visible}, exists={self._path_bar is not None})")

    async def _update_path_bar(self, item_id: str, processing_step=None):
        """
        Update path bar with library path and debug info.

        Args:
            item_id: Library item ID
            processing_step: Optional processing step object for debug info
        """
        try:
            # Get item details from library
            item = await self.library_manager.get_item(item_id)
            if not item:
                self._path_bar.clear()
                return

            # Build simple path: "Item Name › Step Name"
            # The PathBar will handle truncation of the item name if needed
            if processing_step:
                step_name = processing_step.step_name or "Unknown"
                path_string = f"{item.name} › {step_name}"
            else:
                # No step - just show item name
                path_string = item.name

            self._path_bar.set_path(path_string)

        except Exception as e:
            self.logger.error(f"Error updating path bar: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            self._path_bar.clear()

    # ==================== UTILITY METHODS ====================

    def clear(self):
        """Clear current content"""
        self.current_item_id = None
        self.current_step_index = None
        self._show_loading()

    def refresh(self):
        """Refresh current content"""
        if self.current_item_id is not None and self.current_step_index is not None:
            # Re-render current step
            import asyncio
            asyncio.create_task(self.set_step(self.current_item_id, self.current_step_index))

    # ==================== FOCUS INDICATOR (PHASE 5) ====================

    def set_focused(self, is_focused: bool):
        """
        Set focus visual indicator for this pane - PHASE 5.

        Focus border applied to outer wrapper using padding trick:
        - Outer box gets blue background
        - Inner container gets padding to create border effect
        - Inner container gets white background to cover outer background

        Args:
            is_focused: True to show focus border, False to hide it
        """
        if is_focused:
            # Show focus using background color on outer + margin on inner (padding is deprecated)
            from toga.colors import rgb
            self._outer_box.style.background_color = rgb(0, 122, 204)  # VSCode blue
            self._container.style.margin = 3  # Border width (using margin, not padding)
            self._container.style.background_color = rgb(255, 255, 255)  # White inner
            self.logger.info(f"✨ Pane FOCUSED with blue border")
        else:
            # Remove focus border - must use del, not None
            try:
                del self._outer_box.style.background_color
            except (AttributeError, KeyError):
                pass
            self._container.style.margin = 0
            try:
                del self._container.style.background_color
            except (AttributeError, KeyError):
                pass
            self.logger.debug("Pane unfocused")

    # ==================== CONTEXT MANAGEMENT (FEATURE 1) ====================

    def get_context(self) -> Dict[str, Any]:
        """
        Get the current context of this pane.

        Returns:
            Dict with library_id, collection_id, item_id, step_index
        """
        return {
            'library_id': self.current_library_id,
            'collection_id': self.current_collection_id,
            'item_id': self.current_item_id,
            'step_index': self.current_step_index
        }

    async def set_context(self, context: Dict[str, Any]):
        """
        Set the pane's context and load the corresponding content.

        This creates a new VIEW into the library/collection/item/step,
        not new data.

        Args:
            context: Dict with library_id, collection_id, item_id, step_index
        """
        self.current_library_id = context.get('library_id')
        self.current_collection_id = context.get('collection_id')
        self.current_item_id = context.get('item_id')
        self.current_step_index = context.get('step_index', 0)

        # Load the content if we have an item_id
        if self.current_item_id is not None:
            await self.set_step(self.current_item_id, self.current_step_index)

    def clone_context_to(self, target_pane: 'OutputPane'):
        """
        Clone this pane's context to another pane.

        This is used when creating split views or new windows,
        making a new VIEW into the same data.

        Args:
            target_pane: OutputPane to clone context to
        """
        import asyncio
        context = self.get_context()
        asyncio.create_task(target_pane.set_context(context))
