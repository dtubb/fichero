#!/bin/bash
# Run async transcription test

if [ -z "$DASHSCOPE_API_KEY" ]; then
    echo "❌ Error: DASHSCOPE_API_KEY environment variable not set"
    echo ""
    echo "Please run with:"
    echo "  DASHSCOPE_API_KEY=your-key-here ./run_async_test.sh"
    echo ""
    echo "Or export it first:"
    echo "  export DASHSCOPE_API_KEY=your-key-here"
    echo "  ./run_async_test.sh"
    exit 1
fi

echo "🔑 Using API key: ${DASHSCOPE_API_KEY:0:10}..."
echo ""

python3 test_async_minimal.py "/Users/dtubb/Documents/fichero/Small Test/LFH_AHJM_DOC10141 small"
