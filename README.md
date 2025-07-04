# Fichero

Fichero processes archival materials (documents in JPG, PDF, TIFF formats) by cropping, splitting, enhancing contrast, removing backgrounds, and then transcribing text using AI LLMs. The processed documents are exported to Word documents, with the image of the document on the right verso page and the recto page as the text.

Follow along on the Fichero [website](https://www.tubb.ca/fichero/).

Fichero:

- Processes archival materials (scanned documents, images, etc.)
- Splits multi-page materials into single pages
- Enhances image quality and removes backgrounds
- Transcribes text using:
   - Qwen Max (full document or segmented processing)
   - LM Studio Models (full document or segmented processing)
- Cleans and formats transcriptions
- Generates Word documents with a side-by-side layout
- Catalogues the text files using LLMs with configurable prompts
- Converts output to formatted Word (.docx) documents

## Installation

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

3. **Create and activate a virtual environment:**

   **Option 1 - Using venv:**
   ```bash
   cd fichero # to the path where Fichero is installed.
   python -m venv venv
   source venv/bin/activate
   ```

4. **Install Python dependencies:**
```bash
pip install -r requirements.txt
```

## Running Fichero

### Quick Start (GUI Mode - No Briefcase Required)

Run the GUI directly without Briefcase:

```bash
# From the project root directory
python -m src/fichero
```

This launches the GUI application directly using Toga,.

### Command Line Interface (CLI Mode)

Run Fichero from the command line for advanced usage:

```bash
# From the src directory
cd src

# Show all available commands
python -m fichero --help

# Process a single folder
python -m fichero process-folders /path/to/input /path/to/output

# Process folders with a specific workflow
python -m fichero process-folders /path/to/input /path/to/output default

# Prepare folders for processing (first phase)
python -m fichero prepare /path/to/input /path/to/output

# Check worker status
python -m fichero worker-status

# See example usage
python -m fichero example
```

### Available CLI Commands

- **`process-folders`**: Main command to process documents with AI transcription
- **`prepare`**: Prepare folders by copying and organizing files
- **`worker-status`**: Check status of background processing workers
- **`reset-workers`**: Restart all background workers
- **`stop-workers`**: Stop all background workers
- **`purge-tasks`**: Clear all pending processing tasks
- **`example`**: Show detailed usage examples

## Building the Native App (Optional)

Fichero can be built using [BeeWare Briefcase](https://briefcase.readthedocs.io/), which packages Python apps as native applications for multiple platforms.

### Development Mode

Run the app in development mode (faster iteration):

For GUI development, install BeeWare Briefcase.

```bash
pip install briefcase
```

```bash
# Run the GUI app directly
briefcase dev
```

### Building for Distribution

Create a native macOS app:

```bash
# Create the app bundle
briefcase create

# Build the app (compile and package)
briefcase build
```

### Platform Support

The app should build for multiple platforms. But, it is only tested macOS.
- **macOS**: `.app` bundle, `.dmg` installer
- **Windows**: `.exe` application, `.msi` installer
- **Linux**: AppImage, native packages

For more information, see the [BeeWare documentation](https://docs.beeware.org/).

## Configuration

## AI API Key Setup

To transcribe or catalogue with LLM features, you'll need to set up your OpenAI and DashScope API key:

1. Sign up or log in to your Cloud account
2. Navigate to the API Key console 
3. Create an API key
4. Go to Fichero Menu > Settings, then go to AI, and add you API Key. 

## Citation

Citation for Fichero:
Tubb, Daniel, and Andrew Janco. "Fichero: Document Processing and Transcription." GitHub, May 9, 2025. https://github.com/dtubb/fichero.
