# Fichero

Fichero processes archival materials (documents in JPG, PDF, TIFF format), and crops, splits, enhances contrast, removes backgrounds, and then transcribes text using AI LLMs, before exporting them to Word documents, with the image of the document on the right verso page, and the recto page as the text.

Fichero uses Beeware's Briefcase, and Toga for native macOS, Windows, Linux, as well as a terminal app.

## Features

Features

- Processes archival materials (scanned documents, images, etc.)
- Splits multi-page materials into single pages
- Enhances image quality and removes backgrounds
- NEW: Support for JPEG XL (JXL) format with transparency for better compression
- NEW: Support for HEIC/HEIF and RAW image formats
- Transcribe text using various AI models:
- Qwen Max (full document or segmented processing)
- LM Studio Models (full document or segmented processing)
- Cleans and format transcriptions
- Generate Word documents with side-by-side layout
- Processes text files using LLMs with configurable prompts.
- Converts LLM JSON summary files to formatted Word (.docx) documents.
- Converts JSON summary files to a single Excel (.xlsx) file (one row per JSON file).
- See each script's --help for full CLI usage and options.

See each script's `--help` for full CLI usage and options.

## Installation



### 🔧 Developer Installation

For command-line usage or contributing to development:

1. **Clone the repository:**
```bash
git clone https://github.com/dtubb/fichero.git
cd fichero
```

2. **Install system dependencies:**

   **On macOS:**
   ```bash
   brew install poppler  # Required for PDF processing
   brew install libjxl   # Optional: For JPEG XL support
   brew install libheif  # Optional: For HEIC/HEIF support
   brew install libraw   # Optional: For RAW format support
   brew install exiftool # Optional: For metadata handling
   ```

   **On Ubuntu/Debian:**
   ```bash
   sudo apt-get install poppler-utils  # Required for PDF processing
   sudo apt-get install libjxl-tools   # Optional: For JPEG XL support
   sudo apt-get install libheif-dev    # Optional: For HEIC/HEIF support
   sudo apt-get install libraw-dev     # Optional: For RAW format support
   sudo apt-get install libexif-dev    # Optional: For metadata handling
   ```

3. **Create and activate a virtual environment:**

   **Option 1 - Using venv:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

4. **Install Python dependencies:**
```bash
pip install -r requirements.txt
```

5. **For GUI development, install BeeWare Briefcase:**
```bash
pip install briefcase
```

## Building the Native App

Fichero is built using [BeeWare Briefcase](https://briefcase.readthedocs.io/), which packages Python apps as native applications for multiple platforms.

### 🏗️ Development Mode

Run the app in development mode (faster iteration):

```bash
# Run the GUI app directly
briefcase dev
```

### 📦 Building for Distribution

Create a native macOS app:

```bash
# Create the app bundle
briefcase create

# Build the app (compile and package)
briefcase build

# Create a distributable package (.dmg)
briefcase package
```



### 🚀 Platform Support

The app can be built for multiple platforms:
- **macOS**: `.app` bundle, `.dmg` installer
- **Windows**: `.exe` application, `.msi` installer
- **Linux**: AppImage, native packages

### 📱 Additional Briefcase Commands

```bash
# Update app code and resources
briefcase update --update-resources

# Run the packaged app
briefcase run

# Build and run in one step
briefcase run --update-resources

# Clean build artifacts
briefcase package --clean
```

For more information, see the [BeeWare documentation](https://docs.beeware.org/).

## Configuration

### Image Output Format

Fichero now supports multiple output formats for background-removed images. You can configure this in your `project.yml`:

```yaml
vars:
  # Image format configuration
  crop_format: "jpg"  # Options: "png", "jxl", "jpg"
  split_format: "jpg"  # Options: "png", "jxl", "jpg"
  rotate_format: "jpg"  # Options: "png", "jxl", "jpg"
  enhance_format: "jpg"  # Options: "png", "jxl", "jpg"
  background_removed_format: "jxl"  # Options: "png" (with transparency), "jxl" (with transparency and better compression), "jpg" (white background)
  segment_format: "png"  # Options: "png", "jxl", "jpg"
```

- **png**: PNG format with transparency support
- **jxl**: JPEG XL format with transparency support and better compression (requires libjxl installed)
- **jpg**: JPEG format with white background (no transparency)

### Supported Input Formats

Fichero supports a wide range of input formats:

- **Common formats**: JPG, PNG, TIFF, PDF
- **HEIC/HEIF**: High Efficiency Image Format (requires libheif)
- **RAW formats**: Camera RAW formats (CR2, NEF, ARW, etc.)
- **JPEG XL**: Next-generation image format (requires libjxl)

The system will automatically handle format conversion and fall back to PNG if the requested format is not supported.

### JPEG XL (JXL) Support

JPEG XL offers superior compression while maintaining transparency. To use JXL format:

1. Install libjxl tools (see Installation section)
2. Set `background_removed_format: "jxl"` in your project.yml
3. The system will automatically fall back to PNG if libjxl is not available


## Usage

The easiest way to use Fichero:

1. **Launch the Fichero app**.
2. **Click "Choose Folder"** to select a folder containing your documents
3. **Click "Process"** to start processing
4. The app will:
   - Process all documents in the selected folder
   - Show real-time progress in a log window
   - Save processed files to your Desktop in a `Fichero_Output_[folder_name]` folder

No configuration needed - the app uses optimized default settings for the best results.

### 🔧 Command-Line Usage (Advanced)

For advanced users who want more control:

1. **Place your archival materials** in the `documents` folder of your project.

2. **Choose a workflow** based on your needs:
   - `archive-to-word-qwen-max`: Process full documents with Qwen Max model, but requires Alibaba Cloud account and API access
   - `archive-to-word-qwen-max-segmented`: Process documents in vertical segments with Qwen Max model
   - `archive-to-word-qwen-2b`: Process full documents with Qwen 2B model, running locally. Requires 16 GB M1
   - `archive-to-word-qwen-2b-segmented`: Process documents in vertical segments with Qwen 2B model. Requires 16 GB M1
   - `archive-to-word-lmstudio`: Process full documents using LM Studio, with any model. Requires LM Studio to be running locally
   - `archive-to-word-lmstudio-segmented`: Process documents in vertical segments

3. **Run the selected workflow** using Weasel:

For example, to process documents in segments using the Qwen 2B model:
```bash
weasel run archive-to-word-qwen-2b-segmented
```

4. **Or use the director script** for parallel processing:
```bash
python -m fichero process-folders /path/to/output archive-to-word-qwen-max-segmented --input-folder /path/to/input
```

## Parallel Processing with fichero_director.py

For processing multiple folders in parallel, use `fichero_director.py`. This script allows you to process multiple folders simultaneously, with each folder running in its own worker process.

### Basic Usage

```bash
python fichero_director.py \
  <output_folder> \
  <template_yml> \
  <workflow_name> \
  [--input-folder <input_folder>] \
  [--num-processors <number>] \
  [--use-weasel/--no-weasel]
```

Where:
- `<output_folder>`: Base folder for output
- `<template_yml>`: Template project.yml file (usually "project.yml")
- `<workflow_name>`: Name of the Weasel workflow to run
- `--input-folder`: Optional: Folder containing subfolders to process. If not provided, will process existing folders in output_folder
- `--num-processors`: Number of parallel processors to use (default: 4)
- `--use-weasel/--no-weasel`: Whether to use Weasel or run scripts directly (default: --use-weasel)

### Example Commands

Process new folders:
```bash
python fichero_director.py \
  "/path/to/output" \
  "project.yml" \
  "archive-to-word-qwen-max-segmented" \
  --input-folder "/path/to/input/folders" \
  --num-processors 4
```

### Features
- Processes multiple folders in parallel
- Shows real-time progress for each folder
- Creates detailed logs for each processed folder
- Handles interruptions gracefully
- Uses APFS cloning on macOS for faster file operations
- Automatically manages worker processes

### Notes
- Each folder will be processed independently with its own project.yml
- Progress is displayed in a live-updating table
- The number of processors should not exceed your system's capabilities
- For Apple Silicon Mac, M1 Mac, a good default is 4-6 processors

## Alibaba API Key Setup

To transcribe with Alibababa features, you'll need to set up your DashScope API key:

1. Sign up or log in to your Alibaba Cloud account
2. Navigate to the DashScope console
3. Create an API key
4. Create a `.env` file in the project root:
```bash
touch .env
```
5. Open the file with TextEdit:
```bash
open -a TextEdit .env
```
6. Add your API key:
```
DASHSCOPE_API_KEY=your_api_key_here
```
7. Save the file

Note: The DashScope API costs money.

## LM Studio Setup

To use the LM Studio workflows, you'll need to:

1. Download and install LM Studio from [lmstudio.ai](https://lmstudio.ai)
2. Download the Qwen 2.5 VL 7B model (or another VL model) in LM Studio:
   - Open LM Studio
   - Go to the "Models" tab
   - Search for "Qwen2.5-VL-3B-Instruct-8bit"
   - Download the model
3. Start the LM Studio server:
   - Go to the "Local Server" tab
   - Click "Start Server"
   - The server will run on `http://localhost:1234` by default
   - The API endpoint for chat completions is `http://localhost:1234/v1/chat/completions`

For Apple Silicon Macs (M1/M2/M3/M4), make sure to:
- Use the MLX version of LM Studio for best performance
- Download the MLX version from the LM Studio website

## Citation

Citation for Fichero:
Tubb, Daniel, and Andrew Janco. "Fichero: Document Processing and Transcription." GitHub, May 9, 2025. https://github.com/dtubb/fichero.
