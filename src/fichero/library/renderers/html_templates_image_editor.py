"""
Universal Image Editor Template

Provides a macOS Preview-style image editor controlled via JavaScript:
- Pan and zoom with mouse/keyboard
- Crop tool with rubber-band selection
- Rotation and flip transformations
- Controlled via Fichero's BottomToolbar command system
- Works with any image, not tied to specific workflow outputs
"""

import base64
from pathlib import Path
from typing import Optional, Dict


def get_image_editor(
    image_path: Path,
    title: Optional[str] = None,
    use_base64: bool = True,
    crop_box: Optional[Dict] = None
) -> str:
    """
    Generate HTML for universal image editor controlled via JavaScript.

    Provides pan/zoom and crop selection. Controlled via Python→JavaScript
    commands from Fichero's BottomToolbar.

    Args:
        image_path: Path to image file
        title: Optional title
        use_base64: Encode image as base64 (default True)
        crop_box: Optional existing crop box with x1, y1, x2, y2

    Returns:
        Complete HTML document
    """
    if title is None:
        title = image_path.name

    # Prepare image source
    if use_base64:
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
        except Exception:
            img_src = ""
    else:
        img_src = f"file://{image_path}"

    # Extract crop coordinates if provided
    initial_crop = "null"
    if crop_box:
        x1 = crop_box.get('x1', 0)
        y1 = crop_box.get('y1', 0)
        x2 = crop_box.get('x2', 100)
        y2 = crop_box.get('y2', 100)
        initial_crop = f"{{x1: {x1}, y1: {y1}, x2: {x2}, y2: {y2}}}"

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: #969696;
            overflow: hidden;
            width: 100vw;
            height: 100vh;
            position: fixed;
            font-family: -apple-system, BlinkMacSystemFont, sans-serif;
        }}
        #imageContainer {{
            width: 100%;
            height: calc(100vh - 60px);
            overflow: auto;
            position: relative;
            cursor: grab;
        }}
        #imageContainer.grabbing {{ cursor: grabbing; }}
        #imageContainer.crosshair {{ cursor: crosshair; }}
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
            pointer-events: none;
        }}

        /* Crop selection box */
        #selectionBox {{
            position: absolute;
            border: 3px solid #4CAF50;
            background: rgba(76, 175, 80, 0.15);
            cursor: move;
            z-index: 10;
            display: none;
        }}
        #selectionBox.active {{ display: block; }}

        /* Resize handles */
        .handle {{
            position: absolute;
            width: 14px;
            height: 14px;
            background: #4CAF50;
            border: 2px solid white;
            border-radius: 50%;
            z-index: 11;
        }}
        .handle.nw {{ top: -7px; left: -7px; cursor: nw-resize; }}
        .handle.ne {{ top: -7px; right: -7px; cursor: ne-resize; }}
        .handle.sw {{ bottom: -7px; left: -7px; cursor: sw-resize; }}
        .handle.se {{ bottom: -7px; right: -7px; cursor: se-resize; }}
        .handle.n {{ top: -7px; left: 50%; margin-left: -7px; cursor: n-resize; }}
        .handle.s {{ bottom: -7px; left: 50%; margin-left: -7px; cursor: s-resize; }}
        .handle.w {{ top: 50%; left: -7px; margin-top: -7px; cursor: w-resize; }}
        .handle.e {{ top: 50%; right: -7px; margin-top: -7px; cursor: e-resize; }}
    </style>
</head>
<body>
    <div id="imageContainer">
        <div id="imageWrapper">
            <img id="image" src="{img_src}" alt="{title}">
            <div id="selectionBox">
                <div class="handle nw"></div>
                <div class="handle n"></div>
                <div class="handle ne"></div>
                <div class="handle w"></div>
                <div class="handle e"></div>
                <div class="handle sw"></div>
                <div class="handle s"></div>
                <div class="handle se"></div>
            </div>
        </div>
    </div>

    <script>
        // Image state
        let scale = 1;
        let rotation = 0;
        let flipH = false;
        let flipV = false;
        const img = document.getElementById('image');
        const container = document.getElementById('imageContainer');
        const wrapper = document.getElementById('imageWrapper');
        const selectionBoxEl = document.getElementById('selectionBox');

        // Current tool
        let currentTool = null;  // 'crop', 'straighten', null

        // Selection state (in image coordinates)
        let selection = {initial_crop};  // {{x1, y1, x2, y2}} or null

        // Interaction state
        let mode = 'pan';  // 'pan', 'drawing', 'moving', 'resizing'
        let resizeHandle = null;
        let startPoint = null;
        let startSelection = null;

        // Pan state
        let isPanning = false;
        let panStart = null;
        let scrollStart = null;

        // Initialize
        img.onload = function() {{
            fitToWindow();
            // If we have an initial crop box, show it and activate crop tool
            if (selection) {{
                showSelection();
                activateTool('crop');
            }}
        }};

        function fitToWindow() {{
            const containerRect = container.getBoundingClientRect();
            scale = Math.min(
                containerRect.width / img.naturalWidth,
                containerRect.height / img.naturalHeight,
                1.0  // Don't zoom in beyond 100%
            );
            updateImageSize();
        }}

        function updateImageSize() {{
            img.style.width = (img.naturalWidth * scale) + 'px';
            img.style.height = (img.naturalHeight * scale) + 'px';
            wrapper.style.width = Math.max(img.naturalWidth * scale, container.clientWidth) + 'px';
            wrapper.style.height = Math.max(img.naturalHeight * scale, container.clientHeight) + 'px';

            if (selection) showSelection();
        }}

        function activateTool(tool) {{
            // Set or toggle tool (called from Python via BottomToolbar)
            if (currentTool === tool) {{
                // Deactivate if clicking same tool
                currentTool = null;
                container.classList.remove('crosshair');
                console.log('Tool deactivated:', tool);
            }} else {{
                // Activate new tool
                currentTool = tool;

                if (tool === 'crop') {{
                    container.classList.add('crosshair');
                    console.log('Crop tool activated');
                }} else if (tool === 'straighten') {{
                    console.log('Straighten tool activated');
                }}
            }}
        }}

        function rotateImage(degrees) {{
            rotation = (rotation + degrees) % 360;
            if (rotation < 0) rotation += 360;
            updateTransform();
            console.log('Rotate:', degrees, 'New rotation:', rotation);
            // TODO: Send to backend
        }}

        // Toolbar command wrappers - called from Python via OutputView
        function rotateLeft() {{
            rotateImage(-90);
        }}

        function rotateRight() {{
            rotateImage(90);
        }}

        function resetTransforms() {{
            // Reset all transformations to original state
            rotation = 0;
            flipH = false;
            flipV = false;
            scale = 1;
            selection = null;
            updateTransform();
            updateImageSize();
            showSelection();
            console.log('Reset all transformations');
        }}

        function flipImage(direction) {{
            if (direction === 'horizontal') {{
                flipH = !flipH;
            }} else {{
                flipV = !flipV;
            }}
            updateTransform();
            console.log('Flip:', direction, 'H:', flipH, 'V:', flipV);
            // TODO: Send to backend
        }}

        function updateTransform() {{
            let transform = `rotate(${{rotation}}deg)`;
            if (flipH) transform += ' scaleX(-1)';
            if (flipV) transform += ' scaleY(-1)';
            img.style.transform = transform;
        }}

        function showSelection() {{
            if (!selection) {{
                selectionBoxEl.classList.remove('active');
                return;
            }}

            const left = selection.x1 * scale;
            const top = selection.y1 * scale;
            const width = (selection.x2 - selection.x1) * scale;
            const height = (selection.y2 - selection.y1) * scale;

            selectionBoxEl.style.left = left + 'px';
            selectionBoxEl.style.top = top + 'px';
            selectionBoxEl.style.width = width + 'px';
            selectionBoxEl.style.height = height + 'px';
            selectionBoxEl.classList.add('active');

            console.log(`Crop: ${{Math.round(selection.x2 - selection.x1)}}×${{Math.round(selection.y2 - selection.y1)}}`);
        }}

        function getImageCoords(clientX, clientY) {{
            const imgRect = img.getBoundingClientRect();
            const x = (clientX - imgRect.left) / scale;
            const y = (clientY - imgRect.top) / scale;
            return {{
                x: Math.max(0, Math.min(img.naturalWidth, x)),
                y: Math.max(0, Math.min(img.naturalHeight, y))
            }};
        }}

        function isInsideSelection(x, y) {{
            if (!selection) return false;
            return x >= selection.x1 && x <= selection.x2 &&
                   y >= selection.y1 && y <= selection.y2;
        }}

        // Mouse handlers
        container.addEventListener('mousedown', function(e) {{
            const imgCoords = getImageCoords(e.clientX, e.clientY);

            // Crop tool active
            if (currentTool === 'crop') {{
                // Check if clicking on existing selection
                if (selection && isInsideSelection(imgCoords.x, imgCoords.y)) {{
                    mode = 'moving';
                    startPoint = imgCoords;
                    startSelection = {{ ...selection }};
                    e.preventDefault();
                    return;
                }}

                // Start new selection
                mode = 'drawing';
                startPoint = imgCoords;
                selection = {{
                    x1: imgCoords.x,
                    y1: imgCoords.y,
                    x2: imgCoords.x,
                    y2: imgCoords.y
                }};
                e.preventDefault();
                return;
            }}

            // Default: pan
            mode = 'pan';
            isPanning = true;
            panStart = {{ x: e.clientX, y: e.clientY }};
            scrollStart = {{ x: container.scrollLeft, y: container.scrollTop }};
            container.classList.add('grabbing');
            e.preventDefault();
        }});

        document.addEventListener('mousemove', function(e) {{
            if (mode === 'drawing') {{
                const imgCoords = getImageCoords(e.clientX, e.clientY);
                selection.x2 = imgCoords.x;
                selection.y2 = imgCoords.y;
                showSelection();
            }} else if (mode === 'moving') {{
                const imgCoords = getImageCoords(e.clientX, e.clientY);
                const dx = imgCoords.x - startPoint.x;
                const dy = imgCoords.y - startPoint.y;
                const width = startSelection.x2 - startSelection.x1;
                const height = startSelection.y2 - startSelection.y1;

                selection.x1 = Math.max(0, Math.min(img.naturalWidth - width, startSelection.x1 + dx));
                selection.y1 = Math.max(0, Math.min(img.naturalHeight - height, startSelection.y1 + dy));
                selection.x2 = selection.x1 + width;
                selection.y2 = selection.y1 + height;
                showSelection();
            }} else if (mode === 'resizing') {{
                const imgCoords = getImageCoords(e.clientX, e.clientY);
                selection = {{ ...startSelection }};

                if (resizeHandle.includes('n')) selection.y1 = Math.max(0, Math.min(selection.y2 - 10, imgCoords.y));
                if (resizeHandle.includes('s')) selection.y2 = Math.min(img.naturalHeight, Math.max(selection.y1 + 10, imgCoords.y));
                if (resizeHandle.includes('w')) selection.x1 = Math.max(0, Math.min(selection.x2 - 10, imgCoords.x));
                if (resizeHandle.includes('e')) selection.x2 = Math.min(img.naturalWidth, Math.max(selection.x1 + 10, imgCoords.x));

                showSelection();
            }} else if (isPanning) {{
                const dx = e.clientX - panStart.x;
                const dy = e.clientY - panStart.y;
                container.scrollLeft = scrollStart.x - dx;
                container.scrollTop = scrollStart.y - dy;
            }}
        }});

        document.addEventListener('mouseup', function() {{
            if (mode === 'drawing') {{
                // Normalize selection
                if (selection) {{
                    const x1 = Math.min(selection.x1, selection.x2);
                    const x2 = Math.max(selection.x1, selection.x2);
                    const y1 = Math.min(selection.y1, selection.y2);
                    const y2 = Math.max(selection.y1, selection.y2);

                    // Minimum selection size
                    if (x2 - x1 < 10 || y2 - y1 < 10) {{
                        selection = null;
                    }} else {{
                        selection = {{ x1, y1, x2, y2 }};
                    }}
                    showSelection();
                }}
            }}

            mode = 'pan';
            isPanning = false;
            resizeHandle = null;
            startPoint = null;
            startSelection = null;
            container.classList.remove('grabbing');
        }});

        // Handle resizing
        document.querySelectorAll('.handle').forEach(handle => {{
            handle.addEventListener('mousedown', function(e) {{
                if (!selection) return;
                mode = 'resizing';
                resizeHandle = handle.classList[1];
                startSelection = {{ ...selection }};
                e.stopPropagation();
                e.preventDefault();
            }});
        }});

        // Zoom
        container.addEventListener('wheel', function(e) {{
            e.preventDefault();
            const delta = e.deltaY < 0 ? 1.1 : 0.9;
            scale = Math.max(0.1, Math.min(5, scale * delta));
            updateImageSize();
        }}, {{ passive: false }});

        // Keyboard shortcuts
        document.addEventListener('keydown', function(e) {{
            if (e.key === 'Escape') {{
                selection = null;
                showSelection();
                activateTool(null);
            }}
        }});
    </script>
</body>
</html>"""
