"""
Deliverable 3 - Vision Client
================================
Vision-language model client for the Socratic design critique extension.
Students upload architectural images (floor plans, section drawings,
renderings, model photos) and the system discusses their design rationale
in a Socratic manner.

What this does:
    Wraps Ollama's multimodal API (used with LLaVA or similar VLMs) to
    accept a base64-encoded image + text prompt and return a Socratic
    response about the design.  Includes both blocking and streaming
    variants, mirroring the existing OllamaClient interface.

What I learned:
    - Multimodal LLMs (VLMs) are surprisingly capable at spatial reasoning
      on floor plans, though they struggle with scale and precise
      dimensions.  They are better at qualitative critique ("this corridor
      seems narrow relative to the atrium") than quantitative analysis.
    - Ollama's API supports images natively via the 'images' field in the
      /api/generate payload -- you just pass base64 strings.  No need for
      a separate image-processing endpoint.
    - Prompt engineering matters enormously for design critique quality.
      A generic "describe this image" prompt produces a shallow caption;
      a prompt that explicitly asks about design rationale, spatial
      relationships, and circulation flow produces genuinely useful
      Socratic questions.

Author: Akshay T P
Date: March 2025
"""

import base64
import json
import os
from typing import Dict, List, Optional, AsyncGenerator

import aiohttp
import requests

# ---------------------------------------------------------------------------
# DESIGN DECISION: LLaVA via Ollama vs. Qwen-VL vs. InternVL vs. cloud API
# ---------------------------------------------------------------------------
# We chose LLaVA 1.5 (7B, 4-bit) served through Ollama.
#
# Alternative 1 - Qwen-VL:
#   Pros:  strong multilingual support (good for HKU's mixed-language
#          environment), competitive image understanding.
#   Cons:  heavier (14B+ for best results), not yet first-class in Ollama
#          at time of writing.  Would need vLLM or a custom serving setup.
#
# Alternative 2 - InternVL:
#   Pros:  state-of-the-art on benchmarks, excellent spatial reasoning.
#   Cons:  even larger models (26B+), requires significant GPU allocation
#          that would crowd out the text LLM on a single GPU.
#
# Alternative 3 - OpenAI GPT-4V / Google Gemini (cloud API):
#   Pros:  best quality by far, no local GPU needed.
#   Cons:  per-request cost scales with 250 students; data privacy concerns
#          with student work; introduces cloud dependency for an on-prem
#          HPC deployment.
#
# Alternative 4 - CogVLM:
#   Pros:  good open-source option with reasonable spatial understanding.
#   Cons:  similar GPU requirements to InternVL; less community support
#          in Ollama ecosystem.
#
# Verdict: LLaVA 1.5 7B hits the sweet spot.  It runs on Ollama (already
#          in our stack), fits in ~8 GB VRAM alongside the text LLM, and
#          can meaningfully discuss architectural images.  Not as strong as
#          GPT-4V, but good enough for a Socratic probe of design rationale.
# ---------------------------------------------------------------------------


class VisionClient:
    """
    Client for vision-language model inference via Ollama.

    Supports LLaVA and any other multimodal model available in Ollama
    (e.g. bakllava, llava-llama3).
    """

    # System prompt tailored for architectural design critique.
    # This is the single most important knob for response quality.
    DESIGN_CRITIQUE_PROMPT = """You are a Socratic design tutor for architecture students at the University of Hong Kong.

Your role:
- Examine the uploaded design image (floor plan, section drawing, rendering, physical model photo, or site plan).
- Identify key design decisions visible in the image: spatial organization, circulation paths, structural logic, material choices, light and ventilation strategy.
- Ask probing questions about the student's design rationale. Do NOT simply describe what you see -- challenge the student to defend their choices.
- Focus on one or two design aspects per response to keep the dialogue focused.
- Be respectful but intellectually rigorous.
- Keep responses conversational and under 80 words.
- If the image quality is poor or the drawing type is ambiguous, ask the student to clarify before critiquing.

You are NOT providing solutions. You are helping the student think critically about their own design through questions."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llava:latest",
    ):
        """
        Args:
            base_url: Ollama server URL.
            model:    Model name.  Must be a multimodal model that supports
                      the 'images' field (e.g. llava, bakllava).
        """
        self.base_url = base_url
        self.model = model
        self.api_url = f"{base_url}/api/generate"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def encode_image_to_base64(image_path: str) -> str:
        """Read an image file and return its base64-encoded string."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    @staticmethod
    def encode_bytes_to_base64(image_bytes: bytes) -> str:
        """Encode raw image bytes to base64."""
        return base64.b64encode(image_bytes).decode("utf-8")

    def check_model_available(self) -> bool:
        """Verify that the configured VLM is pulled and ready in Ollama."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if resp.status_code != 200:
                return False
            models = [m["name"] for m in resp.json().get("models", [])]
            # Ollama model names may or may not include the tag
            return any(
                self.model.split(":")[0] in m for m in models
            )
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Synchronous inference
    # ------------------------------------------------------------------

    def analyze_image(
        self,
        image_base64: str,
        student_text: str = "",
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict:
        """
        Send an image + text to the VLM and return a Socratic response.

        Args:
            image_base64:         base64-encoded image string.
            student_text:         the student's accompanying explanation
                                  (could be transcribed voice input).
            conversation_history: prior exchanges for context.

        Returns:
            Dict with 'response' key containing the critique text.
        """
        history_text = ""
        if conversation_history:
            history_text = "\n".join(
                f"{msg['speaker'].upper()}: {msg['text']}"
                for msg in conversation_history[-6:]
            )

        prompt = f"""{self.DESIGN_CRITIQUE_PROMPT}

Previous conversation:
{history_text if history_text else "(No prior conversation)"}

Student's comment on their design:
\"{student_text if student_text else '(No text provided -- please describe what you see and ask about design intent.)'}\"

Your Socratic response about the design:"""

        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [image_base64],
            "stream": False,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
            },
        }

        try:
            resp = requests.post(self.api_url, json=payload, timeout=120)
            resp.raise_for_status()
            result = resp.json()
            return {
                "response": result.get("response", "").strip(),
                "done": result.get("done", False),
            }
        except requests.exceptions.RequestException as e:
            return {
                "response": f"Error communicating with vision model: {str(e)}",
                "error": True,
            }

    # ------------------------------------------------------------------
    # Streaming inference (async)
    # ------------------------------------------------------------------

    async def analyze_image_stream(
        self,
        image_base64: str,
        student_text: str = "",
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Streaming variant -- yields response chunks as they arrive.

        Same parameters as analyze_image.
        """
        history_text = ""
        if conversation_history:
            history_text = "\n".join(
                f"{msg['speaker'].upper()}: {msg['text']}"
                for msg in conversation_history[-6:]
            )

        prompt = f"""{self.DESIGN_CRITIQUE_PROMPT}

Previous conversation:
{history_text if history_text else "(No prior conversation)"}

Student's comment on their design:
\"{student_text if student_text else '(No text provided -- please describe what you see and ask about design intent.)'}\"

Your Socratic response about the design:"""

        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [image_base64],
            "stream": True,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
            },
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, json=payload) as resp:
                    async for line in resp.content:
                        if line:
                            try:
                                data = json.loads(line.decode("utf-8"))
                                chunk = data.get("response", "")
                                if chunk:
                                    yield chunk
                            except json.JSONDecodeError:
                                continue
        except Exception as e:
            yield f"[Error: {str(e)}]"


# ---------------------------------------------------------------------------
# FUTURE IMPROVEMENTS (if we had more time)
# ---------------------------------------------------------------------------
# 1. Model comparison harness:
#    Systematically test LLaVA, Qwen-VL, and InternVL on the same set of
#    architectural images and score them on (a) spatial accuracy, (b) design
#    vocabulary, and (c) question quality.  This would let us make a
#    data-driven model choice rather than going off published benchmarks.
#
# 2. Image preprocessing:
#    Architectural drawings often have fine detail (dimension lines, text
#    labels).  Resizing to the VLM's native resolution (e.g. 336x336 for
#    CLIP) loses crucial information.  A preprocessing step that crops to
#    regions of interest or uses higher-resolution patches (as in LLaVA-1.6)
#    would improve critique quality.
#
# 3. Multi-image support:
#    Let the student upload a floor plan AND a section drawing in the same
#    turn, so the VLM can reason about the relationship between plan and
#    section (e.g. "your double-height space in the section does not appear
#    in the plan -- can you explain?").
#
# 4. RAG over design guidelines:
#    Augment the prompt with retrieved chunks from UGC/BD building codes
#    or the course's design brief, so the Socratic questions are grounded
#    in actual requirements (e.g. "the minimum corridor width for means of
#    escape is 1050mm -- how does your design meet that?").
#
# 5. Fine-tuning on architectural corpora:
#    Fine-tune LLaVA on a dataset of annotated architectural images +
#    expert critiques to improve domain-specific vocabulary and reasoning.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Quick smoke test (requires Ollama running with llava pulled)
    client = VisionClient()
    print(f"Vision model available: {client.check_model_available()}")

    # If you have a test image:
    # img_b64 = VisionClient.encode_image_to_base64("test_floor_plan.png")
    # result = client.analyze_image(img_b64, "This is my floor plan layout.")
    # print(result["response"])
