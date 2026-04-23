"""
Socratic Method Bot - Cloud Refactor
FastAPI server prepared for Render, Vercel, and Supabase.
"""

from fastapi import FastAPI, BackgroundTasks, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import asyncio
import os
import json
import httpx
import traceback
from datetime import datetime, timezone
from typing import Optional

from database import DatabaseManager

app = FastAPI(title="Socratic Method Cloud API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For Vercel frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = DatabaseManager()

# Limit concurrent LLM inferences to avoid OOM on Render
inference_semaphore = None

# --- API Keys ---
HKU_API_KEY = os.getenv("HKU_API_KEY") 

@app.on_event("startup")
async def startup_event():
    global inference_semaphore
    inference_semaphore = asyncio.Semaphore(10)
    
    # --- Environment Variable Validation ---
    print("=" * 50)
    print("🚀 Socratic Oracle - Cloud Startup")
    print("=" * 50)
    
    if not HKU_API_KEY:
        print("❌ CRITICAL: HKU_API_KEY is NOT set! LLM calls will fail.")
    else:
        print(f"✅ HKU_API_KEY loaded ({HKU_API_KEY[:8]}...)")
    
    if not db.db_url:
        print("❌ CRITICAL: SUPABASE_DB_URL is NOT set! Database operations will fail.")
    else:
        print(f"✅ SUPABASE_DB_URL loaded")
    
    print("✅ API Mode Active - No local vLLM/Ollama required")
    print("=" * 50)

@app.get("/health")
async def health_check():
    """Lightweight health check for frontend status indicator."""
    return {
        "status": "healthy", 
        "api_key_set": HKU_API_KEY is not None,
        "db_connected": db.db_url is not None
    }

class SocraticRequest(BaseModel):
    session_id: str
    student_input: str
    image_base64: Optional[str] = None

class CreateSessionRequest(BaseModel):
    pdf_context: str
    pdf_metadata: Optional[dict] = {}


async def call_hku_llm(messages: list, stream: bool = False):
    """Call HKU's API endpoint using httpx."""
    if not HKU_API_KEY:
        raise Exception("HKU_API_KEY not set in Render environment variables")
        
    url = "https://api.hku.hk/openai/deployments/gpt-4.1-nano/chat/completions?api-version=2025-04-01-preview"
    headers = {
        "Content-Type": "application/json",
        "api-key": HKU_API_KEY
    }
    
    payload = {
        "messages": messages,
        "temperature": 0.7,
        "stream": stream
    }

    async with httpx.AsyncClient() as client:
        print(f"[LLM] Sending {len(messages)} messages to HKU API...")
        req = await client.post(url, headers=headers, json=payload, timeout=60.0)
        
        if req.status_code != 200:
            error_body = req.text
            print(f"[LLM] ❌ HKU API returned {req.status_code}: {error_body}")
            raise Exception(f"HKU API error ({req.status_code}): {error_body[:500]}")
        
        print(f"[LLM] ✅ Response received successfully")
        return req.json()

from modules.pdf_parser import PDFParser
import shutil

@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    upload_dir = "uploads"
    os.makedirs(upload_dir, exist_ok=True)
    temp_path = os.path.join(upload_dir, f"temp_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf")
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        parser = PDFParser()
        pdf_context = parser.extract_first_n_words(temp_path, n_words=500)
        pdf_metadata = parser.get_metadata(temp_path)
        return {"success": True, "pdf_context": pdf_context, "metadata": pdf_metadata}
    except Exception as e:
        print(f"[PDF] ❌ Upload error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)

@app.post("/api/sessions")
async def create_session(req: CreateSessionRequest):
    """Initialize a Supabase session with PDF context."""
    try:
        session_id = db.create_session(req.pdf_context, req.pdf_metadata)
        print(f"[SESSION] ✅ Created session {session_id[:8]}...")
        return {"session_id": session_id}
    except Exception as e:
        print(f"[SESSION] ❌ Error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Session creation failed: {str(e)}")

@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    history = db.get_conversation_history(session_id)
    return {"session": session, "history": history}

@app.post("/api/chat")
async def chat_socratic(req: SocraticRequest):
    """
    Main dialogue endpoint:
    Receives user text, applies Socratic prompt, and returns LLM critique.
    """
    print(f"[CHAT] Incoming message for session {req.session_id[:8]}...")
    
    # Validate session exists
    session = db.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session invalid or expired")

    # Save student message to DB
    try:
        db.add_message(req.session_id, "student", req.student_input)
    except Exception as e:
        print(f"[CHAT] ⚠️ DB save warning (student msg): {e}")
        # Non-fatal: continue even if save fails
    
    # Retrieve past context
    history = db.get_conversation_history(req.session_id, limit=5)
    
    # Build OpenAI-compatible message array
    pdf_text = session.get('pdf_context', '') or ''
    system_prompt = (
        "You are a Socratic tutor. Guide the student to answer their own questions. "
        "Do not directly give the answer. Analyze their logic and ask probing questions. "
        f"Context from PDF: {pdf_text[:1000]}"
    )
    
    messages = [{"role": "system", "content": system_prompt}]
    
    for msg in history:
        messages.append({
            "role": "assistant" if msg["speaker"] == "bot" else "user", 
            "content": msg["text"]
        })
        
    messages.append({"role": "user", "content": req.student_input})
    
    # Optional multimodal vision support
    if req.image_base64:
        messages[-1]["content"] = [
            {"type": "text", "text": "Please provide an architectural critique: " + req.student_input},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{req.image_base64}"}}
        ]

    # Concurrency control lock
    async with inference_semaphore:
        try:
            response = await call_hku_llm(messages)
            bot_reply = response["choices"][0]["message"]["content"]
            
            # Log bot response to DB
            try:
                db.add_message(req.session_id, "bot", bot_reply)
            except Exception as db_err:
                print(f"[CHAT] ⚠️ DB save warning (bot msg): {db_err}")
            
            if req.image_base64:
                try:
                    db.log_vision_critique(req.session_id, req.student_input, bot_reply)
                except Exception as vis_err:
                    print(f"[CHAT] ⚠️ Vision log warning: {vis_err}")
                
            return {"response": bot_reply}
        except Exception as e:
            error_detail = traceback.format_exc()
            print(f"[CHAT] ❌ LLM INFERENCE FAILED:\n{error_detail}")
            # Return the actual error so the frontend can display it
            return {"response": None, "error": str(e)}

import speech_recognition as sr
from pydub import AudioSegment
import tempfile

@app.post("/api/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """
    Lightweight transcription fallback using SpeechRecognition (Google Web Speech API).
    Avoids Render RAM limits (no PyTorch) and doesn't require a blocked Groq API key!
    """
    # Create temp files for the incoming audio and the converted WAV
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_in:
        audio_content = await file.read()
        temp_in.write(audio_content)
        temp_in_path = temp_in.name
        
    temp_wav_path = temp_in_path + ".wav"
    
    try:
        # Convert webm/mp4 to WAV format required by SpeechRecognition
        audio = AudioSegment.from_file(temp_in_path)
        audio.export(temp_wav_path, format="wav")
        
        # Transcribe
        recognizer = sr.Recognizer()
        with sr.AudioFile(temp_wav_path) as source:
            recorded_audio = recognizer.record(source)
            text = recognizer.recognize_google(recorded_audio)
            
        return {"text": text}
        
    except sr.UnknownValueError:
        # User didn't say anything or it was unintelligible
        return {"text": ""}
    except Exception as e:
        print(f"[STT] ❌ Transcription error: {e}")
        return {"text": ""}
    finally:
        # Clean up temp files
        if os.path.exists(temp_in_path):
            os.remove(temp_in_path)
        if os.path.exists(temp_wav_path):
            os.remove(temp_wav_path)

if __name__ == "__main__":
    uvicorn.run("app_cloud:app", host="0.0.0.0", port=8000, reload=True)
