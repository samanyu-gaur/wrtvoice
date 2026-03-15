# Socratic Method Bot

A web-based application designed to help students refine their essays through Socratic questioning. It utilizes real-time speech transcription (OpenAI's Whisper) and LLM-driven dialogue (vLLM + LLaMA 3.1) to create an interactive tutoring experience.

## 🎯 Features

- **PDF Context**: Upload an essay PDF, and the application extracts the first 500 words to ground the AI's context.
- **Real-time Transcription**: Uses OpenAI's Whisper model for responsive, local speech-to-text.
- **Socratic Dialogue**: Powered by vLLM serving LLaMA 3.1, the bot is prompted to challenge arguments and ask probing questions rather than just providing answers.
- **Conversation Splitting**: Built-in phrase detection segments continuous audio streams based on conversational pauses.
- **Session Logging**: Dialogues are automatically saved as timestamped JSON files and text exports.

## 🏗️ Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Browser   │ ←──→│   FastAPI    │ ←──→│    vLLM     │
│  (WebUI)    │     │   (app.py)   │     │ (Llama 3.1) │
└─────────────┘     └──────────────┘     └─────────────┘
                           ↕
                    ┌──────────────┐
                    │   Whisper    │
                    │  (Local STT) │
                    └──────────────┘
```

## 📋 Prerequisites

1. **Python 3.8+**
2. **vLLM** serving the `meta-llama/Meta-Llama-3.1-8B-Instruct` model locally.
3. **FFmpeg** (for audio processing)
4. **PyAudio** dependencies

### macOS Setup
```bash
brew install ffmpeg
brew install portaudio
```

## 🚀 Installation & Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
pip install -r requirements_web.txt
```

### 2. Start the vLLM Server 
Ensure your local vLLM server is running. If not, start it with:
```bash
python -m vllm.entrypoints.openai.api_server --model meta-llama/Meta-Llama-3.1-8B-Instruct --port 8000
```

### 3. Start the Web Application
```bash
python app.py
```
Navigate to `http://localhost:8000` in your browser.

## 📁 Repository Structure

- `app.py`: The main FastAPI server and WebSocket router.
- `transcribe_demo.py`: The original Whisper base implementation.
- `modules/vllm_client.py`: Custom client for interfacing with the vLLM server.
- `modules/whisper_stt.py`: Handles the real-time speech-to-text pipeline.
- `modules/conversation_manager.py`: Manages session state and JSON logging.
- `static/`: Frontend HTML, CSS, and JavaScript.
- `benchmark_vllm_vs_ollama.py`: A utility script comparing inference backends.

## 🐛 Troubleshooting

### "vLLM not available"
Ensure your vLLM server is active on port 8000 in a separate terminal.

### PyAudio Installation Failing (macOS)
This typically requires the portaudio C library to be installed first:
```bash
brew install portaudio
pip install pyaudio
```

### Whisper Download 
The application downloads the required Whisper model weights on its first run (the `base` model is ~150MB). Subsequent runs will use the cached model.

## 🔒 Privacy & Local Execution

- Temporary PDFs in `uploads/` are deleted automatically after processing.
- The stack is configured for 100% local execution, meaning no audio or text data is sent to external cloud APIs like OpenAI.
