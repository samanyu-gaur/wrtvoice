# Real-Time Socratic Bot (Development En-route)

This repository contains my ongoing work on a real-time Socratic AI tutor.

### Current Progress:
- [x] Establish a proof-of-concept for a conversational bot running entirely on open-source local models.
- [x] Implement a reliable speech-to-text pipeline using OpenAI's Whisper model.
- [x] Migrate backend LLM processing from Ollama to **vLLM** (using Llama 3.1) to support necessary concurrency and lower latency.
- [ ] Evaluate additional open-source models (Mistral, Llama 3.3, etc.)

## Audio Pipeline Notes

![Demo gif](demo.gif)

The application utilizes real-time speech-to-text with OpenAI's Whisper model. It continuously records audio in a background thread and concatenates the raw bytes until it detects an acceptable pause in speech, at which point the phrase is dispatched for processing.

To run the application, install the dependencies:
```bash
pip install -r requirements.txt
```

Whisper requires the command-line tool [`ffmpeg`](https://ffmpeg.org/) for audio processing. You can install it via your preferred package manager:

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install ffmpeg

# Arch Linux
sudo pacman -S ffmpeg

# macOS (Homebrew)
brew install ffmpeg

# Windows (Chocolatey)
choco install ffmpeg

# Windows (Scoop)
scoop install ffmpeg
```

For more details on the original Whisper implementation this builds upon, please refer to: https://github.com/openai/whisper

*(The code in this repository is public domain.)*