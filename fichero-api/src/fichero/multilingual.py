"""Multilingual baseline for claims, entities, and cross-language retrieval.

Provides:
- Language detection (using cld3/ICU)
- Transliteration-aware alias linking
- Language-specific text normalization
- Cross-language search support
"""

import re
import unicodedata
from dataclasses import dataclass


# ISO 639-1 language codes
SUPPORTED_LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "ar": "Arabic",
    "hi": "Hindi",
    "ru": "Russian",
    "pl": "Polish",
    "tr": "Turkish",
    "vi": "Vietnamese",
    "th": "Thai",
    "sv": "Swedish",
    "da": "Danish",
    "no": "Norwegian",
    "fi": "Finnish",
}

# Try to import cld3 for language detection, fallback to heuristic
try:
    import cld3

    CLD3_AVAILABLE = True
except ImportError:
    CLD3_AVAILABLE = False


@dataclass
class LanguageDetectionResult:
    """Result of language detection."""

    language: str  # ISO 639-1 code
    confidence: float
    is_reliable: bool


def detect_language(text: str) -> LanguageDetectionResult:
    """Detect language of text.

    Uses cld3 if available, otherwise falls back to heuristic detection
    for common languages.

    Args:
        text: Text to analyze

    Returns:
        LanguageDetectionResult with ISO 639-1 code and confidence
    """
    if not text or not text.strip():
        return LanguageDetectionResult("en", 0.0, False)

    # Try cld3 first if available
    if CLD3_AVAILABLE:
        try:
            result = cld3.get_language(text)
            if result:
                lang = result.language[:2]  # cld3 returns longer codes sometimes
                # Validate it's in our supported list
                if lang in SUPPORTED_LANGUAGES:
                    return LanguageDetectionResult(
                        language=lang,
                        confidence=result.probability,
                        is_reliable=result.probability > 0.7,
                    )
        except Exception:
            pass  # Fall through to heuristic

    # Fallback heuristic detection
    return _heuristic_language_detection(text)


def _heuristic_language_detection(text: str) -> LanguageDetectionResult:
    """Simple heuristic language detection based on character patterns."""
    text = text.strip()

    # Japanese (Hiragana, Katakana, CJK)
    if re.search(r"[\u3040-\u309F\u30A0-\u30FF]", text):
        confidence = 0.9 if re.search(r"[\u3040-\u309F]", text) else 0.7
        return LanguageDetectionResult("ja", confidence, confidence > 0.7)

    # Korean (Hangul)
    if re.search(r"[\uAC00-\uD7AF]", text):
        return LanguageDetectionResult("ko", 0.9, True)

    # Chinese (CJK Unified Ideographs)
    if re.search(r"[\u4E00-\u9FFF]", text):
        return LanguageDetectionResult("zh", 0.9, True)

    # Arabic
    if re.search(r"[\u0600-\u06FF]", text):
        return LanguageDetectionResult("ar", 0.9, True)

    # Cyrillic (Russian)
    if re.search(r"[\u0400-\u04FF]", text):
        return LanguageDetectionResult("ru", 0.8, True)

    # Hebrew
    if re.search(r"[\u0590-\u05FF]", text):
        return LanguageDetectionResult("he", 0.9, True)

    # Thai
    if re.search(r"[\u0E00-\u0E7F]", text):
        return LanguageDetectionResult("th", 0.9, True)

    # Hindi/Devanagari
    if re.search(r"[\u0900-\u097F]", text):
        return LanguageDetectionResult("hi", 0.9, True)

    # Default to English for Latin script
    # Could be more sophisticated with n-gram analysis
    return LanguageDetectionResult("en", 0.6, False)


def normalize_text(text: str, language: str) -> str:
    """Normalize text for the given language.

    Applies language-specific normalization rules:
    - Lowercasing for Latin scripts
    - NFKC Unicode normalization
    - Language-specific character handling

    Args:
        text: Text to normalize
        language: ISO 639-1 language code

    Returns:
        Normalized text
    """
    if not text:
        return ""

    # Apply Unicode normalization (NFKC for compatibility)
    text = unicodedata.normalize("NFKC", text)

    # Language-specific handling
    if language in ("en", "es", "fr", "de", "it", "pt", "nl", "sv", "da", "no", "fi"):
        # Latin scripts: lowercase
        text = text.lower()

    elif language == "tr":
        # Turkish: special I handling
        text = text.lower()
        # Turkish dotted/dotless I
        text = text.replace("ı", "i").replace("İ", "i")

    elif language == "de":
        # German: expand umlauts for search
        text = text.replace("ß", "ss")

    elif language in ("ja", "zh", "ko"):
        # CJK: no lowercasing, but remove extra whitespace
        pass

    # Remove extra whitespace
    text = " ".join(text.split())

    return text.strip()


# Transliteration mappings for common cases
# This is a simplified approach - full implementation would use a library like unidecode
TRANSLITERATION_PATTERNS = {
    "ja": {
        # Simplified romaji to hiragana patterns for matching
        "tokyo": "東京",
        "osaka": "大阪",
        "kyoto": "京都",
        "iphone": "アイフォン",
    },
    "ko": {
        # Common Korean transliterations
        "iphone": "아이폰",
        "samsung": "삼성",
    },
}


def get_transliteration_variants(text: str, language: str) -> list[str]:
    """Get transliteration variants for cross-language matching.

    For example, "Tokyo" would return ["東京"] for Japanese.

    Args:
        text: Original text
        language: Source language code

    Returns:
        List of possible transliterations in other scripts
    """
    variants = []

    if not text:
        return variants

    text_lower = text.lower().strip()

    # Check patterns for this language
    if language in TRANSLITERATION_PATTERNS:
        patterns = TRANSLITERATION_PATTERNS[language]
        if text_lower in patterns:
            variants.append(patterns[text_lower])

    # Also check if text matches patterns from other languages
    # (i.e., text might be a transliteration of something else)
    for lang, patterns in TRANSLITERATION_PATTERNS.items():
        if lang != language:
            for latin, native in patterns.items():
                if latin == text_lower:
                    variants.append(native)
                elif text_lower == native:
                    variants.append(latin)

    return list(set(variants))


def find_cross_language_matches(
    query: str,
    candidates: list[tuple[str, str, str]],  # (id, text, language)
    threshold: float = 0.6,
) -> list[tuple[str, float]]:
    """Find matches across languages using normalized comparison.

    Args:
        query: Search query
        candidates: List of (id, text, language) tuples
        threshold: Minimum similarity score

    Returns:
        List of (id, score) tuples for matches above threshold
    """
    if not query or not candidates:
        return []

    # Detect query language
    query_lang = detect_language(query).language
    query_normalized = normalize_text(query, query_lang)

    matches = []

    for item_id, text, lang in candidates:
        if not text:
            continue

        score = calculate_cross_language_similarity(
            query_normalized, query_lang, text, lang
        )

        if score >= threshold:
            matches.append((item_id, score))

    # Sort by score descending
    matches.sort(key=lambda x: x[1], reverse=True)

    return matches


def calculate_cross_language_similarity(
    text1: str, lang1: str, text2: str, lang2: str
) -> float:
    """Calculate similarity between two texts possibly in different languages.

    Uses multiple strategies:
    1. Direct normalized comparison if same language
    2. Transliteration matching
    3. Substring matching
    4. Normalized Levenshtein distance

    Args:
        text1: First text (already normalized)
        lang1: Language of first text
        text2: Second text
        lang2: Language of second text

    Returns:
        Similarity score (0.0 to 1.0)
    """
    if not text1 or not text2:
        return 0.0

    text2_normalized = normalize_text(text2, lang2)

    # Exact match (case insensitive, normalized)
    if text1 == text2_normalized:
        return 1.0

    # Substring match
    if text1 in text2_normalized or text2_normalized in text1:
        return 0.9

    # Transliteration matching
    variants1 = get_transliteration_variants(text1, lang1)
    for variant in variants1:
        if normalize_text(variant, lang2) == text2_normalized:
            return 0.95

    variants2 = get_transliteration_variants(text2_normalized, lang2)
    for variant in variants2:
        if text1 == normalize_text(variant, lang1):
            return 0.95

    # Levenshtein distance for similar languages
    if lang1 == lang2 or {lang1, lang2}.issubset(
        {"en", "es", "fr", "de", "it", "pt", "nl"}
    ):
        distance = levenshtein_distance(text1, text2_normalized)
        max_len = max(len(text1), len(text2_normalized))
        if max_len > 0:
            similarity = 1.0 - (distance / max_len)
            return max(0.0, similarity)

    return 0.0


def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Cost: 0 if same, 1 if different
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (0 if c1 == c2 else 1)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


# Language-specific stemmers (simplified)
STEMMER_SUFFIXES = {
    "en": ["ing", "ed", "s", "es", "ies", "ied", "er", "est", "ly", "tion"],
    "es": ["ando", "iendo", "ado", "ido", "aron", "ieron", "an", "en", "es", "s"],
    "fr": ["ant", "ent", "é", "ée", "és", "ées", "ement", "tion"],
    "de": ["ung", "en", "er", "st", "est"],
}


def stem_word(word: str, language: str) -> str:
    """Simple suffix-based stemming.

    Args:
        word: Word to stem
        language: ISO 639-1 language code

    Returns:
        Stemmed word
    """
    if language not in STEMMER_SUFFIXES:
        return word

    word = word.lower()
    suffixes = STEMMER_SUFFIXES[language]

    # Try removing longest suffix first
    for suffix in sorted(suffixes, key=len, reverse=True):
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            return word[: -len(suffix)]

    return word


def stem_text(text: str, language: str) -> str:
    """Stem all words in text.

    Args:
        text: Text to stem
        language: ISO 639-1 language code

    Returns:
        Stemmed text
    """
    words = text.split()
    stemmed = [stem_word(w, language) for w in words]
    return " ".join(stemmed)
