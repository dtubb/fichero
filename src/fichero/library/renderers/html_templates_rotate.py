"""
Interactive Rotate Viewer Template

Provides rotation controls with:
- Click rotate buttons (90° CW/CCW)
- Visual preview of rotation
- Apply to save new rotation
"""

import base64
from pathlib import Path
from typing import Optional


def get_rotate_viewer(
    image_path: Path,
    current_angle: int = 0,
    title: Optional[str] = None,
    use_base64: bool = True
) -> str:
    """
    Generate HTML for interactive rotation editor.

    Args:
        image_path: Path to original image (before rotation)
        current_angle: Current rotation angle in degrees
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

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: #2c2c2c;
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
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        #imageWrapper {{
            display: flex;
            align-items: center;
            justify-content: center;
            transition: transform 0.3s ease;
        }}
        img {{
            display: block;
            max-width: 90vw;
            max-height: calc(90vh - 60px);
            user-select: none;
            -webkit-user-select: none;
        }}
        /* Toolbar */
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
        .rotation-controls {{
            display: flex;
            gap: 10px;
            align-items: center;
        }}
        .info {{
            color: #ccc;
            font-size: 13px;
            font-family: 'Monaco', 'Menlo', monospace;
        }}
        button {{
            background: #4CAF50;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            display: flex;
            align-items: center;
            gap: 5px;
        }}
        button:hover {{ background: #45a049; }}
        button.secondary {{ background: #666; }}
        button.secondary:hover {{ background: #555; }}
        button:disabled {{
            background: #444;
            color: #888;
            cursor: not-allowed;
        }}
        .rotate-icon {{
            font-size: 18px;
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
        <div class="info">
            <span id="angleDisplay">Current: {current_angle}° | Preview: {current_angle}°</span>
        </div>
        <div class="rotation-controls">
            <button class="secondary" onclick="rotateLeft()">
                <span class="rotate-icon">↺</span> 90° CCW
            </button>
            <button class="secondary" onclick="rotateRight()">
                <span class="rotate-icon">↻</span> 90° CW
            </button>
            <button class="secondary" onclick="resetRotation()">Reset</button>
            <button onclick="applyRotation()" id="applyBtn">Apply Rotation</button>
        </div>
    </div>
    <script>
        const img = document.getElementById('image');
        const wrapper = document.getElementById('imageWrapper');
        const angleDisplay = document.getElementById('angleDisplay');
        const applyBtn = document.getElementById('applyBtn');

        // Rotation state
        const originalAngle = {current_angle};
        let currentRotation = 0;  // Preview rotation (relative to original)

        function updateDisplay() {{
            // Apply rotation transform
            wrapper.style.transform = `rotate(${{currentRotation}}deg)`;

            // Update display
            const totalAngle = (originalAngle + currentRotation) % 360;
            const normalizedAngle = totalAngle < 0 ? totalAngle + 360 : totalAngle;
            angleDisplay.textContent = `Current: ${{originalAngle}}° | Preview: ${{normalizedAngle}}°`;

            // Enable/disable apply button
            applyBtn.disabled = (currentRotation === 0);
        }}

        function rotateLeft() {{
            currentRotation = (currentRotation - 90) % 360;
            updateDisplay();
        }}

        function rotateRight() {{
            currentRotation = (currentRotation + 90) % 360;
            updateDisplay();
        }}

        function resetRotation() {{
            currentRotation = 0;
            updateDisplay();
        }}

        function applyRotation() {{
            if (currentRotation === 0) return;

            const totalAngle = (originalAngle + currentRotation) % 360;
            const normalizedAngle = totalAngle < 0 ? totalAngle + 360 : totalAngle;

            console.log('Applying rotation:', normalizedAngle);

            // TODO: Send to Python backend
            alert('Rotation applied!\\n\\n' +
                  `Original: ${{originalAngle}}°\\n` +
                  `Change: ${{currentRotation}}°\\n` +
                  `New angle: ${{normalizedAngle}}°`);
        }}

        // Keyboard shortcuts
        document.addEventListener('keydown', function(e) {{
            if (e.key === 'ArrowLeft' || e.key === '[') {{
                rotateLeft();
                e.preventDefault();
            }} else if (e.key === 'ArrowRight' || e.key === ']') {{
                rotateRight();
                e.preventDefault();
            }} else if (e.key === 'r' || e.key === 'R') {{
                resetRotation();
                e.preventDefault();
            }}
        }});

        // Initialize
        updateDisplay();
    </script>
</body>
</html>"""
