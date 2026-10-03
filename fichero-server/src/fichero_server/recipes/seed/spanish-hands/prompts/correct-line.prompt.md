---
for_job: correct
written_for: {hf: mlx-community/Qwen2.5-VL-7B-Instruct-4bit}
version: 1
variables: [reading, guideline]
---
You are checking a machine transcription of one line of a historical Spanish hand against the
picture of that line. Keep the spelling and abbreviations exactly as written ({guideline}). Change
only letters the picture shows were misread. Return the corrected line and nothing else.

Machine reading: {reading}
