# Fichero Development Tools

This directory contains development and build tools for the Fichero project.

## iOS Icon Generator

### `generate_ios_icons.py`

A Python script that generates all required iOS app icon sizes from the main `fichero.png` icon file.

**Usage:**
```bash
# From the project root (fichero directory)
python tools/generate_ios_icons.py

# Or using the shell wrapper
./tools/generate_ios_icons.sh
```

**What it does:**
- Takes the main `fichero.png` icon from `src/fichero/resources/icons/`
- Generates 16 different icon sizes required by iOS:
  - 20px, 29px, 40px, 58px, 60px, 76px, 80px, 87px
  - 120px, 152px, 167px, 180px, 640px, 1024px, 1280px, 1920px
- Saves them as `fichero-{size}.png` in the same directory
- Uses high-quality LANCZOS resampling for optimal results

**Requirements:**
- Python 3.6+
- Pillow (PIL) library
- Source icon file: `src/fichero/resources/icons/fichero.png`

**Why this is needed:**
Briefcase requires specific icon sizes for iOS packaging. Without these, you'll see warnings like:
```
Unable to find src/fichero/resources/icons/fichero-20.png for 20px application icon; using default
```

### `generate_ios_icons.sh`

A shell script wrapper that makes it easy to run the icon generator from the project root.

**Usage:**
```bash
./tools/generate_ios_icons.sh
```

## When to run

Run the icon generator:
- After updating the main `fichero.png` icon
- Before building for iOS
- When you see icon warnings during `briefcase dev`

The generated icons will eliminate the icon warnings and ensure proper iOS packaging. 