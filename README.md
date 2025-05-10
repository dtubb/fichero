# Fichero

Fichero processes archival materials (documents in JPG, PDF, TIFF format), and crops, splits, enhances contrast, remvoes bakgrounds, and then transcribes text using AI LLMs, before exporting them to Word documents, with the image of the document on the right verso page, amd the recto page as the text. 

## Features
- Powered by the [Weasel GitHub repository](https://github.com/explosion/weasel) workflow management system.
- Processes archival materials (scanned documents, images, etc.)
- Splits multi-page materials into single pages
- Enhances image quality and removes backgrounds
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
   - `archive-to-word-qwen-max`: Process full documents with Qwen Max model, but requires Alibaba Cloud account and API access;
   - `archive-to-word-qwen-max-segmented`: Process documents in vertical segments with Qwen Max model
   - `archive-to-word-qwen-2b`: Process full documents with Qwen 2B model, running locally. Requires 16 GB M1.
   - `archive-to-word-qwen-2b-segmented`: Process documents in vertical segments with Qwen 2B model. Requires 16 GB M1.
   - `archive-to-word-lmstudio`: Process full documents using LM Studio, with any model. Requires LM Studio to be running locally.
   - `archive-to-word-lmstudio-segmented`: Process documents in vertical segments

3. Run the selected workflow using Weasel:

For example, to process documents in segments using the Qwen 2B model:
```bash
weasel run archive-to-word-qwen-2b-segmented
```

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
