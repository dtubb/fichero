"""
Simple text-based spinner utilities for progress indicators. Provides animated spinners using basic ASCII characters that work across all platforms.

Refactored July 6, 2025, to remove redundant code.
"""

import time

def get_spinner_frame(style='circle', frame_index=None) -> str:
    """Get a specific spinner frame or current frame"""
    frames = ['◐', '◓', '◑', '◒']
    if frame_index is None:
        frame_index = int(time.time() * 4) % len(frames)
    return frames[frame_index]

# Test the spinner
if __name__ == "__main__":
    print("Testing text spinner:")
    print(f"circle: {get_spinner_frame('circle')}") 