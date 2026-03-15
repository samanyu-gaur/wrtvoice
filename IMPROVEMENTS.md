# Recent Improvements

This log details the recent changes made to the application, primarily focusing on the vLLM migration and UX updates.

## Changes Made (Latest Session)

### 1. 🚀 Migrating from Ollama to vLLM

**The Problem**: Our initial prototype used Ollama, which processes requests sequentially. This caused significant latency issues when handling multiple concurrent requests, making it unsuitable for a classroom deployment.
**The Fix**: I migrated the backend engine from Ollama to vLLM to utilize continuous batching.

**What was changed**:
- Replaced `modules/ollama_client.py` with a new `modules/vllm_client.py`.
- Adopted the official `openai` Python SDK since vLLM provides an OpenAI-compatible API. This simplified the code by removing the need for custom JSON streaming parsers.
- Updated `app.py` to use `VLLMClient` without altering the existing Whisper WebSocket logic.

**The Result**: Time-To-First-Token latency dropped from ~0.65s to 0.25s, and throughput increased significantly (up to ~71 tokens/second). 

---

### 2. 🔇 Disabled TTS

**The Problem**: The default `pyttsx3` voice sounded unnatural and interrupted the conversational flow.
**The Fix**: I have temporarily disabled the text-to-speech functionality.

**What was changed**:
- `app.py:38` - Commented out the `tts_engine` initialization.
- Commented out the `tts_engine.speak_async()` call in the websocket stream loop.

**Future Plans**: I plan to explore more natural-sounding alternatives later, such as `gTTS` or `coqui-TTS`.

---

### 3. ✨ Better UI Status Indicators

**The Problem**: The frontend UI previously only displayed "Listening...", making it difficult to tell if the bot was transcribing or generating a response.
**The Fix**: I implemented distinct visual status indicators.

**The New Flow**:
```
Listening... → Analyzing... → Responding... → Listening...
     ↓              ↓              ↓               ↓
  (Recording)  (Transcribing) (Bot generating) (Ready again)
```

**What was changed**:
- Added explicit WebSocket status messages when the backend changes state.
- Updated `conversation.html` to handle these status payloads and display animated UI dots during the "Analyzing..." phase.

---

### 4. 📝 Word-by-Word Streaming Responses

**The Problem**: Bot responses were appearing all at once after a noticeable delay.
**The Fix**: I enabled the `stream=True` flag in the vLLM wrapper to stream the output through the WebSocket.

**The Result**: The frontend now receives `bot_response_chunk` messages and displays the text token-by-token. This makes the interaction feel much more responsive and natural.

---

### 5. ⏱️ Reduced Pause Timeout (Configurable)

**The Problem**: The system waited for 5 seconds of silence before processing the audio, which felt too slow for a natural conversation.
**The Fix**: I reduced the default timeout to 2 seconds and made it user-configurable via a UI slider.

**What was changed**:
- Added a `phrase_timeout` slider to the PDF upload interface.
- Users can now adjust the timeout from 1.0s to 5.0+ seconds based on their speaking pace.

---

## How to Test

1. **Start the vLLM Server** in one terminal:
   ```bash
   python -m vllm.entrypoints.openai.api_server --model meta-llama/Meta-Llama-3.1-8B-Instruct --port 8000
   ```
2. **Start the backend** in another terminal:
   ```bash
   ./start_bot.sh
   # (or python app.py)
   ```
3. Open the browser, upload an essay PDF, and adjust the timeout slider before clicking Start. You should see the streaming text and the new status indicators functioning.
