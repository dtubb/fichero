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
   - `archive-to-word-qwen-2b`: Process full documents with Qwen 2B model
   - `archive-to-word-qwen-2b-segmented`: Process documents in vertical segments with Qwen 2B model
   - `archive-to-word-qwen-7b`: Process full documents with Qwen 7B model
   - `archive-to-word-qwen-7b-segmented`: Process documents in vertical segments with Qwen 7B model

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

## Notes

- Full document workflows process the entire page at once, which is faster but may miss some text in complex layouts
- Segmented workflows analyze the document's text layout and split it into vertical segments based on:
  - Text baseline detection
  - Connected component analysis
  - Natural text boundaries
  - Maximum segment height (800px)
  - Overlap between segments (15px) to ensure no text is missed
- The segmentation process includes:
  - Automatic deskewing of text
  - Merging of thin or empty segments
  - Smart cut points between text lines
  - Preservation of document structure
- Word documents include both the processed image and transcribed text in a side-by-side layout

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

## Citation and Credits

Developed by:
- Daniel Tubb
- Andrew Janco

This project uses the following models and tools:

- Qwen2.0-VL-2B-Instruct: [Citation needed]
- Qwen2.0-VL-7B-Instruct: [Citation needed]
- Qwen2.0-VL-Max-Instruct: [Citation needed]

The segmentation and processing pipeline is based on research from:
- Text baseline detection: [Citation needed]
- Connected component analysis: [Citation needed]
- Document structure preservation: [Citation needed]

## License

[Your License Here]

## Contributing

[Your Contributing Guidelines Here]