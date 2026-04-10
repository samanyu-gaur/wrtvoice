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
inference_semaphore = asyncio.Semaphore(10)

class SocraticRequest(BaseModel):
    session_id: str
    student_input: str
    image_base64: Optional[str] = None

class CreateSessionRequest(BaseModel):
    pdf_context: str
    pdf_metadata: Optional[dict] = {}

# --- API Keys ---
HKU_API_KEY = os.getenv("HKU_API_KEY") 
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

async def call_hku_llm(messages: list, stream: bool = False):
    """Call HKU's API endpoint (Llama 3.1 / 3.2 Vision) using httpx."""
    if not HKU_API_KEY:
        raise Exception("HKU_API_KEY not set")
        
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
        req = await client.post(url, headers=headers, json=payload, timeout=60.0)
        req.raise_for_status()
        return req.json()

@app.post("/api/sessions")
async def create_session(req: CreateSessionRequest):
    """Initialize a Supabase session with PDF context."""
    session_id = db.create_session(req.pdf_context, req.pdf_metadata)
    return {"session_id": session_id}

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
    Receives user text (from Whisper frontend), applies Socratic prompt, 
    and returns LLM critique.
    """
    session = db.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session invalid")

    db.add_message(req.session_id, "student", req.student_input)
    
    # Retrieve past context
    history = db.get_conversation_history(req.session_id, limit=5)
    
    # Build OpenAI style messages
    system_prompt = (
        "You are a Socratic tutor. Guide the student to answer their own questions. "
        "Do not directly give the answer. Analyze their logic and ask probing questions. "
        f"Context from PDF: {session.get('pdf_context', '')[:1000]}"
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
            
            # Log to DB
            db.add_message(req.session_id, "bot", bot_reply)
            
            if req.image_base64:
                db.log_vision_critique(req.session_id, req.student_input, bot_reply)
                
            return {"response": bot_reply}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """
    Cloud fallback for Whisper using Groq API (avoids Render OOM).
    """
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not configured")
        
    audio_content = await file.read()
    
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    files = {
        "file": (file.filename, audio_content, file.content_type),
        "model": (None, "whisper-large-v3")
    }
    
    async with httpx.AsyncClient() as client:
        res = await client.post("https://api.groq.com/openai/v1/audio/transcriptions", headers=headers, files=files, timeout=30.0)
        res.raise_for_status()
        return {"text": res.json().get("text", "")}

if __name__ == "__main__":
    uvicorn.run("app_cloud:app", host="0.0.0.0", port=8000, reload=True)
