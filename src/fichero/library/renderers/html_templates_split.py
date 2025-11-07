"""
Interactive Split Viewer Template

Provides split adjustment controls with:
- Visual preview of source image with split lines
- Drag split lines to adjust positions
- Add/remove split lines
- Apply to re-split with new positions
"""

import base64
from pathlib import Path
from typing import Optional, List


def get_split_viewer(
    image_path: Path,
    split_positions: List[int],
    title: Optional[str] = None,
    use_base64: bool = True
) -> str:
    """
    Generate HTML for interactive split editor.

    Args:
        image_path: Path to original image (before split)
        split_positions: List of vertical split positions (x coordinates)
        title: Optional title
        use_base64: Encode image as base64 (default True)

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

    # Convert split positions to JavaScript array
    positions_js = str(split_positions)

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
            height: calc(100vh - 100px);
            overflow: auto;
            position: relative;
            cursor: grab;
        }}
        #imageContainer.grabbing {{ cursor: grabbing; }}
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
        /* Split lines */
        .split-line {{
            position: absolute;
            width: 3px;
            background: #4CAF50;
            cursor: ew-resize;
            z-index: 10;
            box-shadow: 0 0 5px rgba(76, 175, 80, 0.5);
        }}
        .split-line:hover {{
            background: #45a049;
            width: 5px;
        }}
        .split-line.dragging {{
            background: #66BB6A;
            width: 5px;
        }}
        /* Split regions (for visual feedback) */
        .split-region {{
            position: absolute;
            border: 2px dashed #888;
            background: rgba(76, 175, 80, 0.05);
            pointer-events: none;
            z-index: 5;
        }}
        /* Toolbar */
        #toolbar {{
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            height: 100px;
            background: #1e1e1e;
            border-top: 1px solid #444;
            padding: 10px 20px;
            z-index: 1000;
        }}
        .toolbar-row {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 10px;
        }}
        .info {{
            color: #ccc;
            font-size: 13px;
            font-family: 'Monaco', 'Menlo', monospace;
        }}
        .controls {{
            display: flex;
            gap: 10px;
            align-items: center;
        }}
        button {{
            background: #4CAF50;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
        }}
        button:hover {{ background: #45a049; }}
        button.secondary {{ background: #666; }}
        button.secondary:hover {{ background: #555; }}
        button:disabled {{
            background: #444;
            color: #888;
            cursor: not-allowed;
        }}
        input[type="number"] {{
            width: 80px;
            padding: 6px;
            background: #333;
            color: #ccc;
            border: 1px solid #555;
            border-radius: 4px;
            font-size: 13px;
        }}
        label {{
            color: #ccc;
            font-size: 13px;
            margin-right: 5px;
        }}
    </style>
</head>
<body>
    <div id="imageContainer">
        <div id="imageWrapper">
            <img id="image" src="{img_src}" alt="{title}">
        </div>
    </div>
    <div id="toolbar">
        <div class="toolbar-row">
            <div class="info">
                <span id="splitInfo">Splits: 0 | Regions: 1</span>
            </div>
            <div class="controls">
                <label>Position:</label>
                <input type="number" id="newPosition" placeholder="x coord" min="0">
                <button class="secondary" onclick="addSplitAtPosition()">Add Split</button>
                <button class="secondary" onclick="addSplitAtCenter()">Add at Center</button>
                <button class="secondary" onclick="clearAllSplits()">Clear All</button>
            </div>
        </div>
        <div class="toolbar-row">
            <div class="info">
                <span id="instructions">Drag split lines to adjust • Click "Add Split" to add more</span>
            </div>
            <div class="controls">
                <button onclick="applySplit()" id="applyBtn">Apply Split</button>
            </div>
        </div>
    </div>
    <script>
        // Image state
        let scale = 1;
        const img = document.getElementById('image');
        const container = document.getElementById('imageContainer');
        const wrapper = document.getElementById('imageWrapper');
        const splitInfo = document.getElementById('splitInfo');
        const applyBtn = document.getElementById('applyBtn');
        const newPositionInput = document.getElementById('newPosition');

        // Split state (in image coordinates)
        let originalSplits = {positions_js};  // Original split positions
        let splits = [...originalSplits];  // Current split positions (editable)

        // Interaction state
        let draggingSplitIndex = null;
        let isPanning = false;
        let panStart = null;
        let scrollStart = null;

        // Initialize
        img.onload = function() {{
            fitToWindow();
            updateDisplay();
        }};

        function fitToWindow() {{
            const containerRect = container.getBoundingClientRect();
            scale = Math.min(
                containerRect.width / img.naturalWidth,
                (containerRect.height - 20) / img.naturalHeight
            );
            updateImageSize();
        }}

        function updateImageSize() {{
            img.style.width = (img.naturalWidth * scale) + 'px';
            img.style.height = (img.naturalHeight * scale) + 'px';
            wrapper.style.width = Math.max(img.naturalWidth * scale, container.clientWidth) + 'px';
            wrapper.style.height = Math.max(img.naturalHeight * scale, container.clientHeight) + 'px';
            updateDisplay();
        }}

        function updateDisplay() {{
            // Remove old split lines and regions
            document.querySelectorAll('.split-line, .split-region').forEach(el => el.remove());

            // Get image position
            const imgRect = img.getBoundingClientRect();
            const wrapperRect = wrapper.getBoundingClientRect();

            // Draw split lines
            splits.forEach((pos, index) => {{
                const line = document.createElement('div');
                line.className = 'split-line';
                line.style.left = (pos * scale) + 'px';
                line.style.top = '0';
                line.style.height = (img.naturalHeight * scale) + 'px';
                line.dataset.index = index;

                // Make draggable
                line.addEventListener('mousedown', startDraggingSplit);

                wrapper.appendChild(line);
            }});

            // Draw split regions
            const positions = [0, ...splits, img.naturalWidth].sort((a, b) => a - b);
            for (let i = 0; i < positions.length - 1; i++) {{
                const region = document.createElement('div');
                region.className = 'split-region';
                region.style.left = (positions[i] * scale) + 'px';
                region.style.top = '0';
                region.style.width = ((positions[i + 1] - positions[i]) * scale) + 'px';
                region.style.height = (img.naturalHeight * scale) + 'px';
                wrapper.appendChild(region);
            }}

            // Update info
            splitInfo.textContent = `Splits: ${{splits.length}} | Regions: ${{splits.length + 1}}`;

            // Enable/disable apply button
            const changed = JSON.stringify(splits.sort()) !== JSON.stringify(originalSplits.sort());
            applyBtn.disabled = !changed;

            // Update input max value
            newPositionInput.max = img.naturalWidth;
        }}

        function getImageCoords(clientX) {{
            const imgRect = img.getBoundingClientRect();
            const x = (clientX - imgRect.left) / scale;
            return Math.max(0, Math.min(img.naturalWidth, x));
        }}

        function startDraggingSplit(e) {{
            draggingSplitIndex = parseInt(e.target.dataset.index);
            e.target.classList.add('dragging');
            e.preventDefault();
            e.stopPropagation();
        }}

        // Pan with Space+drag
        container.addEventListener('mousedown', function(e) {{
            if (e.key === ' ' || e.code === 'Space') {{
                isPanning = true;
                panStart = {{ x: e.clientX, y: e.clientY }};
                scrollStart = {{ x: container.scrollLeft, y: container.scrollTop }};
                container.classList.add('grabbing');
                e.preventDefault();
            }}
        }});

        document.addEventListener('mousemove', function(e) {{
            if (draggingSplitIndex !== null) {{
                const x = getImageCoords(e.clientX);
                splits[draggingSplitIndex] = Math.round(x);
                updateDisplay();
            }} else if (isPanning) {{
                const dx = e.clientX - panStart.x;
                const dy = e.clientY - panStart.y;
                container.scrollLeft = scrollStart.x - dx;
                container.scrollTop = scrollStart.y - dy;
            }}
        }});

        document.addEventListener('mouseup', function() {{
            if (draggingSplitIndex !== null) {{
                document.querySelectorAll('.split-line').forEach(line => {{
                    line.classList.remove('dragging');
                }});
                draggingSplitIndex = null;
            }}
            isPanning = false;
            container.classList.remove('grabbing');
        }});

        // Zoom
        container.addEventListener('wheel', function(e) {{
            e.preventDefault();
            const delta = e.deltaY < 0 ? 1.1 : 0.9;
            scale = Math.max(0.1, Math.min(5, scale * delta));
            updateImageSize();
        }}, {{ passive: false }});

        // Actions
        function addSplitAtPosition() {{
            const pos = parseInt(newPositionInput.value);
            if (isNaN(pos) || pos < 0 || pos > img.naturalWidth) {{
                alert('Please enter a valid position (0-' + img.naturalWidth + ')');
                return;
            }}
            splits.push(pos);
            newPositionInput.value = '';
            updateDisplay();
        }}

        function addSplitAtCenter() {{
            const center = Math.round(img.naturalWidth / 2);
            splits.push(center);
            updateDisplay();
        }}

        function clearAllSplits() {{
            splits = [];
            updateDisplay();
        }}

        function applySplit() {{
            if (splits.length === 0) {{
                alert('No splits defined');
                return;
            }}

            const sortedSplits = [...splits].sort((a, b) => a - b);
            console.log('Applying split:', sortedSplits);

            // TODO: Send to Python backend
            alert('Split applied!\\n\\n' +
                  `Split positions: ${{sortedSplits.join(', ')}}\\n` +
                  `Number of regions: ${{sortedSplits.length + 1}}`);
        }}

        // Keyboard shortcuts
        document.addEventListener('keydown', function(e) {{
            if (e.key === 'c' || e.key === 'C') {{
                addSplitAtCenter();
                e.preventDefault();
            }} else if (e.key === 'Delete' || e.key === 'Backspace') {{
                if (draggingSplitIndex !== null) {{
                    splits.splice(draggingSplitIndex, 1);
                    draggingSplitIndex = null;
                    updateDisplay();
                    e.preventDefault();
                }}
            }}
        }});

        // Initialize
        updateDisplay();
    </script>
</body>
</html>"""
