# Fichero

Fichero is a tool that processes archival materials, and converts them (for now) to transcribed Word documents with the right verso page as the image and the recto page as the text. 

## Features
- Powered by the Weasel workflow management system, developed by Explosion, which provides a flexible way to manage  workflows. More details can be found at [Weasel GitHub repository](https://github.com/explosion/weasel).
- Processes archival materials (scanned documents, images, etc.)
- Splits multi-page materials into single pages
- Enhances image quality and remove backgrounds
- Transcribe text using various AI models:
  - Qwen Max (full document or segmented processing)
  - Qwen 2B (full document or segmented processing)
  - Qwen 7B (full document or segmented processing)
- Cleans and format transcriptions
- Generate Word documents with side-by-side layout

## Installation

1. Clone the repository:
```bash
git clone https://github.com/dtubb/fichero.git
cd fichero
```

2. Install system dependencies:

   **On macOS:**
   ```bash
   brew install poppler  # Required for PDF processing
   ```

   **On Ubuntu/Debian:**
   ```bash
   sudo apt-get install poppler-utils  # Required for PDF processing
   ```

3. Create and activate a virtual environment (choose one option):

   **Option 1 - Using venv:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

   **Option 2 - Using conda:**
   ```bash
   conda create -n fichero python=3.10
   conda activate fichero
   ```

4. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

1. Place your archival materials in the `documents` folder of your project.

2. Choose a workflow based on your needs:
   - `archive-to-word-qwen-max`: Process full documents with Qwen Max model
   - `archive-to-word-qwen-max-segmented`: Process documents in vertical segments with Qwen Max model
   - `archive-to-word-qwen-2b`: Process full documents with Qwen 2B model, running locally. Requires 16 GB M1.
   - `archive-to-word-qwen-2b-segmented`: Process documents in vertical segments with Qwen 2B model. Requires 16 GB M1.
   - `archive-to-word-qwen-7b`: Process full documents with Qwen 7B model (Untested)
   - `archive-to-word-qwen-7b-segmented`: Process documents in vertical segments with Qwen 7B model (Untested)
   - `archive-to-word-lmstudio`: Process full documents using LM Studio with Qwen 2.5 VL 7B model. Requires LM Studio to be running locally.
   - `archive-to-word-lmstudio-segmented`: Process documents in vertical segments using LM Studio with Qwen 2.5 VL 7B model. Requires LM Studio to be running locally.

3. Run the selected workflow using Weasel:
```bash
weasel run archive-to-word-qwen-max
```

For example, to process documents in segments using the Qwen 2B model:
```bash
weasel run archive-to-word-qwen-2b-segmented
```

## Workflow Steps

Each workflow follows these general steps:
1. Build document manifest
2. Crop and split materials
3. Rotate and enhance images
4. Remove backgrounds
5. Transcribe text (full document or in vertical segments)
6. Clean and format text
7. Generate Word documents

## API Key Setup

To use the transcription features, you'll need to set up your DashScope API key:

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

Note: The DashScope API is a paid service. Please check their pricing page for current rates.

## LM Studio Setup

To use the LM Studio workflows, you'll need to:

1. Download and install LM Studio from [lmstudio.ai](https://lmstudio.ai)
2. Download the Qwen 2.5 VL 7B model in LM Studio:
   - Open LM Studio
   - Go to the "Models" tab
   - Search for "qwen2.5-vl-7b-instruct"
   - Download the model
3. Start the LM Studio server:
   - Go to the "Local Server" tab
   - Click "Start Server"
   - The server will run on `http://localhost:1234` by default
   - The API endpoint for chat completions is `http://localhost:1234/v1/chat/completions`

Note: LM Studio requires significant system resources. For optimal performance:
- 16GB RAM minimum
- M1/M2 Mac or equivalent GPU
- Keep LM Studio running while using the workflows

For Apple Silicon Macs (M1/M2), make sure to:
- Use the MLX version of LM Studio for best performance
- Download the MLX version from the LM Studio website
- The MLX version is optimized for Apple's Neural Engine

## Citation

Citation for Fichero:
Tubb, Daniel, and Andrew Janco. "Fichero: Document Processing and Transcription." GitHub, May 9, 2025. https://github.com/dtubb/fichero.