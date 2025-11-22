"""
HTML Templates for Interactive Viewers

Provides reusable HTML/CSS/JavaScript templates for rendering content in WebViews.
Includes interactive controls for images (zoom, pan, rotate, minimap).

Based on the proven implementation from commit d511a9d.
"""

import base64
from pathlib import Path
from typing import Optional


def get_interactive_image_viewer(
    image_path,
    title: Optional[str] = None,
    use_base64: bool = True
) -> str:
    """
    Generate HTML for interactive image viewer with full controls.

    Features:
    - Zoom in/out, fit to window, actual size, fit to width/height
    - Pan/drag navigation
    - Rotate left/right (90° increments)
    - Minimap overlay with draggable viewport
    - Mouse wheel zoom
    - Viewer state persistence

    Args:
        image_path: Path to image file or URL string
        title: Optional title (defaults to filename)
        use_base64: If True, encode image as base64 data URL (default, ignored for URLs)
                   If False, use file:// URL

    Returns:
        Complete HTML document string
    """
    # Check if this is a URL
    is_url = isinstance(image_path, str) and image_path.startswith(('http://', 'https://'))

    if title is None:
        if is_url:
            title = image_path.split('/')[-1] or 'Remote Image'
        else:
            title = image_path.name

    # Prepare image source
    if is_url:
        img_src = image_path
    elif use_base64:
        # Encode as base64 data URL
        try:
            with open(image_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')

            # Determine MIME type
            ext = image_path.suffix.lower()
            mime_types = {
                '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.png': 'image/png', '.gif': 'image/gif',
                '.bmp': 'image/bmp', '.webp': 'image/webp',
                '.tiff': 'image/tiff', '.tif': 'image/tiff'
            }
            mime_type = mime_types.get(ext, 'image/jpeg')

            img_src = f"data:{mime_type};base64,{image_data}"
        except Exception as e:
            img_src = ""
    else:
        # Use file:// URL
        img_src = f"file://{image_path}"

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: #969696;
            overflow: hidden;
            width: 100vw;
            height: 100vh;
            position: fixed;
        }}
        #imageContainer {{
            width: 100%;
            height: 100%;
            overflow: auto;
            position: relative;
            cursor: grab;
            -webkit-overflow-scrolling: touch;
        }}
        #imageContainer.grabbing {{ cursor: grabbing; }}
        #imageWrapper {{
            min-width: 100%;
            min-height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        img {{
            display: block;
            user-select: none;
            -webkit-user-select: none;
            pointer-events: none;
        }}
        #minimap {{
            position: fixed;
            top: 10px;
            right: 10px;
            width: 80px;
            height: 80px;
            background: rgba(0, 0, 0, 0.7);
            border: 2px solid #666;
            border-radius: 4px;
            overflow: hidden;
            display: none;  /* Hidden when not zoomed */
            cursor: pointer;
            z-index: 1000;
        }}
        #minimapCanvas {{
            width: 100%;
            height: 100%;
        }}
        #minimapViewport {{
            position: absolute;
            border: 2px solid #4CAF50;
            background: rgba(76, 175, 80, 0.2);
            cursor: move;
            pointer-events: auto;
        }}
        #selectionBox {{
            position: fixed;
            border: 2px dashed #4CAF50;
            background: rgba(76, 175, 80, 0.1);
            display: none;
            pointer-events: none;
            z-index: 999;
        }}
    </style>
</head>
<body>
    <div id="imageContainer">
        <div id="imageWrapper">
            <img id="image" src="{img_src}" alt="{title}">
        </div>
    </div>
    <div id="minimap">
        <canvas id="minimapCanvas"></canvas>
        <div id="minimapViewport"></div>
    </div>
    <div id="selectionBox"></div>
    <script>
        let scale = 1;
        let rotation = 0;  // Track rotation in degrees (0, 90, 180, 270)
        let isDragging = false;
        let startX, startY, scrollLeft, scrollTop;

        const img = document.getElementById('image');
        const container = document.getElementById('imageContainer');
        const wrapper = document.getElementById('imageWrapper');
        const minimap = document.getElementById('minimap');
        const minimapCanvas = document.getElementById('minimapCanvas');
        const minimapViewport = document.getElementById('minimapViewport');
        const ctx = minimapCanvas.getContext('2d');

        // Load image fitted to window by default
        img.onload = function() {{
            fitToWindow();
            drawMinimap();
        }};

        function updateImageSize() {{
            img.style.width = (img.naturalWidth * scale) + 'px';
            img.style.height = (img.naturalHeight * scale) + 'px';
            img.style.transform = `rotate(${{rotation}}deg)`;

            // Update wrapper to be at least container size or image size
            // Account for rotation by using bounding box size
            let imgWidth = img.naturalWidth * scale;
            let imgHeight = img.naturalHeight * scale;

            // Swap dimensions if rotated 90 or 270 degrees
            if (rotation === 90 || rotation === 270) {{
                [imgWidth, imgHeight] = [imgHeight, imgWidth];
            }}

            wrapper.style.width = Math.max(imgWidth, container.clientWidth) + 'px';
            wrapper.style.height = Math.max(imgHeight, container.clientHeight) + 'px';

            // Update minimap
            updateMinimap();
        }}

        function fitToWindow() {{
            const containerRect = container.getBoundingClientRect();
            const imgNaturalWidth = img.naturalWidth;
            const imgNaturalHeight = img.naturalHeight;

            scale = Math.min(
                containerRect.width / imgNaturalWidth,
                containerRect.height / imgNaturalHeight
            );

            updateImageSize();
        }}

        function fitToWidth() {{
            const containerRect = container.getBoundingClientRect();
            scale = containerRect.width / img.naturalWidth;
            updateImageSize();
        }}

        function fitToHeight() {{
            const containerRect = container.getBoundingClientRect();
            scale = containerRect.height / img.naturalHeight;
            updateImageSize();
        }}

        function actualSize() {{
            scale = 1;
            updateImageSize();
            container.scrollTop = 0;
            container.scrollLeft = 0;
        }}

        function zoomIn() {{
            scale = Math.min(scale * 1.2, 5);
            updateImageSize();
        }}

        function zoomOut() {{
            scale = Math.max(scale / 1.2, 0.1);
            updateImageSize();
        }}

        function getZoomLevel() {{
            return Math.round(scale * 100);
        }}

        function zoomToSelection(left, top, width, height) {{
            // Calculate scale needed to fit selection to window
            const scaleX = container.clientWidth / width;
            const scaleY = container.clientHeight / height;
            scale = Math.min(scaleX, scaleY, 5.0);

            updateImageSize();

            // Center the selection
            const centerX = left + width / 2;
            const centerY = top + height / 2;
            container.scrollLeft = centerX * scale - container.clientWidth / 2;
            container.scrollTop = centerY * scale - container.clientHeight / 2;
        }}

        function rotateLeft() {{
            rotation = (rotation - 90 + 360) % 360;
            updateImageSize();
        }}

        function rotateRight() {{
            rotation = (rotation + 90) % 360;
            updateImageSize();
        }}

        function restoreViewerState(savedScale, savedRotation, savedScrollX, savedScrollY) {{
            scale = savedScale;
            rotation = savedRotation;
            updateImageSize();

            // Restore scroll position after a brief delay to ensure layout is complete
            setTimeout(function() {{
                container.scrollLeft = savedScrollX;
                container.scrollTop = savedScrollY;
            }}, 50);
        }}

        function drawMinimap() {{
            minimapCanvas.width = 80;
            minimapCanvas.height = 80;

            const minimapScale = Math.min(80 / img.naturalWidth, 80 / img.naturalHeight);
            const minimapWidth = img.naturalWidth * minimapScale;
            const minimapHeight = img.naturalHeight * minimapScale;
            const offsetX = (80 - minimapWidth) / 2;
            const offsetY = (80 - minimapHeight) / 2;

            ctx.clearRect(0, 0, 80, 80);
            ctx.drawImage(img, offsetX, offsetY, minimapWidth, minimapHeight);
        }}

        function updateMinimap() {{
            // Show minimap except when viewing at exact fit-to-window scale
            const fitScale = Math.min(container.clientWidth / img.naturalWidth, container.clientHeight / img.naturalHeight);
            if (Math.abs(scale - fitScale) > 0.01) {{
                minimap.style.display = 'block';
                updateMinimapViewport();
            }} else {{
                minimap.style.display = 'none';
            }}
        }}

        function updateMinimapViewport() {{
            const minimapScale = Math.min(80 / img.naturalWidth, 80 / img.naturalHeight);
            const minimapWidth = img.naturalWidth * minimapScale;
            const minimapHeight = img.naturalHeight * minimapScale;
            const offsetX = (80 - minimapWidth) / 2;
            const offsetY = (80 - minimapHeight) / 2;

            // Get actual displayed image dimensions
            const displayedWidth = img.naturalWidth * scale;
            const displayedHeight = img.naturalHeight * scale;

            // Calculate viewport size and position relative to displayed image
            const viewportWidth = (container.clientWidth / displayedWidth) * minimapWidth;
            const viewportHeight = (container.clientHeight / displayedHeight) * minimapHeight;
            const viewportX = (container.scrollLeft / displayedWidth) * minimapWidth + offsetX;
            const viewportY = (container.scrollTop / displayedHeight) * minimapHeight + offsetY;

            minimapViewport.style.width = viewportWidth + 'px';
            minimapViewport.style.height = viewportHeight + 'px';
            minimapViewport.style.left = viewportX + 'px';
            minimapViewport.style.top = viewportY + 'px';
        }}

        // Update minimap viewport on scroll
        container.addEventListener('scroll', updateMinimapViewport);

        // Drag viewport box or click minimap to jump
        let isDraggingViewport = false;
        let dragOffset = null;

        function minimapToImageCoords(minimapX, minimapY) {{
            const minimapScale = Math.min(80 / img.naturalWidth, 80 / img.naturalHeight);
            const minimapWidth = img.naturalWidth * minimapScale;
            const minimapHeight = img.naturalHeight * minimapScale;
            const offsetX = (80 - minimapWidth) / 2;
            const offsetY = (80 - minimapHeight) / 2;

            const relX = (minimapX - offsetX) / minimapWidth;
            const relY = (minimapY - offsetY) / minimapHeight;

            return {{
                x: relX * img.naturalWidth * scale - container.clientWidth / 2,
                y: relY * img.naturalHeight * scale - container.clientHeight / 2
            }};
        }}

        minimapViewport.addEventListener('mousedown', function(e) {{
            e.preventDefault();
            e.stopPropagation();
            isDraggingViewport = true;

            // Store the offset from the viewport's top-left corner
            const viewportRect = minimapViewport.getBoundingClientRect();
            dragOffset = {{
                x: e.clientX - viewportRect.left,
                y: e.clientY - viewportRect.top
            }};
        }});

        minimap.addEventListener('mousedown', function(e) {{
            if (e.target === minimap || e.target === minimapCanvas) {{
                const rect = minimap.getBoundingClientRect();
                const clickX = e.clientX - rect.left;
                const clickY = e.clientY - rect.top;
                const coords = minimapToImageCoords(clickX, clickY);
                container.scrollLeft = coords.x;
                container.scrollTop = coords.y;
            }}
        }});

        document.addEventListener('mousemove', function(e) {{
            if (isDraggingViewport && dragOffset) {{
                const rect = minimap.getBoundingClientRect();
                // Calculate new viewport position (accounting for the drag offset)
                const viewportX = e.clientX - rect.left - dragOffset.x;
                const viewportY = e.clientY - rect.top - dragOffset.y;

                // Center the viewport at this position
                const coords = minimapToImageCoords(viewportX + minimapViewport.offsetWidth / 2, viewportY + minimapViewport.offsetHeight / 2);
                container.scrollLeft = coords.x;
                container.scrollTop = coords.y;
            }}
        }});

        document.addEventListener('mouseup', function() {{
            isDraggingViewport = false;
            dragOffset = null;
        }});

        // Pan/drag navigation
        container.addEventListener('mousedown', function(e) {{
            isDragging = true;
            startX = e.pageX - container.offsetLeft;
            startY = e.pageY - container.offsetTop;
            scrollLeft = container.scrollLeft;
            scrollTop = container.scrollTop;
            container.classList.add('grabbing');
        }});

        container.addEventListener('mouseleave', function() {{
            isDragging = false;
            container.classList.remove('grabbing');
        }});

        container.addEventListener('mouseup', function() {{
            isDragging = false;
            container.classList.remove('grabbing');
        }});

        container.addEventListener('mousemove', function(e) {{
            if (!isDragging) return;
            e.preventDefault();
            const x = e.pageX - container.offsetLeft;
            const y = e.pageY - container.offsetTop;
            const walkX = (x - startX);
            const walkY = (y - startY);
            container.scrollLeft = scrollLeft - walkX;
            container.scrollTop = scrollTop - walkY;
        }});

        // Mouse wheel zoom
        container.addEventListener('wheel', function(e) {{
            e.preventDefault();
            if (e.deltaY < 0) {{
                zoomIn();
            }} else {{
                zoomOut();
            }}
        }}, {{ passive: false }});

        // Selection rectangle for zoom-to-selection (Shift+drag)
        let isSelecting = false;
        let selectionStart = {{ x: 0, y: 0 }};
        const selectionBox = document.getElementById('selectionBox');

        container.addEventListener('mousedown', function(e) {{
            if (e.shiftKey) {{
                // Start selection
                isSelecting = true;
                const rect = container.getBoundingClientRect();
                selectionStart.x = e.clientX;
                selectionStart.y = e.clientY;

                selectionBox.style.left = e.clientX + 'px';
                selectionBox.style.top = e.clientY + 'px';
                selectionBox.style.width = '0px';
                selectionBox.style.height = '0px';
                selectionBox.style.display = 'block';

                e.preventDefault();
                return;
            }}
        }});

        document.addEventListener('mousemove', function(e) {{
            if (isSelecting) {{
                const width = Math.abs(e.clientX - selectionStart.x);
                const height = Math.abs(e.clientY - selectionStart.y);
                const left = Math.min(e.clientX, selectionStart.x);
                const top = Math.min(e.clientY, selectionStart.y);

                selectionBox.style.left = left + 'px';
                selectionBox.style.top = top + 'px';
                selectionBox.style.width = width + 'px';
                selectionBox.style.height = height + 'px';
            }}
        }});

        document.addEventListener('mouseup', function(e) {{
            if (isSelecting) {{
                isSelecting = false;
                selectionBox.style.display = 'none';

                // Calculate selection in image coordinates
                const rect = container.getBoundingClientRect();
                const width = Math.abs(e.clientX - selectionStart.x);
                const height = Math.abs(e.clientY - selectionStart.y);

                if (width > 10 && height > 10) {{  // Minimum selection size
                    const left = Math.min(e.clientX, selectionStart.x) - rect.left + container.scrollLeft;
                    const top = Math.min(e.clientY, selectionStart.y) - rect.top + container.scrollTop;

                    // Convert to image coordinates (account for current scale)
                    const imgLeft = left / scale;
                    const imgTop = top / scale;
                    const imgWidth = width / scale;
                    const imgHeight = height / scale;

                    zoomToSelection(imgLeft, imgTop, imgWidth, imgHeight);
                }}
            }}
        }});

        // Double-click to cycle through zoom levels
        let lastClickTime = 0;
        let zoomCycleIndex = 0;  // 0=fitToWindow, 1=fitToWidth, 2=actualSize

        container.addEventListener('dblclick', function(e) {{
            if (e.shiftKey) return;  // Don't interfere with shift-drag selection

            e.preventDefault();

            // Cycle through zoom levels: fit → fit-width → 100% → fit
            zoomCycleIndex = (zoomCycleIndex + 1) % 3;

            switch(zoomCycleIndex) {{
                case 0:
                    fitToWindow();
                    break;
                case 1:
                    fitToWidth();
                    break;
                case 2:
                    actualSize();
                    break;
            }}
        }});
    </script>
</body>
</html>"""


def get_interactive_crop_viewer(
    image_path,
    crop_box: dict,
    title: Optional[str] = None,
    use_base64: bool = True
) -> str:
    """
    Generate HTML for interactive crop editor with draggable crop box.

    Features:
    - All features from get_interactive_image_viewer (zoom, pan, rotate, minimap)
    - Draggable crop box overlay
    - Resizable crop box (drag corners/edges)
    - Displays crop coordinates
    - Apply button to save crop

    Args:
        image_path: Path to image file or URL string
        crop_box: Dict with x1, y1, x2, y2 coordinates
        title: Optional title (defaults to filename)
        use_base64: If True, encode image as base64 data URL (default, ignored for URLs)

    Returns:
        Complete HTML document string
    """
    # Check if this is a URL
    is_url = isinstance(image_path, str) and image_path.startswith(('http://', 'https://'))

    if title is None:
        if is_url:
            title = image_path.split('/')[-1] or 'Remote Image'
        else:
            title = image_path.name

    # Prepare image source
    if is_url:
        img_src = image_path
    elif use_base64:
        try:
            with open(image_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')

            ext = image_path.suffix.lower()
            mime_types = {
                '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.png': 'image/png', '.gif': 'image/gif',
                '.bmp': 'image/bmp', '.webp': 'image/webp',
                '.tiff': 'image/tiff', '.tif': 'image/tiff'
            }
            mime_type = mime_types.get(ext, 'image/jpeg')
            img_src = f"data:{mime_type};base64,{image_data}"
        except Exception as e:
            img_src = ""
    else:
        img_src = f"file://{image_path}"

    # Extract crop box coordinates
    x1 = crop_box.get('x1', 0)
    y1 = crop_box.get('y1', 0)
    x2 = crop_box.get('x2', 100)
    y2 = crop_box.get('y2', 100)

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: #969696;
            overflow: hidden;
            width: 100vw;
            height: 100vh;
            position: fixed;
        }}
        #imageContainer {{
            width: 100%;
            height: calc(100vh - 60px);
            overflow: auto;
            position: relative;
            cursor: grab;
            -webkit-overflow-scrolling: touch;
        }}
        #imageContainer.grabbing {{ cursor: grabbing; }}
        #imageContainer.crop-mode {{ cursor: crosshair; }}
        #imageWrapper {{
            min-width: 100%;
            min-height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
        }}
        img {{
            display: block;
            user-select: none;
            -webkit-user-select: none;
        }}
        #currentCropBox {{
            position: absolute;
            border: 2px dashed #888;
            background: transparent;
            pointer-events: none;
            z-index: 5;
            display: none;
        }}
        #selectionBox {{
            position: absolute;
            border: 3px solid #4CAF50;
            background: rgba(76, 175, 80, 0.15);
            cursor: move;
            z-index: 10;
            display: none;
        }}
        #selectionBox.active {{
            display: block;
        }}
        .selection-handle {{
            position: absolute;
            width: 12px;
            height: 12px;
            background: #4CAF50;
            border: 2px solid white;
            border-radius: 50%;
            z-index: 11;
        }}
        .selection-handle.nw {{ top: -6px; left: -6px; cursor: nw-resize; }}
        .selection-handle.ne {{ top: -6px; right: -6px; cursor: ne-resize; }}
        .selection-handle.sw {{ bottom: -6px; left: -6px; cursor: sw-resize; }}
        .selection-handle.se {{ bottom: -6px; right: -6px; cursor: se-resize; }}
        .selection-handle.n {{ top: -6px; left: 50%; margin-left: -6px; cursor: n-resize; }}
        .selection-handle.s {{ bottom: -6px; left: 50%; margin-left: -6px; cursor: s-resize; }}
        .selection-handle.w {{ top: 50%; left: -6px; margin-top: -6px; cursor: w-resize; }}
        .selection-handle.e {{ top: 50%; right: -6px; margin-top: -6px; cursor: e-resize; }}
        #toolbar {{
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            height: 60px;
            background: #1e1e1e;
            border-top: 1px solid #444;
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 20px;
            z-index: 1000;
        }}
        .crop-info {{
            color: #ccc;
            font-family: monospace;
            font-size: 13px;
        }}
        .toolbar-buttons {{
            display: flex;
            gap: 10px;
        }}
        button {{
            background: #4CAF50;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        }}
        button:hover {{
            background: #45a049;
        }}
        button.secondary {{
            background: #666;
        }}
        button.secondary:hover {{
            background: #555;
        }}
        #minimap {{
            position: fixed;
            top: 10px;
            right: 10px;
            width: 80px;
            height: 80px;
            background: rgba(0, 0, 0, 0.7);
            border: 2px solid #666;
            border-radius: 4px;
            overflow: hidden;
            display: none;
            cursor: pointer;
            z-index: 1000;
        }}
        #minimapCanvas {{
            width: 100%;
            height: 100%;
        }}
        #minimapViewport {{
            position: absolute;
            border: 2px solid #4CAF50;
            background: rgba(76, 175, 80, 0.2);
            cursor: move;
            pointer-events: auto;
        }}
    </style>
</head>
<body>
    <div id="imageContainer">
        <div id="imageWrapper">
            <img id="image" src="{img_src}" alt="{title}">
            <div id="currentCropBox"></div>
            <div id="selectionBox">
                <div class="selection-handle nw"></div>
                <div class="selection-handle n"></div>
                <div class="selection-handle ne"></div>
                <div class="selection-handle w"></div>
                <div class="selection-handle e"></div>
                <div class="selection-handle sw"></div>
                <div class="selection-handle s"></div>
                <div class="selection-handle se"></div>
            </div>
        </div>
    </div>
    <div id="minimap">
        <canvas id="minimapCanvas"></canvas>
        <div id="minimapViewport"></div>
    </div>
    <div id="toolbar">
        <div class="crop-info">
            Crop: <span id="cropCoords">Loading...</span>
        </div>
        <div class="toolbar-buttons">
            <button class="secondary" onclick="resetCrop()">Reset</button>
            <button onclick="applyCrop()">Apply Crop</button>
        </div>
    </div>
    <script>
        let scale = 1;
        let rotation = 0;
        let isPanning = false;
        let startX, startY, scrollLeft, scrollTop;

        // Original crop box from manifest (shown as reference in gray)
        const originalCropBox = {{
            x1: {x1},
            y1: {y1},
            x2: {x2},
            y2: {y2}
        }};

        // New selection box (user draws this)
        let selectionBox = null;  // null = no selection yet

        // Rubber-band drawing state
        let isDrawing = false;
        let drawStartX, drawStartY;

        // Selection manipulation state
        let isDraggingSelection = false;
        let isResizingSelection = false;
        let resizeHandle = null;
        let dragStartBox = null;
        let dragStartMouseX, dragStartMouseY;

        const img = document.getElementById('image');
        const container = document.getElementById('imageContainer');
        const wrapper = document.getElementById('imageWrapper');
        const currentCropBoxEl = document.getElementById('currentCropBox');
        const selectionBoxEl = document.getElementById('selectionBox');
        const minimap = document.getElementById('minimap');
        const minimapCanvas = document.getElementById('minimapCanvas');
        const minimapViewport = document.getElementById('minimapViewport');
        const ctx = minimapCanvas.getContext('2d');
        const cropCoordsEl = document.getElementById('cropCoords');

        // Load image fitted to window by default
        img.onload = function() {{
            fitToWindow();
            drawMinimap();
            updateDisplay();
        }};

        function updateImageSize() {{
            img.style.width = (img.naturalWidth * scale) + 'px';
            img.style.height = (img.naturalHeight * scale) + 'px';
            img.style.transform = `rotate(${{rotation}}deg)`;

            let imgWidth = img.naturalWidth * scale;
            let imgHeight = img.naturalHeight * scale;

            if (rotation === 90 || rotation === 270) {{
                [imgWidth, imgHeight] = [imgHeight, imgWidth];
            }}

            wrapper.style.width = Math.max(imgWidth, container.clientWidth) + 'px';
            wrapper.style.height = Math.max(imgHeight, container.clientHeight) + 'px';

            updateMinimap();
            updateCropBox();
        }}

        function fitToWindow() {{
            const containerRect = container.getBoundingClientRect();
            scale = Math.min(
                containerRect.width / img.naturalWidth,
                containerRect.height / img.naturalHeight
            );
            updateImageSize();
        }}

        function zoomIn() {{
            scale = Math.min(scale * 1.2, 5);
            updateImageSize();
        }}

        function zoomOut() {{
            scale = Math.max(scale / 1.2, 0.1);
            updateImageSize();
        }}

        function updateCropBox() {{
            // Convert image coordinates to screen coordinates
            const imgRect = img.getBoundingClientRect();
            const wrapperRect = wrapper.getBoundingClientRect();

            const left = (cropBox.x1 * scale);
            const top = (cropBox.y1 * scale);
            const width = ((cropBox.x2 - cropBox.x1) * scale);
            const height = ((cropBox.y2 - cropBox.y1) * scale);

            cropBoxEl.style.left = left + 'px';
            cropBoxEl.style.top = top + 'px';
            cropBoxEl.style.width = width + 'px';
            cropBoxEl.style.height = height + 'px';

            // Update coordinates display
            cropCoordsEl.textContent = `x1=${{Math.round(cropBox.x1)}}, y1=${{Math.round(cropBox.y1)}}, x2=${{Math.round(cropBox.x2)}}, y2=${{Math.round(cropBox.y2)}} | w=${{Math.round(cropBox.x2 - cropBox.x1)}}, h=${{Math.round(cropBox.y2 - cropBox.y1)}}`;
        }}

        function resetCrop() {{
            cropBox.x1 = 0;
            cropBox.y1 = 0;
            cropBox.x2 = img.naturalWidth;
            cropBox.y2 = img.naturalHeight;
            updateCropBox();
        }}

        function applyCrop() {{
            // Send crop coordinates back to Python
            const cropData = {{
                x1: Math.round(cropBox.x1),
                y1: Math.round(cropBox.y1),
                x2: Math.round(cropBox.x2),
                y2: Math.round(cropBox.y2),
                width: Math.round(cropBox.x2 - cropBox.x1),
                height: Math.round(cropBox.y2 - cropBox.y1)
            }};

            console.log('Applying crop:', cropData);

            // TODO: Call Python handler via Toga WebView messaging
            // For now, just log
            alert('Crop applied: ' + JSON.stringify(cropData));
        }}

        // Crop box dragging
        let isDraggingCrop = false;
        let dragStartCropX, dragStartCropY;
        let dragStartMouseX, dragStartMouseY;

        cropBoxEl.addEventListener('mousedown', function(e) {{
            if (e.target === cropBoxEl) {{
                isDraggingCrop = true;
                dragStartCropX = cropBox.x1;
                dragStartCropY = cropBox.y1;
                dragStartMouseX = e.clientX;
                dragStartMouseY = e.clientY;
                e.preventDefault();
                e.stopPropagation();
            }}
        }});

        document.addEventListener('mousemove', function(e) {{
            if (isDraggingCrop) {{
                const dx = (e.clientX - dragStartMouseX) / scale;
                const dy = (e.clientY - dragStartMouseY) / scale;

                const width = cropBox.x2 - cropBox.x1;
                const height = cropBox.y2 - cropBox.y1;

                cropBox.x1 = Math.max(0, Math.min(img.naturalWidth - width, dragStartCropX + dx));
                cropBox.y1 = Math.max(0, Math.min(img.naturalHeight - height, dragStartCropY + dy));
                cropBox.x2 = cropBox.x1 + width;
                cropBox.y2 = cropBox.y1 + height;

                updateCropBox();
            }}
        }});

        document.addEventListener('mouseup', function() {{
            isDraggingCrop = false;
        }});

        // Crop handle resizing
        let isResizing = false;
        let resizeHandle = null;
        let resizeStartBox = null;

        document.querySelectorAll('.crop-handle').forEach(handle => {{
            handle.addEventListener('mousedown', function(e) {{
                isResizing = true;
                resizeHandle = handle.classList[1];
                resizeStartBox = {{ ...cropBox }};
                dragStartMouseX = e.clientX;
                dragStartMouseY = e.clientY;
                e.preventDefault();
                e.stopPropagation();
            }});
        }});

        document.addEventListener('mousemove', function(e) {{
            if (isResizing) {{
                const dx = (e.clientX - dragStartMouseX) / scale;
                const dy = (e.clientY - dragStartMouseY) / scale;

                cropBox = {{ ...resizeStartBox }};

                if (resizeHandle.includes('n')) {{
                    cropBox.y1 = Math.max(0, Math.min(cropBox.y2 - 10, resizeStartBox.y1 + dy));
                }}
                if (resizeHandle.includes('s')) {{
                    cropBox.y2 = Math.min(img.naturalHeight, Math.max(cropBox.y1 + 10, resizeStartBox.y2 + dy));
                }}
                if (resizeHandle.includes('w')) {{
                    cropBox.x1 = Math.max(0, Math.min(cropBox.x2 - 10, resizeStartBox.x1 + dx));
                }}
                if (resizeHandle.includes('e')) {{
                    cropBox.x2 = Math.min(img.naturalWidth, Math.max(cropBox.x1 + 10, resizeStartBox.x2 + dx));
                }}

                updateCropBox();
            }}
        }});

        document.addEventListener('mouseup', function() {{
            isResizing = false;
            resizeHandle = null;
        }});

        // Pan/drag navigation (only when not dragging crop)
        container.addEventListener('mousedown', function(e) {{
            if (!isDraggingCrop && !isResizing && e.target === container) {{
                isDragging = true;
                startX = e.pageX - container.offsetLeft;
                startY = e.pageY - container.offsetTop;
                scrollLeft = container.scrollLeft;
                scrollTop = container.scrollTop;
                container.classList.add('grabbing');
            }}
        }});

        container.addEventListener('mouseleave', function() {{
            isDragging = false;
            container.classList.remove('grabbing');
        }});

        container.addEventListener('mouseup', function() {{
            isDragging = false;
            container.classList.remove('grabbing');
        }});

        container.addEventListener('mousemove', function(e) {{
            if (!isDragging) return;
            e.preventDefault();
            const x = e.pageX - container.offsetLeft;
            const y = e.pageY - container.offsetTop;
            const walkX = (x - startX);
            const walkY = (y - startY);
            container.scrollLeft = scrollLeft - walkX;
            container.scrollTop = scrollTop - walkY;
        }});

        // Mouse wheel zoom
        container.addEventListener('wheel', function(e) {{
            e.preventDefault();
            if (e.deltaY < 0) {{
                zoomIn();
            }} else {{
                zoomOut();
            }}
        }}, {{ passive: false }});

        function drawMinimap() {{
            minimapCanvas.width = 80;
            minimapCanvas.height = 80;

            const minimapScale = Math.min(80 / img.naturalWidth, 80 / img.naturalHeight);
            const minimapWidth = img.naturalWidth * minimapScale;
            const minimapHeight = img.naturalHeight * minimapScale;
            const offsetX = (80 - minimapWidth) / 2;
            const offsetY = (80 - minimapHeight) / 2;

            ctx.clearRect(0, 0, 80, 80);
            ctx.drawImage(img, offsetX, offsetY, minimapWidth, minimapHeight);
        }}

        function updateMinimap() {{
            const fitScale = Math.min(container.clientWidth / img.naturalWidth, container.clientHeight / img.naturalHeight);
            if (Math.abs(scale - fitScale) > 0.01) {{
                minimap.style.display = 'block';
                updateMinimapViewport();
            }} else {{
                minimap.style.display = 'none';
            }}
        }}

        function updateMinimapViewport() {{
            const minimapScale = Math.min(80 / img.naturalWidth, 80 / img.naturalHeight);
            const minimapWidth = img.naturalWidth * minimapScale;
            const minimapHeight = img.naturalHeight * minimapScale;
            const offsetX = (80 - minimapWidth) / 2;
            const offsetY = (80 - minimapHeight) / 2;

            const displayedWidth = img.naturalWidth * scale;
            const displayedHeight = img.naturalHeight * scale;

            const viewportWidth = (container.clientWidth / displayedWidth) * minimapWidth;
            const viewportHeight = (container.clientHeight / displayedHeight) * minimapHeight;
            const viewportX = (container.scrollLeft / displayedWidth) * minimapWidth + offsetX;
            const viewportY = (container.scrollTop / displayedHeight) * minimapHeight + offsetY;

            minimapViewport.style.width = viewportWidth + 'px';
            minimapViewport.style.height = viewportHeight + 'px';
            minimapViewport.style.left = viewportX + 'px';
            minimapViewport.style.top = viewportY + 'px';
        }}

        container.addEventListener('scroll', updateMinimapViewport);
    </script>
</body>
</html>"""


def get_simple_content_viewer(content: str, title: Optional[str] = None) -> str:
    """
    Generate HTML for simple content display (text, JSON, etc.).

    Args:
        content: Content to display
        title: Optional title

    Returns:
        Complete HTML document string
    """
    if title is None:
        title = "Content"

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #969696;
            padding: 20px;
        }}
        .content {{
            background: #ECEBED;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            max-width: 800px;
            margin: 0 auto;
        }}
        pre {{
            white-space: pre-wrap;
            word-wrap: break-word;
            font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
            font-size: 13px;
        }}
    </style>
</head>
<body>
    <div class="content">
        <pre>{content}</pre>
    </div>
</body>
</html>"""
