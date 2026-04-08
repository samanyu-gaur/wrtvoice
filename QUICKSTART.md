# Quick Start Guide - Socratic Method Bot

This guide covers how to set up and run the Socratic Method Bot locally.

## Prerequisites Check

Before starting, ensure you have:
✅ **vLLM installed** (or accessible on your network)
✅ **Llama3.1-8B-Instruct** (or a similar instruction-tuned model)
✅ **Whisper dependencies**: (Included in the `transcribe_demo.py` setup)

## Installation (One-time Setup)

```bash
# 1. Install the required Python packages
pip install -r requirements_web.txt

# 2. Install FFmpeg for audio processing (macOS example)
brew install ffmpeg

# 3. Install PyAudio dependencies for microphone access (macOS example)
brew install portaudio
```

## Running the Application

### Option 1: Use the Start Script (Recommended)

I've included a bash script that checks the environment before starting the FastAPI server.
```bash
./start_bot.sh
```

### Option 2: Manual Start

Alternatively, you can run the services manually:
```bash
# Terminal 1: Start the vLLM server
python -m vllm.entrypoints.openai.api_server --model meta-llama/Meta-Llama-3.1-8B-Instruct --port 8000

# Terminal 2: Start the web application
python app.py
```

## How to Use the App

1. **Open your Browser**: Navigate to `http://localhost:8000`.
2. **Upload a PDF**: Drag and drop an essay PDF into the upload area. The application will extract the first 500 words to provide context for the LLM.
3. **Start Session**: Click "Start Session". The Whisper audio model takes a moment to load into memory on the first run. The bot will then provide an initial greeting.
4. **Engage in Dialogue**: Speak into your microphone. The application transcribes your speech in real-time. Once you pause, it sends the transcription to the LLM, which will generate a Socratic question to challenge your arguments.
5. **End Session**: Click "End Session" when finished. Your conversation history is automatically saved to `conversations/<timestamp>.json` and exported as a `.txt` file.

## Testing Individual Components

You can test the distinct modules using these commands:
```bash
# Test the PDF text extraction
python modules/pdf_parser.py path/to/essay.pdf

# Test the vLLM connection
python modules/deliv1_vllm_client.py

# Test the Whisper Speech-to-Text pipeline
python modules/whisper_stt.py

# Test the Text-to-Speech (currently disabled by default)
python modules/tts_engine.py

# Test the JSON Database manager
python modules/conversation_manager.py
```

## Troubleshooting

### vLLM isn't responding
Ensure your vLLM server is running in a separate terminal:
```bash
python -m vllm.entrypoints.openai.api_server --model meta-llama/Meta-Llama-3.1-8B-Instruct --port 8000
```

### Whisper model not found
The first time you run the application, it will download the necessary model weights. The base model is approximately 150MB.

### Microphone not working
If the OS assigns the wrong audio index, list the available microphones by running:
```bash
python modules/whisper_stt.py
```

## Configuration Options

### Changing the Whisper Model (Speed vs Quality)
You can adjust the Whisper model size in `app.py` based on your hardware capabilities:
```python
# Options: tiny, base, small, medium, large
whisper_model = "base"  # Recommended balance of speed and accuracy
```

### Adjusting Silence Detection
The application waits for a brief period of silence before processing your speech. You can adjust this default in `app.py`:
```python
phrase_timeout: float = 2.0  # Faster response
phrase_timeout: float = 5.0  # More patient listening
```
*(There is also a slider on the frontend UI to adjust this setting dynamically).*

### Customizing the Socratic Prompt
To adjust how the bot frames its questions, edit `modules/deliv1_vllm_client.py`:
```python
SOCRATIC_SYSTEM_PROMPT = """
Your custom framing instructions here...
"""
```

## Privacy

- Uploaded PDFs are stored in `uploads/` and deleted immediately after text extraction.
- The application is designed to run entirely locally.
