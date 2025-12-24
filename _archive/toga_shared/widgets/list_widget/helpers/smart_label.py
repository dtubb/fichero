"""
SmartLabel - Text processing helper for Canvas-based renderers.

Provides accurate text truncation and wrapping for Canvas.write_text()
with multiple truncation modes and platform-specific font metrics.
"""

import sys
from enum import Enum
from typing import List, Optional, Dict
import logging

logger = logging.getLogger(__name__)


class TruncationMode(Enum):
    """Truncation modes for SmartLabel."""
    END = "end"          # "Long file name here…"
    MIDDLE = "middle"    # "Long file…name.txt"
    WRAP = "wrap"        # Multiline wrapping
    WORD_LIMIT = "words" # "First N words…"


class SmartLabel:
    """
    Text processing helper for Canvas-based renderers.

    Provides accurate text truncation and wrapping using platform-specific
    font metrics. Works with toga.Canvas.write_text() for rendering.

    Example:
        >>> smart_label = SmartLabel(font_size=10)
        >>> truncated = smart_label.truncate("Long file name.txt", max_width=100)
        >>> print(truncated)
        "Long file…txt"

        >>> lines = smart_label.wrap("Long text here", max_width=50)
        >>> print(lines)
        ["Long text", "here"]
    """

    # Default character width multipliers per platform
    # These are conservative estimates (actual width / font_size)
    CHAR_WIDTH_MULTIPLIERS = {
        'darwin': 0.60,   # macOS (SF Pro, Helvetica)
        'win32': 0.65,    # Windows (Segoe UI)
        'linux': 0.62,    # Linux (Ubuntu, DejaVu)
    }

    # Ellipsis character (Unicode)
    ELLIPSIS = "…"

    def __init__(
        self,
        font_family: str = 'SYSTEM',
        font_size: int = 10,
        font_weight: str = 'NORMAL'
    ):
        """
        Initialize SmartLabel with font settings.

        Args:
            font_family: Font family name (default: 'SYSTEM')
            font_size: Font size in points (default: 10)
            font_weight: Font weight ('NORMAL' or 'BOLD') (default: 'NORMAL')
        """
        self.font_family = font_family
        self.font_size = font_size
        self.font_weight = font_weight

        # Character width cache: {char: width_in_pixels}
        self._char_width_cache: Dict[str, float] = {}

        # Get platform-specific character width multiplier
        platform = sys.platform
        self._char_width_multiplier = self.CHAR_WIDTH_MULTIPLIERS.get(
            platform,
            0.62  # Default fallback
        )

        # Adjust for bold (bold is typically ~10% wider)
        if font_weight == 'BOLD':
            self._char_width_multiplier *= 1.1

        logger.debug(
            f"SmartLabel initialized: platform={platform}, "
            f"font_size={font_size}, multiplier={self._char_width_multiplier:.2f}"
        )

    def measure_text(self, text: str) -> float:
        """
        Measure text width using font metrics.

        Currently uses estimated character widths. Future versions may use
        platform-specific APIs (CoreText, GDI+, Pango) for exact measurements.

        Args:
            text: Text to measure

        Returns:
            Width in pixels (float)
        """
        if not text:
            return 0.0

        # Use cached measurements when available
        total_width = 0.0
        for char in text:
            if char not in self._char_width_cache:
                # Estimate character width
                # Most chars are ~0.6x font size, but some are wider/narrower
                if char in 'iIl1!|':
                    # Narrow characters
                    self._char_width_cache[char] = self.font_size * 0.3
                elif char in 'mMwW@':
                    # Wide characters
                    self._char_width_cache[char] = self.font_size * 0.85
                elif char == ' ':
                    # Space
                    self._char_width_cache[char] = self.font_size * 0.25
                else:
                    # Average character
                    self._char_width_cache[char] = self.font_size * self._char_width_multiplier

            total_width += self._char_width_cache[char]

        return total_width

    def truncate(
        self,
        text: str,
        max_width: float,
        mode: TruncationMode = TruncationMode.END
    ) -> str:
        """
        Truncate text to fit within max_width.

        Args:
            text: Text to truncate
            max_width: Maximum width in pixels
            mode: Truncation mode (END, MIDDLE, or WORD_LIMIT)

        Returns:
            Truncated text with ellipsis (…)

        Raises:
            ValueError: If mode is WRAP (use wrap() method instead)
        """
        if not text:
            return ""

        # Check if truncation is needed
        text_width = self.measure_text(text)
        if text_width <= max_width:
            return text

        # Dispatch to mode-specific truncation
        if mode == TruncationMode.END:
            return self._truncate_end(text, max_width)
        elif mode == TruncationMode.MIDDLE:
            return self._truncate_middle(text, max_width)
        elif mode == TruncationMode.WORD_LIMIT:
            raise ValueError("WORD_LIMIT mode requires word_count parameter. Use truncate_words() instead.")
        else:
            raise ValueError(f"Use wrap() for WRAP mode, not truncate()")

    def truncate_words(self, text: str, word_count: int) -> str:
        """
        Truncate text to first N words.

        Args:
            text: Text to truncate
            word_count: Maximum number of words to keep

        Returns:
            Truncated text with ellipsis if truncated
        """
        if not text:
            return ""

        words = text.split()
        if len(words) <= word_count:
            return text

        # Take first N words and add ellipsis
        truncated_words = words[:word_count]
        return " ".join(truncated_words) + self.ELLIPSIS

    def wrap(
        self,
        text: str,
        max_width: float,
        max_lines: Optional[int] = None
    ) -> List[str]:
        """
        Wrap text into multiple lines.

        Args:
            text: Text to wrap
            max_width: Maximum width per line in pixels
            max_lines: Maximum number of lines (None = unlimited)

        Returns:
            List of text lines
        """
        if not text:
            return []

        words = text.split()
        lines = []
        current_line = []
        current_width = 0.0

        space_width = self.measure_text(" ")

        for word in words:
            word_width = self.measure_text(word)

            # Check if adding this word would exceed line width
            potential_width = current_width
            if current_line:
                potential_width += space_width  # Add space before word
            potential_width += word_width

            if potential_width <= max_width or not current_line:
                # Add word to current line
                current_line.append(word)
                current_width = potential_width
            else:
                # Start new line
                lines.append(" ".join(current_line))
                current_line = [word]
                current_width = word_width

                # Check max_lines limit
                if max_lines and len(lines) >= max_lines:
                    # Truncate remaining text with ellipsis
                    if words.index(word) < len(words) - 1:
                        # There are more words, add ellipsis to last line
                        last_line = lines[-1]
                        ellipsis_width = self.measure_text(self.ELLIPSIS)
                        if self.measure_text(last_line) + space_width + ellipsis_width <= max_width:
                            lines[-1] = last_line + " " + self.ELLIPSIS
                        else:
                            # Truncate last line to fit ellipsis
                            lines[-1] = self._truncate_end(last_line, max_width)
                    return lines

        # Add remaining words
        if current_line:
            lines.append(" ".join(current_line))

        return lines

    def _truncate_end(self, text: str, max_width: float) -> str:
        """
        Truncate text with ellipsis at end.

        Args:
            text: Text to truncate
            max_width: Maximum width in pixels

        Returns:
            "Long file name…"
        """
        if not text:
            return ""

        ellipsis_width = self.measure_text(self.ELLIPSIS)

        # Binary search for optimal truncation point
        left, right = 0, len(text)
        best_length = 0

        while left <= right:
            mid = (left + right) // 2
            candidate = text[:mid] + self.ELLIPSIS
            candidate_width = self.measure_text(candidate)

            if candidate_width <= max_width:
                best_length = mid
                left = mid + 1
            else:
                right = mid - 1

        # Safety check - ensure we don't return empty string
        if best_length == 0:
            return self.ELLIPSIS

        return text[:best_length] + self.ELLIPSIS

    def _truncate_middle(self, text: str, max_width: float) -> str:
        """
        Truncate text with ellipsis in middle (Finder-style).

        Preserves file extension if detected.

        Args:
            text: Text to truncate
            max_width: Maximum width in pixels

        Returns:
            "Long file…name.txt"
        """
        if not text:
            return ""

        ellipsis_width = self.measure_text(self.ELLIPSIS)

        # Try to detect file extension (last dot)
        if '.' in text:
            parts = text.rsplit('.', 1)
            name_part = parts[0]
            ext_part = '.' + parts[1]
        else:
            name_part = text
            ext_part = ''

        ext_width = self.measure_text(ext_part)
        available_width = max_width - ellipsis_width - ext_width

        if available_width <= 0:
            # Not enough space, fallback to end truncation
            return self._truncate_end(text, max_width)

        # Split remaining width between start and end of name
        # Finder typically uses 2:1 ratio (more at start)
        start_width = available_width * 0.65
        end_width = available_width * 0.35

        # Binary search for start part
        left, right = 0, len(name_part)
        best_start = 0

        while left <= right:
            mid = (left + right) // 2
            start_candidate = name_part[:mid]
            if self.measure_text(start_candidate) <= start_width:
                best_start = mid
                left = mid + 1
            else:
                right = mid - 1

        # Binary search for end part
        left, right = 0, len(name_part)
        best_end = len(name_part)

        while left <= right:
            mid = (left + right) // 2
            end_candidate = name_part[mid:]
            if self.measure_text(end_candidate) <= end_width:
                best_end = mid
                right = mid - 1
            else:
                left = mid + 1

        # Ensure we don't have overlap
        if best_start >= best_end:
            # Fallback: just use start
            return name_part[:best_start] + self.ELLIPSIS + ext_part

        start_part = name_part[:best_start]
        end_part = name_part[best_end:]

        return start_part + self.ELLIPSIS + end_part + ext_part

    def estimate_line_count(self, text: str, max_width: float) -> int:
        """
        Estimate how many lines text would wrap to.

        Args:
            text: Text to estimate
            max_width: Maximum width per line

        Returns:
            Estimated line count
        """
        lines = self.wrap(text, max_width)
        return len(lines)

    def fits_in_width(self, text: str, max_width: float) -> bool:
        """
        Check if text fits within max_width without truncation.

        Args:
            text: Text to check
            max_width: Maximum width in pixels

        Returns:
            True if text fits, False otherwise
        """
        return self.measure_text(text) <= max_width
