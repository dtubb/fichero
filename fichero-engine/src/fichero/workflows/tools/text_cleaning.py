"""Deterministic text cleaning utilities for workflow tools."""

from __future__ import annotations

import re


def clean_ocr_text(text: str) -> str:
    """Clean OCR/transcription text with deterministic rules only."""
    return TextCleaner.clean_text(text)


class TextCleaner:
    """Pure string-to-string cleanup pipeline."""

    _LINE_REPLACEMENTS = (
        (re.compile(r"\bINTENDE\s+ICIA\b", flags=re.IGNORECASE), "INTENDENCIA"),
        (re.compile(r"\bCIBCEITO\b", flags=re.IGNORECASE), "CIRCUITO"),
        (re.compile(r"\bISTMIN\b", flags=re.IGNORECASE), "ISTMINA"),
        (re.compile(r"\bTTP\.", flags=re.IGNORECASE), "TIP."),
        (re.compile(r"\bDEL\s+CHOCO\b", flags=re.IGNORECASE), "DEL CHOCÓ"),
    )

    @staticmethod
    def remove_pathological_patterns(text: str) -> str:
        """Remove patterns that can cause expensive regex behavior."""
        text = re.sub(r"(\[Guess:[^\]]*\]\s*){3,}", "", text, flags=re.IGNORECASE)
        text = re.sub(r"(\b\w+\b\s*){20,}", "", text)

        lines = text.splitlines()
        clean_lines: list[str] = []
        for line in lines:
            if len(line) > 100:
                words = line.split()
                if len(words) > 50:
                    word_counts: dict[str, int] = {}
                    for word in words:
                        word_counts[word] = word_counts.get(word, 0) + 1
                    max_count = max(word_counts.values()) if word_counts else 0
                    if max_count > len(words) * 0.5:
                        continue
            clean_lines.append(line)

        return "\n".join(clean_lines)

    @staticmethod
    def remove_ocr_garbage_lines(text: str) -> str:
        """Drop obvious OCR garbage while preserving plausible content lines."""
        lines = text.splitlines()
        kept: list[str] = []

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                kept.append("")
                continue

            # Keep plausible year-only lines (timeline-relevant).
            if re.fullmatch(r"(1[5-9]\d{2}|20\d{2})", line):
                kept.append(line)
                continue

            letters = sum(1 for ch in line if ch.isalpha())
            digits = sum(1 for ch in line if ch.isdigit())
            alnum = sum(1 for ch in line if ch.isalnum())
            non_space = sum(1 for ch in line if not ch.isspace())
            words = [w for w in re.split(r"\s+", line) if w]
            alpha_words = [w for w in words if sum(c.isalpha() for c in w) >= 2]

            if non_space == 0:
                kept.append("")
                continue

            letter_ratio = letters / non_space
            digit_ratio = digits / non_space
            alpha_word_ratio = (len(alpha_words) / len(words)) if words else 0.0

            # Drop extreme repeated-char lines such as "000000000000000000".
            collapsed = re.sub(r"\s+", "", line)
            if len(collapsed) >= 10 and len(set(collapsed)) <= 2:
                continue

            # Drop very short pure number lines (page noise / OCR residue).
            if re.fullmatch(r"\d{1,8}", line):
                continue

            # Drop symbol/digit soup lines with too little alphabetic signal.
            if digit_ratio >= 0.4 and letter_ratio < 0.35 and alpha_word_ratio < 0.5:
                continue

            # Lines like "..." are non-content separators.
            if re.fullmatch(r"[.\-_=:;,*]{3,}", line):
                continue

            # Keep line by default when it has meaningful alphabetic content.
            if letters >= 3 or alnum >= 3:
                kept.append(line)

        return "\n".join(kept)

    @staticmethod
    def normalize_obvious_ocr_tokens(text: str) -> str:
        """Apply narrow OCR token corrections with low false-positive risk."""
        normalized_lines: list[str] = []
        for line in text.splitlines():
            normalized = line
            for pattern, replacement in TextCleaner._LINE_REPLACEMENTS:
                normalized = pattern.sub(replacement, normalized)
            normalized_lines.append(normalized)
        return "\n".join(normalized_lines)

    @staticmethod
    def remove_specific_phrases(text: str) -> str:
        """Remove common OCR/LLM wrapper phrases and formatting noise."""
        phrases_to_remove = [
            "handwritten document with",
            "extracted text is",
            "here is the text",
            "plaintext",
            "say nothing else",
            "image of a sheet",
            "piece of parchment",
            "extracted line by line",
            "note:",
            "here it is",
            "in black ink",
            "visible text on the",
            "original document to be preserved",
            "appears damaged or incomplete",
            "difficult to read",
            "poor resolution",
            "cannot be discerned",
            "parts of the text are damaged",
            "cannot be fully interpreted",
            "visible wear and tear",
            "unknown language or script",
            "cursive script",
            "aged and worn",
            "faint lines or patterns",
            "scan of handwritten text",
            "line by line",
            "let me know",
            "help analyze",
            "help with that",
            "ayudarte con eso",
            "provide more details",
            "clarify what you",
            "text on the parchment",
            "text on the paper",
            "text starts with",
            "document says",
            "extracted text",
            "note mentions",
            "following text",
            "document reads",
            "handwriting is difficult",
            "I am sorry, but I cannot assist with that",
            "I cannot assist with that",
            "sorry, but I cannot assist",
            "I'm sorry, I cannot assist",
            "I am unable to assist",
            "I can't assist with that",
            "Lo siento, no puedo ayudar",
            "from the image",
            "as follows",
            "as follows:",
            "is as follows",
            "is as follows:",
            "are as follows",
            "are as follows:",
            "```",
            "Document Text",
            "reads as follows",
        ]

        for phrase in phrases_to_remove:
            pattern = phrase.replace(" ", r"\s+")
            pattern = f".*?{pattern}.*?[.:]?"
            text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)

        cleanup_patterns = [
            r"(?:here|this)\s+(?:is|are)\s+(?:the|an?)\s+(?:text|document|image).*?[.:]",
            r"(?:the|this)\s+(?:text|document|image)\s+(?:shows|contains|has|is).*?[.:]",
            r"(?:please|kindly)\s+(?:note|be aware|let me know).*?[.:]",
            r"(?:I can|I will|I could)\s+(?:help|assist).*?[.:]",
            r"(?:due to|because of)\s+(?:the|its)\s+(?:condition|state|quality).*?[.:]",
            r"(?:some|many|several)\s+(?:parts?|sections?|areas?)\s+(?:are|is)\s+(?:damaged|worn|faded).*?[.:]",
            r"(?:I am|I'm)?\s*(?:sorry|apolog[a-z]+),?\s*(?:but|however)?\s*(?:I|we)\s*(?:can(?:no)?t|am unable to)\s*(?:help|assist)",
            r"(?:from|in|on)\s+(?:the|this)\s+(?:image|page|document)[:.]?\s*",
            r"(?:is|are|reads?)\s+as\s+follows[:.]?\s*",
            r"[-]{3,}\s*",
            r"(?:^|\n)\s*[\":]\s*(?:\n|$)",
            r"(?:^|\n)\s+(?:\n|$)",
            r"\n{3,}",
            r"^line\s+\d+:\s*",
            r"(?:^|\n)(?:line\s+)?\d+:\s*(?:\n|$)",
            r"```.*?```",
        ]
        for pattern in cleanup_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.MULTILINE)

        lines = text.splitlines()
        clean_lines: list[str] = []
        for line in lines:
            clean_line = re.sub(r"\s+", " ", line).strip()
            if clean_line:
                clean_lines.append(clean_line)
            elif clean_lines and clean_lines[-1]:
                clean_lines.append("")
        return "\n\n".join(line for line in clean_lines if line or clean_lines[-1]).strip()

    @staticmethod
    def remove_repeated_phrases(text: str, min_phrase_length: int = 5) -> str:
        lines = text.splitlines()
        clean_lines: list[str] = []
        previous_phrases: set[str] = set()
        for line in lines:
            words = line.split()
            clean_line: list[str] = []
            i = 0
            while i < len(words):
                phrase = " ".join(words[i:i + min_phrase_length])
                if phrase not in previous_phrases:
                    clean_line.append(" ".join(words[i:i + min_phrase_length]))
                    previous_phrases.add(phrase)
                i += min_phrase_length
            clean_lines.append(" ".join(clean_line))
        return "\n".join(clean_lines)

    @staticmethod
    def remove_repeated_words(text: str) -> str:
        lines = text.splitlines()
        clean_lines: list[str] = []
        for line in lines:
            words = line.split()
            clean_line: list[str] = []
            previous_word = ""
            for word in words:
                if word.lower() != previous_word.lower():
                    clean_line.append(word)
                previous_word = word
            clean_lines.append(" ".join(clean_line))
        return "\n".join(clean_lines)

    @staticmethod
    def combine_single_word_paragraphs(text: str) -> str:
        lines = text.splitlines()
        combined_lines: list[str] = []
        current_line: list[str] = []
        for line in lines:
            if len(line.split()) == 1:
                current_line.append(line)
            else:
                if current_line:
                    combined_lines.append(" ".join(current_line))
                    current_line = []
                combined_lines.append(line)
        if current_line:
            combined_lines.append(" ".join(current_line))
        return "\n".join(combined_lines)

    @staticmethod
    def split_long_lines(text: str, max_length: int = 72) -> str:
        lines = text.splitlines()
        wrapped_lines: list[str] = []
        for line in lines:
            if len(line) <= max_length:
                wrapped_lines.append(line)
                continue
            current_line = ""
            words = line.split()
            for word in words:
                test_line = f"{current_line} {word}".strip()
                if len(test_line) <= max_length:
                    current_line = test_line
                else:
                    if current_line:
                        wrapped_lines.append(current_line)
                    current_line = word
            if current_line:
                wrapped_lines.append(current_line)
        return "\n".join(wrapped_lines)

    @staticmethod
    def clean_line_spacing(text: str) -> str:
        lines = text.splitlines()
        cleaned_lines = [re.sub(r"\s+", " ", line).strip() for line in lines]
        text = "\n".join(cleaned_lines)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def clean_text(text: str) -> str:
        """Run deterministic cleaning passes in fixed order."""
        text = TextCleaner.remove_pathological_patterns(text)
        text = TextCleaner.remove_ocr_garbage_lines(text)
        text = TextCleaner.normalize_obvious_ocr_tokens(text)
        text = TextCleaner.remove_specific_phrases(text)
        text = TextCleaner.combine_single_word_paragraphs(text)
        text = TextCleaner.remove_repeated_phrases(text)
        text = TextCleaner.remove_repeated_words(text)
        text = TextCleaner.split_long_lines(text, max_length=72)
        text = TextCleaner.clean_line_spacing(text)
        return text.strip()
