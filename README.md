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
- Processes text files using LLMs with configurable prompts
- Converts output to formatted Word (.docx) documents

## Installation

### Ubuntu ARM64 (Recommended)

For Ubuntu ARM64 systems, download the latest release from GitHub:

1. **Download the .deb package** from the [Releases page](https://github.com/dtubb/fichero/releases)
2. **Install the package:**
   ```bash
   sudo dpkg -i fichero_0.1.0.dev1-1~ubuntu-plucky_arm64.deb
   ```
3. **Run Fichero:**
   ```bash
   fichero
   ```

### Development Installation

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

This launches the GUI application directly using Toga, without needing to use Briefcase.

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

## Current Release Status

**v0.1.0.dev1** - Development Release
- ✅ Ubuntu ARM64 (.deb package)
- 🔄 Windows (.exe) - Coming soon
- 🔄 macOS (.dmg) - Coming soon
- 🔄 Linux AppImage - Coming soon

## Building the Native App (Optional)

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

# Create a distributable package (.dmg) of the console app.
briefcase package
```

### Platform Support

The app should be able to be  built for multiple platforms. But, I've only tested macOS.
- **macOS**: `.app` bundle, `.dmg` installer
- **Windows**: `.exe` application, `.msi` installer
- **Linux**: AppImage, native packages

For more information, see the [BeeWare documentation](https://docs.beeware.org/).

The easiest way to use Fichero:

1. **Run the app directly**:
   ```briefcase dev```
2. **Click "Choose Folder"** to select a folder containing your documents
3. **Click "Process"** to start processing
4. The app will:
   - Process all documents in the selected folder
   - Save processed files to your Desktop in a `Fichero_Output_[folder_name]` folder


## Configuration

### Plan.yml files

Fichero  supports multiple formats and features.You can configure this in your `plan.yml` file stored in /src/resources/plans/plan.yml:

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

## Citation

Citation for Fichero:
Tubb, Daniel, and Andrew Janco. "Fichero: Document Processing and Transcription." GitHub, May 9, 2025. https://github.com/dtubb/fichero.
