"""
Socratic Method Bot - Core Modules
"""

from .pdf_parser import PDFParser
from .vllm_client import VLLMClient
from .whisper_stt import WhisperSTT
from .tts_engine import TTSEngine
from .conversation_manager import ConversationManager

__all__ = [
    'PDFParser',
    'OllamaClient',
    'WhisperSTT',
    'TTSEngine',
    'ConversationManager'
]
