# Frontend Cloud Migration Instructions

Since you are migrating the frontend to **Vercel** and the backend to **Render**, the frontend Javascript files must be updated to target the new remote endpoints instead of `localhost`.

Here are the step-by-step instructions for updating your Vanilla JS logic:

## 1. Define the API Base URL

At the top of your main JS file (e.g., `main.js` or directly inside the `<script>` tag of `conversation.html`), define a constant for the remote backend URL:

```javascript
// Replace with your actual Render deployment URL
const API_BASE_URL = "https://socratic-oracle-backend.onrender.com";
```

## 2. Update Fetch Endpoints

Every `fetch()` call must prefix the local route with `API_BASE_URL`. 

**In file uploads:**
```javascript
// Old
const response = await fetch('/upload-pdf', ...);

// New
const response = await fetch(`${API_BASE_URL}/upload-pdf`, ...);
```

**In session initialization:**
```javascript
// Old
const response = await fetch('/api/sessions', ...);

// New
const response = await fetch(`${API_BASE_URL}/api/sessions`, ...);
```

**For Vision Critiques:**
```javascript
// Old
const response = await fetch('/api/vision/analyze', ...);

// New
const response = await fetch(`${API_BASE_URL}/api/vision/analyze`, ...);
```

## 3. Transition from WebSockets to HTTP Fetch (Optional but Recommended)

In the local setup, the backend used an active WebSocket connection (`/ws/conversation`) to ingest audio chunks.
Since we are using Groq API for Whisper due to Render restrictions, the easiest path is for the frontend to record voice phrases via standard `MediaRecorder`, compile them to a `.webm` or `.wav` blob, and `POST` it to the backend.

### Transcribe Audio Call:
```javascript
async function transcribeAudio(audioBlob) {
    const formData = new FormData();
    formData.append("file", audioBlob, "speech.webm");

    const transcribeRes = await fetch(`${API_BASE_URL}/api/transcribe`, {
        method: "POST",
        body: formData
    });
    
    const data = await transcribeRes.json();
    return data.text; // Send this text to the /api/chat endpoint
}
```

### Send Text to Socratic LLM Call:
Once transcribed, pass the text to our new Socratic chat endpoint:
```javascript
async function generateSocraticResponse(text, imageBase64 = null) {
    const chatRes = await fetch(`${API_BASE_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            session_id: currentSessionId,
            student_input: text,
            image_base64: imageBase64
        })
    });
    
    const data = await chatRes.json();
    return data.response;
}
```

## 4. Deploying to Vercel
1. Ensure your `static/` directory is isolated as its own simple project, or point Vercel's Root Directory setting directly to the `/static` folder.
2. Vercel will serve the `index.html` static file natively without any build commands.
