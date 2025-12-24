# Replace Empty Test Files with Real Sample Files

## Issue
The current test files for MP3, MP4, and WAV are empty or contain only headers:
- `sample.mp3` - 13 bytes (header only)
- `sample.mp4` - 20 bytes (header only)
- `sample.wav` - 44 bytes (header only)

These files need to be replaced with real, valid sample files for proper testing.

## Requirements
1. **Download real sample files** from reliable sources:
   - MP3: Small audio sample (e.g., 5-10 seconds of music/speech)
   - MP4: Small video sample (e.g., 3-5 seconds with audio)
   - WAV: Small WAV sample (e.g., 2-3 seconds of audio)

2. **Verify file integrity**:
   - Files should be playable
   - Files should have proper metadata
   - Files should be small (< 1MB each)

3. **Update tests** if needed:
   - Verify metadata extraction works with real files
   - Test audio/video duration extraction (if implemented)

## Questions for Human
- Should I download real sample files from the internet?
- Are there specific sample files you prefer to use?
- Should I generate synthetic files instead?
- Any copyright considerations for sample files?

## Priority
**P1 - High**: This is needed for proper audio/video file testing and metadata extraction validation.
