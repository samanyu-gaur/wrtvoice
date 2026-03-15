"""
Deliverable 3 - Vision Routes
================================
FastAPI routes for the visual design critique extension.

What this does:
    Adds two API endpoints:
      POST /api/vision/analyze         -- accepts image + text, returns
                                          a Socratic design critique.
      POST /api/vision/analyze-stream  -- same, but streams the response
                                          via Server-Sent Events (SSE).

    Images are saved per-session under uploads/sessions/<session_id>/ so
    they can be referenced in the conversation JSON later.

What I learned:
    - FastAPI's UploadFile + File(...) combo handles multipart form data
      painlessly.  The file is spooled to disk automatically for large
      uploads, which is exactly what you want for high-res architectural
      drawings.
    - Server-Sent Events (SSE) via StreamingResponse are simpler than
      WebSockets for a one-directional stream (server -> client).  You
      do not need to manage connection state or heartbeats.
    - Storing uploaded images on the filesystem (not in the database) is
      fine for a pilot.  If you ever need to serve images across multiple
      servers, move to S3 or a shared NFS mount.

Author: Akshay T P
Date: March 2025
"""

import os
import shutil
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from modules.deliv3_vision_client import VisionClient

# ---------------------------------------------------------------------------
# DESIGN DECISION: multipart form upload vs. base64 in JSON body
# ---------------------------------------------------------------------------
# We chose multipart form upload (UploadFile) for the image.
#
# Alternative: have the client base64-encode the image and send it in a
#              JSON POST body alongside the text.
#   Pros:  simpler API surface (single content type), easier to test with
#          curl or Postman by pasting JSON.
#   Cons:  base64 encoding inflates the payload by ~33%.  For a 5 MB
#          architectural rendering, that is an extra 1.7 MB of network
#          transfer.  Multipart is the standard approach for file uploads.
#
# Alternative 2: presigned URL upload (S3-style):
#   Pros:  decouples upload from inference; client uploads directly to
#          storage, then sends the URL to the API.
#   Cons:  requires an object store (S3, MinIO); adds complexity for a
#          pilot that runs on a single server.
#
# Verdict: multipart upload is the pragmatic choice.
# ---------------------------------------------------------------------------


# The VisionClient instance is injected at startup via init_vision_routes().
_vision_client: Optional[VisionClient] = None
_upload_base_dir: str = "uploads/sessions"


def init_vision_routes(
    vision_client: VisionClient,
    upload_dir: str = "uploads/sessions"
) -> None:
    """
    Inject dependencies.  Called once during app startup.

    Args:
        vision_client: an initialized VisionClient instance.
        upload_dir:    root directory for per-session image storage.
    """
    global _vision_client, _upload_base_dir
    _vision_client = vision_client
    _upload_base_dir = upload_dir
    os.makedirs(upload_dir, exist_ok=True)


router = APIRouter(prefix="/api/vision", tags=["vision"])


def _save_upload(file: UploadFile, session_id: str) -> str:
    """
    Save an uploaded image to disk under the session directory.

    Returns the path relative to the project root.
    """
    session_dir = os.path.join(_upload_base_dir, session_id)
    os.makedirs(session_dir, exist_ok=True)

    safe_name = (
        f"{datetime.now(timezone.utc).strftime('%H%M%S')}_"
        f"{file.filename.replace(' ', '_')}"
    )
    dest = os.path.join(session_dir, safe_name)

    with open(dest, "wb") as buf:
        shutil.copyfileobj(file.file, buf)

    return dest


@router.post("/analyze")
async def analyze_image(
    image: UploadFile = File(...),
    text: str = Form(""),
    session_id: str = Form(""),
):
    """
    Accept an architectural image and optional text commentary, then
    return a Socratic design critique from the vision-language model.

    Form fields:
        image       -- the image file (PNG, JPEG, etc.)
        text        -- student's textual commentary or transcribed speech
        session_id  -- (optional) session ID for file storage grouping

    Returns:
        JSON with 'response' containing the critique text.
    """
    if _vision_client is None:
        raise HTTPException(status_code=503,
                            detail="Vision service not initialized")

    # Validate file type
    allowed = {"image/png", "image/jpeg", "image/jpg", "image/webp",
               "image/gif", "image/bmp", "image/tiff"}
    if image.content_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type: {image.content_type}. "
                   f"Accepted: {', '.join(sorted(allowed))}"
        )

    try:
        # Read and encode image
        image_bytes = await image.read()
        image_base64 = VisionClient.encode_bytes_to_base64(image_bytes)

        # Optionally save the file for later reference
        if session_id:
            saved_path = _save_upload(image, session_id)
        else:
            saved_path = None

        # Run inference (blocking call -- the session manager semaphore
        # should wrap this at a higher level in app.py).
        result = _vision_client.analyze_image(
            image_base64=image_base64,
            student_text=text,
        )

        return {
            "success": not result.get("error", False),
            "response": result.get("response", ""),
            "saved_path": saved_path,
        }

    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"Vision analysis failed: {str(e)}")


@router.post("/analyze-stream")
async def analyze_image_stream(
    image: UploadFile = File(...),
    text: str = Form(""),
    session_id: str = Form(""),
):
    """
    Streaming variant of /analyze.  Returns the critique as Server-Sent
    Events (SSE) so the frontend can display tokens as they arrive.

    The event stream format is:
        data: {"chunk": "..."}
        ...
        data: {"done": true, "full_response": "..."}
    """
    if _vision_client is None:
        raise HTTPException(status_code=503,
                            detail="Vision service not initialized")

    # Validate image type (same as above)
    allowed = {"image/png", "image/jpeg", "image/jpg", "image/webp",
               "image/gif", "image/bmp", "image/tiff"}
    if image.content_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type: {image.content_type}"
        )

    image_bytes = await image.read()
    image_base64 = VisionClient.encode_bytes_to_base64(image_bytes)

    if session_id:
        _save_upload(image, session_id)

    async def event_generator():
        """Yield SSE-formatted chunks from the VLM."""
        import json as _json

        full_response = ""
        async for chunk in _vision_client.analyze_image_stream(
            image_base64=image_base64,
            student_text=text,
        ):
            full_response += chunk
            yield f"data: {_json.dumps({'chunk': chunk})}\n\n"

        # Final event signals completion
        yield f"data: {_json.dumps({'done': True, 'full_response': full_response})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )


# ---------------------------------------------------------------------------
# FUTURE IMPROVEMENTS (if we had more time)
# ---------------------------------------------------------------------------
# 1. Image validation and preprocessing:
#    Check image dimensions, file size limits, and optionally resize
#    oversized images before sending them to the VLM (which internally
#    resizes to its patch size anyway, so we lose nothing).
#
# 2. Conversation-aware analysis:
#    Right now each /analyze call is stateless.  Wiring it into the
#    SessionManager so the VLM sees prior conversation history would make
#    multi-turn design critique much more coherent.
#
# 3. Batch image upload:
#    Let students upload multiple images at once (plan + section + photo)
#    and have the VLM reason across all of them.  LLaVA supports multiple
#    images in the 'images' list.
#
# 4. Annotation overlay:
#    Have the VLM output bounding boxes or region references, then overlay
#    them on the original image in the frontend so the student can see
#    exactly which part of the design is being discussed.
# ---------------------------------------------------------------------------
