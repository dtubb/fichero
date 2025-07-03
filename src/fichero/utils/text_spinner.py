"""
Simple text-based spinner utilities for progress indicators.

Provides animated spinners using basic ASCII characters that work across all platforms.
No external dependencies required.
"""

import time
import threading
from typing import Optional

class TextSpinner:
    """Simple text spinner for progress indicators"""
    
    # Different spinner styles
    SPINNERS = {
        'wave': ['·', '•', '●', '•', '·'],
        'circle': ['◐', '◓', '◑', '◒']
    }
    
    def __init__(self, style='circle', speed=0.1):
        self.style = style
        self.speed = speed
        self.frames = self.SPINNERS.get(style, self.SPINNERS['circle'])
        self.current_frame = 0
        self._running = False
        self._thread = None
    
    def get_frame(self) -> str:
        """Get current spinner frame"""
        return self.frames[self.current_frame]
    
    def next_frame(self) -> str:
        """Get next spinner frame"""
        frame = self.frames[self.current_frame]
        self.current_frame = (self.current_frame + 1) % len(self.frames)
        return frame
    
    def start(self):
        """Start the spinner animation"""
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._animate, daemon=True)
            self._thread.start()
    
    def stop(self):
        """Stop the spinner animation"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
    
    def _animate(self):
        """Animation loop"""
        while self._running:
            self.next_frame()
            time.sleep(self.speed)

def get_spinner_frame(style='circle', frame_index=None) -> str:
    """Get a specific spinner frame or current frame"""
    frames = TextSpinner.SPINNERS.get(style, TextSpinner.SPINNERS['circle'])
    if frame_index is None:
        frame_index = int(time.time() * 4) % len(frames)
    return frames[frame_index]

def get_progress_bar(progress: float, width: int = 10, filled_char='█', empty_char='░') -> str:
    """Create a text-based progress bar"""
    if progress < 0:
        progress = 0
    elif progress > 100:
        progress = 100
    
    filled_width = int((progress / 100) * width)
    empty_width = width - filled_width
    
    bar = filled_char * filled_width + empty_char * empty_width
    return f"[{bar}] {progress:.1f}%"

def get_status_with_spinner(status: str, style='circle') -> str:
    """Combine status text with spinner"""
    spinner = get_spinner_frame(style)
    return f"{spinner} {status}"

# Test the spinner
if __name__ == "__main__":
    print("Testing text spinners:")
    
    for style in TextSpinner.SPINNERS.keys():
        print(f"{style}: {get_spinner_frame(style)}")
    
    print("\nTesting progress bars:")
    for progress in [0, 25, 50, 75, 100]:
        print(f"{progress}%: {get_progress_bar(progress)}")
    
    print("\nTesting status with spinner:")
    print(get_status_with_spinner("Processing...")) 