#!/bin/bash

echo "=========================================="
echo "  Socratic Method Bot - Startup Script"
echo "=========================================="
echo ""

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
    echo "✓ Virtual environment activated"
    echo ""
fi

# Check if vLLM is running
echo "Checking vLLM status..."
if curl -s http://localhost:8000/v1/models > /dev/null 2>&1; then
    echo "✓ vLLM is running"
else
    echo "✗ vLLM is not running!"
    echo ""
    echo "Please start vLLM in another terminal:"
    echo "  python -m vllm.entrypoints.openai.api_server --model meta-llama/Meta-Llama-3.1-8B-Instruct --port 8000"
    echo ""
    echo "Note: If you don't have a GPU, vLLM may fail to run properly unless built for CPU."
    echo ""
    read -p "Press Enter after starting vLLM, or Ctrl+C to exit..."
fi

# Check Python dependencies
echo ""
echo "Checking Python dependencies..."
if python3 -c "import fastapi, uvicorn, whisper, speech_recognition, PyPDF2, pyttsx3" 2>/dev/null; then
    echo "✓ All Python dependencies installed"
else
    echo "✗ Missing dependencies!"
    echo ""
    echo "Please install dependencies:"
    echo "  pip install -r requirements.txt"
    echo "  pip install -r requirements_web.txt"
    exit 1
fi

# Create necessary directories
mkdir -p conversations uploads static modules

echo ""
echo "=========================================="
echo "  Starting FastAPI Server..."
echo "=========================================="
echo ""
echo "Access the application at:"
echo "  http://localhost:8000"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Start the server
python3 app.py
