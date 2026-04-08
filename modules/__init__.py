"""
Socratic Method Bot - Core Modules
"""

from .pdf_parser import PDFParser
from .deliv1_vllm_client import VLLMClient
from .whisper_stt import WhisperSTT
from .tts_engine import TTSEngine
from .conversation_manager import ConversationManager

# Deliverable 2
from .deliv2_session_manager import SessionManager
from .deliv2_resource_estimation import generate_full_report

# Deliverable 3
from .deliv3_vision_client import VisionClient
from .deliv3_compute_assessment import full_assessment

__all__ = [
    'PDFParser',
    'VLLMClient',
    'WhisperSTT',
    'TTSEngine',
    'ConversationManager',
    # Deliverable 2
    'SessionManager',
    'generate_full_report',
    # Deliverable 3
    'VisionClient',
    'full_assessment',
]

